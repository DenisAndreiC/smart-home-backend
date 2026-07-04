"""
routines.py — Router FastAPI pentru gestionarea rutinelor automate.

Rutinele sunt actiuni programate sa se execute la o anumita ora si in anumite
zile ale saptamanii. Ele pot fi:
  - manuale: create explicit de utilizator prin POST /routines/
  - sugerate de ML: detectate automat de algoritmul DBSCAN din ml_service.py
    pe baza tiparelor repetitive din istoricul comenzilor

Prefixul routerului este "/routines", deci toate caile de mai jos sunt
relative la /api/routines/ (prefixul /api este adaugat in main.py).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Importam modelele ORM necesare pentru interogarea bazei de date
# Device  — tabelul cu dispozitivele utilizatorilor
# Routine — tabelul cu rutinele automate (manuale + ML)
# User    — tabelul cu utilizatorii; folosit ca tip de adnotare
# get_db  — generatorul de sesiuni SQLAlchemy injectat prin Depends
from database.db import Device, Routine, User, get_db

# Schemele Pydantic pentru validarea datelor de intrare si serializarea raspunsurilor
from models.schemas import RoutineCreate, RoutineResponse, RoutineToggle

# get_current_user — dependenta FastAPI care decodifica JWT-ul si returneaza
# utilizatorul autentificat; arunca HTTP 401 daca token-ul lipseste sau e invalid
from services.auth_service import get_current_user

# detect_routines   — functia ML care aplica DBSCAN pe istoricul de comenzi
# generate_test_data — functia care genereaza comenzi sintetice pentru demo ML
from services.ml_service import detect_routines, generate_test_data

# Constante pentru parametrii algoritmului ML — definite central in constants.py
# ML_DAYS_BACK       — cate zile in urma se analizeaza istoricul (ex: 30)
# ML_MIN_OCCURRENCES — de cate ori trebuie sa apara un tipar ca sa fie considerat rutina
# ML_TIME_EPSILON    — toleranta in minute pentru gruparea orelor similare in DBSCAN
from utils.constants import ML_DAYS_BACK, ML_MIN_OCCURRENCES, ML_TIME_EPSILON

# Exceptie personalizata aruncata cand dispozitivul nu exista sau nu apartine userului
from utils.exceptions import DeviceNotFoundException

# Instanta de router cu prefixul "/routines" si tagul afisat in documentatia Swagger
router = APIRouter(prefix="/routines", tags=["Rutine"])


def _get_owned_routine(routine_id: int, current_user: User, db: Session) -> Routine:
    """
    Functie helper privata (prefixul _ indica utilizarea interna).

    Cauta rutina cu ID-ul dat care apartine utilizatorului curent.
    Scopul este de a centraliza logica de verificare a proprietatii rutinei
    si de a evita duplicarea codului in fiecare endpoint care lucreaza cu o rutina specifica.

    Parametri:
      routine_id   — ID-ul numeric al rutinei din URL path (ex: /routines/5/toggle)
      current_user — obiectul User al utilizatorului autentificat, injectat de get_current_user
      db           — sesiunea SQLAlchemy injectata de get_db

    Returneaza:
      Obiectul ORM Routine daca exista si apartine userului

    Arunca:
      HTTP 404 Not Found daca rutina nu exista sau apartine altui utilizator
      (cele doua cazuri sunt tratate identic pentru a nu expune informatii despre
      rutinele altor utilizatori)
    """
    # Interogam baza de date cu doua filtre combinate (AND implicit):
    # 1. Routine.id == routine_id — potrivire dupa ID
    # 2. Routine.user_id == current_user.id — garanteaza proprietatea userului
    rutina = db.query(Routine).filter(
        Routine.id == routine_id,
        Routine.user_id == current_user.id,
    ).first()

    # Daca rutina nu a fost gasita (fie nu exista, fie apartine altui user), returnam 404
    if not rutina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rutina nu a fost gasita")

    # Rutina exista si apartine userului curent — o returnam pentru procesare ulterioara
    return rutina


# GET /api/routines/ — lista tuturor rutinelor utilizatorului curent

# response_model=List[RoutineResponse] serializeaza lista de obiecte ORM
# in lista de dictionare JSON conform schemei RoutineResponse
@router.get("/", response_model=List[RoutineResponse])
def list_routines(
    # db — sesiunea de baza de date injectata automat prin FastAPI Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat extras din JWT prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Returneaza toate rutinele utilizatorului curent: atat cele create manual,
    cat si cele sugerate de ML (indiferent de starea is_active).
    """
    # Filtram rutinele dupa user_id pentru a returna doar rutinele proprii
    return db.query(Routine).filter(Routine.user_id == current_user.id).all()


# POST /api/routines/ — crearea unei rutine manuale

# status_code=201 indica ca resursa a fost creata cu succes (standard REST)
@router.post("/", response_model=RoutineResponse, status_code=status.HTTP_201_CREATED)
def create_routine(
    # date — corpul request-ului JSON, validat automat de Pydantic conform RoutineCreate
    date: RoutineCreate,
    # db — sesiunea de baza de date injectata prin Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat injectat prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Creeaza o rutina manuala noua.

    Verifica intai ca dispozitivul specificat exista si apartine utilizatorului curent,
    apoi salveaza rutina cu is_ml_suggested=False si is_active=True.
    """
    # Pasul 1: verificam ca dispozitivul exista si apartine userului curent
    # Dubla filtrare (id + owner_id) previne accesul la dispozitivele altor utilizatori
    device = db.query(Device).filter(
        Device.id == date.device_id,        # dispozitivul cu ID-ul specificat in body
        Device.owner_id == current_user.id, # trebuie sa apartina userului autentificat
    ).first()

    # Daca dispozitivul nu a fost gasit, aruncam exceptia personalizata (HTTP 404)
    if not device:
        raise DeviceNotFoundException()

    # Pasul 2: construim obiectul ORM Routine cu datele din schema de input
    rutina_noua = Routine(
        user_id=current_user.id,       # asociem rutina cu utilizatorul curent
        name=date.name,                # numele descriptiv al rutinei
        device_id=date.device_id,      # dispozitivul pe care va actiona rutina
        action=date.action,            # actiunea de executat (ex: "on", "off")
        value=date.value,              # valoarea optionala a actiunii
        trigger_time=date.trigger_time, # ora de declansare in format "HH:MM"
        days_of_week=date.days_of_week, # zilele de declansare (ex: "1,2,3,4,5")
        is_ml_suggested=False,         # creata manual, nu de ML
        is_active=True,                # rutinele manuale sunt active imediat dupa creare
    )

    # Pasul 3: salvam rutina in baza de date
    db.add(rutina_noua)    # adaugam obiectul in sesiunea curenta
    db.commit()            # persistam tranzactia in SQLite
    db.refresh(rutina_noua) # reincarcam obiectul pentru a obtine id si created_at generate de DB

    # Returnam rutina creata — Pydantic o serialzeaza conform RoutineResponse
    return rutina_noua


# GET /api/routines/detect — detectia ML a tiparelor repetitive

# Nu avem response_model explicit deoarece returnam un dict cu statistici,
# nu o schema Pydantic fixa
@router.get("/detect")
def detect_ml_routines(
    # db — sesiunea de baza de date injectata prin Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat injectat prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Analyze the user's command history with DBSCAN and return candidate routines.

    This endpoint is READ-ONLY - it does not save anything to the database.
    The user reviews the candidates and picks which ones to keep; each selected
    candidate is then created individually via POST /api/routines/ using the same
    device_id/action/value/trigger_time/days_of_week fields returned here.

    Candidates that already match a saved routine (same device/action/value/time)
    are filtered out so the same suggestion isn't shown again on every call.
    """
    detected = detect_routines(
        db,
        current_user.id,
        days_back=ML_DAYS_BACK,
        min_occurrences=ML_MIN_OCCURRENCES,
        time_epsilon_minutes=ML_TIME_EPSILON,
    )

    # Filter out candidates that already exist as a saved routine for this user
    candidates = []
    for idx, rutina in enumerate(detected):
        exista = db.query(Routine).filter(
            Routine.user_id == current_user.id,
            Routine.device_id == rutina["device_id"],
            Routine.action == rutina["action"],
            Routine.value == rutina["value"],
            Routine.trigger_time == rutina["trigger_time"],
        ).first()

        if exista:
            continue

        # candidate_index lets the frontend reference a specific suggestion
        # (there is no DB id yet since nothing is persisted here)
        candidates.append({**rutina, "candidate_index": idx})

    return {
        "routines_detected": len(detected),
        "routines_saved": 0,  # nothing is auto-saved anymore; kept for API compatibility
        "data": candidates,
    }


# PUT /api/routines/{routine_id}/toggle — activare / dezactivare rutina

@router.put("/{routine_id}/toggle", response_model=RoutineResponse)
def toggle_routine(
    # routine_id — ID-ul rutinei extras din URL path (ex: /routines/5/toggle)
    routine_id: int,
    # date — corpul JSON cu noua stare dorita: {"is_active": true/false}
    date: RoutineToggle,
    # db — sesiunea de baza de date injectata prin Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat injectat prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Activeaza sau dezactiveaza o rutina (functioneaza atat pentru rutinele manuale,
    cat si pentru cele sugerate de ML).

    Rutinele ML sugerate sunt salvate cu is_active=False; utilizatorul le poate
    activa prin acest endpoint dupa ce le-a revizuit.
    """
    # Obtinem rutina verificand si proprietatea — arunca 404 daca nu e gasita
    rutina = _get_owned_routine(routine_id, current_user, db)

    # Actualizam starea rutinei cu valoarea primita din body
    # APScheduler va include sau exclude rutina din planificator la urmatorul ciclu
    rutina.is_active = date.is_active

    # Persistam modificarea in baza de date
    db.commit()
    # Reincarcam obiectul pentru a returna starea actualizata din DB
    db.refresh(rutina)

    # Returnam rutina actualizata — Pydantic o serialzeaza conform RoutineResponse
    return rutina


# DELETE /api/routines/{routine_id} — stergerea unei rutine

@router.delete("/{routine_id}")
def delete_routine(
    # routine_id — ID-ul rutinei de sters extras din URL path
    routine_id: int,
    # db — sesiunea de baza de date injectata prin Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat injectat prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Sterge definitiv o rutina (manuala sau sugerata de ML).

    Daca rutina nu exista sau nu apartine utilizatorului curent, returnam HTTP 404.
    Stergerea este ireversibila — rutinele ML pot fi regenerate la urmatoarea rulare
    a endpoint-ului /detect.
    """
    # Obtinem rutina verificand si proprietatea — arunca 404 daca nu e gasita
    rutina = _get_owned_routine(routine_id, current_user, db)

    # Marcam rutina pentru stergere in sesiunea curenta
    db.delete(rutina)
    # Executam DELETE in baza de date si inchidem tranzactia
    db.commit()

    # Returnam un mesaj de confirmare (nu mai exista obiect de serializat)
    return {"message": "Rutina a fost stearsa"}


# POST /api/routines/generate-test-data — generare date sintetice pentru demo ML

@router.post("/generate-test-data")
def generate_demo_data(
    # device_id — ID-ul dispozitivului pentru care se genereaza comenzile sintetice
    # Trimis ca query parameter (ex: /generate-test-data?device_id=3)
    device_id: int,
    # db — sesiunea de baza de date injectata prin Depends
    db: Session = Depends(get_db),
    # current_user — utilizatorul autentificat injectat prin Depends
    current_user: User = Depends(get_current_user),
):
    """
    Genereaza 30 de zile de comenzi sintetice in istoricul utilizatorului curent.

    Scopul este de a popula baza de date cu date realiste pentru demonstrarea
    algoritmului ML fara a fi nevoie de o utilizare reala prealabila a aplicatiei.
    Comenzile generate respecta tipare repetitive (aceeasi ora, aceleasi zile)
    pentru ca DBSCAN sa le poata detecta ca rutine.
    """
    # Verificam ca dispozitivul exista si apartine utilizatorului curent
    # (nu generam date pentru dispozitivele altor utilizatori)
    device = db.query(Device).filter(
        Device.id == device_id,              # dispozitivul cu ID-ul specificat
        Device.owner_id == current_user.id,  # trebuie sa apartina userului autentificat
    ).first()

    # Daca dispozitivul nu a fost gasit, aruncam exceptia personalizata (HTTP 404)
    if not device:
        raise DeviceNotFoundException()

    # Apelam functia din ml_service care insereaza comenzile sintetice in tabelul commands_log
    # Returneaza numarul de comenzi efectiv generate si salvate
    count = generate_test_data(db, current_user.id, device_id)

    # Returnam confirmarea cu numarul de comenzi generate
    return {"message": f"Generate {count} comenzi de test", "count": count}

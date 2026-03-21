# Router pentru gestionarea camerelor din casa inteligenta.
# Expune endpoint-uri REST CRUD sub prefixul /rooms.
# Toate operatiile sunt protejate — necesita autentificare JWT.
# Fiecare utilizator poate accesa si modifica doar propriile camere.

from typing import List  # Tip pentru anotarea returnului de lista

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Importam modelele ORM (tabele din baza de date) si functia de sesiune
# Device este necesar pentru dezasocierea dispozitivelor la stergerea unei camere
from database.db import Device, Room, User, get_db

# Importam schemele Pydantic pentru validarea datelor de intrare si formatarea raspunsurilor
from models.schemas import (
    RoomCreate,    # Schema pentru crearea unei camere noi (name obligatoriu, icon optional)
    RoomResponse,  # Schema pentru raspunsul cu datele unei camere (include device_count)
    RoomUpdate,    # Schema pentru actualizarea unei camere (ambele campuri optionale)
)

# Importam dependenta pentru autentificare — extrage userul din token-ul JWT
from services.auth_service import get_current_user

# Instantiem router-ul cu prefixul /rooms si tag-ul pentru gruparea in Swagger UI
router = APIRouter(prefix="/rooms", tags=["Camere"])


def _get_owned_room(room_id: int, current_user: User, db: Session) -> Room:
    """
    Functie helper interna: cauta camera si verifica ca apartine utilizatorului curent.

    Interogheaza baza de date filtrand simultan dupa room_id si owner_id pentru a preveni
    accesul neautorizat la camerele altor utilizatori (security by design).
    Returneaza 404 in loc de 403 pentru a nu dezvalui existenta camerei.

    Parametri:
        room_id:      ID-ul numeric al camerei cautate in baza de date
        current_user: Obiectul ORM al utilizatorului autentificat curent (din token JWT)
        db:           Sesiunea SQLAlchemy activa pentru interogarea bazei de date

    Returneaza:
        Obiectul ORM Room daca exista si apartine utilizatorului curent

    Arunca:
        HTTPException 404 - daca camera nu exista sau nu apartine utilizatorului curent
    """
    # Filtram dupa ambele conditii simultan: id-ul camerei SI owner-ul
    # Comportamentul de 404 in loc de 403 evita scurgerea de informatii despre alte camere
    room = db.query(Room).filter(
        Room.id == room_id,              # Conditie: camera cu id-ul specificat
        Room.owner_id == current_user.id,  # Conditie: camera apartine userului curent
    ).first()  # Returneaza primul rezultat sau None daca nu exista

    # Daca nu am gasit nicio camera care satisface ambele conditii, aruncam 404
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # 404 = resursa nu a fost gasita
            detail="Camera nu a fost gasita",        # Mesaj generic (nu dezvaluie daca exista)
        )

    return room  # Returnam camera gasita si verificata


def _room_to_response(room: Room) -> RoomResponse:
    """
    Converteste un obiect ORM Room la schema de raspuns RoomResponse.

    Calculeaza numarul de dispozitive din camera accesand relatia ORM 'devices'.
    Aceasta functie centralizeaza conversia pentru a evita duplicarea codului
    in toate endpoint-urile care returneaza date despre camere.

    Parametri:
        room: Obiectul ORM Room de convertit (trebuie sa aiba relatia 'devices' incarcata)

    Returneaza:
        RoomResponse cu id, name, icon si device_count (numarul de dispozitive din camera)
    """
    # Construim schema de raspuns din campurile obiectului ORM
    # len(room.devices) calculeaza numarul de dispozitive asociate acestei camere
    return RoomResponse(
        id=room.id,                   # ID-ul unic al camerei in baza de date
        name=room.name,               # Numele camerei (ex: "Living", "Dormitor")
        icon=room.icon,               # Iconita camerei pentru UI (ex: "sofa", "bed")
        device_count=len(room.devices),  # Numarul de dispozitive asociate camerei (din relatia ORM)
    )


@router.get("/", response_model=List[RoomResponse])
def list_rooms(
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Returneaza toate camerele utilizatorului curent cu numarul de dispozitive per camera.

    Fiecare camera din raspuns include campul 'device_count' calculat din relatia ORM
    cu tabelul de dispozitive.

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Lista de RoomResponse cu toate camerele utilizatorului (poate fi goala)
    """
    # Interogam toate camerele apartinand utilizatorului curent
    # Filtram intotdeauna dupa owner_id pentru a asigura izolarea datelor intre utilizatori
    rooms = db.query(Room).filter(Room.owner_id == current_user.id).all()  # Lista de obiecte ORM

    # Convertim fiecare obiect ORM Room la schema RoomResponse folosind helper-ul intern
    return [_room_to_response(r) for r in rooms]  # List comprehension pentru conversie eficienta


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    date: RoomCreate,                                # Datele camerei noi validate de Pydantic
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Creeaza o camera noua asociata utilizatorului curent.

    Camera este automat asociata utilizatorului autentificat prin owner_id.
    Campul 'icon' este optional — poate fi None daca nu este furnizat.

    Parametri:
        date:         Datele camerei noi (name obligatoriu, icon optional)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        RoomResponse cu datele camerei nou create (HTTP 201 Created)
        device_count va fi 0 pentru o camera nou creata
    """
    # Cream obiectul ORM pentru noua camera cu datele furnizate si owner-ul curent
    camera = Room(
        name=date.name,             # Numele camerei furnizat de utilizator
        icon=date.icon,             # Iconita camerei (poate fi None daca nu a fost furnizata)
        owner_id=current_user.id,   # ID-ul utilizatorului proprietar — setat automat din token
    )

    # Persistam camera noua in baza de date
    db.add(camera)      # Marcam obiectul pentru inserare in baza de date
    db.commit()         # Executam tranzactia — INSERT efectiv in baza de date
    db.refresh(camera)  # Reincarcam din DB pentru a obtine id-ul si valorile generate automat

    # Convertim la schema de raspuns si returnam; device_count = 0 pentru camera noua
    return _room_to_response(camera)


@router.put("/{room_id}", response_model=RoomResponse)
def update_room(
    room_id: int,                                    # ID-ul camerei de actualizat (path param)
    date: RoomUpdate,                                # Datele de actualizare (campuri optionale)
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Actualizeaza numele sau iconita unei camere existente.

    Suporta actualizare partiala (comportament PATCH-like): doar campurile trimise explicit
    in body-ul request-ului sunt modificate, restul raman neschimbate.

    Parametri:
        room_id:      ID-ul numeric al camerei de actualizat (din URL path)
        date:         Datele de actualizare validate de Pydantic (name si icon optionale)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        RoomResponse cu datele actualizate ale camerei

    Arunca:
        HTTPException 404 - daca camera nu exista sau nu apartine utilizatorului curent
    """
    # Verificam ca camera exista si apartine utilizatorului curent inainte de actualizare
    camera = _get_owned_room(room_id, current_user, db)

    # Extragem doar campurile furnizate explicit in request body
    # exclude_unset=True asigura actualizare partiala — campurile omise raman neschimbate
    campuri = date.model_dump(exclude_unset=True)  # Dict cu campurile modificate explicit

    # Aplicam fiecare camp actualizat direct pe obiectul ORM folosind setattr
    for camp, val in campuri.items():
        setattr(camera, camp, val)  # Actualizam atributul ORM cu noua valoare furnizata

    # Persistam modificarile in baza de date
    db.commit()        # Executam UPDATE-ul efectiv in baza de date
    db.refresh(camera) # Reincarcam din DB pentru valorile finale actualizate

    # Convertim la schema de raspuns si returnam; device_count reflecta starea curenta
    return _room_to_response(camera)


@router.delete("/{room_id}")
def delete_room(
    room_id: int,                                    # ID-ul camerei de sters (path param)
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Sterge o camera. Dispozitivele asociate NU se sterg —
    room_id-ul lor este setat la null (dezasociere, nu stergere).

    Comportament intentionat: dispozitivele raman in sistem dar nu mai au o camera asignata.
    Utilizatorul poate ulterior reasigna dispozitivele dezasociate la alte camere.

    Parametri:
        room_id:      ID-ul numeric al camerei de sters (din URL path)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict cu mesaj de confirmare a stergerii camerei

    Arunca:
        HTTPException 404 - daca camera nu exista sau nu apartine utilizatorului curent
    """
    # Verificam ca camera exista si apartine utilizatorului curent inainte de stergere
    camera = _get_owned_room(room_id, current_user, db)

    # Dezasociem dispozitivele din aceasta camera setand room_id la None (NULL in DB)
    # Dispozitivele NU sunt sterse — doar legatura cu camera este eliminata
    # synchronize_session="fetch" asigura ca sesiunea SQLAlchemy ramane consistenta
    db.query(Device).filter(Device.room_id == room_id).update(
        {Device.room_id: None},          # Setam room_id la NULL pentru toate dispozitivele camerei
        synchronize_session="fetch",     # Sincronizam sesiunea pentru consistenta obiectelor ORM
    )

    # Stergem camera din baza de date dupa dezasocierea dispozitivelor
    db.delete(camera)  # Marcam camera pentru stergere
    db.commit()        # Executam toate operatiile in aceeasi tranzactie (UPDATE + DELETE)

    # Returnam mesaj de confirmare ca stergerea s-a efectuat cu succes
    return {"message": "Camera a fost stearsa"}

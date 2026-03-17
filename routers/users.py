# Router pentru gestionarea profilului utilizatorului autentificat.
# Expune endpoint-uri REST sub prefixul /users.
# Permite actualizarea username-ului, display_name-ului si incarcarea unui avatar.
# Toate operatiile sunt protejate — necesita autentificare JWT.

import os    # Folosit pentru operatii pe sistemul de fisiere (creare director, stergere fisier vechi)
import uuid  # Genereaza identificatori unici pentru numele fisierelor de avatar

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

# Importam modelul ORM User si functia de sesiune a bazei de date
from database.db import User, get_db

# Importam schemele Pydantic pentru validarea datelor si formatarea raspunsurilor
from models.schemas import UserResponse, UserUpdate

# Dependency de autentificare — extrage si valideaza utilizatorul din token-ul JWT
from services.auth_service import get_current_user

# Router cu prefix /users — toate rutele devin /api/users/...
router = APIRouter(prefix="/users", tags=["Utilizatori"])

# Calea relativa a directorului unde sunt stocate avatarele utilizatorilor
AVATARS_DIR = "static/avatars"


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),  # utilizatorul autentificat din token JWT
):
    """
    Returneaza profilul complet al utilizatorului curent.

    Include toate campurile publice: id, email, username, display_name, avatar_url, created_at.
    Nu include parola sau hash-ul acesteia.

    Parametri:
        current_user : utilizatorul autentificat (injectat din token JWT)

    Returneaza:
        UserResponse cu datele complete ale utilizatorului curent
    """
    # Returnam direct obiectul ORM — FastAPI il serializeaza dupa schema UserResponse
    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(
    date: UserUpdate,                                # campurile de actualizat (username, display_name)
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Actualizeaza profilul utilizatorului curent (username si/sau display_name).

    Suporta actualizare partiala — campurile omise din body raman neschimbate.
    Verifica unicitatea noului username inainte de salvare pentru a preveni duplicatele.

    Parametri:
        date:         Campurile de actualizat (toate optionale, partial update)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        UserResponse cu datele actualizate ale utilizatorului

    Arunca:
        HTTPException 400 — daca body-ul este gol (niciun camp de actualizat)
        HTTPException 409 — daca noul username este deja folosit de alt utilizator
    """
    # Extragem doar campurile furnizate explicit in request body (actualizare partiala)
    # exclude_unset=True asigura ca nu suprascriem campuri cu None pentru campurile omise
    campuri = date.model_dump(exclude_unset=True)  # dict cu campurile modificate explicit

    # Daca body-ul nu contine niciun camp, returnam eroare 400 — nu avem ce actualiza
    if not campuri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,    # 400 = cerere invalida
            detail="Niciun camp de actualizat",         # mesaj explicit pentru client
        )

    # Verificam unicitatea noului username daca a fost furnizat in request
    # Cautam alt utilizator cu acelasi username, excludand utilizatorul curent (id diferit)
    if "username" in campuri:
        existing = (
            db.query(User)
            .filter(
                User.username == campuri["username"],  # username identic cu cel dorit
                User.id != current_user.id,            # dar apartin altui utilizator
            )
            .first()  # returneaza primul rezultat sau None
        )
        # Daca exista deja un utilizator cu acest username, returnam conflict 409
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,   # 409 = conflict de date
                detail="Username-ul este deja folosit", # mesaj explicit pentru client
            )

    # Aplicam fiecare camp actualizat direct pe obiectul ORM al utilizatorului curent
    for camp, val in campuri.items():
        setattr(current_user, camp, val)  # actualizam atributul ORM cu noua valoare

    # Persistam modificarile in baza de date intr-o singura tranzactie
    db.commit()            # executam UPDATE-ul efectiv
    db.refresh(current_user)  # reincarcam din DB pentru valorile finale actualizate

    # Returnam utilizatorul actualizat; FastAPI il serializeaza dupa schema UserResponse
    return current_user


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),                   # fisierul imagine incarcat prin multipart/form-data
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Incarca o imagine de profil (avatar) pentru utilizatorul curent.

    Fisierul este salvat in static/avatars/ cu un nume unic format din
    id-ul utilizatorului si un UUID random pentru a evita coliziunile.
    Avatarul vechi este sters automat de pe disk daca exista.
    Campul avatar_url din DB este actualizat cu path-ul relativ al noului fisier.

    Formate acceptate: JPEG, PNG, GIF, WebP.

    Parametri:
        file:         Fisierul imagine incarcat (multipart/form-data)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        UserResponse cu noul avatar_url populat

    Arunca:
        HTTPException 400 — daca tipul MIME al fisierului nu este suportat
    """
    # Setul tipurilor MIME acceptate pentru avatare
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    # Verificam ca fisierul incarcat are un tip MIME suportat
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,                                # 400 = date invalide
            detail="Tipul fisierului nu este suportat. Folositi JPEG, PNG, GIF sau WebP.",
        )

    # Cream directorul de avatare daca nu exista inca pe disk
    # exist_ok=True previne eroarea daca directorul exista deja
    os.makedirs(AVATARS_DIR, exist_ok=True)

    # Extragem extensia fisierului original; fallback la 'jpg' daca nu are extensie
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"

    # Generam un nume unic: {user_id}_{uuid_hex}.{ext} (ex: "42_a3f1b2c4...d9.jpg")
    # UUID random previne suprascrierile accidentale si ghicirea numelor de fisiere
    filename = f"{current_user.id}_{uuid.uuid4().hex}.{ext}"

    # Construim calea completa relativa catre fisierul de salvat
    filepath = os.path.join(AVATARS_DIR, filename)  # ex: "static/avatars/42_abc123.jpg"

    # Citim continutul fisierului incarcat in memorie si il scriem pe disk
    content = await file.read()         # citim bytes-ii fisierului din request
    with open(filepath, "wb") as f:
        f.write(content)                # scriem bytes-ii in fisierul de pe disk

    # Stergem avatarul vechi de pe disk daca utilizatorul are deja unul setat
    # Evitam acumularea fisierelor inutile in directorul de avatare
    if current_user.avatar_url:
        # Eliminam slash-ul initial pentru a obtine o cale relativa valida pe disk
        old_path = current_user.avatar_url.lstrip("/")  # ex: "static/avatars/42_old.jpg"
        if os.path.exists(old_path):
            try:
                os.remove(old_path)  # stergem fisierul vechi de pe disk
            except OSError:
                pass  # ignoram eroarea daca fisierul nu mai exista sau nu poate fi sters

    # Actualizam avatar_url in DB cu path-ul HTTP relativ al noului fisier
    # Formatul este "/static/avatars/filename" — accesibil prin FastAPI StaticFiles
    current_user.avatar_url = f"/static/avatars/{filename}"
    db.commit()               # persistam modificarea in baza de date
    db.refresh(current_user)  # reincarcam obiectul pentru a reflecta starea actualizata

    # Returnam utilizatorul actualizat; FastAPI il serializeaza dupa schema UserResponse
    return current_user

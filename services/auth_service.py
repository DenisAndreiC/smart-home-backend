from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database.db import User, get_db

# Schema OAuth2 - indica FastAPI unde se obtine token-ul (folosit pentru Swagger UI)
# tokenUrl este path-ul endpoint-ului de login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# Parole - folosim bcrypt direct (passlib 1.7.4 nu e compatibil cu bcrypt 4+)


def hash_password(password: str) -> str:
    """
    Returneaza hash-ul bcrypt al parolei in clar.
    gensalt() genereaza un salt aleator pentru fiecare hash (protectie rainbow tables).
    """
    # Encode parola la bytes, aplica hash bcrypt cu salt aleator, decodifica rezultatul la str
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Compara parola in clar cu hash-ul stocat in baza de date.
    Returneaza True daca parola corespunde, False altfel.
    bcrypt.checkpw este time-constant (rezistent la timing attacks).
    """
    # Encode ambele strings la bytes inainte de comparatie
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# JWT - generare si validare token-uri de autentificare


def create_access_token(data: dict) -> str:
    """
    Creeaza un JWT semnat cu secretul din settings.
    Campul 'sub' trebuie sa contina email-ul utilizatorului (standard JWT).
    Token-ul expira dupa jwt_expiration_minutes minute (configurat in .env).
    """
    # Copiaza payload-ul pentru a nu modifica dict-ul original
    payload = data.copy()

    # Calculeaza timestamp-ul de expirare (UTC aware)
    expira_la = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)

    # Adauga campul standard 'exp' (expiration) in payload
    payload["exp"] = expira_la

    # Semneaza si returneaza token-ul JWT ca string
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Dependency FastAPI - user autentificat curent


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency FastAPI pentru endpoint-urile protejate.
    Decodifica token-ul JWT, extrage email-ul si returneaza utilizatorul din DB.
    Ridica HTTP 401 daca token-ul lipseste, este invalid sau utilizatorul nu exista.
    """
    # Pregatim eroarea 401 o singura data pentru reutilizare
    eroare_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid sau expirat",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decodifica si valideaza token-ul JWT (verifica semnatura si expirarea)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

        # Extrage email-ul din campul standard 'sub' (subject)
        email: str | None = payload.get("sub")

        # Daca campul 'sub' lipseste, token-ul este malformat
        if email is None:
            raise eroare_401

    except JWTError:
        # JWTError acopera: semnatura invalida, token expirat, format gresit
        raise eroare_401

    # Cauta utilizatorul in baza de date dupa email-ul din token
    user = db.query(User).filter(User.email == email).first()

    # Daca userul a fost sters dupa emiterea token-ului, returnam 401
    if user is None:
        raise eroare_401

    return user

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database.db import User, get_db

# Schema OAuth2 — indică FastAPI unde se obține token-ul
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ---------------------------------------------------------------------------
# Parole — folosim bcrypt direct (passlib 1.7.4 nu e compatibil cu bcrypt 4+)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Returnează hash-ul bcrypt al parolei în clar."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Compară parola în clar cu hash-ul stocat în baza de date."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_access_token(data: dict) -> str:
    """
    Creează un JWT semnat cu secretul din settings.
    Câmpul 'sub' trebuie să conțină email-ul utilizatorului.
    """
    payload = data.copy()
    expira_la = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload["exp"] = expira_la
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Dependency — user autentificat
# ---------------------------------------------------------------------------


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency FastAPI pentru endpoint-urile protejate.
    Decodează token-ul JWT și returnează utilizatorul din baza de date.
    """
    eroare_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid sau expirat",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email: str | None = payload.get("sub")
        if email is None:
            raise eroare_401
    except JWTError:
        raise eroare_401

    # Caută utilizatorul în baza de date după email-ul din token
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise eroare_401

    return user

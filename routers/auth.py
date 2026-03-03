from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import User, UserPreferences, get_db
from models.schemas import Token, UserLogin, UserPreferencesResponse, UserPreferencesUpdate, UserRegister, UserResponse
from services.auth_service import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from utils.exceptions import DuplicateEmailException, DuplicateUsernameException

router = APIRouter(prefix="/auth", tags=["Autentificare"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(date: UserRegister, db: Session = Depends(get_db)):
    """Înregistrează un utilizator nou în sistem."""
    if db.query(User).filter(User.email == date.email).first():
        raise DuplicateEmailException()
    if db.query(User).filter(User.username == date.username).first():
        raise DuplicateUsernameException()

    user_nou = User(
        email=date.email,
        username=date.username,
        hashed_password=hash_password(date.password),
    )
    db.add(user_nou)
    db.commit()
    db.refresh(user_nou)
    return user_nou


@router.post("/login", response_model=Token)
def login(date: UserLogin, db: Session = Depends(get_db)):
    """Autentifică utilizatorul și returnează un JWT Bearer token."""
    user = db.query(User).filter(User.email == date.email).first()
    if not user or not verify_password(date.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email sau parolă incorectă",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.email})
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Returnează datele utilizatorului autentificat curent."""
    return current_user


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returnează preferințele user-ului.
    Dacă nu există încă, le creează cu valorile implicite.
    """
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)

    # Mapăm câmpul tz → timezone pentru schema de răspuns
    return UserPreferencesResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        timezone=prefs.tz,
        language=prefs.language,
        theme=prefs.theme,
        notifications_enabled=prefs.notifications_enabled,
        auto_detect_routines=prefs.auto_detect_routines,
    )


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_preferences(
    date: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizează preferințele user-ului. Creează înregistrarea dacă nu există."""
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    # Mapăm timezone → tz (câmpul intern al modelului)
    campuri = date.model_dump(exclude_unset=True)
    for camp, val in campuri.items():
        attr = "tz" if camp == "timezone" else camp
        setattr(prefs, attr, val)

    db.commit()
    db.refresh(prefs)
    return UserPreferencesResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        timezone=prefs.tz,
        language=prefs.language,
        theme=prefs.theme,
        notifications_enabled=prefs.notifications_enabled,
        auto_detect_routines=prefs.auto_detect_routines,
    )

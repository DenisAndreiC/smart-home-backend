# Router for user authentication and account management.
# Exposes REST endpoints under the /auth prefix.
# Handles registration, login, profile retrieval, preferences, password change,
# password reset (stub), and email verification (stub).

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ORM models and DB session factory
from database.db import User, UserPreferences, get_db

# Pydantic schemas for request validation and response serialisation
from models.schemas import (
    ChangePasswordRequest,    # Body for POST /auth/change-password
    ForgotPasswordRequest,    # Body for POST /auth/forgot-password
    ResetPasswordRequest,     # Body for POST /auth/reset-password
    Token,                    # Response schema for JWT token
    UserLogin,                # Body for POST /auth/login
    UserPreferencesResponse,  # Response schema for user preferences
    UserPreferencesUpdate,    # Body for PUT /auth/preferences
    UserRegister,             # Body for POST /auth/register
    UserResponse,             # Response schema for user data
)

# Auth service helpers
from services.auth_service import (
    create_access_token,  # Creates a signed JWT token
    get_current_user,     # FastAPI dependency: extracts user from Bearer token
    hash_password,        # Hashes a plain-text password with bcrypt
    verify_password,      # Compares plain-text password against a bcrypt hash
)

# Custom exceptions for duplicate account data
from utils.exceptions import DuplicateEmailException, DuplicateUsernameException

router = APIRouter(prefix="/auth", tags=["Autentificare"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(date: UserRegister, db: Session = Depends(get_db)):
    """
    Inregistreaza un utilizator nou in sistem.

    Verifica unicitatea email-ului si a username-ului inainte de creare.
    Parola este hasata cu bcrypt inainte de a fi salvata in baza de date.
    Niciodata nu se stocheaza parola in text clar.

    Parametri:
        date: Datele de inregistrare (email, username, parola) validate de Pydantic
        db:   Sesiunea SQLAlchemy injectata automat prin dependenta get_db

    Returneaza:
        UserResponse cu datele utilizatorului nou creat (HTTP 201 Created)

    Arunca:
        DuplicateEmailException    - daca email-ul exista deja in baza de date (HTTP 409)
        DuplicateUsernameException - daca username-ul exista deja in baza de date (HTTP 409)
    """
    # Verificam daca exista deja un utilizator cu acelasi email in baza de date
    # .first() returneaza primul rezultat gasit sau None daca nu exista
    if db.query(User).filter(User.email == date.email).first():
        raise DuplicateEmailException()  # HTTP 409 Conflict — email duplicat

    # Verificam daca exista deja un utilizator cu acelasi username
    if db.query(User).filter(User.username == date.username).first():
        raise DuplicateUsernameException()  # HTTP 409 Conflict — username duplicat

    # Generate a one-time email verification token (UUID4 hex)
    verification_token = uuid.uuid4().hex

    # Log the token so it can be used during development (no real SMTP yet)
    logger.info("Email verification token for %s: %s", date.email, verification_token)

    # Create the ORM object for the new user.
    # Password is hashed with bcrypt — the plain-text password is never stored.
    # is_verified starts as False; set to True after the user clicks the verification link.
    user_nou = User(
        email=date.email,
        username=date.username,
        hashed_password=hash_password(date.password),
        is_verified=False,
        verification_token=verification_token,
    )

    # Insert the new user into the database
    db.add(user_nou)
    db.commit()
    db.refresh(user_nou)

    return user_nou


@router.post("/login", response_model=Token)
def login(date: UserLogin, db: Session = Depends(get_db)):
    """
    Autentifica utilizatorul si returneaza un JWT Bearer token.

    Cauta utilizatorul dupa email in baza de date, verifica parola,
    apoi genereaza un token JWT cu subject = email-ul utilizatorului.
    Folosim mesaj generic de eroare pentru a nu dezvalui daca email-ul exista.

    Parametri:
        date: Datele de autentificare (email + parola) validate de Pydantic
        db:   Sesiunea SQLAlchemy injectata automat prin dependenta get_db

    Returneaza:
        Token cu campul access_token (JWT semnat) si token_type = "bearer"

    Arunca:
        HTTPException 401 Unauthorized - daca email-ul nu exista sau parola este gresita
    """
    # Cautam utilizatorul dupa email in baza de date
    # .first() returneaza None daca nu exista niciun utilizator cu email-ul respectiv
    user = db.query(User).filter(User.email == date.email).first()

    # Verificam simultan daca utilizatorul exista SI daca parola corespunde hash-ului stocat
    # Verificarea combinata previne timing attacks si nu dezvaluie daca email-ul exista
    if not user or not verify_password(date.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # 401 = credentiale invalide
            detail="Email sau parola incorecta",        # Mesaj generic intentionat pentru securitate
            headers={"WWW-Authenticate": "Bearer"},     # Header standard conform OAuth2 Bearer spec
        )

    # Generam token-ul JWT cu subject = email-ul utilizatorului autentificat
    # Token-ul va fi trimis in header-ul Authorization la fiecare request protejat
    token = create_access_token(data={"sub": user.email})  # sub = subject field in JWT payload

    # Returnam token-ul impachetat in schema Token (access_token + token_type)
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """
    Returneaza datele utilizatorului autentificat curent.

    Endpoint protejat — necesita token JWT valid in header-ul Authorization: Bearer <token>.
    Dependenta get_current_user extrage si valideaza automat token-ul din header.

    Parametri:
        current_user: Utilizatorul ORM extras din token-ul JWT prin dependenta get_current_user

    Returneaza:
        UserResponse cu datele utilizatorului autentificat (id, email, username etc.)
    """
    # Returnam direct obiectul ORM al utilizatorului curent
    # FastAPI il serializeaza automat conform schemei UserResponse declarate in response_model
    return current_user


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Returneaza preferintele utilizatorului autentificat.

    Daca utilizatorul nu are inca preferinte salvate in baza de date, creeaza automat
    o inregistrare cu valorile implicite definite in modelul ORM si o returneaza.
    Campul intern 'tz' din ORM este expus ca 'timezone' in raspunsul API.

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        UserPreferencesResponse cu toate campurile de preferinte ale utilizatorului
    """
    # Cautam preferintele existente ale utilizatorului curent filtrand dupa user_id
    # .first() returneaza None daca utilizatorul nu are inca preferinte salvate
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    # Daca nu exista preferinte pentru acest utilizator, le cream cu valorile implicite din model
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)  # Obiect nou cu valorile implicite din ORM
        db.add(prefs)      # Adaugam in sesiune pentru inserare
        db.commit()        # Persistam in baza de date
        db.refresh(prefs)  # Reincarcam pentru a obtine id-ul generat si valorile implicite efective

    # Construim si returnam schema de raspuns mapand campurile din modelul ORM la schema API
    # Nota: campul 'tz' din ORM este expus ca 'timezone' in API pentru claritate
    return UserPreferencesResponse(
        id=prefs.id,                                        # ID-ul unic al inregistrarii de preferinte
        user_id=prefs.user_id,                             # ID-ul utilizatorului caruia ii apartin
        timezone=prefs.tz,                                  # Fusul orar (tz in ORM -> timezone in API)
        language=prefs.language,                           # Limba interfetei (ex: "ro", "en")
        theme=prefs.theme,                                  # Tema vizuala (ex: "dark", "light")
        notifications_enabled=prefs.notifications_enabled, # True daca notificarile push sunt activate
        auto_detect_routines=prefs.auto_detect_routines,   # True daca detectia automata ML este activa
    )


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_preferences(
    date: UserPreferencesUpdate,                          # Datele de actualizare cu campuri optionale
    db: Session = Depends(get_db),                        # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),       # Utilizatorul autentificat curent din token JWT
):
    """
    Actualizeaza preferintele utilizatorului autentificat.

    Suporta actualizare partiala (comportament PATCH-like): doar campurile trimise explicit
    in body-ul request-ului sunt modificate, restul campurilor raman neschimbate.
    Daca utilizatorul nu are inca preferinte salvate, le creeaza automat inainte de actualizare.
    Campul 'timezone' din request este mapat la campul intern 'tz' din modelul ORM.

    Parametri:
        date:         Datele de actualizare validate de Pydantic (toate campurile sunt optionale)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        UserPreferencesResponse cu preferintele actualizate ale utilizatorului
    """
    # Cautam preferintele existente ale utilizatorului curent in baza de date
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    # Daca nu exista inca preferinte pentru acest utilizator, initializam un obiect nou
    # Nu facem commit inca — il facem o singura data la finalul functiei
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)  # Obiect nou cu valorile implicite din ORM
        db.add(prefs)  # Adaugam in sesiune — commit-ul va face si INSERT-ul initial

    # Extragem doar campurile care au fost explicit furnizate in request body
    # exclude_unset=True garanteaza ca nu suprascriem campuri cu None pentru campurile omise
    campuri = date.model_dump(exclude_unset=True)  # Dict cu doar campurile modificate explicit

    # Iteram prin fiecare camp trimis si il aplicam pe obiectul ORM corespunzator
    for camp, val in campuri.items():
        # Tratam special campul 'timezone' care in modelul ORM se numeste 'tz'
        # Aceasta mapare evita conflictul cu cuvantul rezervat 'timezone' in unele dialecte SQL
        attr = "tz" if camp == "timezone" else camp  # Convertim numele campului daca este necesar
        setattr(prefs, attr, val)  # Setam atributul corespunzator pe obiectul ORM cu noua valoare

    # Persistam toate modificarile intr-o singura tranzactie
    db.commit()        # Executam UPDATE-ul (sau INSERT daca prefs era nou)
    db.refresh(prefs)  # Reincarcam obiectul din DB pentru a obtine valorile finale actualizate

    # Build and return the updated preferences response
    return UserPreferencesResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        timezone=prefs.tz,
        language=prefs.language,
        theme=prefs.theme,
        notifications_enabled=prefs.notifications_enabled,
        auto_detect_routines=prefs.auto_detect_routines,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change the authenticated user's password.

    Verifies the current password against the stored bcrypt hash before
    hashing and saving the new one. Login is NOT blocked during this flow.

    Args:
        body:         {current_password, new_password}
        db:           SQLAlchemy session injected by FastAPI
        current_user: Authenticated user from JWT

    Returns:
        {"message": "Password changed successfully"} on success

    Raises:
        HTTPException 400: if current_password does not match the stored hash
    """
    # Verify that the supplied current password matches the bcrypt hash in DB
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Hash the new password and persist it
    current_user.hashed_password = hash_password(body.new_password)
    db.add(current_user)
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiate a password reset flow (stub — no real email is sent yet).

    Generates a UUID4 reset token, saves it to the user record, and logs it.
    Always returns a generic message regardless of whether the email exists,
    to avoid leaking account information to potential attackers.

    Args:
        body: {email}
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        {"message": "If that email exists, a reset link has been sent."}
    """
    user = db.query(User).filter(User.email == body.email).first()

    if user:
        # Generate a one-time reset token and store it on the user record
        token = uuid.uuid4().hex
        user.reset_token = token
        db.add(user)
        db.commit()

        # Log the token so it can be used during development (no SMTP yet)
        logger.info("Password reset token for %s: %s", body.email, token)

    # Always return the same response — do not reveal whether the email exists
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Complete a password reset using the token from the forgot-password flow.

    Looks up the user by reset_token, sets the new password, and clears the token.

    Args:
        body: {token, new_password}
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        {"message": "Password has been reset successfully."}

    Raises:
        HTTPException 400: if the token is invalid or has already been used
    """
    # Find the user that owns this reset token
    user = db.query(User).filter(User.reset_token == body.token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # Update the password and invalidate the token so it cannot be reused
    user.hashed_password = hash_password(body.new_password)
    user.reset_token = None
    db.add(user)
    db.commit()

    return {"message": "Password has been reset successfully."}


@router.get("/verify-email")
def verify_email(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Verify a user's email address using the token sent at registration.

    Marks the user as verified and clears the verification token.
    Login is NOT blocked for unverified users — this is a stub flow.

    Args:
        token: UUID hex token from the registration verification link
        db:    SQLAlchemy session injected by FastAPI

    Returns:
        {"message": "Email verified successfully."}

    Raises:
        HTTPException 400: if the token is invalid or has already been used
    """
    # Look up the user by verification token
    user = db.query(User).filter(User.verification_token == token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    # Mark the account as verified and clear the single-use token
    user.is_verified = True
    user.verification_token = None
    db.add(user)
    db.commit()

    return {"message": "Email verified successfully."}

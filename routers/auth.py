# Router pentru autentificare si gestionarea conturilor de utilizator.
# Expune endpoint-uri REST sub prefixul /auth.
# Toate operatiile de autentificare (register, login, profil, preferinte) sunt definite aici.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Importam modelele ORM (tabele din baza de date) si functia de sesiune
from database.db import User, UserPreferences, get_db

# Importam schemele Pydantic pentru validarea datelor de intrare si formatarea raspunsurilor
from models.schemas import (
    Token,                    # Schema pentru raspunsul cu JWT token
    UserLogin,                # Schema pentru datele de autentificare (email + parola)
    UserPreferencesResponse,  # Schema pentru raspunsul cu preferintele utilizatorului
    UserPreferencesUpdate,    # Schema pentru actualizarea preferintelor (campuri optionale)
    UserRegister,             # Schema pentru inregistrarea unui utilizator nou
    UserResponse,             # Schema pentru raspunsul cu datele utilizatorului
)

# Importam functiile din serviciul de autentificare
from services.auth_service import (
    create_access_token,  # Genereaza un JWT token semnat cu cheia secreta
    get_current_user,     # Dependenta FastAPI: extrage userul din token-ul Bearer
    hash_password,        # Haseaza o parola folosind algoritmul bcrypt
    verify_password,      # Verifica daca parola in clar corespunde hash-ului stocat
)

# Importam exceptiile personalizate pentru cazurile de date duplicate
from utils.exceptions import DuplicateEmailException, DuplicateUsernameException

# Instantiem router-ul cu prefixul /auth si tag-ul pentru gruparea in Swagger UI
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

    # Cream obiectul ORM pentru noul utilizator
    # Parola este hasata cu bcrypt — niciodata nu stocam parola in text clar
    user_nou = User(
        email=date.email,                            # Email-ul unic al utilizatorului
        username=date.username,                      # Username-ul unic ales de utilizator
        hashed_password=hash_password(date.password),  # Hash bcrypt al parolei furnizate
    )

    # Adaugam utilizatorul in sesiunea SQLAlchemy si il persistam in baza de date
    db.add(user_nou)      # Marcam obiectul pentru inserare in baza de date
    db.commit()           # Executam tranzactia — INSERT efectiv in baza de date
    db.refresh(user_nou)  # Reincarcam obiectul din DB pentru a obtine id-ul generat automat

    # Returnam utilizatorul nou creat; FastAPI il serializeaza dupa schema UserResponse
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

    # Construim si returnam schema de raspuns cu preferintele actualizate
    return UserPreferencesResponse(
        id=prefs.id,                                        # ID-ul unic al inregistrarii de preferinte
        user_id=prefs.user_id,                             # ID-ul utilizatorului proprietar
        timezone=prefs.tz,                                  # Fusul orar (tz in ORM -> timezone in API)
        language=prefs.language,                           # Limba interfetei actualizata
        theme=prefs.theme,                                  # Tema vizuala actualizata
        notifications_enabled=prefs.notifications_enabled, # Starea notificarilor actualizata
        auto_detect_routines=prefs.auto_detect_routines,   # Starea detectiei automate ML actualizata
    )

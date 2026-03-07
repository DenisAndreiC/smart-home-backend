"""
Fixture-uri pytest partajate intre toate modulele de test ale proiectului Smart Home.

Strategie baza de date:
  - Baza de date SQLite in-memory, creata fresh pentru fiecare test (scope="function")
  - get_db override -> toate request-urile din test folosesc aceeasi sesiune in-memory
  - Dupa fiecare test tabelele sunt sterse si motorul dispus (izolare completa)

Strategie mock-uri:
  - MQTT si WoL (Wake-on-LAN) sunt mock-uite in tot suite-ul de teste
  - Serviciile externe nu sunt apelate real in teste (nu avem broker MQTT real)
  - APScheduler este oprit pentru a preveni executia rutinelor in teste

Conventie fixture-uri:
  - test_db     : sesiunea DB in-memory (infrastructura)
  - test_client : clientul HTTP FastAPI cu override-uri active
  - test_user   : utilizator creat direct in DB (fara HTTP register)
  - test_device : dispozitiv creat direct in DB (fara HTTP create)
  - auth_headers: functie helper (nu fixture) - importata direct
"""

# patch - functie unittest.mock pentru inlocuirea temporara a obiectelor cu mock-uri
from unittest.mock import patch

# pytest - framework de testare; fixture = decorator pentru definirea fixture-urilor
import pytest

# TestClient - client HTTP sincron pentru testarea aplicatiei FastAPI
from fastapi.testclient import TestClient

# create_engine - creeaza motorul de conectare la baza de date
from sqlalchemy import create_engine

# sessionmaker - fabrica de sesiuni SQLAlchemy
from sqlalchemy.orm import sessionmaker

# StaticPool - pool de conexiuni cu o singura conexiune reutilizabila
# Obligatoriu pentru SQLite in-memory ca toate sesiunile sa vada aceleasi date
from sqlalchemy.pool import StaticPool

# Importam modelele ORM necesare pentru crearea datelor de test
from database.db import Base, Device, User, get_db

# Importam aplicatia FastAPI principala
from main import app

# Importam utilitarele pentru autentificare: generare token si hashare parola
from services.auth_service import create_access_token, hash_password

# URL-ul bazei de date de test: SQLite in-memory (nu scrie pe disc)
# "sqlite:///:memory:" inseamna ca baza de date exista doar in RAM
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixture-uri de infrastructura (baza de date si client HTTP)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_db():
    """
    Creeaza o baza de date SQLite in-memory izolata pentru un singur test.

    Ciclul de viata al fixture-ului:
      1. Setup:    creeaza motorul, toate tabelele si deschide sesiunea
      2. Yield:    pune sesiunea la dispozitia testului
      3. Teardown: inchide sesiunea, sterge toate tabelele si dispune motorul

    Motivul pentru StaticPool:
      SQLite in-memory creeaza o baza de date noua (goala) pentru fiecare
      conexiune noua. StaticPool forteaza reutilizarea aceleiasi conexiuni,
      astfel incat toate sesiunile dintr-un test vad aceleasi date.

    scope="function" garanteaza izolarea completa intre teste:
      fiecare test primeste o baza de date goala, fresh.
    """
    # Cream motorul SQLAlchemy pentru SQLite in-memory
    # check_same_thread=False: permite accesul din thread-uri diferite (necesar pentru FastAPI)
    # poolclass=StaticPool: o singura conexiune reutilizata (obligatoriu pentru in-memory)
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},  # dezactivam verificarea thread-ului
        poolclass=StaticPool,                        # pool cu conexiune unica reutilizabila
    )

    # Cream fabrica de sesiuni legata de motorul de test
    # autocommit=False: tranzactiile trebuie confirmate explicit cu db.commit()
    # autoflush=False:  flush-ul nu se face automat inainte de fiecare query
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Cream toate tabelele definite in modelele ORM (Base.metadata)
    Base.metadata.create_all(bind=engine)

    # Deschidem sesiunea de baza de date pentru acest test
    db = TestingSessionLocal()

    try:
        # Punem sesiunea la dispozitia testului prin yield
        yield db
    finally:
        # Teardown: inchidem sesiunea dupa ce testul s-a terminat
        db.close()

        # Stergem toate tabelele pentru a curata dupa test
        Base.metadata.drop_all(bind=engine)

        # Eliberam resursele motorului (inchidem pool-ul de conexiuni)
        engine.dispose()


@pytest.fixture(scope="function")
def test_client(test_db):
    """
    TestClient FastAPI configurat cu override pe get_db si mock-uri active.

    Override get_db:
      Inlocuim dependency-ul get_db al aplicatiei cu o functie care
      returneaza sesiunea in-memory din fixture-ul test_db. Astfel,
      toate request-urile HTTP din test folosesc aceeasi baza de date.

    Mock-uri active pe durata testului:
      - mqtt_service.connect        : previne conectarea la broker MQTT real
      - mqtt_service.disconnect     : previne deconectarea de la broker MQTT
      - mqtt_service.publish_command: simuleaza publicarea comenzilor (returneaza True)
      - scheduler_service.start     : previne pornirea APScheduler
      - scheduler_service.stop      : previne oprirea APScheduler
      - routers.commands.wake_device: simuleaza Wake-on-LAN (returneaza True)
      - routers.scenes.wake_device  : simuleaza Wake-on-LAN in scene (returneaza True)

    Parametri:
      test_db: sesiunea in-memory de la fixture-ul test_db (injectata automat)

    Yields:
      Instanta TestClient configurata si gata de utilizare in test
    """

    # Definim functia de override care inlocuieste get_db din aplicatie
    # Aceasta functie generator cedeaza sesiunea in-memory din test_db
    def override_get_db():
        yield test_db  # returnam sesiunea in-memory in loc de sesiunea reala

    # Inregistram override-ul pentru dependency-ul get_db in aplicatia FastAPI
    app.dependency_overrides[get_db] = override_get_db

    # Activam toate mock-urile simultan folosind context managers imbricate
    # Fiecare patch() inlocuieste obiectul real cu un Mock pe durata blocului with
    with (
        patch("services.mqtt_service.mqtt_service.connect"),                          # mock connect MQTT
        patch("services.mqtt_service.mqtt_service.disconnect"),                       # mock disconnect MQTT
        patch("services.mqtt_service.mqtt_service.publish_command", return_value=True),  # mock publish (returneaza True)
        patch("services.scheduler_service.scheduler_service.start"),                  # mock start scheduler
        patch("services.scheduler_service.scheduler_service.stop"),                   # mock stop scheduler
        patch("routers.commands.wake_device", return_value=True),                     # mock WoL in comenzi
        patch("routers.scenes.wake_device", return_value=True),                       # mock WoL in scene
    ):
        # Cream clientul HTTP de test; contextul with gestioneaza startup/shutdown
        with TestClient(app) as client:
            yield client  # punem clientul la dispozitia testului

    # Curatam toate override-urile dupa test pentru a nu afecta alte teste
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fixture-uri de date (utilizator si dispozitiv de test)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_user(test_db):
    """
    Creeaza un utilizator de test direct in baza de date (fara HTTP register).

    Crearea directa in DB (nu prin API) este mai rapida si nu depinde de logica
    endpoint-ului de register. Parola este hash-uita la fel ca in productie.

    Parametri:
      test_db: sesiunea in-memory de la fixture-ul test_db (injectata automat)

    Returneaza:
      Dictionar cu datele utilizatorului:
        - "id"       : ID-ul generat de baza de date (integer)
        - "email"    : adresa de email a utilizatorului
        - "username" : numele de utilizator
        - "token"    : token JWT valid pentru autentificare in teste
    """
    # Cream obiectul User cu datele de test
    # hashed_password: hash-ul parolei "parola123" (nu parola in clar)
    user = User(
        email="test@test.com",                      # email de test
        username="tester",                          # username de test
        hashed_password=hash_password("parola123"), # parola hash-uita pentru securitate
    )

    # Adaugam utilizatorul in sesiunea SQLAlchemy (nu e inca in DB)
    test_db.add(user)

    # Salvam utilizatorul in baza de date si generam ID-ul automat
    test_db.commit()

    # Reincarcam obiectul pentru a obtine valorile generate (id, created_at etc.)
    test_db.refresh(user)

    # Generam un token JWT valid pentru utilizatorul creat
    # "sub" (subject) = email-ul utilizatorului, conform conventiei JWT
    token = create_access_token(data={"sub": user.email})

    # Returnam dictionarul cu datele necesare in teste
    return {
        "id": user.id,            # ID-ul utilizatorului din baza de date
        "email": user.email,      # adresa de email
        "username": user.username, # numele de utilizator
        "token": token,           # token JWT pentru headerul Authorization
    }


@pytest.fixture(scope="function")
def test_device(test_db, test_user):
    """
    Creeaza un dispozitiv de tip ir_rgb (bec RGB cu infrarosu) direct in baza de date.

    Dispozitivul apartine utilizatorului creat de fixture-ul test_user.
    Crearea directa in DB este mai rapida decat crearea prin API.

    Parametri:
      test_db  : sesiunea in-memory de la fixture-ul test_db (injectata automat)
      test_user: dictionarul cu datele utilizatorului (injectat automat)

    Returneaza:
      Dictionar cu datele dispozitivului:
        - "id"          : ID-ul generat de baza de date (integer)
        - "name"        : numele dispozitivului
        - "device_type" : tipul dispozitivului (ex: "ir_rgb")
        - "room"        : camera in care se afla dispozitivul
        - "mqtt_topic"  : topic-ul MQTT al dispozitivului
    """
    # Cream obiectul Device cu datele de test
    device = Device(
        name="Bec Test",                        # numele dispozitivului de test
        device_type="ir_rgb",                   # tipul: bec RGB cu infrarosu
        room="Living",                          # camera: living
        mqtt_topic="home/living/bec-test",      # topic-ul MQTT pentru comunicare
        owner_id=test_user["id"],               # ID-ul utilizatorului proprietar
    )

    # Adaugam dispozitivul in sesiunea SQLAlchemy
    test_db.add(device)

    # Salvam dispozitivul in baza de date si generam ID-ul automat
    test_db.commit()

    # Reincarcam obiectul pentru a obtine valorile generate (id, created_at etc.)
    test_db.refresh(device)

    # Returnam dictionarul cu datele necesare in teste
    return {
        "id": device.id,                    # ID-ul dispozitivului din baza de date
        "name": device.name,                # numele dispozitivului
        "device_type": device.device_type,  # tipul dispozitivului
        "room": device.room,                # camera dispozitivului
        "mqtt_topic": device.mqtt_topic,    # topic-ul MQTT
    }


# ---------------------------------------------------------------------------
# Functie helper (nu fixture) - se importa direct in modulele de test
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict:
    """
    Construieste dictionarul de headere HTTP pentru autentificare cu JWT.

    Aceasta este o functie simpla (nu un fixture pytest) care poate fi
    importata si apelata direct in orice test.

    Parametri:
      token : token-ul JWT (string) obtinut de la fixture-ul test_user

    Returneaza:
      Dictionar cu headerul Authorization in formatul standard Bearer:
        {"Authorization": "Bearer <token>"}

    Exemplu de utilizare:
      resp = test_client.get("/api/auth/me", headers=auth_headers(test_user["token"]))
    """
    # Construim headerul Authorization cu schema "Bearer" conform standardului JWT
    return {"Authorization": f"Bearer {token}"}

"""
Fixtures pytest partajate între toate modulele de test.

Strategie DB:
- Baza de date SQLite in-memory, creată fresh pentru fiecare test (scope="function")
- get_db override → toate request-urile din test folosesc aceeași sesiune in-memory
- MQTT și WoL sunt mock-uite în tot suite-ul (nu rulează servicii externe în teste)
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base, Device, User, get_db
from main import app
from services.auth_service import create_access_token, hash_password

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures de infrastructură
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_db():
    """
    Creează o bază de date SQLite in-memory pentru un singur test.
    Toate tabelele sunt create la setup și distruse la teardown.
    """
    # StaticPool → o singură conexiune reutilizată pentru tot testul.
    # Obligatoriu pentru sqlite:///:memory: — altfel fiecare sesiune
    # primește o conexiune nouă cu o bază de date goală.
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def test_client(test_db):
    """
    TestClient FastAPI cu override pe get_db → sesiunea in-memory.
    Mock-urile active pentru toată durata testului:
      - MQTT connect/disconnect/publish_command
      - APScheduler start/stop
      - wake_device (WoL) în routerele commands și scenes
    """

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    with (
        patch("services.mqtt_service.mqtt_service.connect"),
        patch("services.mqtt_service.mqtt_service.disconnect"),
        patch("services.mqtt_service.mqtt_service.publish_command", return_value=True),
        patch("services.scheduler_service.scheduler_service.start"),
        patch("services.scheduler_service.scheduler_service.stop"),
        patch("routers.commands.wake_device", return_value=True),
        patch("routers.scenes.wake_device", return_value=True),
    ):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fixtures de date
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_user(test_db):
    """
    Creează un utilizator de test direct în DB (fără HTTP).
    Returnează dict cu: id, email, username, token JWT valid.
    """
    user = User(
        email="test@test.com",
        username="tester",
        hashed_password=hash_password("parola123"),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    token = create_access_token(data={"sub": user.email})
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "token": token,
    }


@pytest.fixture(scope="function")
def test_device(test_db, test_user):
    """
    Creează un dispozitiv ir_rgb de test direct în DB.
    Returnează dict cu: id, name, device_type, room, mqtt_topic.
    """
    device = Device(
        name="Bec Test",
        device_type="ir_rgb",
        room="Living",
        mqtt_topic="home/living/bec-test",
        owner_id=test_user["id"],
    )
    test_db.add(device)
    test_db.commit()
    test_db.refresh(device)
    return {
        "id": device.id,
        "name": device.name,
        "device_type": device.device_type,
        "room": device.room,
        "mqtt_topic": device.mqtt_topic,
    }


# ---------------------------------------------------------------------------
# Helper (funcție, nu fixture — se importă direct)
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict:
    """Returnează header-ul Authorization pentru un token JWT."""
    return {"Authorization": f"Bearer {token}"}

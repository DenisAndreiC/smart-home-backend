"""
Teste autentificare — register, login, /me, token invalid.
"""
import pytest

from tests.conftest import auth_headers


def test_register_success(test_client):
    """Înregistrare cu date valide → 201, email și username în response."""
    resp = test_client.post("/api/auth/register", json={
        "email": "nou@test.com",
        "username": "utilizator_nou",
        "password": "parola123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "nou@test.com"
    assert data["username"] == "utilizator_nou"
    assert "id" in data


def test_register_duplicate_email(test_client, test_user):
    """Al doilea register cu același email → 400."""
    resp = test_client.post("/api/auth/register", json={
        "email": test_user["email"],
        "username": "alt_username",
        "password": "parola123",
    })
    assert resp.status_code == 400


def test_register_duplicate_username(test_client, test_user):
    """Al doilea register cu același username → 400."""
    resp = test_client.post("/api/auth/register", json={
        "email": "alt@test.com",
        "username": test_user["username"],
        "password": "parola123",
    })
    assert resp.status_code == 400


def test_register_short_password(test_client):
    """Parolă sub 6 caractere → 422 Unprocessable Entity (validare Pydantic)."""
    resp = test_client.post("/api/auth/register", json={
        "email": "scurt@test.com",
        "username": "scurt_user",
        "password": "abc",
    })
    assert resp.status_code == 422


def test_login_success(test_client, test_user):
    """Login cu credențiale corecte → 200, access_token prezent."""
    resp = test_client.post("/api/auth/login", json={
        "email": test_user["email"],
        "password": "parola123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_email(test_client):
    """Login cu email inexistent → 401."""
    resp = test_client.post("/api/auth/login", json={
        "email": "inexistent@test.com",
        "password": "parola123",
    })
    assert resp.status_code == 401


def test_login_wrong_password(test_client, test_user):
    """Login cu parolă greșită → 401."""
    resp = test_client.post("/api/auth/login", json={
        "email": test_user["email"],
        "password": "parolaGresita!",
    })
    assert resp.status_code == 401


def test_me_authenticated(test_client, test_user):
    """GET /me cu token valid → 200, date corecte ale userului."""
    resp = test_client.get("/api/auth/me", headers=auth_headers(test_user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == test_user["email"]
    assert data["username"] == test_user["username"]
    assert data["id"] == test_user["id"]


def test_me_no_token(test_client):
    """GET /me fără token → 401."""
    resp = test_client.get("/api/auth/me")
    assert resp.status_code == 401

"""
Suite de teste pentru modulul de autentificare al aplicatiei Smart Home.

Acopera urmatoarele scenarii:
  - Inregistrare utilizator nou (register)
    - date valide -> 201 Created
    - email duplicat -> 400 Bad Request
    - username duplicat -> 400 Bad Request
    - parola prea scurta -> 422 Unprocessable Entity
  - Autentificare (login)
    - credentiale corecte -> 200 OK cu access_token
    - email inexistent -> 401 Unauthorized
    - parola gresita -> 401 Unauthorized
  - Obtinere profil propriu (GET /me)
    - token valid -> 200 OK cu datele utilizatorului
    - fara token -> 401 Unauthorized

Toate testele folosesc fixture-urile din conftest.py:
  - test_client : clientul HTTP cu baza de date in-memory si mock-uri active
  - test_user   : utilizator precreat direct in DB (fara HTTP)
"""

# pytest este necesar pentru decoratoarele si utilitarele de test
import pytest

# Importam functia helper pentru construirea headerelor de autentificare
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul POST /api/auth/register
# ---------------------------------------------------------------------------


def test_register_success(test_client):
    """
    Scenariul fericit: inregistrare cu date valide.

    Trimitem o cerere POST cu email, username si parola valide.
    Asteptam raspuns 201 Created cu datele utilizatorului creat
    (email, username si id prezent in raspuns).
    """
    # Trimitem cererea de inregistrare cu date valide
    resp = test_client.post("/api/auth/register", json={
        "email": "nou@test.com",          # email nou, unic in baza de date
        "username": "utilizator_nou",     # username nou, unic in baza de date
        "password": "parola123",          # parola valida (minim 6 caractere)
    })

    # Verificam ca raspunsul are codul 201 Created (utilizator creat cu succes)
    assert resp.status_code == 201

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam ca email-ul din raspuns corespunde celui trimis
    assert data["email"] == "nou@test.com"

    # Verificam ca username-ul din raspuns corespunde celui trimis
    assert data["username"] == "utilizator_nou"

    # Verificam ca raspunsul contine campul "id" (generat de baza de date)
    assert "id" in data


def test_register_duplicate_email(test_client, test_user):
    """
    Inregistrare cu email deja existent in baza de date -> 400 Bad Request.

    test_user este un utilizator precreat cu email "test@test.com".
    Incercam sa inregistram un al doilea utilizator cu acelasi email.
    API-ul trebuie sa returneze 400 (conflct de unicitate).
    """
    # Incercam inregistrarea cu email-ul deja folosit de test_user
    resp = test_client.post("/api/auth/register", json={
        "email": test_user["email"],   # email duplicat - deja existent in DB
        "username": "alt_username",    # username diferit (altfel ar fi eroare de username)
        "password": "parola123",       # parola valida
    })

    # Verificam ca raspunsul are codul 400 Bad Request (email duplicat)
    assert resp.status_code == 400


def test_register_duplicate_username(test_client, test_user):
    """
    Inregistrare cu username deja existent in baza de date -> 400 Bad Request.

    test_user este un utilizator precreat cu username "tester".
    Incercam sa inregistram un al doilea utilizator cu acelasi username.
    API-ul trebuie sa returneze 400 (conflict de unicitate).
    """
    # Incercam inregistrarea cu username-ul deja folosit de test_user
    resp = test_client.post("/api/auth/register", json={
        "email": "alt@test.com",           # email diferit (altfel ar fi eroare de email)
        "username": test_user["username"], # username duplicat - deja existent in DB
        "password": "parola123",           # parola valida
    })

    # Verificam ca raspunsul are codul 400 Bad Request (username duplicat)
    assert resp.status_code == 400


def test_register_short_password(test_client):
    """
    Inregistrare cu parola prea scurta (sub 6 caractere) -> 422 Unprocessable Entity.

    Validarea Pydantic impune lungimea minima a parolei.
    Eroarea 422 este returnata inainte ca cererea sa ajunga la logica endpoint-ului.
    """
    # Incercam inregistrarea cu o parola de 3 caractere (sub minimul de 6)
    resp = test_client.post("/api/auth/register", json={
        "email": "scurt@test.com",   # email valid
        "username": "scurt_user",    # username valid
        "password": "abc",           # parola invalida: doar 3 caractere
    })

    # Verificam ca raspunsul are codul 422 Unprocessable Entity (validare Pydantic)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul POST /api/auth/login
# ---------------------------------------------------------------------------


def test_login_success(test_client, test_user):
    """
    Scenariul fericit: autentificare cu credentiale corecte -> 200 OK.

    test_user a fost creat cu parola "parola123" (hash-uita in DB).
    Asteptam un token JWT valid si tipul "bearer" in raspuns.
    """
    # Trimitem cererea de login cu credentialele corecte ale test_user
    resp = test_client.post("/api/auth/login", json={
        "email": test_user["email"],  # email-ul utilizatorului existent
        "password": "parola123",      # parola corecta (in clar, se compara cu hash-ul din DB)
    })

    # Verificam ca raspunsul are codul 200 OK (autentificare reusita)
    assert resp.status_code == 200

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam ca raspunsul contine campul "access_token" (token-ul JWT)
    assert "access_token" in data

    # Verificam ca tipul token-ului este "bearer" (schema standard OAuth2)
    assert data["token_type"] == "bearer"


def test_login_wrong_email(test_client):
    """
    Login cu email inexistent in baza de date -> 401 Unauthorized.

    Nu exista niciun utilizator cu email-ul "inexistent@test.com".
    API-ul trebuie sa returneze 401 fara a dezvalui daca email-ul exista sau nu.
    """
    # Incercam login-ul cu un email care nu exista in baza de date
    resp = test_client.post("/api/auth/login", json={
        "email": "inexistent@test.com",  # email care nu exista in DB
        "password": "parola123",         # parola (irelevanta, email-ul nu exista)
    })

    # Verificam ca raspunsul are codul 401 Unauthorized (autentificare esuata)
    assert resp.status_code == 401


def test_login_wrong_password(test_client, test_user):
    """
    Login cu email corect dar parola gresita -> 401 Unauthorized.

    Email-ul apartine lui test_user, dar parola trimisa este incorecta.
    API-ul trebuie sa returneze 401 fara a confirma ca email-ul exista.
    """
    # Incercam login-ul cu parola gresita pentru utilizatorul existent
    resp = test_client.post("/api/auth/login", json={
        "email": test_user["email"],  # email corect (utilizatorul exista)
        "password": "parolaGresita!", # parola incorecta (nu coincide cu hash-ul din DB)
    })

    # Verificam ca raspunsul are codul 401 Unauthorized (parola gresita)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/auth/me
# ---------------------------------------------------------------------------


def test_me_authenticated(test_client, test_user):
    """
    GET /me cu token JWT valid -> 200 OK cu datele corecte ale utilizatorului.

    Folosim token-ul generat in fixture-ul test_user si trimitem
    headerul Authorization cu schema Bearer.
    Verificam ca datele returnate corespund cu cele ale utilizatorului creat.
    """
    # Trimitem cererea GET cu headerul de autentificare corect
    # auth_headers() construieste {"Authorization": "Bearer <token>"}
    resp = test_client.get("/api/auth/me", headers=auth_headers(test_user["token"]))

    # Verificam ca raspunsul are codul 200 OK (autentificare reusita)
    assert resp.status_code == 200

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam ca email-ul din raspuns corespunde celui din test_user
    assert data["email"] == test_user["email"]

    # Verificam ca username-ul din raspuns corespunde celui din test_user
    assert data["username"] == test_user["username"]

    # Verificam ca id-ul din raspuns corespunde celui din test_user
    assert data["id"] == test_user["id"]


def test_me_no_token(test_client):
    """
    GET /me fara header Authorization -> 401 Unauthorized.

    Endpoint-ul /me necesita autentificare. Daca nu trimitem token-ul,
    FastAPI trebuie sa returneze 401 prin dependency-ul get_current_user.
    """
    # Trimitem cererea GET fara niciun header de autentificare
    resp = test_client.get("/api/auth/me")

    # Verificam ca raspunsul are codul 401 Unauthorized (lipsa token)
    assert resp.status_code == 401

"""
Suite de teste pentru modulul de gestionare a scenelor Smart Home.

Acopera urmatoarele scenarii:
  - Creare scena cu actiuni multiple (POST /api/scenes/)
    - date valide -> 201 Created cu actiunile incluse
  - Executie scena (POST /api/scenes/{id}/execute)
    - scena cu 1 actiune -> 200 OK, actions_count == 1
  - Listare scene (GET /api/scenes/)
    - dupa creare -> 200 OK cu cel putin o scena
  - Obtinere scena (GET /api/scenes/{id})
    - ID valid -> 200 OK cu actiunile incluse
  - Stergere scena (DELETE /api/scenes/{id})
    - ID valid -> 200 OK; GET ulterior -> 404

MQTT este mock-uit global in conftest.py, astfel incat nicio comanda reala
nu este trimisa la broker pe durata testelor. delay_seconds=0 in toate
actiunile de test pentru a nu introduce asteptari reale in suite.

Fixture-urile folosite (definite in conftest.py):
  - test_client : clientul HTTP cu baza de date in-memory si mock-uri active
  - test_user   : utilizator precreat direct in DB
  - test_device : dispozitiv precreat direct in DB (tip ir_rgb, camera Living)
"""

# Importam functia helper pentru construirea headerelor de autentificare
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Helper intern — reutilizat in mai multe teste
# ---------------------------------------------------------------------------


def _creare_scena(test_client, test_user, test_device, name="Mod Film"):
    """
    Helper intern: creeaza o scena cu 2 actiuni si returneaza obiectul Response.

    Scena contine doua actiuni pentru test_device:
      - Actiunea 0: power=on (pornire), exec_order=0, delay_seconds=0
      - Actiunea 1: brightness=20 (luminozitate redusa), exec_order=1, delay_seconds=0

    Parametri:
        test_client : clientul HTTP de test
        test_user   : dictionarul cu datele utilizatorului (email, token, id)
        test_device : dictionarul cu datele dispozitivului (id, name)
        name        : numele scenei (implicit "Mod Film")

    Returneaza:
        Obiectul Response de la POST /api/scenes/
    """
    # Trimitem cererea POST de creare scena cu 2 actiuni
    return test_client.post(
        "/api/scenes/",                         # endpoint-ul de creare scene
        json={
            "name": name,                       # numele scenei (parametrizat)
            "icon": "film",                     # iconita scenei
            "actions": [
                {
                    "device_id": test_device["id"],  # ID-ul dispozitivului tinta
                    "action": "power",               # tipul actiunii: power
                    "value": "on",                   # valoarea: pornire
                    "order": 0,                      # prima actiune (exec_order=0)
                    "delay_seconds": 0,              # fara delay (test rapid)
                },
                {
                    "device_id": test_device["id"],  # acelasi dispozitiv
                    "action": "brightness",          # tipul actiunii: luminozitate
                    "value": "20",                   # valoarea: 20% luminozitate
                    "order": 1,                      # a doua actiune (exec_order=1)
                    "delay_seconds": 0,              # fara delay (test rapid)
                },
            ],
        },
        headers=auth_headers(test_user["token"]),  # token JWT in header Authorization
    )


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul POST /api/scenes/
# ---------------------------------------------------------------------------


def test_create_scene(test_client, test_user, test_device):
    """
    Scenariul fericit: creare scena cu 2 actiuni -> 201 Created.

    Verificam:
    - codul de raspuns este 201 (creata cu succes)
    - numele scenei este corect
    - scena contine exact 2 actiuni
    - prima actiune are device_name populat din relatia ORM
    """
    # Cream scena cu helper-ul intern (2 actiuni, delay=0)
    resp = _creare_scena(test_client, test_user, test_device)

    # Verificam ca raspunsul are codul 201 Created (scena creata cu succes)
    assert resp.status_code == 201

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam ca numele scenei corespunde celui trimis
    assert data["name"] == "Mod Film"

    # Verificam ca scena contine exact 2 actiuni (cum am trimis)
    assert len(data["actions"]) == 2

    # Verificam ca prima actiune are device_name populat din relatia ORM
    # (nu ID-ul, ci numele dispozitivului extras prin JOIN)
    assert data["actions"][0]["device_name"] == test_device["name"]


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul POST /api/scenes/{id}/execute
# ---------------------------------------------------------------------------


def test_execute_scene(test_client, test_user, test_device):
    """
    Executie scena: POST /scenes/{id}/execute -> 200 OK cu actions_count corect.

    Cream o scena cu 1 actiune (delay=0 pentru test rapid) si o executam.
    Verificam ca raspunsul confirma executia cu numarul corect de actiuni.
    MQTT este mock-uit in conftest.py, deci comanda nu ajunge la broker real.
    """
    # Cream o scena cu o singura actiune pentru a testa executia
    create_resp = test_client.post(
        "/api/scenes/",                             # endpoint-ul de creare scene
        json={
            "name": "Scena Execute",                # numele scenei de test
            "actions": [
                {
                    "device_id": test_device["id"], # dispozitivul tinta
                    "action": "power",              # tipul actiunii
                    "value": "on",                  # valoarea actiunii
                    "order": 0,                     # prima (si singura) actiune
                    "delay_seconds": 0,             # fara delay (test rapid)
                },
            ],
        },
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca scena a fost creata cu succes
    assert create_resp.status_code == 201

    # Extragem ID-ul scenei create din raspuns
    scene_id = create_resp.json()["id"]

    # Trimitem cererea POST de executie a scenei
    resp = test_client.post(
        f"/api/scenes/{scene_id}/execute",          # endpoint-ul de executie
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca executia a reusit (200 OK)
    assert resp.status_code == 200

    # Extragem datele de confirmare din raspuns
    data = resp.json()

    # Verificam ca numarul de actiuni executate este egal cu 1 (cata am trimis)
    assert data["actions_count"] == 1


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/scenes/
# ---------------------------------------------------------------------------


def test_list_scenes(test_client, test_user, test_device):
    """
    Listare scene: GET /scenes/ -> 200 OK cu cel putin o scena dupa creare.

    Cream o scena cu helper-ul intern, apoi verificam ca endpoint-ul de listare
    returneaza o lista cu cel putin o scena.
    """
    # Cream o scena pentru a popula lista
    _creare_scena(test_client, test_user, test_device, name="Scena Lista")

    # Trimitem cererea GET pentru lista scenelor utilizatorului
    resp = test_client.get("/api/scenes/", headers=auth_headers(test_user["token"]))

    # Verificam ca raspunsul are codul 200 OK
    assert resp.status_code == 200

    # Extragem lista de scene din raspuns
    data = resp.json()

    # Verificam ca raspunsul este o lista (nu un dict sau alt tip)
    assert isinstance(data, list)

    # Verificam ca lista contine cel putin scena creata anterior
    assert len(data) >= 1


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/scenes/{id}
# ---------------------------------------------------------------------------


def test_get_scene(test_client, test_user, test_device):
    """
    Obtinere scena dupa ID: GET /scenes/{id} -> 200 OK cu actiunile incluse.

    Cream o scena cu 2 actiuni si verificam ca GET-ul individual
    returneaza corect ID-ul, numele si lista completa de actiuni.
    """
    # Cream o scena cu 2 actiuni pentru a testa GET-ul individual
    create_resp = _creare_scena(test_client, test_user, test_device, name="Scena Detail")

    # Extragem ID-ul scenei create din raspuns
    scene_id = create_resp.json()["id"]

    # Trimitem cererea GET pentru scena specifica
    resp = test_client.get(
        f"/api/scenes/{scene_id}",              # URL cu ID-ul scenei
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca raspunsul are codul 200 OK
    assert resp.status_code == 200

    # Extragem datele scenei din raspuns
    data = resp.json()

    # Verificam ca ID-ul din raspuns corespunde celui cerut
    assert data["id"] == scene_id

    # Verificam ca numele din raspuns corespunde celui trimis la creare
    assert data["name"] == "Scena Detail"

    # Verificam ca scena contine exact 2 actiuni (cum am creat)
    assert len(data["actions"]) == 2


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul DELETE /api/scenes/{id}
# ---------------------------------------------------------------------------


def test_delete_scene(test_client, test_user, test_device):
    """
    Stergere scena: DELETE /scenes/{id} -> 200 OK; GET ulterior -> 404.

    Dupa stergerea cu succes, verificam ca scena nu mai poate fi accesata.
    Un GET cu acelasi ID trebuie sa returneze 404 Not Found.
    Actiunile se sterg automat prin cascade (definit in ORM si la nivel DB).
    """
    # Cream o scena pentru a o sterge
    create_resp = _creare_scena(test_client, test_user, test_device, name="Scena Stearsa")

    # Extragem ID-ul scenei create
    scene_id = create_resp.json()["id"]

    # Trimitem cererea DELETE pentru scena
    resp = test_client.delete(
        f"/api/scenes/{scene_id}",              # URL cu ID-ul scenei de sters
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca stergerea a reusit (200 OK)
    assert resp.status_code == 200

    # Verificam ca scena nu mai exista — GET dupa DELETE trebuie sa returneze 404
    resp2 = test_client.get(
        f"/api/scenes/{scene_id}",              # acelasi ID, acum sters
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca GET-ul returneaza 404 (scena a fost stearsa)
    assert resp2.status_code == 404

"""
Teste rutine — CRUD manual, generare date ML, detectare tipare, toggle.
"""
from tests.conftest import auth_headers


def test_create_routine(test_client, test_user, test_device):
    """POST /routines/ cu date valide → 201, câmpurile corecte."""
    resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Seara - Bec Off",
            "device_id": test_device["id"],
            "action": "power",
            "value": "off",
            "trigger_time": "22:00",
            "days_of_week": "1,2,3,4,5",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Seara - Bec Off"
    assert data["trigger_time"] == "22:00"
    assert data["days_of_week"] == "1,2,3,4,5"
    assert data["device_id"] == test_device["id"]


def test_list_routines(test_client, test_user, test_device):
    """GET /routines/ → 200, returnează lista rutinelor utilizatorului."""
    # Creăm o rutină mai întâi
    test_client.post(
        "/api/routines/",
        json={
            "name": "Dimineața - Bec On",
            "device_id": test_device["id"],
            "action": "power",
            "value": "on",
            "trigger_time": "07:00",
            "days_of_week": "1,2,3,4,5",
        },
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get("/api/routines/", headers=auth_headers(test_user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_generate_test_data(test_client, test_user, test_device):
    """POST /routines/generate-test-data → 200, count > 0 comenzi generate."""
    resp = test_client.post(
        f"/api/routines/generate-test-data?device_id={test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert data["count"] > 0


def test_detect_routines(test_client, test_user, test_device):
    """
    GET /routines/detect → 200 după generare date sintetice.
    Algoritmul DBSCAN detectează cel puțin o rutină din datele generate.
    """
    # Generăm date sintetice — 3 tipare pe 30 zile
    test_client.post(
        f"/api/routines/generate-test-data?device_id={test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/routines/detect",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "routines_detected" in data
    assert "routines_saved" in data
    assert "data" in data
    # Cu 30 zile de date sintetice, ML-ul trebuie să găsească tipare
    assert data["routines_detected"] > 0


def test_toggle_routine(test_client, test_user, test_device):
    """PUT /routines/{id}/toggle → 200, is_active schimbat."""
    # Creăm o rutină (pornită implicit)
    create_resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Test Toggle",
            "device_id": test_device["id"],
            "action": "power",
            "value": "on",
            "trigger_time": "08:00",
            "days_of_week": "1,2,3",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert create_resp.status_code == 201
    routine_id = create_resp.json()["id"]
    initial_state = create_resp.json()["is_active"]

    # Inversăm starea
    resp = test_client.put(
        f"/api/routines/{routine_id}/toggle",
        json={"is_active": not initial_state},
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] == (not initial_state)


def test_delete_routine(test_client, test_user, test_device):
    """DELETE /routines/{id} → 200, rutina dispare din listing."""
    create_resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Rutina de Sters",
            "device_id": test_device["id"],
            "action": "power",
            "value": "off",
            "trigger_time": "23:59",
            "days_of_week": "7",
        },
        headers=auth_headers(test_user["token"]),
    )
    routine_id = create_resp.json()["id"]

    resp = test_client.delete(
        f"/api/routines/{routine_id}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200

    # Verificăm că nu mai apare în listing
    listing = test_client.get("/api/routines/", headers=auth_headers(test_user["token"]))
    ids = [r["id"] for r in listing.json()]
    assert routine_id not in ids

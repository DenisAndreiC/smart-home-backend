"""
Teste dispozitive — CRUD complet, filtrare după cameră, validare WoL.
"""
from tests.conftest import auth_headers


def test_create_device(test_client, test_user):
    """POST /devices/ cu date valide → 201, name și device_type corecte."""
    resp = test_client.post(
        "/api/devices/",
        json={
            "name": "LED Living",
            "device_type": "ir_rgb",
            "room": "Living",
            "mqtt_topic": "home/living/led",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "LED Living"
    assert data["device_type"] == "ir_rgb"
    assert data["owner_id"] == test_user["id"]


def test_create_wol_without_mac(test_client, test_user):
    """Dispozitiv WoL fără mac_address → 400 Bad Request."""
    resp = test_client.post(
        "/api/devices/",
        json={
            "name": "PC Birou",
            "device_type": "wol",
            "room": "Birou",
            "mqtt_topic": "home/birou/pc",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 400


def test_list_devices(test_client, test_user, test_device):
    """GET /devices/ → 200, lista conține cel puțin test_device-ul."""
    resp = test_client.get("/api/devices/", headers=auth_headers(test_user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [d["id"] for d in data]
    assert test_device["id"] in ids


def test_list_devices_filter_room(test_client, test_user, test_device):
    """GET /devices/?room=Living → returnează doar dispozitivele din Living."""
    # Adăugăm un device în altă cameră
    test_client.post(
        "/api/devices/",
        json={
            "name": "Aer Condiționat",
            "device_type": "ir_ac",
            "room": "Dormitor",
            "mqtt_topic": "home/dormitor/ac",
        },
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/devices/?room=Living",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(d["room"] == "Living" for d in data)


def test_get_device(test_client, test_user, test_device):
    """GET /devices/{id} → 200, datele dispozitivului sunt corecte."""
    resp = test_client.get(
        f"/api/devices/{test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_device["id"]
    assert data["name"] == test_device["name"]


def test_get_device_not_found(test_client, test_user):
    """GET /devices/999 → 404 Not Found."""
    resp = test_client.get(
        "/api/devices/999",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 404


def test_update_device(test_client, test_user, test_device):
    """PUT /devices/{id} cu name nou → 200, name actualizat în response."""
    resp = test_client.put(
        f"/api/devices/{test_device['id']}",
        json={"name": "Bec Test Redenumit"},
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Bec Test Redenumit"
    assert data["id"] == test_device["id"]


def test_delete_device(test_client, test_user, test_device):
    """DELETE /devices/{id} → 200; GET ulterior → 404."""
    resp = test_client.delete(
        f"/api/devices/{test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200

    resp2 = test_client.get(
        f"/api/devices/{test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp2.status_code == 404

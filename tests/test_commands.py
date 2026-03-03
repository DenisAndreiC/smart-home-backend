"""
Teste comenzi — trimitere, istoric, filtrare, WoL.
MQTT și wake_device sunt mock-uite global în conftest.py.
"""
from tests.conftest import auth_headers


def test_send_command(test_client, test_user, test_device):
    """POST /commands/send → 200, action și value prezente în response."""
    resp = test_client.post(
        "/api/commands/send",
        json={
            "device_id": test_device["id"],
            "action": "power",
            "value": "on",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "power"
    assert data["value"] == "on"
    assert data["device_id"] == test_device["id"]


def test_send_command_nonexistent_device(test_client, test_user):
    """device_id inexistent → 404 Not Found."""
    resp = test_client.post(
        "/api/commands/send",
        json={"device_id": 999, "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 404


def test_command_history(test_client, test_user, test_device):
    """GET /commands/history → 200, returnează lista de comenzi."""
    # Trimitem o comandă pentru a umple istoricul
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/commands/history",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_command_history_filter(test_client, test_user, test_device):
    """GET /commands/history?device_id={id} → doar comenzile acelui device."""
    # Trimitem o comandă specifică acestui device
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "brightness", "value": "50"},
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        f"/api/commands/history?device_id={test_device['id']}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(cmd["device_id"] == test_device["id"] for cmd in data)


def test_command_saved_in_db(test_client, test_user, test_device):
    """După send, comanda apare în history cu source='app'."""
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "color", "value": "red"},
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/commands/history",
        headers=auth_headers(test_user["token"]),
    )
    data = resp.json()
    assert len(data) >= 1
    # Cel mai recent este primul (ordenat DESC)
    assert data[0]["source"] == "app"
    assert data[0]["action"] == "color"
    assert data[0]["value"] == "red"


def test_wol_command(test_client, test_user):
    """POST /commands/wol cu device WoL valid → 200, magic packet trimis."""
    # Creăm un device WoL cu MAC valid
    create_resp = test_client.post(
        "/api/devices/",
        json={
            "name": "PC Birou",
            "device_type": "wol",
            "room": "Birou",
            "mqtt_topic": "home/birou/pc",
            "mac_address": "AA:BB:CC:DD:EE:FF",
        },
        headers=auth_headers(test_user["token"]),
    )
    assert create_resp.status_code == 201
    device_id = create_resp.json()["id"]

    resp = test_client.post(
        "/api/commands/wol",
        json={"device_id": device_id},
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "magic packet" in data["message"].lower() or "trimis" in data["message"].lower()

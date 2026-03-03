"""
Teste scene — creare cu acțiuni multiple, execuție, listing, detaliu, ștergere.
MQTT este mock-uit global în conftest.py; delay_seconds=0 pentru teste rapide.
"""
from tests.conftest import auth_headers


def _creare_scena(test_client, test_user, test_device, name="Mod Film"):
    """Helper intern: creează o scenă cu 2 acțiuni și returnează response JSON."""
    return test_client.post(
        "/api/scenes/",
        json={
            "name": name,
            "icon": "film",
            "actions": [
                {
                    "device_id": test_device["id"],
                    "action": "power",
                    "value": "on",
                    "order": 0,
                    "delay_seconds": 0,
                },
                {
                    "device_id": test_device["id"],
                    "action": "brightness",
                    "value": "20",
                    "order": 1,
                    "delay_seconds": 0,
                },
            ],
        },
        headers=auth_headers(test_user["token"]),
    )


def test_create_scene(test_client, test_user, test_device):
    """POST /scenes/ cu 2 acțiuni → 201, actions_count == 2."""
    resp = _creare_scena(test_client, test_user, test_device)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Mod Film"
    assert len(data["actions"]) == 2
    # Verificăm că acțiunile au device_name populat
    assert data["actions"][0]["device_name"] == test_device["name"]


def test_execute_scene(test_client, test_user, test_device):
    """POST /scenes/{id}/execute → 200, actions_count corect în response."""
    create_resp = test_client.post(
        "/api/scenes/",
        json={
            "name": "Scena Execute",
            "actions": [
                {
                    "device_id": test_device["id"],
                    "action": "power",
                    "value": "on",
                    "order": 0,
                    "delay_seconds": 0,
                },
            ],
        },
        headers=auth_headers(test_user["token"]),
    )
    assert create_resp.status_code == 201
    scene_id = create_resp.json()["id"]

    resp = test_client.post(
        f"/api/scenes/{scene_id}/execute",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["actions_count"] == 1


def test_list_scenes(test_client, test_user, test_device):
    """GET /scenes/ → 200, lista non-goală după creare."""
    _creare_scena(test_client, test_user, test_device, name="Scena Lista")

    resp = test_client.get("/api/scenes/", headers=auth_headers(test_user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_scene(test_client, test_user, test_device):
    """GET /scenes/{id} → 200, acțiunile scenei sunt incluse."""
    create_resp = _creare_scena(test_client, test_user, test_device, name="Scena Detail")
    scene_id = create_resp.json()["id"]

    resp = test_client.get(
        f"/api/scenes/{scene_id}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == scene_id
    assert data["name"] == "Scena Detail"
    assert len(data["actions"]) == 2


def test_delete_scene(test_client, test_user, test_device):
    """DELETE /scenes/{id} → 200; GET ulterior → 404."""
    create_resp = _creare_scena(test_client, test_user, test_device, name="Scena Stearsa")
    scene_id = create_resp.json()["id"]

    resp = test_client.delete(
        f"/api/scenes/{scene_id}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200

    resp2 = test_client.get(
        f"/api/scenes/{scene_id}",
        headers=auth_headers(test_user["token"]),
    )
    assert resp2.status_code == 404

"""
Teste dashboard și notificări — statistici agregate, activity log, unread count.
"""
from tests.conftest import auth_headers


def test_dashboard_stats(test_client, test_user, test_device):
    """
    GET /dashboard/stats → 200, toate câmpurile DashboardStats prezente.
    Trimitem o comandă înainte pentru a popula comenzile de azi.
    """
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/dashboard/stats",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()

    # Câmpuri obligatorii conform DashboardStats schema
    assert "total_devices" in data
    assert "total_commands_today" in data
    assert "total_routines_active" in data
    assert "total_scenes" in data
    assert "commands_by_day" in data
    assert "commands_by_device" in data
    assert "device_type_distribution" in data

    # Avem 1 device creat prin test_device
    assert data["total_devices"] >= 1
    # commands_by_day trebuie să fie o listă de 7 elemente (ultimele 7 zile)
    assert len(data["commands_by_day"]) == 7


def test_dashboard_activity(test_client, test_user):
    """GET /dashboard/activity → 200, returnează o listă."""
    resp = test_client.get(
        "/api/dashboard/activity",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_notifications_count(test_client, test_user, test_device):
    """
    GET /notifications/count → 200, unread_count prezent.
    Trimitem o comandă care generează automat o notificare.
    """
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )

    resp = test_client.get(
        "/api/notifications/count",
        headers=auth_headers(test_user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "unread_count" in data
    assert isinstance(data["unread_count"], int)
    assert data["unread_count"] >= 0

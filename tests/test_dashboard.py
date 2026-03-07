"""
Suite de teste pentru modulul de dashboard si notificari Smart Home.

Acopera urmatoarele scenarii:
  - Statistici dashboard (GET /api/dashboard/stats)
    - dupa o comanda -> 200 OK cu toate campurile DashboardStats prezente
    - commands_by_day are exact 7 elemente (ultimele 7 zile)
  - Jurnal activitate (GET /api/dashboard/activity)
    - 200 OK cu o lista (poate fi goala)
  - Contor notificari necitite (GET /api/notifications/count)
    - dupa o comanda -> 200 OK cu unread_count >= 0

Nota: trimiterea unei comenzi prin /api/commands/send genereaza automat o
notificare de tip 'success' (prin notify_device_command din notification_service).
Acesta este motivul pentru care trimitem o comanda inainte de a testa /count.

Fixture-urile folosite (definite in conftest.py):
  - test_client : clientul HTTP cu baza de date in-memory si mock-uri active
  - test_user   : utilizator precreat direct in DB
  - test_device : dispozitiv precreat direct in DB (tip ir_rgb, camera Living)
"""

# Importam functia helper pentru construirea headerelor de autentificare
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/dashboard/stats
# ---------------------------------------------------------------------------


def test_dashboard_stats(test_client, test_user, test_device):
    """
    Statistici dashboard: GET /dashboard/stats -> 200 OK cu toate campurile.

    Trimitem o comanda inainte pentru a popula:
    - total_commands_today (comanda trimisa azi)
    - commands_by_day (lista ultimelor 7 zile)
    - commands_by_device (top dispozitive)

    Verificam prezenta tuturor campurilor din schema DashboardStats si
    ca commands_by_day contine exact 7 intrari (una pentru fiecare zi).
    """
    # Trimitem o comanda pentru a popula statisticile de azi
    # Aceasta comanda va fi numarata in total_commands_today si commands_by_day
    test_client.post(
        "/api/commands/send",                       # endpoint-ul de trimitere comenzi
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )

    # Trimitem cererea GET pentru statisticile dashboard-ului
    resp = test_client.get(
        "/api/dashboard/stats",                     # endpoint-ul de statistici
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca raspunsul are codul 200 OK
    assert resp.status_code == 200

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam prezenta campului total_devices (numarul total de dispozitive)
    assert "total_devices" in data

    # Verificam prezenta campului total_commands_today (comenzi trimise azi)
    assert "total_commands_today" in data

    # Verificam prezenta campului total_routines_active (rutine activate)
    assert "total_routines_active" in data

    # Verificam prezenta campului total_scenes (numarul total de scene)
    assert "total_scenes" in data

    # Verificam prezenta campului commands_by_day (comenzi per zi, ultimele 7 zile)
    assert "commands_by_day" in data

    # Verificam prezenta campului commands_by_device (top dispozitive dupa utilizare)
    assert "commands_by_device" in data

    # Verificam prezenta campului device_type_distribution (distributie tipuri dispozitive)
    assert "device_type_distribution" in data

    # Verificam ca avem cel putin 1 dispozitiv (test_device creat de fixture)
    assert data["total_devices"] >= 1

    # Verificam ca commands_by_day contine exact 7 intrari (ultimele 7 zile)
    # Dashboard-ul afiseaza intotdeauna 7 zile, chiar daca unele au 0 comenzi
    assert len(data["commands_by_day"]) == 7


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/dashboard/activity
# ---------------------------------------------------------------------------


def test_dashboard_activity(test_client, test_user):
    """
    Jurnal activitate: GET /dashboard/activity -> 200 OK cu o lista.

    Endpoint-ul returneaza jurnalul de activitate al utilizatorului curent.
    In contextul testului, lista poate fi goala (nicio actiune inregistrata
    inainte de apelul GET), dar formatul trebuie sa fie o lista valida.
    """
    # Trimitem cererea GET pentru jurnalul de activitate
    resp = test_client.get(
        "/api/dashboard/activity",                  # endpoint-ul de jurnal activitate
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca raspunsul are codul 200 OK
    assert resp.status_code == 200

    # Verificam ca raspunsul este o lista (poate fi goala, dar trebuie sa fie list)
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Teste pentru endpoint-ul GET /api/notifications/count
# ---------------------------------------------------------------------------


def test_notifications_count(test_client, test_user, test_device):
    """
    Contor notificari necitite: GET /notifications/count -> 200 OK.

    Trimitem o comanda inainte deoarece send_command genereaza automat o
    notificare de tip 'success' prin notify_device_command. Astfel avem
    garantia ca unread_count >= 1 dupa apelul send.

    Verificam ca:
    - campul unread_count este prezent in raspuns
    - tipul sau este int (nu string sau null)
    - valoarea este >= 0 (nu poate fi negativa)
    """
    # Trimitem o comanda care va genera automat o notificare de succes
    # notify_device_command din notification_service adauga notificarea
    test_client.post(
        "/api/commands/send",                       # endpoint-ul de trimitere comenzi
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),
    )

    # Trimitem cererea GET pentru contorul de notificari necitite
    resp = test_client.get(
        "/api/notifications/count",                 # endpoint-ul de contor notificari
        headers=auth_headers(test_user["token"]),
    )

    # Verificam ca raspunsul are codul 200 OK
    assert resp.status_code == 200

    # Extragem datele din raspunsul JSON
    data = resp.json()

    # Verificam ca campul unread_count este prezent in raspuns
    assert "unread_count" in data

    # Verificam ca tipul valorii unread_count este int (nu string sau null)
    assert isinstance(data["unread_count"], int)

    # Verificam ca valoarea unread_count este >= 0 (nu poate fi negativa)
    assert data["unread_count"] >= 0

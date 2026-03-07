"""
Teste comenzi — trimitere, istoric, filtrare, WoL.
MQTT si wake_device sunt mock-uite global in conftest.py astfel incat
niciun pachet real nu este trimis in retea pe durata testelor.
Toate testele folosesc fixture-urile test_client, test_user si test_device din conftest.py.
"""
from tests.conftest import auth_headers


def test_send_command(test_client, test_user, test_device):
    """
    Verifica ca POST /api/commands/send cu date valide returneaza 200.
    Campurile action, value si device_id trebuie sa fie prezente si corecte in raspuns.
    Scopul testului: confirma ca trimiterea unei comenzi catre un dispozitiv existent functioneaza.
    """
    # Trimitem o cerere POST pentru a trimite comanda 'power on' catre dispozitivul de test
    resp = test_client.post(
        "/api/commands/send",
        json={
            "device_id": test_device["id"],  # id-ul dispozitivului caruia i se trimite comanda
            "action": "power",               # actiunea de executat pe dispozitiv
            "value": "on",                   # valoarea asociata actiunii
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata cu tokenul utilizatorului
    )

    # Verificam ca serverul raspunde cu 200 OK (comanda a fost procesata cu succes)
    assert resp.status_code == 200

    # Extragem corpul JSON al raspunsului pentru verificari detaliate
    data = resp.json()

    # Verificam ca actiunea returnata in raspuns este cea trimisa
    assert data["action"] == "power"

    # Verificam ca valoarea returnata in raspuns este cea trimisa
    assert data["value"] == "on"

    # Verificam ca device_id din raspuns corespunde dispozitivului tinta
    assert data["device_id"] == test_device["id"]


def test_send_command_nonexistent_device(test_client, test_user):
    """
    Verifica ca POST /api/commands/send cu un device_id inexistent returneaza 404.
    ID-ul 999 nu exista in baza de date de test izolata.
    Scopul testului: confirma ca serverul valideaza existenta dispozitivului inainte de a procesa comanda.
    """
    # Trimitem o cerere POST cu un device_id care nu exista in baza de date
    resp = test_client.post(
        "/api/commands/send",
        json={"device_id": 999, "action": "power", "value": "on"},  # id 999 este absent in DB
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 404 Not Found — dispozitivul nu a fost gasit
    assert resp.status_code == 404


def test_command_history(test_client, test_user, test_device):
    """
    Verifica ca GET /api/commands/history returneaza 200 si o lista de comenzi.
    Trimitem mai intai o comanda pentru a ne asigura ca istoricul nu este gol.
    Scopul testului: confirma ca endpoint-ul de istoric returneaza comenzile salvate in DB.
    """
    # Trimitem o comanda in prealabil pentru a popula istoricul cu cel putin o intrare
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "power", "value": "on"},
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET pentru a obtine istoricul tuturor comenzilor utilizatorului
    resp = test_client.get(
        "/api/commands/history",
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK
    assert resp.status_code == 200

    # Extragem lista de comenzi din raspuns
    data = resp.json()

    # Verificam ca raspunsul este o lista Python (nu un dict sau alt tip)
    assert isinstance(data, list)

    # Verificam ca lista contine cel putin comanda trimisa anterior
    assert len(data) >= 1


def test_command_history_filter(test_client, test_user, test_device):
    """
    Verifica ca GET /api/commands/history?device_id={id} returneaza doar comenzile unui device.
    Trimitem o comanda specifica pentru test_device si filtram istoricul dupa id-ul sau.
    Scopul testului: confirma ca filtrul pe device_id izoleaza corect comenzile unui singur dispozitiv.
    """
    # Trimitem o comanda specifica pentru dispozitivul de test cu actiunea 'brightness'
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "brightness", "value": "50"},
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET cu filtrul device_id pentru a obtine doar comenzile acestui dispozitiv
    resp = test_client.get(
        f"/api/commands/history?device_id={test_device['id']}",  # filtram dupa id-ul dispozitivului
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK
    assert resp.status_code == 200

    # Extragem lista filtrata de comenzi din raspuns
    data = resp.json()

    # Verificam ca lista filtrata contine cel putin comanda trimisa anterior
    assert len(data) >= 1

    # Verificam ca absolut toate comenzile returnate apartin dispozitivului filtrat
    assert all(cmd["device_id"] == test_device["id"] for cmd in data)


def test_command_saved_in_db(test_client, test_user, test_device):
    """
    Verifica ca dupa POST /api/commands/send comanda apare in istoric cu source='app'.
    Cel mai recent element din istoric trebuie sa reflecte exact comanda trimisa.
    Scopul testului: confirma persistenta comenzii in DB si corectitudinea campurilor salvate.
    """
    # Trimitem o comanda cu actiunea 'color' si valoarea 'red' pentru a o verifica ulterior in istoric
    test_client.post(
        "/api/commands/send",
        json={"device_id": test_device["id"], "action": "color", "value": "red"},
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET pentru a obtine istoricul comenzilor si a verifica persistenta
    resp = test_client.get(
        "/api/commands/history",
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Extragem lista de comenzi din raspuns
    data = resp.json()

    # Verificam ca lista nu este goala — comanda trimisa trebuie sa fie prezenta
    assert len(data) >= 1

    # Cel mai recent element este primul din lista deoarece istoricul este ordonat DESC dupa timestamp
    # Verificam ca sursa comenzii este 'app' — comenzile trimise manual au aceasta sursa
    assert data[0]["source"] == "app"

    # Verificam ca actiunea salvata in DB corespunde cu cea trimisa in cerere
    assert data[0]["action"] == "color"

    # Verificam ca valoarea salvata in DB corespunde cu cea trimisa in cerere
    assert data[0]["value"] == "red"


def test_wol_command(test_client, test_user):
    """
    Verifica ca POST /api/commands/wol cu un dispozitiv WoL valid returneaza 200.
    Mesajul din raspuns trebuie sa confirme ca magic packet-ul a fost trimis.
    wake_device este mock-uit in conftest.py — niciun pachet real nu este transmis.
    Scopul testului: confirma ca fluxul complet WoL (creare dispozitiv + trimitere packet) functioneaza.
    """
    # Cream un dispozitiv de tip WoL cu o adresa MAC valida inainte de a trimite comanda WoL
    create_resp = test_client.post(
        "/api/devices/",
        json={
            "name": "PC Birou",                  # numele dispozitivului WoL
            "device_type": "wol",                # tipul WoL — necesita mac_address
            "room": "Birou",                     # camera in care se afla PC-ul
            "mqtt_topic": "home/birou/pc",       # topic MQTT asociat
            "mac_address": "AA:BB:CC:DD:EE:FF",  # adresa MAC valida necesara pentru WoL
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca dispozitivul WoL a fost creat cu succes inainte de a continua testul
    assert create_resp.status_code == 201

    # Extragem id-ul dispozitivului WoL creat pentru a-l folosi in cererea de wake
    device_id = create_resp.json()["id"]

    # Trimitem o cerere POST pentru a declansa trimiterea magic packet-ului catre dispozitiv
    resp = test_client.post(
        "/api/commands/wol",
        json={"device_id": device_id},            # id-ul dispozitivului WoL tinta
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (comanda WoL a fost procesata)
    assert resp.status_code == 200

    # Extragem corpul raspunsului pentru a verifica mesajul de confirmare
    data = resp.json()

    # Verificam ca mesajul de raspuns contine confirmare — fie 'magic packet' fie 'trimis'
    assert "magic packet" in data["message"].lower() or "trimis" in data["message"].lower()

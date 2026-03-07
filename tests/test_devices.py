"""
Teste dispozitive — CRUD complet, filtrare dupa camera, validare WoL.
Fiecare test acopera un scenariu distinct al endpoint-urilor din /api/devices/.
Fixture-urile test_client, test_user si test_device sunt definite in conftest.py.
"""
from tests.conftest import auth_headers


def test_create_device(test_client, test_user):
    """
    Verifica ca POST /api/devices/ cu date valide returneaza 201 Created.
    Campurile name, device_type si owner_id trebuie sa fie corecte in raspuns.
    Scopul testului: confirma ca endpoint-ul de creare persista corect un dispozitiv nou.
    """
    # Trimitem o cerere POST cu datele unui dispozitiv LED de tip IR-RGB
    resp = test_client.post(
        "/api/devices/",
        json={
            "name": "LED Living",          # numele dispozitivului care va fi creat
            "device_type": "ir_rgb",       # tipul dispozitivului — bec RGB controlat IR
            "room": "Living",              # camera in care se afla dispozitivul
            "mqtt_topic": "home/living/led",  # topic MQTT asociat dispozitivului
        },
        headers=auth_headers(test_user["token"]),  # autentificam cererea cu tokenul utilizatorului de test
    )

    # Verificam ca serverul a raspuns cu codul 201 Created (creare reusita)
    assert resp.status_code == 201

    # Extragem corpul JSON al raspunsului pentru verificari detaliate
    data = resp.json()

    # Verificam ca numele dispozitivului salvat coincide cu cel trimis
    assert data["name"] == "LED Living"

    # Verificam ca tipul dispozitivului este cel specificat in cerere
    assert data["device_type"] == "ir_rgb"

    # Verificam ca owner_id din raspuns corespunde utilizatorului autentificat
    assert data["owner_id"] == test_user["id"]


def test_create_wol_without_mac(test_client, test_user):
    """
    Verifica ca POST /api/devices/ cu device_type='wol' fara mac_address returneaza 400.
    Un dispozitiv Wake-on-LAN fara adresa MAC este invalid — serverul trebuie sa respinga cererea.
    Scopul testului: confirma ca validarea campurilor obligatorii functioneaza corect.
    """
    # Trimitem o cerere POST pentru un dispozitiv WoL fara camp mac_address
    resp = test_client.post(
        "/api/devices/",
        json={
            "name": "PC Birou",           # numele dispozitivului WoL
            "device_type": "wol",         # tipul WoL impune prezenta mac_address
            "room": "Birou",              # camera dispozitivului
            "mqtt_topic": "home/birou/pc",  # topic MQTT — prezent dar insuficient fara MAC
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul respinge cererea cu 400 Bad Request din cauza lipsei mac_address
    assert resp.status_code == 400


def test_list_devices(test_client, test_user, test_device):
    """
    Verifica ca GET /api/devices/ returneaza 200 si o lista ce contine test_device.
    Fixture-ul test_device creeaza automat un dispozitiv inainte de test.
    Scopul testului: confirma ca listing-ul dispozitivelor functioneaza si include datele perseverate.
    """
    # Trimitem o cerere GET pentru a obtine toate dispozitivele utilizatorului curent
    resp = test_client.get("/api/devices/", headers=auth_headers(test_user["token"]))

    # Verificam ca serverul raspunde cu 200 OK
    assert resp.status_code == 200

    # Extragem lista de dispozitive din raspuns
    data = resp.json()

    # Verificam ca raspunsul este o lista Python (nu un dict sau alt tip)
    assert isinstance(data, list)

    # Verificam ca lista contine cel putin un element (cel putin test_device)
    assert len(data) >= 1

    # Extragem lista de id-uri din raspuns pentru cautare rapida
    ids = [d["id"] for d in data]

    # Verificam ca id-ul dispozitivului creat de fixture apare in lista returnata
    assert test_device["id"] in ids


def test_list_devices_filter_room(test_client, test_user, test_device):
    """
    Verifica ca GET /api/devices/?room=Living returneaza doar dispozitivele din camera Living.
    Cream un al doilea dispozitiv in camera Dormitor pentru a valida izolarea filtrului.
    Scopul testului: confirma ca parametrul de interogare 'room' filtreaza corect rezultatele.
    """
    # Adaugam un dispozitiv intr-o alta camera pentru a testa ca filtrul il exclude
    test_client.post(
        "/api/devices/",
        json={
            "name": "Aer Conditionat",    # dispozitiv din alta camera decat Living
            "device_type": "ir_ac",       # tip aer conditionat controlat IR
            "room": "Dormitor",           # camera Dormitor — trebuie exclusa din filtrul pe Living
            "mqtt_topic": "home/dormitor/ac",  # topic MQTT al dispozitivului din dormitor
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET cu filtrul room=Living pentru a obtine doar dispozitivele din Living
    resp = test_client.get(
        "/api/devices/?room=Living",
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK
    assert resp.status_code == 200

    # Extragem lista filtrata de dispozitive
    data = resp.json()

    # Verificam ca lista filtrata nu este goala (test_device este in Living)
    assert len(data) >= 1

    # Verificam ca absolut toate dispozitivele returnate apartin camerei Living
    assert all(d["room"] == "Living" for d in data)


def test_get_device(test_client, test_user, test_device):
    """
    Verifica ca GET /api/devices/{id} returneaza 200 si datele corecte ale dispozitivului.
    Folosim id-ul din fixture-ul test_device pentru a accesa un dispozitiv existent.
    Scopul testului: confirma ca endpoint-ul de detaliu returneaza campurile corecte.
    """
    # Trimitem o cerere GET pentru dispozitivul specific identificat prin id
    resp = test_client.get(
        f"/api/devices/{test_device['id']}",   # id-ul din fixture-ul test_device
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (dispozitivul a fost gasit)
    assert resp.status_code == 200

    # Extragem datele dispozitivului din raspuns
    data = resp.json()

    # Verificam ca id-ul din raspuns coincide cu cel al dispozitivului solicitat
    assert data["id"] == test_device["id"]

    # Verificam ca numele din raspuns coincide cu cel stocat in fixture
    assert data["name"] == test_device["name"]


def test_get_device_not_found(test_client, test_user):
    """
    Verifica ca GET /api/devices/999 returneaza 404 Not Found pentru un id inexistent.
    ID-ul 999 nu exista in baza de date de test izolata.
    Scopul testului: confirma ca serverul gestioneaza corect accesul la resurse inexistente.
    """
    # Trimitem o cerere GET cu un id care nu exista in baza de date de test
    resp = test_client.get(
        "/api/devices/999",                        # id 999 este garantat absent in DB de test
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 404 Not Found
    assert resp.status_code == 404


def test_update_device(test_client, test_user, test_device):
    """
    Verifica ca PUT /api/devices/{id} cu un name nou returneaza 200 si name actualizat.
    Trimitem doar campul 'name' pentru a valida actualizarea partiala a dispozitivului.
    Scopul testului: confirma ca endpoint-ul de actualizare modifica corect datele in DB.
    """
    # Trimitem o cerere PUT cu un nou nume pentru dispozitivul existent
    resp = test_client.put(
        f"/api/devices/{test_device['id']}",       # id-ul dispozitivului de actualizat
        json={"name": "Bec Test Redenumit"},        # noul nume trimis in corpul cererii
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (actualizare reusita)
    assert resp.status_code == 200

    # Extragem datele actualizate din raspuns
    data = resp.json()

    # Verificam ca numele din raspuns reflecta noua valoare trimisa
    assert data["name"] == "Bec Test Redenumit"

    # Verificam ca id-ul dispozitivului nu s-a schimbat in urma actualizarii
    assert data["id"] == test_device["id"]


def test_delete_device(test_client, test_user, test_device):
    """
    Verifica ca DELETE /api/devices/{id} returneaza 200, iar un GET ulterior returneaza 404.
    Dupa stergere, dispozitivul nu mai trebuie sa existe in baza de date.
    Scopul testului: confirma ca stergerea este persistenta si resursele sunt eliminate corect.
    """
    # Trimitem o cerere DELETE pentru a sterge dispozitivul creat de fixture
    resp = test_client.delete(
        f"/api/devices/{test_device['id']}",       # id-ul dispozitivului de sters
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (stergere reusita)
    assert resp.status_code == 200

    # Trimitem o cerere GET pentru a confirma ca dispozitivul nu mai exista
    resp2 = test_client.get(
        f"/api/devices/{test_device['id']}",       # acelasi id dupa stergere
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 404 Not Found — dispozitivul a fost eliminat
    assert resp2.status_code == 404

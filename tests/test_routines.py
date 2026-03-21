"""
Teste rutine — CRUD manual, generare date ML, detectare tipare, toggle.
Rutinele sunt automatizari planificate ce se executa la ore si zile configurate.
Testele ML genereaza date sintetice pentru ca algoritmul DBSCAN sa aiba suficient
input fara sa depinda de date reale acumulate in timp.
Fixture-urile test_client, test_user si test_device sunt definite in conftest.py.
"""
from tests.conftest import auth_headers


def test_create_routine(test_client, test_user, test_device):
    """
    Verifica ca POST /api/routines/ cu date valide returneaza 201 Created.
    Campurile name, trigger_time, days_of_week si device_id trebuie sa fie corecte in raspuns.
    Scopul testului: confirma ca o rutina noua este creata si persistata corect in DB.
    """
    # Trimitem o cerere POST cu datele complete ale unei rutine de seara pentru bec
    resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Seara - Bec Off",         # numele rutinei — descriptiv pentru utilizator
            "device_id": test_device["id"],    # id-ul dispozitivului pe care se aplica rutina
            "action": "power",                 # actiunea de executat la declanasare
            "value": "off",                    # valoarea actiunii — stinge becul
            "trigger_time": "22:00",           # ora de declansare a rutinei
            "days_of_week": "1,2,3,4,5",       # zilele active — luni pana vineri
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 201 Created (rutina a fost creata)
    assert resp.status_code == 201

    # Extragem datele rutinei create din raspuns
    data = resp.json()

    # Verificam ca numele rutinei salvate corespunde cu cel trimis
    assert data["name"] == "Seara - Bec Off"

    # Verificam ca ora de declansare este salvata corect
    assert data["trigger_time"] == "22:00"

    # Verificam ca zilele active sunt salvate corect ca sir de caractere
    assert data["days_of_week"] == "1,2,3,4,5"

    # Verificam ca rutina este asociata dispozitivului corect
    assert data["device_id"] == test_device["id"]


def test_list_routines(test_client, test_user, test_device):
    """
    Verifica ca GET /api/routines/ returneaza 200 si o lista de rutine.
    Cream o rutina inainte de apelul GET pentru a garanta ca lista nu este goala.
    Scopul testului: confirma ca listing-ul rutinelor functioneaza si include rutinele perseverate.
    """
    # Cream o rutina de dimineata inainte de a apela endpoint-ul de listing
    test_client.post(
        "/api/routines/",
        json={
            "name": "Dimineata - Bec On",      # rutina de dimineata pentru aprindere bec
            "device_id": test_device["id"],    # dispozitivul tinta
            "action": "power",                 # actiunea de executat
            "value": "on",                     # aprinde becul la ora configurata
            "trigger_time": "07:00",           # ora de dimineata la care se executa rutina
            "days_of_week": "1,2,3,4,5",       # activa in zilele lucratoare
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET pentru a obtine toate rutinele utilizatorului curent
    resp = test_client.get("/api/routines/", headers=auth_headers(test_user["token"]))

    # Verificam ca serverul raspunde cu 200 OK
    assert resp.status_code == 200

    # Extragem lista de rutine din raspuns
    data = resp.json()

    # Verificam ca raspunsul este o lista Python (nu un dict sau alt tip)
    assert isinstance(data, list)

    # Verificam ca lista contine cel putin rutina creata anterior
    assert len(data) >= 1


def test_generate_test_data(test_client, test_user, test_device):
    """
    Verifica ca POST /api/routines/generate-test-data returneaza 200 si count > 0.
    Endpoint-ul genereaza comenzi sintetice in DB pentru a alimenta algoritmul ML.
    Scopul testului: confirma ca generarea de date de antrenament functioneaza si produce intrari reale.
    """
    # Trimitem o cerere POST pentru a genera comenzi sintetice pentru dispozitivul de test
    resp = test_client.post(
        f"/api/routines/generate-test-data?device_id={test_device['id']}",  # device_id ca parametru query
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (generarea a reusit)
    assert resp.status_code == 200

    # Extragem datele din raspuns pentru a verifica numarul de comenzi generate
    data = resp.json()

    # Verificam ca raspunsul contine campul 'count' care indica numarul de comenzi create
    assert "count" in data

    # Verificam ca cel putin o comanda sintetica a fost generata in DB
    assert data["count"] > 0


def test_detect_routines(test_client, test_user, test_device):
    """
    Verifica ca GET /api/routines/detect returneaza 200 si detecteaza cel putin o rutina.
    Algoritmul DBSCAN analizeaza comenzile din DB si grupeaza tiparele repetitive.
    Generam date sintetice in prealabil — 3 tipare pe 30 de zile — pentru a garanta detectia.
    Scopul testului: confirma ca serviciul ML functioneaza end-to-end si salveaza rutinele detectate.
    """
    # Generam date sintetice inainte de detectie pentru a alimenta algoritmul cu suficiente intrari
    test_client.post(
        f"/api/routines/generate-test-data?device_id={test_device['id']}",  # generam 30 zile de tipare
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Trimitem o cerere GET pentru a declansa algoritmul de detectie a rutinelor
    resp = test_client.get(
        "/api/routines/detect",
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (detectia a rulat fara erori)
    assert resp.status_code == 200

    # Extragem rezultatele detectiei din raspuns
    data = resp.json()

    # Verificam ca raspunsul contine campul 'routines_detected' — numarul de rutine gasite
    assert "routines_detected" in data

    # Verificam ca raspunsul contine campul 'routines_saved' — numarul de rutine persistate in DB
    assert "routines_saved" in data

    # Verificam ca raspunsul contine campul 'data' — detaliile rutinelor detectate
    assert "data" in data

    # Cu 30 de zile de date sintetice cu 3 tipare fixe, DBSCAN trebuie sa gaseasca cel putin o rutina
    assert data["routines_detected"] > 0


def test_toggle_routine(test_client, test_user, test_device):
    """
    Verifica ca PUT /api/routines/{id}/toggle schimba campul is_active al rutinei.
    Cream o rutina, citim starea initiala si o inversam printr-un apel PUT.
    Scopul testului: confirma ca mecanismul de activare/dezactivare a rutinelor functioneaza corect.
    """
    # Cream o rutina noua pentru a o folosi in testul de toggle — este activa implicit la creare
    create_resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Test Toggle",             # numele rutinei de test pentru toggle
            "device_id": test_device["id"],    # dispozitivul asociat rutinei
            "action": "power",                 # actiunea rutinei
            "value": "on",                     # valoarea actiunii
            "trigger_time": "08:00",           # ora de declansare
            "days_of_week": "1,2,3",           # activa luni, marti, miercuri
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca rutina a fost creata cu succes inainte de a incerca toggle-ul
    assert create_resp.status_code == 201

    # Extragem id-ul rutinei pentru a-l folosi in cererea de toggle
    routine_id = create_resp.json()["id"]

    # Citim starea initiala is_active pentru a putea verifica inversarea
    initial_state = create_resp.json()["is_active"]

    # Trimitem o cerere PUT pentru a inversa starea activa a rutinei
    resp = test_client.put(
        f"/api/routines/{routine_id}/toggle",      # endpoint-ul de toggle cu id-ul rutinei
        json={"is_active": not initial_state},     # trimitem starea inversata fata de cea initiala
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (toggle reusit)
    assert resp.status_code == 200

    # Verificam ca is_active din raspuns este exact opusul starii initiale
    assert resp.json()["is_active"] == (not initial_state)


def test_delete_routine(test_client, test_user, test_device):
    """
    Verifica ca DELETE /api/routines/{id} returneaza 200 si rutina dispare din listing.
    Dupa stergere, id-ul rutinei nu trebuie sa mai apara in lista returnata de GET /routines/.
    Scopul testului: confirma ca stergerea rutinelor este persistenta si se reflecta in listing.
    """
    # Cream o rutina dedicata testului de stergere
    create_resp = test_client.post(
        "/api/routines/",
        json={
            "name": "Rutina de Sters",         # rutina creata exclusiv pentru a fi stearsa
            "device_id": test_device["id"],    # dispozitivul asociat
            "action": "power",                 # actiunea rutinei
            "value": "off",                    # valoarea actiunii — stinge dispozitivul
            "trigger_time": "23:59",           # ora de declansare — tarziu in noapte
            "days_of_week": "7",               # activa doar duminica
        },
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Extragem id-ul rutinei create pentru a o putea sterge si verifica ulterior
    routine_id = create_resp.json()["id"]

    # Trimitem o cerere DELETE pentru a sterge rutina creata anterior
    resp = test_client.delete(
        f"/api/routines/{routine_id}",             # endpoint-ul de stergere cu id-ul rutinei
        headers=auth_headers(test_user["token"]),  # cerere autentificata
    )

    # Verificam ca serverul raspunde cu 200 OK (stergerea a reusit)
    assert resp.status_code == 200

    # Trimitem o cerere GET pentru a obtine lista curenta de rutine dupa stergere
    listing = test_client.get("/api/routines/", headers=auth_headers(test_user["token"]))

    # Extragem lista de id-uri din raspuns pentru cautare rapida
    ids = [r["id"] for r in listing.json()]

    # Verificam ca id-ul rutinei sterse nu mai apare in lista curenta
    assert routine_id not in ids

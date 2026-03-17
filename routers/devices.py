# Router pentru gestionarea dispozitivelor smart home.
# Expune endpoint-uri REST CRUD sub prefixul /devices.
# Toate operatiile sunt protejate — necesita autentificare JWT.
# Fiecare utilizator poate accesa si modifica doar propriile dispozitive.

import asyncio  # pentru asyncio.sleep in endpoint-urile bulk
import json  # Folosit pentru serializarea/deserializarea codurilor IR (dict <-> string JSON)
from typing import List, Optional  # Tipuri pentru anotarile de tip ale parametrilor

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Importam modelul ORM Device, modelul User, Command si functia de sesiune a bazei de date
from database.db import Command, Device, User, get_db

# Importam schemele Pydantic pentru validarea datelor de intrare si formatarea raspunsurilor
from models.schemas import (
    DeviceCreate,    # Schema pentru crearea unui dispozitiv nou (campuri obligatorii si optionale)
    DeviceResponse,  # Schema pentru raspunsul cu datele unui dispozitiv
    DeviceUpdate,    # Schema pentru actualizarea unui dispozitiv (toate campurile optionale)
)

# Importam dependenta pentru autentificare — extrage userul din token-ul JWT
from services.auth_service import get_current_user

# Importam dictionarul cu actiunile IR suportate per tip de dispozitiv
from utils.constants import SUPPORTED_IR_ACTIONS

# Importam exceptiile personalizate pentru erori specifice domeniului
from utils.exceptions import DeviceNotFoundException, InvalidMacAddressException

# Importam functia de validare a adreselor MAC
from utils.helpers import validate_mac_address

# Importam serviciul MQTT pentru comenzile bulk (all-off, away-mode)
from services.mqtt_service import mqtt_service

# Importam notificarile pentru comenzile bulk
from services.notification_service import notify_device_command

# Instantiem router-ul cu prefixul /devices si tag-ul pentru gruparea in Swagger UI
router = APIRouter(prefix="/devices", tags=["Dispozitive"])


def _get_owned_device(device_id: int, current_user: User, db: Session) -> Device:
    """
    Functie helper interna: cauta dispozitivul si verifica ca apartine utilizatorului curent.

    Interogheaza baza de date filtrând simultan dupa device_id si owner_id pentru a preveni
    accesul neautorizat la dispozitivele altor utilizatori (security by design).

    Parametri:
        device_id:    ID-ul numeric al dispozitivului cautat in baza de date
        current_user: Obiectul ORM al utilizatorului autentificat curent (din token JWT)
        db:           Sesiunea SQLAlchemy activa pentru interogarea bazei de date

    Returneaza:
        Obiectul ORM Device daca exista si apartine utilizatorului curent

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
    """
    # Filtram dupa ambele conditii simultan: id-ul dispozitivului SI owner-ul
    # Daca userul incearca sa acceseze un dispozitiv al altcuiva, primeste 404 (nu 403)
    # Comportamentul de 404 in loc de 403 evita scurgerea de informatii despre alte dispozitive
    device = db.query(Device).filter(
        Device.id == device_id,              # Conditie: dispozitivul cu id-ul specificat
        Device.owner_id == current_user.id,  # Conditie: dispozitivul apartine userului curent
    ).first()  # Returneaza primul rezultat sau None daca nu exista

    # Daca nu am gasit niciun dispozitiv care satisface ambele conditii, aruncam 404
    if not device:
        raise DeviceNotFoundException()  # HTTP 404 Not Found cu mesaj predefinit

    return device  # Returnam dispozitivul gasit si verificat


@router.get("/", response_model=List[DeviceResponse])
def list_devices(
    room: Optional[str] = None,                      # Filtru optional dupa numele camerei
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Returneaza toate dispozitivele utilizatorului curent, optional filtrate dupa camera.

    Daca parametrul 'room' este furnizat in query string, rezultatele sunt filtrate
    pentru a include doar dispozitivele din camera respectiva.

    Parametri:
        room:         Numele camerei pentru filtrare (optional, query param)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Lista de DeviceResponse cu toate dispozitivele (filtrate sau nefiltrate)
    """
    # Construim interogarea de baza — filtram intotdeauna dupa owner_id pentru securitate
    query = db.query(Device).filter(Device.owner_id == current_user.id)

    # Aplicam filtrul dupa camera doar daca parametrul 'room' a fost furnizat in request
    if room:
        query = query.filter(Device.room == room)  # Filtru suplimentar dupa numele camerei

    # Executam interogarea si returnam toate rezultatele ca lista
    return query.all()  # Lista de obiecte ORM; FastAPI le serializeaza dupa schema DeviceResponse


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    date: DeviceCreate,                              # Datele dispozitivului nou validate de Pydantic
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Adauga un dispozitiv nou asociat utilizatorului curent.

    Pentru dispozitivele de tip 'wol' (Wake-on-LAN), adresa MAC este obligatorie
    si este validata inainte de creare. Codurile IR sunt stocate ca JSON string
    in coloana de tip Text din baza de date.

    Parametri:
        date:         Datele dispozitivului nou (name, device_type, room, mqtt_topic etc.)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        DeviceResponse cu datele dispozitivului nou creat (HTTP 201 Created)

    Arunca:
        HTTPException 400      - daca tipul este 'wol' dar lipseste adresa MAC
        InvalidMacAddressException - daca adresa MAC are un format invalid (HTTP 422)
    """
    # Validare speciala pentru dispozitivele de tip Wake-on-LAN
    # Aceste dispozitive necesita adresa MAC pentru a putea trimite magic packet-ul
    if date.device_type == "wol":
        # Verificam mai intai daca adresa MAC a fost furnizata (nu este None sau string gol)
        if not date.mac_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,  # 400 = date de intrare invalide
                detail="MAC address obligatoriu pentru WoL",  # Mesaj explicit pentru utilizator
            )
        # Validam formatul adresei MAC (ex: "AA:BB:CC:DD:EE:FF" sau "AA-BB-CC-DD-EE-FF")
        if not validate_mac_address(date.mac_address):
            raise InvalidMacAddressException()  # HTTP 422 cu mesaj predefinit pentru MAC invalid

    # Serializăm codurile IR din dict Python in JSON string pentru stocare in coloana Text
    # Daca nu exista coduri IR (None sau dict gol), stocam None in coloana
    ir_codes_str = json.dumps(date.ir_codes) if date.ir_codes else None  # JSON string sau None

    # Cream obiectul ORM pentru noul dispozitiv cu toate campurile furnizate
    device_nou = Device(
        name=date.name,               # Numele dispozitivului (ex: "Televizor Living")
        device_type=date.device_type, # Tipul dispozitivului (ex: "mqtt", "ir", "wol")
        room=date.room,               # Numele camerei in care se afla dispozitivul
        mqtt_topic=date.mqtt_topic,   # Topic-ul MQTT pentru comunicare (ex: "home/living/tv")
        mac_address=date.mac_address, # Adresa MAC pentru WoL (None pentru celelalte tipuri)
        ir_codes=ir_codes_str,        # Codurile IR serializate ca JSON string (sau None)
        owner_id=current_user.id,     # ID-ul utilizatorului proprietar al dispozitivului
    )

    # Persistam dispozitivul nou in baza de date
    db.add(device_nou)      # Marcam obiectul pentru inserare in baza de date
    db.commit()             # Executam tranzactia — INSERT efectiv in baza de date
    db.refresh(device_nou)  # Reincarcam din DB pentru a obtine id-ul si valorile generate

    # Returnam dispozitivul nou creat; FastAPI il serializeaza dupa schema DeviceResponse
    return device_nou


@router.get("/supported-actions")
def get_supported_actions():
    """
    Returneaza dictionarul cu actiunile IR suportate per tip de dispozitiv.

    Aceasta informatie provine din fisierul constants.py si este folosita de frontend
    pentru a afisa butoanele corecte de control pentru fiecare tip de dispozitiv IR.
    Endpoint public in cadrul routerului (nu necesita autentificare suplimentara,
    dar routerul principal poate aplica middleware global).

    Returneaza:
        Dict mapat tip_dispozitiv -> lista de actiuni suportate (ex: {"tv": ["power", "vol+"]})
    """
    # Returnam direct dictionarul constant importat din utils/constants.py
    return SUPPORTED_IR_ACTIONS  # Dict cu actiunile IR suportate per tip de dispozitiv


@router.post("/all-off")
async def all_off(
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Trimite comanda power OFF tuturor dispozitivelor controlabile ale utilizatorului.

    Itereaza secvential toate dispozitivele userului si trimite power OFF
    prin canalul corespunzator tipului (IR sau relay).
    Dispozitivele de tip 'wol' sunt sarite — nu pot fi oprite prin magic packet.
    Delay de 0.3s intre comenzi consecutive pentru a nu satura ESP32-ul.
    Fiecare comanda este inregistrata in DB si genereaza o notificare.

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict {"status": "ok", "devices_turned_off": int} cu numarul de dispozitive oprite
    """
    # Preluam toate dispozitivele apartinand utilizatorului curent
    devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
    count = 0  # numarul de dispozitive carora li s-a trimis comanda de oprire

    # Iteram fiecare dispozitiv si trimitem comanda power OFF
    for i, device in enumerate(devices):
        # Asteptam 0.3s incepand cu al doilea dispozitiv pentru a evita supraaglomerarea ESP32
        if i > 0:
            await asyncio.sleep(0.3)  # delay non-blocking intre comenzi consecutive

        # Trimitem comanda power OFF prin canalul corespunzator tipului de dispozitiv
        if device.device_type in ("ir_tv", "ir_ac", "ir_rgb"):
            # Dispozitive IR — trimitem pe topic-ul ESP32 IR Controller
            mqtt_service.publish_ir_command(device.name, device.device_type, "power", "off")
        elif device.device_type == "relay":
            # Dispozitive relay — trimitem pe topic-ul specific al releului
            mqtt_service.publish_relay_command(device.mqtt_topic, "power", "off")
        else:
            # wol si alte tipuri necunoscute nu pot fi oprite remote — sarim
            continue

        # Actualizam last_status al dispozitivului in obiectul ORM (va fi persistat la commit)
        device.last_status = "off"

        # Inregistram comanda in tabelul commands — critic pentru modulul ML
        cmd = Command(
            device_id=device.id,       # dispozitivul care a primit comanda
            user_id=current_user.id,   # utilizatorul care a initiat all-off
            action="power",            # actiunea executata
            value="off",               # valoarea trimisa
            source="app",              # sursa: initiata manual din aplicatie
        )
        db.add(cmd)  # adaugam comanda in sesiune (commit la final)

        # Cream notificare pentru utilizator despre oprirea acestui dispozitiv
        notify_device_command(db, current_user.id, device.name, "power", "off")

        count += 1  # incrementam contorul de dispozitive oprite cu succes

    # Comitem toate comenzile, actualizarile last_status si notificarile intr-o singura tranzactie
    db.commit()

    # Returnam confirmarea cu numarul de dispozitive oprite
    return {"status": "ok", "devices_turned_off": count}


@router.post("/away-mode")
async def away_mode(
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Activeaza modul Away — pregateste locuinta pentru plecare.

    Comportament per tip de dispozitiv:
      - ir_rgb : trimite culoarea ROSIE ca semnal vizual de alarma activa
      - ir_tv  : trimite power OFF
      - ir_ac  : trimite power OFF
      - relay  : trimite power OFF
      - wol    : ignorat (nu poate fi oprit remote)

    Delay de 0.3s intre comenzi consecutive pentru a nu satura ESP32-ul.
    Fiecare comanda este inregistrata in DB si genereaza o notificare.

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict {"status": "ok", "rgb_count": int, "off_count": int}
    """
    # Preluam toate dispozitivele apartinand utilizatorului curent
    devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
    rgb_count = 0   # numarul de becuri RGB care au primit culoarea rosie
    off_count = 0   # numarul de dispozitive care au primit power OFF
    processed = 0   # contor pentru dispozitivele efectiv procesate (pentru delay)

    # Iteram fiecare dispozitiv si trimitem comanda corespunzatoare tipului sau
    for device in devices:
        # Asteptam 0.3s incepand cu al doilea dispozitiv procesat pentru a evita supraaglomerarea
        if processed > 0:
            await asyncio.sleep(0.3)  # delay non-blocking intre comenzi consecutive

        if device.device_type == "ir_rgb":
            # Becuri RGB — trimitem culoarea rosie ca indicator vizual de alarma activa
            mqtt_service.publish_ir_command(device.name, device.device_type, "color", "red")
            device.last_status = "red"  # actualizam starea cunoscuta a becului

            # Inregistram comanda de culoare in istoricul ML
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="color",   # actiunea de schimbare culoare
                value="red",      # culoarea rosie pentru alarma
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "color", "red")
            rgb_count += 1  # incrementam contorul de becuri RGB procesate

        elif device.device_type in ("ir_tv", "ir_ac"):
            # Televizoare si aparate de aer conditionat IR — trimitem power OFF
            mqtt_service.publish_ir_command(device.name, device.device_type, "power", "off")
            device.last_status = "off"

            # Inregistram comanda de oprire in istoricul ML
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="power",
                value="off",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "power", "off")
            off_count += 1  # incrementam contorul de dispozitive oprite

        elif device.device_type == "relay":
            # Prize si intrerupatoare relay — trimitem power OFF pe topic-ul specific
            mqtt_service.publish_relay_command(device.mqtt_topic, "power", "off")
            device.last_status = "off"

            # Inregistram comanda de oprire in istoricul ML
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="power",
                value="off",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "power", "off")
            off_count += 1  # incrementam contorul de dispozitive oprite

        else:
            # wol si alte tipuri necunoscute — sarim fara a incrementa processed
            continue

        processed += 1  # incrementam doar pentru dispozitivele efectiv procesate (pentru delay)

    # Comitem toate comenzile, actualizarile last_status si notificarile intr-o singura tranzactie
    db.commit()

    # Returnam confirmarea cu numarul de dispozitive procesate per categorie
    return {"status": "ok", "rgb_count": rgb_count, "off_count": off_count}


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: int,                                  # ID-ul dispozitivului din path parameter
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Returneaza detaliile unui dispozitiv specific daca apartine utilizatorului curent.

    Verifica atat existenta dispozitivului cat si ownership-ul prin functia helper.
    Daca dispozitivul nu exista sau apartine altui utilizator, returneaza 404.

    Parametri:
        device_id:    ID-ul numeric al dispozitivului (din URL path)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        DeviceResponse cu toate detaliile dispozitivului solicitat

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
    """
    # Folosim helper-ul intern care verifica existenta si ownership-ul simultan
    return _get_owned_device(device_id, current_user, db)


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: int,                                  # ID-ul dispozitivului de actualizat (path param)
    date: DeviceUpdate,                              # Datele de actualizare (campuri optionale)
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Actualizeaza campurile unui dispozitiv existent.

    Suporta actualizare partiala (comportament PATCH-like): doar campurile trimise explicit
    in body-ul request-ului sunt modificate, restul raman neschimbate.
    Campul ir_codes este automat convertit din dict la JSON string daca este furnizat.

    Parametri:
        device_id:    ID-ul numeric al dispozitivului de actualizat (din URL path)
        date:         Datele de actualizare validate de Pydantic (toate campurile optionale)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        DeviceResponse cu datele actualizate ale dispozitivului

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
    """
    # Verificam ca dispozitivul exista si apartine utilizatorului curent
    device = _get_owned_device(device_id, current_user, db)

    # Extragem doar campurile furnizate explicit in request body
    # exclude_unset=True asigura actualizare partiala — campurile omise raman neschimbate
    campuri_actualizate = date.model_dump(exclude_unset=True)  # Dict cu campurile modificate

    # Tratam special campul ir_codes: daca a fost trimis ca dict, il convertim la JSON string
    # Baza de date stocheaza codurile IR ca Text (JSON string), nu ca obiect JSON nativ
    if "ir_codes" in campuri_actualizate and isinstance(campuri_actualizate["ir_codes"], dict):
        campuri_actualizate["ir_codes"] = json.dumps(campuri_actualizate["ir_codes"])  # Serializare

    # Aplicam fiecare camp actualizat direct pe obiectul ORM folosind setattr
    for camp, valoare in campuri_actualizate.items():
        setattr(device, camp, valoare)  # Actualizam atributul ORM cu noua valoare

    # Persistam toate modificarile in baza de date intr-o singura tranzactie
    db.commit()      # Executam UPDATE-ul efectiv
    db.refresh(device)  # Reincarcam din DB pentru valorile finale actualizate

    # Returnam dispozitivul actualizat; FastAPI il serializeaza dupa schema DeviceResponse
    return device


@router.delete("/{device_id}")
def delete_device(
    device_id: int,                                  # ID-ul dispozitivului de sters (path param)
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Sterge un dispozitiv si toate comenzile asociate (stergere in cascada).

    Cascade delete-ul este configurat la nivel de model ORM/baza de date,
    astfel toate comenzile (Command) legate de acest dispozitiv sunt sterse automat.

    Parametri:
        device_id:    ID-ul numeric al dispozitivului de sters (din URL path)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict cu mesaj de confirmare a stergerii

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
    """
    # Verificam ca dispozitivul exista si apartine utilizatorului curent inainte de stergere
    device = _get_owned_device(device_id, current_user, db)

    # Stergem dispozitivul din baza de date
    # Cascade delete configurat in ORM va sterge automat si comenzile asociate
    db.delete(device)  # Marcam dispozitivul pentru stergere (si cascade pentru comenzi)
    db.commit()        # Executam DELETE-ul efectiv in baza de date

    # Returnam mesaj de confirmare ca stergerea s-a efectuat cu succes
    return {"message": "Dispozitivul a fost sters"}

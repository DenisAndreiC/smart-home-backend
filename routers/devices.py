# Router pentru gestionarea dispozitivelor smart home.
# Expune endpoint-uri REST CRUD sub prefixul /devices.
# Toate operatiile sunt protejate — necesita autentificare JWT.
# Fiecare utilizator poate accesa si modifica doar propriile dispozitive.

import asyncio   # asyncio.sleep for non-blocking delay between bulk commands
import json      # JSON serialisation/deserialisation of IR codes stored as Text in DB
import logging   # structured logging for bulk-command debug output
from typing import List, Optional

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

# Helper to check whether a device is currently on, based on last_status
from services.device_command_service import is_device_on

# Notification helper — creates in-app notification records for each bulk command
from services.notification_service import notify_device_command

# Module-level logger — visible in Docker logs via `docker-compose logs backend`
logger = logging.getLogger(__name__)

# Router prefix /devices — all routes resolve to /api/devices/...
# IMPORTANT: static routes (/all-off, /away-mode, /supported-actions) are defined
# BEFORE the parameterised route (/{device_id}) so FastAPI matches them first.
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

    # Create the ORM object for the new device with all supplied fields
    device_nou = Device(
        name=date.name,
        device_type=date.device_type,
        room=date.room,
        room_id=date.room_id,
        mqtt_topic=date.mqtt_topic,
        mac_address=date.mac_address,
        ir_codes=ir_codes_str,
        # ir_remote_type is only meaningful for ir_rgb devices ("44" or "24")
        ir_remote_type=date.ir_remote_type,
        owner_id=current_user.id,
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
    db: Session = Depends(get_db),                  # SQLAlchemy session injected by FastAPI
    current_user: User = Depends(get_current_user), # authenticated user injected from JWT
):
    """
    Send a power-OFF command to every controllable device owned by the current user.

    Iterates devices sequentially and dispatches the correct MQTT call per device type.
    WoL devices are skipped — there is no standard way to power them off remotely.
    A 0.3 s delay is inserted between consecutive commands to avoid flooding the ESP32.
    Each command is recorded in the commands table and triggers an in-app notification.

    Args:
        db:           SQLAlchemy session (shared with get_current_user via FastAPI cache).
        current_user: ORM User object injected from the JWT token.

    Returns:
        {"status": "ok", "devices_turned_off": <count>}
    """
    # Fetch all devices belonging to the current user
    devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
    count = 0  # number of devices that actually received a power-OFF command

    logger.info("all-off triggered by user_id=%d for %d device(s)", current_user.id, len(devices))

    for i, device in enumerate(devices):
        # Wait 0.3 s before each command after the first to avoid flooding the ESP32
        if i > 0:
            await asyncio.sleep(0.3)  # non-blocking delay between commands

        # Dispatch through the channel matching the device type
        if device.device_type in ("ir_tv", "ir_rgb"):
            # These IR remotes only expose a single toggle "power" code (no discrete
            # off) — sending it blindly to an already-off device would turn it ON.
            if not is_device_on(device):
                logger.debug("all-off skipping already-off device='%s'", device.name)
                device.last_status = "off"  # normalise unknown/off state
                continue
            tv_brand = None
            if device.device_type == "ir_tv" and device.ir_codes:
                try:
                    tv_brand = json.loads(device.ir_codes).get("brand")
                except Exception:
                    pass
            logger.info(
                "all-off IR toggle-off -> device='%s' type=%s brand=%s", device.name, device.device_type, tv_brand
            )
            mqtt_service.publish_ir_command(
                device.name, device.device_type, "power", "off",
                ir_remote_type=device.ir_remote_type,
                brand=tv_brand,
            )

        elif device.device_type == "ir_ac":
            # AC has a discrete power_off IR code - always safe to send
            logger.info("all-off IR AC power_off -> device='%s'", device.name)
            mqtt_service.publish_ir_command(device.name, device.device_type, "power", "off")

        elif device.device_type == "relay":
            # Relay devices: publish to the device-specific MQTT topic
            logger.info("all-off relay -> topic='%s' device='%s'", device.mqtt_topic, device.name)
            mqtt_service.publish_relay_command(device.mqtt_topic, "power", "off")

        else:
            # wol and unknown types cannot be powered off remotely — skip
            logger.debug("all-off skipping device='%s' type=%s", device.name, device.device_type)
            continue

        # Update the cached status on the ORM object (persisted in the commit below)
        device.last_status = "off"

        # Record the command in the commands table — used by the ML routine detector
        cmd = Command(
            device_id=device.id,
            user_id=current_user.id,
            action="power",
            value="off",
            source="app",  # manually initiated from the application
        )
        db.add(cmd)

        # Create an in-app notification so the user sees the action in the notifications list
        notify_device_command(db, current_user.id, device.name, "power", "off")

        count += 1

    # Single commit for all commands, last_status updates and notifications
    db.commit()

    logger.info("all-off done: %d device(s) turned off", count)
    return {"status": "ok", "devices_turned_off": count}


@router.post("/away-mode")
async def away_mode(
    db: Session = Depends(get_db),                  # SQLAlchemy session injected by FastAPI
    current_user: User = Depends(get_current_user), # authenticated user injected from JWT
):
    """
    Activate Away Mode — prepares the home for the user leaving.

    Per device type behaviour:
      - ir_rgb : send color RED as a visible alarm indicator
      - ir_tv  : send power OFF
      - ir_ac  : send power OFF
      - relay  : send power OFF
      - wol    : skipped (cannot be powered off remotely)

    A 0.3 s delay is inserted between processed devices to avoid flooding the ESP32.
    Each command is recorded in the commands table and triggers an in-app notification.

    Args:
        db:           SQLAlchemy session (shared with get_current_user via FastAPI cache).
        current_user: ORM User object injected from the JWT token.

    Returns:
        {"status": "ok", "rgb_count": <x>, "off_count": <y>}
    """
    devices = db.query(Device).filter(Device.owner_id == current_user.id).all()
    rgb_count = 0   # RGB bulbs that received the red-alert colour command
    off_count = 0   # devices that received a power-OFF command
    processed = 0   # counter of devices actually processed (used to gate the sleep)

    logger.info("away-mode triggered by user_id=%d for %d device(s)", current_user.id, len(devices))

    for device in devices:
        # Insert a 0.3 s gap before every device after the first one
        if processed > 0:
            await asyncio.sleep(0.3)

        if device.device_type == "ir_rgb":
            # RGB bulb: set colour to RED as a visual alarm indicator
            logger.info("away-mode RGB red -> device='%s'", device.name)
            mqtt_service.publish_ir_command(
                device.name, device.device_type, "color", "red",
                ir_remote_type=device.ir_remote_type,
            )
            device.last_status = "red"
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="color",
                value="red",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "color", "red")
            rgb_count += 1

        elif device.device_type == "ir_tv":
            # TV IR remote only has a single toggle "power" code (no discrete off) -
            # sending it blindly to an already-off TV would turn it ON.
            if not is_device_on(device):
                logger.debug("away-mode skipping already-off device='%s'", device.name)
                device.last_status = "off"  # normalise unknown/off state
                continue
            tv_brand = None
            if device.ir_codes:
                try:
                    tv_brand = json.loads(device.ir_codes).get("brand")
                except Exception:
                    pass
            logger.info("away-mode IR TV toggle-off -> device='%s' brand=%s", device.name, tv_brand)
            mqtt_service.publish_ir_command(device.name, device.device_type, "power", "off", brand=tv_brand)
            device.last_status = "off"
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="power",
                value="off",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "power", "off")
            off_count += 1

        elif device.device_type == "ir_ac":
            # AC has a discrete power_off IR code - always safe to send
            logger.info("away-mode IR AC power_off -> device='%s'", device.name)
            mqtt_service.publish_ir_command(device.name, device.device_type, "power", "off")
            device.last_status = "off"
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="power",
                value="off",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "power", "off")
            off_count += 1

        elif device.device_type == "relay":
            # Relay smart plug/switch: power off via the device-specific topic
            logger.info("away-mode relay off -> topic='%s' device='%s'", device.mqtt_topic, device.name)
            mqtt_service.publish_relay_command(device.mqtt_topic, "power", "off")
            device.last_status = "off"
            cmd = Command(
                device_id=device.id,
                user_id=current_user.id,
                action="power",
                value="off",
                source="app",
            )
            db.add(cmd)
            notify_device_command(db, current_user.id, device.name, "power", "off")
            off_count += 1

        else:
            # wol and unknown types: skip without incrementing processed
            logger.debug("away-mode skipping device='%s' type=%s", device.name, device.device_type)
            continue

        processed += 1  # only incremented for devices that were actually processed

    # Single commit for all commands, last_status updates and notifications
    db.commit()

    logger.info("away-mode done: rgb=%d off=%d", rgb_count, off_count)
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
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a device and all associated data for any device type.

    Manually removes SceneAction rows first (no cascade configured on that
    relation) then deletes the device — the ORM cascade will clean up
    the Command rows automatically.

    Args:
        device_id:    Numeric device ID from the URL path
        db:           SQLAlchemy session injected by FastAPI
        current_user: Authenticated user from JWT

    Returns:
        {"message": "Device deleted"}

    Raises:
        DeviceNotFoundException: HTTP 404 if device does not exist or belongs to another user
    """
    from database.db import SceneAction  # local import to avoid circular reference

    device = _get_owned_device(device_id, current_user, db)

    # SceneAction has no ORM cascade from Device, so delete those rows manually first
    db.query(SceneAction).filter(SceneAction.device_id == device_id).delete(
        synchronize_session=False
    )

    # Delete the device — the ORM cascade will remove associated Command rows
    db.delete(device)
    db.commit()

    return {"message": "Device deleted"}


@router.post("/{device_id}/configure")
def configure_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send the RGB remote-type configuration to the ESP32 IR Controller.

    Publishes: {"device": "config", "command": "set_rgb_type", "data": "<44|24>"}

    Only valid for ir_rgb devices that have ir_remote_type set.
    Call this once before the first RGB command (e.g. after app startup or
    when pairing a new RGB bulb) so the ESP32 loads the correct IR code set.

    Args:
        device_id:    Numeric device ID from the URL path
        db:           SQLAlchemy session injected by FastAPI
        current_user: Authenticated user from JWT

    Returns:
        {"message": "Config sent", "ir_remote_type": "<value>"}

    Raises:
        DeviceNotFoundException:  HTTP 404 if device does not exist or belongs to another user
        HTTPException 400:        if the device is not ir_rgb or has no ir_remote_type set
    """
    device = _get_owned_device(device_id, current_user, db)

    if device.device_type != "ir_rgb":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure endpoint is only supported for ir_rgb devices",
        )

    if not device.ir_remote_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device has no ir_remote_type set. Update the device first.",
        )

    mqtt_service.publish_rgb_config(device.ir_remote_type)
    logger.info(
        "RGB config sent for device='%s' ir_remote_type=%s",
        device.name, device.ir_remote_type,
    )

    return {"message": "Config sent", "ir_remote_type": device.ir_remote_type}

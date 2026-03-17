# Router pentru trimiterea si istoricul comenzilor catre dispozitive.
# Expune endpoint-uri REST sub prefixul /commands.
# Comenzile pot fi trimise prin MQTT (dispozitive IR/relay) sau Wake-on-LAN (PC-uri).
# Toate comenzile trimise sunt inregistrate in baza de date — CRITIC pentru modulul ML.
# Toate operatiile sunt protejate — necesita autentificare JWT.

from typing import List, Optional  # Tipuri pentru anotarile de tip ale parametrilor

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Importam modelele ORM (tabele din baza de date) si functia de sesiune
from database.db import Command, Device, User, get_db

# Importam schemele Pydantic pentru validarea datelor de intrare si formatarea raspunsurilor
from models.schemas import (
    CommandResponse,  # Schema pentru raspunsul cu datele unei comenzi
    CommandSend,      # Schema pentru trimiterea unei comenzi (device_id, action, value)
    WolRequest,       # Schema pentru cererea Wake-on-LAN (device_id)
)

# Importam dependenta pentru autentificare — extrage userul din token-ul JWT
from services.auth_service import get_current_user

# Importam singleton-ul serviciului MQTT pentru publicarea comenzilor pe broker
from services.mqtt_service import mqtt_service

# Importam functia de notificare pentru a alerta utilizatorul despre comenzi executate
from services.notification_service import notify_device_command

# Importam functia Wake-on-LAN pentru trezirea PC-urilor din standby
from services.wol_service import wake_device

# Importam constanta pentru limita maxima a istoricului de comenzi returnate
from utils.constants import MAX_COMMAND_HISTORY

# Importam exceptia personalizata pentru cazul in care dispozitivul nu este gasit
from utils.exceptions import DeviceNotFoundException

# Instantiem router-ul cu prefixul /commands si tag-ul pentru gruparea in Swagger UI
router = APIRouter(prefix="/commands", tags=["Comenzi"])


def _get_owned_device(device_id: int, current_user: User, db: Session) -> Device:
    """
    Functie helper interna: cauta dispozitivul si verifica ca apartine utilizatorului curent.

    Interogheaza baza de date filtrand simultan dupa device_id si owner_id pentru a preveni
    accesul neautorizat la dispozitivele altor utilizatori (security by design).
    Returneaza 404 in loc de 403 pentru a nu dezvalui existenta dispozitivului.

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
    # Comportamentul de 404 in loc de 403 evita scurgerea de informatii despre alte dispozitive
    device = db.query(Device).filter(
        Device.id == device_id,              # Conditie: dispozitivul cu id-ul specificat
        Device.owner_id == current_user.id,  # Conditie: dispozitivul apartine userului curent
    ).first()  # Returneaza primul rezultat sau None daca nu exista

    # Daca nu am gasit niciun dispozitiv care satisface ambele conditii, aruncam 404
    if not device:
        raise DeviceNotFoundException()  # HTTP 404 Not Found cu mesaj predefinit

    return device  # Returnam dispozitivul gasit si verificat


@router.post("/send", response_model=CommandResponse)
def send_command(
    date: CommandSend,                               # Datele comenzii validate de Pydantic
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Trimite o comanda la un dispozitiv prin MQTT sau Wake-on-LAN.

    Fluxul de executie:
    1. Verifica ca dispozitivul exista si apartine utilizatorului curent.
    2. Trimite comanda prin canalul potrivit (WoL pentru pc-uri, MQTT pentru restul).
    3. Inregistreaza comanda in baza de date — CRITIC pentru antrenarea modelului ML.
    4. Actualizeaza last_status al dispozitivului cu noua valoare a comenzii.
    5. Creeaza o notificare pentru utilizator.
    6. Returneaza detaliile comenzii inregistrate.

    Parametri:
        date:         Datele comenzii (device_id, action, value optional)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        CommandResponse cu toate detaliile comenzii inregistrate (inclusiv device_name)

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
    """
    # Verificam ca dispozitivul exista si apartine utilizatorului curent
    device = _get_owned_device(date.device_id, current_user, db)

    # Trimitem comanda prin canalul corespunzator tipului de dispozitiv
    if device.device_type == "wol":
        # Dispozitivele WoL (ex: PC-uri) primesc un magic packet UDP prin retea locala
        wake_device(device.mac_address)
    elif device.device_type in ("ir_tv", "ir_ac", "ir_rgb"):
        # IR devices — publish to the ESP32 IR Controller topic
        # Pass ir_remote_type so the RGB payload includes the "data" field
        mqtt_service.publish_ir_command(
            device.name, device.device_type, date.action, date.value,
            ir_remote_type=device.ir_remote_type,
        )
    elif device.device_type == "relay":
        # Dispozitive Relay — trimitem pe topic-ul specific relay-ului
        mqtt_service.publish_relay_command(device.mqtt_topic, date.action, date.value)
    else:
        # Fallback — folosim metoda veche pentru tipuri necunoscute
        mqtt_service.publish_command(device.mqtt_topic, date.action, date.value)

    # Inregistram comanda in baza de date — CRITIC pentru modulul ML de detectie rutine
    # Toate comenzile trimise (inclusiv cele automate) trebuie inregistrate pentru antrenare
    comanda = Command(
        device_id=device.id,       # ID-ul dispozitivului care a primit comanda
        user_id=current_user.id,   # ID-ul utilizatorului care a trimis comanda
        action=date.action,        # Actiunea executata (ex: "power", "volume_up", "set_temp")
        value=date.value,          # Valoarea asociata actiunii (ex: "on", "22", poate fi None)
        source="app",              # Sursa comenzii: "app" = initiata manual din aplicatie
    )
    db.add(comanda)  # Adaugam comanda in sesiunea SQLAlchemy pentru inserare

    # Actualizam ultimul status cunoscut al dispozitivului cu noua valoare trimisa
    # Aceasta informatie este folosita de frontend pentru a afisa starea curenta a dispozitivului
    device.last_status = date.value  # Setam last_status cu valoarea din comanda trimisa

    # Cream o notificare pentru utilizator despre comanda executata
    # Notificarea este stocata in DB si poate fi afisata in interfata aplicatiei
    notify_device_command(db, current_user.id, device.name, date.action, date.value)

    # Persistam comanda, actualizarea last_status si notificarea intr-o singura tranzactie
    db.commit()       # Executam toate INSERT-urile si UPDATE-urile intr-o singura tranzactie
    db.refresh(comanda)  # Reincarcam comanda din DB pentru a obtine timestamp-ul si id-ul generat

    # Construim si returnam schema de raspuns cu toate detaliile comenzii inregistrate
    return CommandResponse(
        id=comanda.id,              # ID-ul unic al comenzii generate in baza de date
        device_id=comanda.device_id,  # ID-ul dispozitivului care a primit comanda
        action=comanda.action,       # Actiunea executata (ex: "power")
        value=comanda.value,         # Valoarea asociata actiunii (ex: "on", poate fi None)
        source=comanda.source,       # Sursa comenzii ("app" in acest caz)
        timestamp=comanda.timestamp, # Marca de timp a executiei comenzii (generata de DB)
        device_name=device.name,     # Numele dispozitivului pentru afisare in UI
    )


@router.get("/history", response_model=List[CommandResponse])
def get_history(
    device_id: Optional[int] = None,                 # Filtru optional dupa ID-ul dispozitivului
    limit: int = MAX_COMMAND_HISTORY,                # Numarul maxim de comenzi returnate
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Returneaza istoricul comenzilor utilizatorului curent in ordine cronologica inversa.

    Limita implicita este MAX_COMMAND_HISTORY din constants.py.
    Optional, rezultatele pot fi filtrate pentru a include doar comenzile
    unui anumit dispozitiv prin parametrul de query 'device_id'.
    Istoricul este esential pentru auditul activitatii si pentru antrenarea modelului ML.

    Parametri:
        device_id:    ID-ul dispozitivului pentru filtrare (optional, query param)
        limit:        Numarul maxim de comenzi de returnat (default: MAX_COMMAND_HISTORY)
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Lista de CommandResponse ordonata descrescator dupa timestamp (cele mai recente primele)
    """
    # Construim interogarea cu JOIN intre Command si Device pentru a obtine si numele dispozitivului
    # Labelam Device.name ca 'device_name' pentru a fi accesibil in rezultatele tuple
    query = (
        db.query(Command, Device.name.label("device_name"))  # Selectam comanda si numele device-ului
        .join(Device, Command.device_id == Device.id)         # JOIN cu tabelul Device dupa device_id
        .filter(Command.user_id == current_user.id)           # Filtram doar comenzile userului curent
    )

    # Aplicam filtrul dupa device_id doar daca a fost furnizat in query string
    if device_id:
        query = query.filter(Command.device_id == device_id)  # Filtru optional dupa dispozitiv

    # Executam interogarea cu ordonare descrescatoare dupa timestamp si limitare la 'limit' rezultate
    # .desc() asigura ca cele mai recente comenzi apar primele in lista returnata
    rezultate = query.order_by(Command.timestamp.desc()).limit(limit).all()  # Lista de tuple (cmd, name)

    # Convertim fiecare tuple (Command, device_name) la schema CommandResponse
    return [
        CommandResponse(
            id=cmd.id,              # ID-ul unic al comenzii
            device_id=cmd.device_id,  # ID-ul dispozitivului care a primit comanda
            action=cmd.action,       # Actiunea executata
            value=cmd.value,         # Valoarea asociata actiunii (poate fi None)
            source=cmd.source,       # Sursa comenzii (ex: "app", "routine", "mqtt")
            timestamp=cmd.timestamp, # Marca de timp a executiei comenzii
            device_name=device_name, # Numele dispozitivului (din JOIN cu tabelul Device)
        )
        for cmd, device_name in rezultate  # Despachetam fiecare tuple din rezultatele interogarii
    ]


@router.post("/wol")
def wake_on_lan(
    date: WolRequest,                                # Datele cererii WoL validate de Pydantic
    db: Session = Depends(get_db),                   # Sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user),  # Utilizatorul autentificat curent din token JWT
):
    """
    Endpoint dedicat Wake-on-LAN: trimite magic packet si inregistreaza comanda in baza de date.

    Verifica ca dispozitivul este de tip 'wol' inainte de a trimite magic packet-ul.
    In caz de esec al trimiterii (adresa MAC invalida sau eroare de retea), returneaza 500.
    Comanda WoL este inregistrata in DB pentru tracking si istoricul activitatii.

    Parametri:
        date:         Datele cererii WoL (device_id) validate de Pydantic
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict cu mesaj de confirmare si adresa MAC la care s-a trimis magic packet-ul

    Arunca:
        DeviceNotFoundException - HTTP 404 daca dispozitivul nu exista sau nu apartine userului
        HTTPException 400       - daca dispozitivul nu este de tip Wake-on-LAN
        HTTPException 500       - daca trimiterea magic packet-ului a esuat
    """
    # Verificam ca dispozitivul exista si apartine utilizatorului curent
    device = _get_owned_device(date.device_id, current_user, db)

    # Verificam ca dispozitivul este efectiv de tip 'wol' inainte de a trimite magic packet
    # Nu putem trimite WoL la dispozitive MQTT sau IR — ar fi o operatie invalida
    if device.device_type != "wol":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,         # 400 = cerere invalida
            detail="Dispozitivul nu este de tip Wake-on-LAN",  # Mesaj explicit pentru client
        )

    # Trimitem magic packet la adresa MAC a dispozitivului si verificam rezultatul
    # wake_device returneaza True la succes, False la esec (adresa MAC invalida, eroare retea)
    succes = wake_device(device.mac_address)  # True daca pachetul UDP a fost trimis cu succes

    # Daca trimiterea a esuat, returnam eroare 500 cu detalii despre cauza posibila
    if not succes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,                   # 500 = eroare server
            detail="Trimiterea magic packet a esuat -- verificati adresa MAC",   # Sugestie de debugging
        )

    # Inregistram comanda WoL in baza de date pentru tracking si istoricul activitatii
    # Aceasta inregistrare este importanta si pentru modulul ML care analizeaza tipare de utilizare
    comanda = Command(
        device_id=device.id,      # ID-ul dispozitivului care a primit magic packet-ul
        user_id=current_user.id,  # ID-ul utilizatorului care a initiat comanda WoL
        action="wol",             # Actiunea standard pentru Wake-on-LAN
        value="magic_packet",     # Valoarea fixa — indica tipul de pachet trimis
        source="app",             # Sursa comenzii: "app" = initiata manual din aplicatie
    )
    db.add(comanda)  # Adaugam comanda in sesiunea SQLAlchemy pentru inserare

    # Cream o notificare pentru utilizator despre comanda WoL executata
    # Valoarea None indica ca aceasta notificare nu are o valoare numerica asociata
    notify_device_command(db, current_user.id, device.name, "wake", None)  # Notificare "wake"

    # Persistam comanda si notificarea intr-o singura tranzactie
    db.commit()  # Executam INSERT-ul pentru comanda si notificare

    # Returnam mesaj de confirmare cu adresa MAC folosita pentru magic packet
    return {
        "message": "Magic packet trimis",         # Confirmare ca pachetul a fost trimis cu succes
        "mac_address": device.mac_address,         # Adresa MAC la care s-a trimis magic packet-ul
    }


@router.post("/set-brand")
def set_tv_brand(
    brand: str,
    current_user: User = Depends(get_current_user),
):
    """
    Schimba brand-ul TV pe ESP32 IR Controller.
    Branduri suportate: philips, samsung, lg, sony, panasonic, nec
    """
    valid_brands = ["philips", "samsung", "lg", "sony", "panasonic", "nec"]
    if brand.lower() not in valid_brands:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Brand invalid. Branduri suportate: {', '.join(valid_brands)}",
        )
    mqtt_service.publish_brand_config(brand)
    return {"message": f"Brand TV schimbat la {brand}", "brand": brand}

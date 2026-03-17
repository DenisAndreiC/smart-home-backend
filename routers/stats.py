# Router pentru statistici si analitice Smart Home.
# Expune endpoint-uri REST sub prefixul /stats.
# Furnizeaza informatii despre consumul energetic zilnic si numarul de comenzi.
# Toate operatiile sunt protejate — necesita autentificare JWT.
# Consumul energetic este calculat din istoricul comenzilor power din tabelul commands.

from datetime import datetime, timezone  # pentru calculul intervalului zilnic (UTC)
from typing import Any, Dict, List       # tipuri generice pentru adnotarile de raspuns

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Importam modelele ORM necesare pentru interogarea bazei de date
from database.db import Command, Device, User, get_db

# Dependency de autentificare — extrage si valideaza utilizatorul din token-ul JWT
from services.auth_service import get_current_user

# Router cu prefix /stats — toate rutele devin /api/stats/...
router = APIRouter(prefix="/stats", tags=["Statistici"])

# Consumul electric estimat in kilowati (kW) per tip de dispozitiv.
# Valorile sunt aproximari tipice pentru categoria respectiva de dispozitive.
# ir_tv  = televizor (aprox. 100W)
# ir_ac  = aer conditionat (aprox. 1500W)
# ir_rgb = bec RGB IR (aprox. 10W)
# relay  = priza inteligenta / releu (aprox. 60W sarcina medie)
POWER_KW = {
    "ir_tv": 0.1,    # televizor — 100W
    "ir_ac": 1.5,    # aer conditionat — 1500W
    "ir_rgb": 0.01,  # bec RGB infrarosu — 10W
    "relay": 0.06,   # releu / priza inteligenta — 60W
}


@router.get("/commands-today")
def commands_today(
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Returneaza numarul total de comenzi trimise astazi de utilizatorul curent.

    'Astazi' este definit ca intervalul de la miezul noptii UTC pana in momentul curent.
    Numara toate comenzile indiferent de sursa (app, scene, rutine, ML).

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict {"count": int} cu numarul de comenzi din ziua curenta
    """
    # Obtinem momentul curent in UTC si calculam inceputul zilei (miezul noptii)
    now = datetime.now(timezone.utc)                                          # momentul curent UTC
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)    # miezul noptii UTC

    # Numaram comenzile utilizatorului din intervalul [start_of_day, acum]
    # .count() executa SELECT COUNT(*) eficient la nivel de baza de date
    count = (
        db.query(Command)
        .filter(
            Command.user_id == current_user.id,  # doar comenzile utilizatorului curent
            Command.timestamp >= start_of_day,   # doar comenzile din ziua curenta
        )
        .count()  # numarul de randuri care satisfac filtrele
    )

    # Returnam numarul de comenzi impachetat intr-un dictionar
    return {"count": count}


@router.get("/energy")
def energy_today(
    db: Session = Depends(get_db),                  # sesiunea SQLAlchemy injectata prin dependenta
    current_user: User = Depends(get_current_user), # utilizatorul autentificat din token JWT
):
    """
    Calculeaza consumul energetic estimat al utilizatorului pentru ziua curenta.

    Algoritmul pentru fiecare dispozitiv:
      1. Extrage comenzile 'power' din ziua curenta sortate cronologic
      2. Reconstituie intervalele ON/OFF prin parcurgerea secventiala a comenzilor
      3. Calculeaza durata totala in ore in care dispozitivul a fost pornit
      4. Inmulteste durata cu consumul in kW al tipului de dispozitiv

    Dispozitivele fara consum definit (ex: wol) sunt excluse din calcul.

    Parametri:
        db:           Sesiunea SQLAlchemy injectata automat prin dependenta get_db
        current_user: Utilizatorul autentificat extras din token-ul JWT

    Returneaza:
        Dict cu total_kwh (float) si per_device (lista cu detalii per dispozitiv)
    """
    # Obtinem momentul curent si inceputul zilei in UTC pentru filtrarea comenzilor
    now = datetime.now(timezone.utc)                                          # acum UTC
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)    # miezul noptii UTC

    # Preluam toate dispozitivele apartinand utilizatorului curent din baza de date
    devices = db.query(Device).filter(Device.owner_id == current_user.id).all()

    total_kwh = 0.0                          # acumulator pentru consumul total al zilei
    per_device: List[Dict[str, Any]] = []    # lista cu detaliile per dispozitiv pentru raspuns

    # Iteram fiecare dispozitiv si calculam consumul individual
    for device in devices:
        # Cautam consumul in kW al tipului de dispozitiv in dictionarul POWER_KW
        # Daca tipul nu are consum definit (ex: wol), .get() returneaza None
        power_kw = POWER_KW.get(device.device_type)

        # Sarim dispozitivele fara consum definit (wol si eventuale tipuri necunoscute)
        if power_kw is None:
            continue  # trecem la urmatorul dispozitiv fara a adauga la total

        # Preluam comenzile 'power' ale dispozitivului din ziua curenta, sortate cronologic
        # Sortarea ascendenta este critica pentru reconstructia corecta a intervalelor ON/OFF
        cmds = (
            db.query(Command)
            .filter(
                Command.device_id == device.id,     # comenzile acestui dispozitiv specific
                Command.action == "power",           # doar comenzile de tip power (on/off)
                Command.timestamp >= start_of_day,   # doar cele din ziua curenta
            )
            .order_by(Command.timestamp.asc())  # sortam cronologic pentru reconstructia intervalelor
            .all()
        )

        # Calculam orele de functionare folosind helper-ul de reconstructie intervale
        hours_on = _calculate_hours_on(cmds, device.last_status, start_of_day, now)

        # Calculam consumul in kWh: durata (ore) x putere (kW)
        kwh = round(hours_on * power_kw, 4)  # rotunjim la 4 zecimale pentru precizie

        # Acumulam consumul acestui dispozitiv in totalul zilei
        total_kwh += kwh

        # Adaugam intrarea cu detaliile dispozitivului in lista de raspuns
        per_device.append({
            "device_id": device.id,           # ID-ul dispozitivului
            "device_name": device.name,        # numele dispozitivului (pentru afisare)
            "device_type": device.device_type, # tipul dispozitivului (ir_tv, relay etc.)
            "hours_on": round(hours_on, 2),    # ore de functionare, rotunjit la 2 zecimale
            "power_kw": power_kw,              # puterea nominala in kW a tipului
            "kwh": kwh,                        # consumul calculat in kWh pentru ziua curenta
        })

    # Returnam totalul si lista detaliata per dispozitiv
    return {
        "total_kwh": round(total_kwh, 4),  # consumul total al zilei, rotunjit la 4 zecimale
        "per_device": per_device,          # lista cu detaliile fiecarui dispozitiv
    }


def _calculate_hours_on(
    cmds: list,               # lista comenzilor 'power' ale dispozitivului din ziua curenta
    last_status: str | None,  # ultimul status cunoscut al dispozitivului (din coloana last_status)
    start_of_day: datetime,   # miezul noptii UTC al zilei curente
    now: datetime,            # momentul curent UTC (capatul drept al intervalului de calcul)
) -> float:
    """
    Calculeaza numarul de ore in care dispozitivul a fost pornit in ziua curenta.

    Parcurge comenzile in ordine cronologica si reconstituie intervalele ON/OFF:
      - Cand valoarea comenzii este 'on' (sau echivalente), marcam inceputul unui interval ON
      - Cand valoarea comenzii este 'off' (sau echivalente), inchidem intervalul si acumulam durata
      - Daca dispozitivul este inca pornit la momentul 'now', inchidem intervalul pana la 'now'

    Parametri:
        cmds:         Lista de obiecte Command cu action='power', sortata cronologic ascendent
        last_status:  Valoarea din coloana last_status a dispozitivului (poate fi None)
        start_of_day: Inceputul zilei curente (miezul noptii UTC) — pentru eventuale ajustari
        now:          Momentul curent UTC — folosit ca capat drept daca dispozitivul e inca ON

    Returneaza:
        Numarul total de ore in care dispozitivul a fost pornit (float)
    """
    total_seconds = 0.0        # acumulator pentru durata totala de functionare in secunde
    on_since: datetime | None = None  # timestamp-ul de la care dispozitivul este pornit (None = oprit)

    # Setul valorilor comenzii care semnifica starea ON
    # Acoperim mai multe formate posibile pentru robustete
    on_values = {"on", "1", "true", "power_on"}

    # Setul valorilor comenzii care semnifica starea OFF
    off_values = {"off", "0", "false", "power_off"}

    # Parcurgem comenzile in ordine cronologica pentru a reconstitui intervalele
    for cmd in cmds:
        # Normalizam valoarea la lowercase si inlocuim None cu string gol
        val = (cmd.value or "").lower()

        # Obtinem timestamp-ul comenzii
        ts = cmd.timestamp

        # Asiguram ca timestamp-ul este timezone-aware (UTC) pentru comparatii corecte
        # Comenzile vechi pot fi naive (fara tzinfo) daca au fost salvate fara timezone
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)  # presupunem UTC pentru datele naive

        if val in on_values:
            # Comanda de pornire — marcam inceputul intervalului ON daca nu e deja pornit
            if on_since is None:
                on_since = ts  # retinem timestamp-ul pornirii
        elif val in off_values:
            # Comanda de oprire — inchidem intervalul ON si acumulam durata
            if on_since is not None:
                total_seconds += (ts - on_since).total_seconds()  # durata intervalului in secunde
                on_since = None  # resetam — dispozitivul este acum oprit

    # Daca dispozitivul este inca pornit la finalul intervalului de calcul (now),
    # acumulam durata de la ultima pornire pana in momentul curent
    if on_since is not None:
        total_seconds += (now - on_since).total_seconds()  # durata pana acum

    # Convertim secundele acumulate in ore si returnam
    return total_seconds / 3600.0

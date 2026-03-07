"""
Router pentru dashboard-ul aplicatiei Smart Home.

Expune doua endpoint-uri:
  - GET /dashboard/stats   : statistici agregate (nr. dispozitive, comenzi, rutine etc.)
  - GET /dashboard/activity: ultimele 50 activitati ale utilizatorului curent

Toate datele sunt filtrate strict pe utilizatorul autentificat (current_user.id),
astfel incat un utilizator nu poate vedea datele altui utilizator.
"""

# Importam Counter pentru numararea aparitiilor elementelor dintr-o lista
from collections import Counter

# datetime  - pentru obtinerea timpului curent si calcule cu date
# timedelta - pentru construirea intervalelor (7 zile, 30 zile etc.)
# timezone  - pentru lucrul cu timestamp-uri UTC
from datetime import datetime, timedelta, timezone

# APIRouter - clasa FastAPI pentru gruparea endpoint-urilor intr-un modul
# Depends   - mecanism de dependency injection FastAPI
from fastapi import APIRouter, Depends

# func - utilitare SQLAlchemy pentru functii SQL (COUNT, SUM etc.)
from sqlalchemy import func

# Session - tipul sesiunii de baza de date SQLAlchemy
from sqlalchemy.orm import Session

# Importam modelele ORM si functia de factory a sesiunii DB
from database.db import ActivityLog, Command, Device, Routine, Scene, User, get_db

# Importam schemele Pydantic pentru serializarea raspunsurilor
from models.schemas import ActivityLogResponse, DashboardStats

# Dependency FastAPI care extrage si valideaza utilizatorul din JWT
from services.auth_service import get_current_user

# Cream router-ul cu prefix si tag pentru documentatia Swagger
# prefix="/dashboard" -> toate rutele vor fi /dashboard/...
# tags=["Dashboard"]  -> grupare vizuala in Swagger UI
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),              # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),  # utilizatorul autentificat
):
    """
    Returneaza statisticile agregate pentru dashboard-ul aplicatiei.

    Calculeaza urmatoarele date, toate filtrate pe utilizatorul curent:
      - total dispozitive inregistrate
      - total comenzi trimise azi
      - total rutine active
      - total scene salvate
      - cel mai folosit dispozitiv (ultimele 30 de zile)
      - ora de varf a utilizarii (0-23, ultimele 30 de zile)
      - comenzi per zi (ultimele 7 zile) -> pentru grafic tip bar
      - top 5 dispozitive dupa numar de comenzi (ultimele 30 de zile)
      - distributia tipurilor de dispozitive (nr. per tip)

    Parametri:
      db           : sesiunea SQLAlchemy injectata de FastAPI
      current_user : utilizatorul extras si validat din token-ul JWT
    """

    # -----------------------------------------------------------------------
    # Calcul timestamp-uri pentru filtrele de interval
    # -----------------------------------------------------------------------

    # Momentul curent in UTC (timezone-aware) - folosit ca referinta
    acum = datetime.now(timezone.utc)

    # Inceputul zilei curente la miezul noptii UTC (00:00:00.000000)
    # Folosit pentru a numara comenzile trimise azi
    azi_start = acum.replace(hour=0, minute=0, second=0, microsecond=0)

    # Timestamp-ul de acum 30 de zile - pentru analizele pe termen mediu
    treizeci_zile = acum - timedelta(days=30)

    # Timestamp-ul de acum 7 zile - pentru graficul comenzilor per zi
    sapte_zile = acum - timedelta(days=7)

    # -----------------------------------------------------------------------
    # Conturi simple (scalare) - interogari SQL COUNT directe
    # -----------------------------------------------------------------------

    # Numarul total de dispozitive inregistrate de utilizatorul curent
    # .scalar() extrage valoarea numerica; `or 0` protejeaza impotriva None
    total_devices = db.query(func.count(Device.id)).filter(
        Device.owner_id == current_user.id  # filtram doar dispozitivele proprii
    ).scalar() or 0

    # Numarul de comenzi trimise de utilizatorul curent in ziua curenta
    # Filtram pe timestamp >= azi_start pentru a obtine doar comenzile de azi
    total_commands_today = db.query(func.count(Command.id)).filter(
        Command.user_id == current_user.id,   # doar comenzile utilizatorului curent
        Command.timestamp >= azi_start,        # doar comenzile din ziua curenta
    ).scalar() or 0

    # Numarul de rutine active ale utilizatorului curent
    # is_active == True filtreaza doar rutinele pornite (nu cele oprite)
    total_routines_active = db.query(func.count(Routine.id)).filter(
        Routine.user_id == current_user.id,   # doar rutinele utilizatorului curent
        Routine.is_active == True,  # noqa: E712  # filtram doar rutinele active
    ).scalar() or 0

    # Numarul total de scene salvate de utilizatorul curent
    total_scenes = db.query(func.count(Scene.id)).filter(
        Scene.owner_id == current_user.id  # filtram doar scenele proprii
    ).scalar() or 0

    # -----------------------------------------------------------------------
    # Comenzi din ultimele 30 de zile - incarcate o singura data in memorie
    # pentru a calcula atat cel mai folosit dispozitiv cat si ora de varf
    # -----------------------------------------------------------------------

    # Lista tuturor obiectelor Command din ultimele 30 de zile ale utilizatorului
    comenzi_30_zile = (
        db.query(Command)
        .filter(
            Command.user_id == current_user.id,       # doar comenzile proprii
            Command.timestamp >= treizeci_zile,        # din ultimele 30 de zile
        )
        .all()  # incarcam toate in memorie pentru analiza cu Counter
    )

    # -----------------------------------------------------------------------
    # Determinarea celui mai folosit dispozitiv (ultimele 30 de zile)
    # -----------------------------------------------------------------------

    # Verificam daca exista comenzi in perioada analizata
    if comenzi_30_zile:
        # Cream un dictionar {device_id: numar_aparitii} folosind Counter
        # Iteram prin toate comenzile si extragem device_id-ul fiecareia
        device_counts = Counter(cmd.device_id for cmd in comenzi_30_zile)

        # most_common(1) returneaza lista [(device_id, count)] cu cel mai frecvent
        # [0][0] extrage doar device_id-ul (primul element al primului tuplu)
        top_device_id = device_counts.most_common(1)[0][0]

        # Cautam dispozitivul in baza de date dupa id-ul gasit
        top_device = db.query(Device).filter(Device.id == top_device_id).first()

        # Returnam numele dispozitivului daca acesta exista, altfel None
        most_used_device = top_device.name if top_device else None
    else:
        # Nu exista comenzi in ultimele 30 de zile -> nu putem determina un top
        most_used_device = None

    # -----------------------------------------------------------------------
    # Determinarea orei de varf a utilizarii (ultimele 30 de zile)
    # Ora de varf = ora din zi (0-23) cu cele mai multe comenzi trimise
    # -----------------------------------------------------------------------

    # Verificam din nou daca exista comenzi (reutilizam aceeasi lista)
    if comenzi_30_zile:
        # Cream un dictionar {ora: numar_comenzi} extragand .hour din timestamp
        # Exemplu: {14: 45, 20: 38, 9: 22, ...}
        ora_counts = Counter(cmd.timestamp.hour for cmd in comenzi_30_zile)

        # Extragem ora cu cele mai multe comenzi si o convertim la int
        # int() asigura tipul corect pentru schema Pydantic (nu numpy.int64)
        peak_hour = int(ora_counts.most_common(1)[0][0])
    else:
        # Nu exista comenzi -> nu putem determina o ora de varf
        peak_hour = None

    # -----------------------------------------------------------------------
    # Comenzi per zi - ultimele 7 zile (pentru graficul de activitate zilnica)
    # -----------------------------------------------------------------------

    # Interogam comenzile din ultimele 7 zile separate de cele din 30 de zile
    # pentru a reduce cantitatea de date procesate in memoria Python
    comenzi_7_zile = (
        db.query(Command)
        .filter(
            Command.user_id == current_user.id,  # doar comenzile proprii
            Command.timestamp >= sapte_zile,      # din ultimele 7 zile
        )
        .all()  # incarcam toate in memorie pentru numarare cu Counter
    )

    # Cream un dictionar {data_ISO: numar_comenzi} pentru acces rapid
    # data_ISO = string de forma "YYYY-MM-DD" (ex: "2025-03-05")
    zi_counts = Counter(cmd.timestamp.date().isoformat() for cmd in comenzi_7_zile)

    # Construim o lista de 7 dictionare, una per zi, in ordine cronologica
    # range(6, -1, -1) = [6, 5, 4, 3, 2, 1, 0] -> de la 6 zile in urma pana azi
    # zi_counts.get(..., 0) returneaza 0 pentru zilele fara comenzi
    commands_by_day = [
        {
            "date": (acum - timedelta(days=i)).date().isoformat(),  # data ca string ISO
            "count": zi_counts.get((acum - timedelta(days=i)).date().isoformat(), 0),  # nr. comenzi
        }
        for i in range(6, -1, -1)  # iteram de la 6 zile in urma pana la ziua curenta
    ]

    # -----------------------------------------------------------------------
    # Top 5 dispozitive dupa numarul de comenzi (ultimele 30 de zile)
    # Folosim un JOIN SQL pentru eficienta in loc sa procesam in Python
    # -----------------------------------------------------------------------

    # Interogare SQL cu JOIN, GROUP BY si ORDER BY pentru a obtine top 5
    top5 = (
        db.query(Device.name, func.count(Command.id).label("cnt"))  # selectam numele si numarul
        .join(Command, Command.device_id == Device.id)              # JOIN intre Device si Command
        .filter(
            Command.user_id == current_user.id,      # doar comenzile utilizatorului curent
            Command.timestamp >= treizeci_zile        # din ultimele 30 de zile
        )
        .group_by(Device.id)                         # grupam rezultatele pe dispozitiv
        .order_by(func.count(Command.id).desc())     # ordonam descrescator dupa numar comenzi
        .limit(5)                                    # luam doar primele 5 rezultate
        .all()
    )

    # Transformam rezultatele SQL intr-o lista de dictionare pentru schema Pydantic
    # row.name = numele dispozitivului, row.cnt = numarul de comenzi
    commands_by_device = [{"device_name": row.name, "count": row.cnt} for row in top5]

    # -----------------------------------------------------------------------
    # Distributia tipurilor de dispozitive (cate dispozitive per tip)
    # Exemplu: {"type": "ir_rgb", "count": 3}, {"type": "wol", "count": 1}
    # -----------------------------------------------------------------------

    # Interogare SQL cu GROUP BY pe campul device_type
    distributie = (
        db.query(Device.device_type, func.count(Device.id).label("cnt"))  # tip si numar
        .filter(Device.owner_id == current_user.id)  # doar dispozitivele proprii
        .group_by(Device.device_type)                # grupam pe tip de dispozitiv
        .all()
    )

    # Transformam rezultatele SQL intr-o lista de dictionare pentru schema Pydantic
    # row.device_type = tipul dispozitivului (string), row.cnt = numarul de dispozitive
    device_type_distribution = [{"type": row.device_type, "count": row.cnt} for row in distributie]

    # -----------------------------------------------------------------------
    # Construim si returnam obiectul DashboardStats cu toate datele calculate
    # -----------------------------------------------------------------------
    return DashboardStats(
        total_devices=total_devices,                      # nr. total dispozitive
        total_commands_today=total_commands_today,        # nr. comenzi azi
        total_routines_active=total_routines_active,      # nr. rutine active
        total_scenes=total_scenes,                        # nr. scene salvate
        most_used_device=most_used_device,                # numele dispozitivului cel mai folosit
        peak_hour=peak_hour,                              # ora de varf (int 0-23) sau None
        commands_by_day=commands_by_day,                  # lista 7 zile cu nr. comenzi
        commands_by_device=commands_by_device,            # top 5 dispozitive
        device_type_distribution=device_type_distribution,  # distributie pe tipuri
    )


@router.get("/activity", response_model=list[ActivityLogResponse])
def get_activity(
    db: Session = Depends(get_db),              # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),  # utilizatorul autentificat
):
    """
    Returneaza ultimele 50 de activitati ale utilizatorului curent.

    Activitatile sunt ordonate descrescator dupa data crearii (cele mai recente
    apar primele), astfel incat interfata sa afiseze un timeline actualizat.

    Parametri:
      db           : sesiunea SQLAlchemy injectata de FastAPI
      current_user : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Lista de obiecte ActivityLogResponse (max 50 intrari)
    """
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id)  # doar activitatile proprii
        .order_by(ActivityLog.created_at.desc())          # cele mai recente primele
        .limit(50)                                        # limita de 50 de intrari
        .all()
    )

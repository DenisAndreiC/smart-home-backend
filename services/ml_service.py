import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from database.db import Command, Device, Routine

# Logger dedicat serviciului ML
logger = logging.getLogger(__name__)

# Mapare numar zi ISO (1=Luni...7=Duminica) -> denumire in romana fara diacritice
_ZILE_RO = {
    1: "Luni",
    2: "Marti",
    3: "Miercuri",
    4: "Joi",
    5: "Vineri",
    6: "Sambata",
    7: "Duminica",
}


def _minutes_to_time(minutes: float) -> str:
    """
    Converteste minute fata de miezul noptii in format HH:MM.
    Exemplu: 1095.5 -> '18:15' (1095 / 60 = 18h 15min)
    """
    # Rotunjeste la cel mai apropiat minut intreg
    total = int(round(minutes))

    # Calculeaza ora (impartire intreaga) si minutul (restul)
    return f"{total // 60:02d}:{total % 60:02d}"


def _days_to_romanian(days_str: str) -> str:
    """
    Converteste un sir de numere de zile in denumiri romanesti.
    Exemplu: '1,2,3,4,5' -> 'Luni, Marti, Miercuri, Joi, Vineri'
    """
    # Converteste fiecare element din sirul CSV la int
    zile = [int(z) for z in days_str.split(",")]

    # Mapeaza numerele la denumiri si le uneste cu virgula si spatiu
    return ", ".join(_ZILE_RO[z] for z in sorted(zile) if z in _ZILE_RO)


# ---------------------------------------------------------------------------
# Algoritm principal de detectie DBSCAN
# ---------------------------------------------------------------------------


def detect_routines(
    db: Session,
    user_id: int,
    days_back: int = 30,
    min_occurrences: int = 5,
    time_epsilon_minutes: float = 15.0,
) -> list[dict]:
    """
    Analizeaza istoricul comenzilor manuale si detecteaza tipare repetitive
    folosind algoritmul de clustering DBSCAN (Density-Based Spatial Clustering).

    Pasi:
    1. Preia comenzile manuale din ultimele days_back zile
    2. Grupeaza pe (device_id, action, value)
    3. Aplica DBSCAN pe vectorul de ore (minute fata de miezul noptii)
    4. Calculeaza confidence score pentru fiecare cluster
    5. Returneaza lista rutinelor sugerate, sortate descrescator dupa confidence

    Args:
        db: sesiunea SQLAlchemy
        user_id: ID-ul utilizatorului analizat
        days_back: numarul de zile din trecut de analizat (implicit 30)
        min_occurrences: minimum de comenzi pentru a forma un cluster (implicit 5)
        time_epsilon_minutes: toleranta in minute intre comenzi din acelasi cluster
    """
    # Calculeaza data limita (acum - days_back zile) pentru filtrul SQL
    data_limita = datetime.now(timezone.utc) - timedelta(days=days_back)

    # --- Pasul 1: Preia comenzile manuale din perioada analizata ---
    # Filtram doar source='app' pentru a exclude comenzile automate (rutine, scene)
    comenzi = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.source == "app",                # doar comenzi manuale
            Command.timestamp >= data_limita,       # in fereastra de timp
        )
        .all()
    )

    # Daca nu sunt suficiente date, returnam lista goala fara a rula DBSCAN
    if len(comenzi) < min_occurrences:
        logger.info("Date insuficiente pentru user %s (%d comenzi)", user_id, len(comenzi))
        return []

    # --- Pasul 2: Grupeaza comenzile dupa tripletul (device, action, value) ---
    # defaultdict(list) evita verificarea cheii inainte de append
    grupe: dict[tuple, list[Command]] = defaultdict(list)
    for cmd in comenzi:
        # Cheia grupei este tripletul unic care defineste o actiune specifica
        cheie = (cmd.device_id, cmd.action, cmd.value)
        grupe[cheie].append(cmd)

    # Lista rezultatelor (rutinele detectate)
    rutine_detectate = []

    # --- Pasul 3: Aplica DBSCAN pe fiecare grupa ---
    for (device_id, action, value), grup in grupe.items():
        # Sari grupele cu prea putine comenzi (sub pragul minim)
        if len(grup) < min_occurrences:
            continue

        # Converteste timestamp-urile la minute fata de miezul noptii (0-1439)
        # Reshape(-1, 1) este necesar deoarece DBSCAN asteapta matrice 2D
        time_minutes = np.array(
            [cmd.timestamp.hour * 60 + cmd.timestamp.minute for cmd in grup],
            dtype=float,
        ).reshape(-1, 1)

        # Extrage ziua saptamanii (1=Luni...7=Duminica) pentru fiecare comanda
        weekdays = [cmd.timestamp.isoweekday() for cmd in grup]

        # Aplica DBSCAN cu epsilon = toleranta in minute si min_samples = pragul minim
        # Rezultatul 'labels' contine: -1 pentru zgomot, 0,1,2... pentru clustere
        labels = DBSCAN(eps=time_epsilon_minutes, min_samples=min_occurrences).fit_predict(time_minutes)

        # Itereaza fiecare cluster distinct gasit
        for label in set(labels):
            if label == -1:
                # Label -1 = zgomot DBSCAN - comenzi izolate, nu formeaza un tipar
                continue

            # Gaseste indicii comenzilor care apartin acestui cluster
            idx_cluster = [i for i, lbl in enumerate(labels) if lbl == label]

            # Extrage minutele si zilele pentru comenzile din cluster
            times_cluster = time_minutes[idx_cluster].flatten()
            days_cluster = [weekdays[i] for i in idx_cluster]

            # Calculeaza ora medie de declansare (media aritmetica a minutelor)
            trigger_time = _minutes_to_time(float(np.mean(times_cluster)))

            # Extrage zilele unice active (sortate crescator pentru afisare)
            zile_active = sorted(set(days_cluster))

            # Formeaza sirul CSV cu zilele (ex: "1,2,3,4,5")
            days_of_week = ",".join(str(z) for z in zile_active)

            # --- Calcul confidence score ---
            # Confidence = cat de des apare pattern-ul fata de cat ar putea aparea
            # Formula: (comenzi in cluster) / (zile_analizate * zile_active / 7)
            # Rezultatul este clampat la [0.0, 1.0]
            frecventa_asteptata = days_back * len(zile_active) / 7
            confidence = min(1.0, max(0.0, len(idx_cluster) / frecventa_asteptata))

            # Preia numele dispozitivului din DB pentru a construi descrierea rutinei
            device = db.query(Device).filter(Device.id == device_id).first()
            device_name = device.name if device else f"Device {device_id}"

            # Genereaza un nume descriptiv pentru rutina (afisat utilizatorului)
            zile_ro = _days_to_romanian(days_of_week)
            name = f"{action.capitalize()} {device_name} la {trigger_time} - {zile_ro}"

            # Adauga rutina detectata in lista de rezultate
            rutine_detectate.append(
                {
                    "device_id": device_id,
                    "device_name": device_name,
                    "action": action,
                    "value": value,
                    "trigger_time": trigger_time,
                    "days_of_week": days_of_week,
                    "confidence": round(confidence, 3),  # rotunjit la 3 zecimale
                    "name": name,
                }
            )

    # --- Pasul 4: Sorteaza descrescator dupa confidence ---
    # Rutinele cu confidence mai mare sunt afisate primele in aplicatie
    rutine_detectate.sort(key=lambda r: r["confidence"], reverse=True)
    logger.info("Detectate %d rutine pentru user %s", len(rutine_detectate), user_id)
    return rutine_detectate


# ---------------------------------------------------------------------------
# Generator date sintetice pentru demo ML
# ---------------------------------------------------------------------------


def generate_test_data(db: Session, user_id: int, device_id: int) -> int:
    """
    Genereaza 30 de zile de comenzi sintetice cu 3 tipare clare, pentru demo ML.
    Fiecare tipar are un offset aleator mic (+/- cateva minute) pentru a simula
    comportamentul real al utilizatorului (nu fix la ora exacta).

    Tipare generate:
    - Pattern 1: power=ON la ~18:00, Luni-Vineri (zile lucratoare)
    - Pattern 2: power=OFF la ~23:00, zilnic (toate cele 7 zile)
    - Pattern 3: color=RED la ~19:30, Sambata-Duminica (weekend)

    Returneaza numarul total de comenzi generate.
    """
    # Timestamp de referinta: momentul curent in UTC
    acum = datetime.now(timezone.utc)

    # Contor pentru numarul total de comenzi create
    count = 0

    # Itereaza ultimele 30 de zile (de la 1 zi inapoi la 30 zile inapoi)
    for zile_inapoi in range(1, 31):
        # Calculeaza data zilei de generat
        data_zi = acum - timedelta(days=zile_inapoi)

        # Obtine ziua saptamanii (1=Luni...7=Duminica) pentru filtrarea pattern-urilor
        zi_saptamana = data_zi.isoweekday()

        # --- Pattern 1: Aprins seara in zilele lucratoare (Luni-Vineri) ---
        if zi_saptamana <= 5:
            # Offset aleator intre -10 si +10 minute pentru a simula comportament natural
            offset = random.randint(-10, 10)
            ts = data_zi.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(
                device_id=device_id,
                user_id=user_id,
                action="power",
                value="ON",
                source="app",   # sursa 'app' pentru a fi inclus in analiza ML
                timestamp=ts,
            ))
            count += 1

        # --- Pattern 2: Stins noaptea, in fiecare zi (zilnic) ---
        offset = random.randint(-8, 8)
        ts = data_zi.replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
        db.add(Command(
            device_id=device_id,
            user_id=user_id,
            action="power",
            value="OFF",
            source="app",
            timestamp=ts,
        ))
        count += 1

        # --- Pattern 3: Culoare rosie seara de weekend (Sambata=6, Duminica=7) ---
        if zi_saptamana >= 6:
            offset = random.randint(-5, 5)
            ts = data_zi.replace(hour=19, minute=30, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(
                device_id=device_id,
                user_id=user_id,
                action="color",
                value="RED",
                source="app",
                timestamp=ts,
            ))
            count += 1

    # Comite toate comenzile generate intr-o singura tranzactie
    db.commit()
    logger.info("Generate %d comenzi de test pentru user %s, device %s", count, user_id, device_id)
    return count

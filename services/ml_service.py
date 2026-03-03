import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from database.db import Command, Device, Routine

logger = logging.getLogger(__name__)

# Mapare număr zi → denumire română
_ZILE_RO = {
    1: "Luni",
    2: "Marți",
    3: "Miercuri",
    4: "Joi",
    5: "Vineri",
    6: "Sâmbătă",
    7: "Duminică",
}


def _minutes_to_time(minutes: float) -> str:
    """Convertește minute față de miezul nopții în format HH:MM. Ex: 1095.5 → '18:15'"""
    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


def _days_to_romanian(days_str: str) -> str:
    """Convertește '1,2,3,4,5' în 'Luni, Marți, Miercuri, Joi, Vineri'."""
    zile = [int(z) for z in days_str.split(",")]
    return ", ".join(_ZILE_RO[z] for z in sorted(zile) if z in _ZILE_RO)


# ---------------------------------------------------------------------------
# Algoritm principal de detecție
# ---------------------------------------------------------------------------


def detect_routines(
    db: Session,
    user_id: int,
    days_back: int = 30,
    min_occurrences: int = 5,
    time_epsilon_minutes: float = 15.0,
) -> list[dict]:
    """
    Analizează istoricul comenzilor manuale și detectează tipare repetitive
    folosind algoritmul de clustering DBSCAN.

    Returnează o listă de dicționare cu rutinele sugerate, sortate după confidence.
    """
    data_limita = datetime.now(timezone.utc) - timedelta(days=days_back)

    # 1. Preluăm doar comenzile manuale din perioada analizată
    comenzi = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.source == "app",
            Command.timestamp >= data_limita,
        )
        .all()
    )

    if len(comenzi) < min_occurrences:
        logger.info("Date insuficiente pentru user %s (%d comenzi)", user_id, len(comenzi))
        return []

    # 2. Grupăm comenzile după acțiunea efectuată pe dispozitiv
    grupe: dict[tuple, list[Command]] = defaultdict(list)
    for cmd in comenzi:
        cheie = (cmd.device_id, cmd.action, cmd.value)
        grupe[cheie].append(cmd)

    rutine_detectate = []

    # 3. Analizăm fiecare grupă cu DBSCAN
    for (device_id, action, value), grup in grupe.items():
        if len(grup) < min_occurrences:
            continue

        # Convertim timestamp-urile la minute față de miezul nopții + ziua săptămânii
        time_minutes = np.array(
            [cmd.timestamp.hour * 60 + cmd.timestamp.minute for cmd in grup],
            dtype=float,
        ).reshape(-1, 1)

        weekdays = [cmd.timestamp.isoweekday() for cmd in grup]

        # DBSCAN grupează punctele aproape în timp (eps = toleranță în minute)
        labels = DBSCAN(eps=time_epsilon_minutes, min_samples=min_occurrences).fit_predict(time_minutes)

        for label in set(labels):
            if label == -1:
                # Puncte zgomot — nu formează un tipar coerent
                continue

            # Indicii comenzilor din acest cluster
            idx_cluster = [i for i, lbl in enumerate(labels) if lbl == label]
            times_cluster = time_minutes[idx_cluster].flatten()
            days_cluster = [weekdays[i] for i in idx_cluster]

            # Ora medie de declanșare
            trigger_time = _minutes_to_time(float(np.mean(times_cluster)))

            # Zilele active (unice, sortate)
            zile_active = sorted(set(days_cluster))
            days_of_week = ",".join(str(z) for z in zile_active)

            # Confidence = cât de des apare pattern-ul față de câte ori ar putea apărea
            # (nr. comenzi din cluster) / (zile_analizate * zile_active_per_săptămână / 7)
            frecventa_asteptata = days_back * len(zile_active) / 7
            confidence = min(1.0, max(0.0, len(idx_cluster) / frecventa_asteptata))

            # Preluăm numele dispozitivului pentru descrierea rutinei
            device = db.query(Device).filter(Device.id == device_id).first()
            device_name = device.name if device else f"Device {device_id}"

            # Descriere generată automat în română
            zile_ro = _days_to_romanian(days_of_week)
            name = f"{action.capitalize()} {device_name} la {trigger_time} - {zile_ro}"

            rutine_detectate.append(
                {
                    "device_id": device_id,
                    "device_name": device_name,
                    "action": action,
                    "value": value,
                    "trigger_time": trigger_time,
                    "days_of_week": days_of_week,
                    "confidence": round(confidence, 3),
                    "name": name,
                }
            )

    # 4. Sortăm după confidence descrescător — cele mai sigure primele
    rutine_detectate.sort(key=lambda r: r["confidence"], reverse=True)
    logger.info("Detectate %d rutine pentru user %s", len(rutine_detectate), user_id)
    return rutine_detectate


# ---------------------------------------------------------------------------
# Generator date de test
# ---------------------------------------------------------------------------


def generate_test_data(db: Session, user_id: int, device_id: int) -> int:
    """
    Generează 30 de zile de comenzi sintetice cu 3 tipare clare, pentru demo ML.

    Pattern 1: power=ON la ~18:00, Luni–Vineri
    Pattern 2: power=OFF la ~23:00, zilnic
    Pattern 3: color=RED la ~19:30, Sâmbătă–Duminică
    """
    acum = datetime.now(timezone.utc)
    count = 0

    for zile_inapoi in range(1, 31):
        data_zi = acum - timedelta(days=zile_inapoi)
        zi_saptamana = data_zi.isoweekday()  # 1=Luni ... 7=Duminică

        # Pattern 1 — aprins seara în zilele lucrătoare
        if zi_saptamana <= 5:
            offset = random.randint(-10, 10)
            ts = data_zi.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(device_id=device_id, user_id=user_id, action="power", value="ON", source="app", timestamp=ts))
            count += 1

        # Pattern 2 — stins noaptea, în fiecare zi
        offset = random.randint(-8, 8)
        ts = data_zi.replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
        db.add(Command(device_id=device_id, user_id=user_id, action="power", value="OFF", source="app", timestamp=ts))
        count += 1

        # Pattern 3 — culoare roșie seara de weekend
        if zi_saptamana >= 6:
            offset = random.randint(-5, 5)
            ts = data_zi.replace(hour=19, minute=30, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(device_id=device_id, user_id=user_id, action="color", value="RED", source="app", timestamp=ts))
            count += 1

    db.commit()
    logger.info("Generate %d comenzi de test pentru user %s, device %s", count, user_id, device_id)
    return count

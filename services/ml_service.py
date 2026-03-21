import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from database.db import Command, Device, Routine

# Dedicated logger for the ML service
logger = logging.getLogger(__name__)

# Mapping ISO weekday number (1=Mon...7=Sun) -> short English name
_WEEKDAY_EN = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}


def _minutes_to_time(minutes: float) -> str:
    """Convert minutes-since-midnight to HH:MM string. Example: 1095.5 -> '18:15'."""
    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


def _hours_to_time(hours: float) -> str:
    """Convert decimal hours to HH:MM string. Example: 13.5 -> '13:30'."""
    total_minutes = int(round(hours * 60))
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _days_to_english(days_str: str) -> str:
    """Convert CSV weekday numbers to English names. Example: '1,2,3' -> 'Monday, Tuesday, Wednesday'."""
    days = [int(d) for d in days_str.split(",")]
    return ", ".join(_WEEKDAY_EN[d] for d in sorted(days) if d in _WEEKDAY_EN)


# ---------------------------------------------------------------------------
# New API: analyze_user_patterns — used by GET /api/ml/recommendations
# ---------------------------------------------------------------------------


def analyze_user_patterns(
    user_id: int,
    db: Session,
    min_occurrences: int = 5,
    min_days: int = 4,
) -> list[dict]:
    """
    Analyze the user's command history using DBSCAN to identify repeated patterns.

    Steps:
    1. Fetch all commands for the user from the last 30 days.
    2. Group by (device_id, action) pair.
    3. Extract hour as numeric feature: hour + minute/60 (e.g. 13:30 -> 13.5).
    4. Apply DBSCAN(eps=0.5, min_samples=min_occurrences) on the hours array.
       eps=0.5 means commands within 30 minutes belong to the same cluster.
    5. For each valid cluster (label != -1):
       a. Count distinct calendar days covered by the cluster.
       b. Skip if distinct_days < min_days (avoids spam from a single session).
       c. Compute centroid, std deviation, and confidence.
    6. Return recommendations sorted by confidence descending.

    Returns a list of recommendation dicts matching RecommendationResponse schema.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    commands = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.timestamp >= cutoff,
        )
        .all()
    )

    total = len(commands)

    if total < min_occurrences:
        logger.info("Not enough data for user %s (%d commands)", user_id, total)
        return []

    # Group by (device_id, action) — ignore value for broader pattern matching
    groups: dict[tuple, list[Command]] = defaultdict(list)
    for cmd in commands:
        groups[(cmd.device_id, cmd.action)].append(cmd)

    recommendations = []

    for (device_id, action), group in groups.items():
        if len(group) < min_occurrences:
            continue

        # Extract decimal hours as clustering feature
        hours = np.array(
            [cmd.timestamp.hour + cmd.timestamp.minute / 60.0 for cmd in group],
            dtype=float,
        ).reshape(-1, 1)

        # DBSCAN: eps=0.5 hours (30 min window), min_samples configurable
        labels = DBSCAN(eps=0.5, min_samples=min_occurrences).fit_predict(hours)

        device = db.query(Device).filter(Device.id == device_id).first()
        device_name = device.name if device else f"Device {device_id}"

        for label in set(labels):
            if label == -1:
                continue  # noise points — not a pattern

            cluster_indices = [i for i, lbl in enumerate(labels) if lbl == label]
            cluster_cmds = [group[i] for i in cluster_indices]

            # Count distinct calendar days spanned by this cluster.
            # Patterns that occurred on fewer days than min_days are skipped —
            # they are likely command bursts within a single session, not habits.
            distinct_days = len(set(cmd.timestamp.date() for cmd in cluster_cmds))
            if distinct_days < min_days:
                continue

            cluster_hours = hours[cluster_indices].flatten()

            mean_hour = float(np.mean(cluster_hours))
            std_hour = float(np.std(cluster_hours))
            occurrences = len(cluster_indices)

            # Confidence: 1.0 - normalised std deviation; capped to [0.0, 1.0]
            # std_hour is in hours; divide by 12 to normalise (max half-day spread)
            confidence = max(0.0, min(1.0, 1.0 - std_hour / 12.0))

            suggested_time = _hours_to_time(mean_hour)

            # Determine AM/PM for the message
            hour_int = int(mean_hour)
            period = "AM" if hour_int < 12 else "PM"
            display_hour = hour_int if hour_int <= 12 else hour_int - 12
            if display_hour == 0:
                display_hour = 12

            message = (
                f"You usually {action.replace('_', ' ')} {device_name} "
                f"around {display_hour:02d}:{int(round((mean_hour % 1) * 60)):02d} {period} "
                f"(detected on {distinct_days} different days)"
            )

            recommendations.append({
                "device_id": device_id,
                "device_name": device_name,
                "action": action,
                "suggested_time": suggested_time,
                "confidence": round(confidence, 3),
                "occurrences": occurrences,
                "distinct_days": distinct_days,
                "message": message,
            })

    recommendations.sort(key=lambda r: r["confidence"], reverse=True)
    logger.info("Found %d recommendations for user %s", len(recommendations), user_id)
    return recommendations


# ---------------------------------------------------------------------------
# New API: detect_anomalies — used by GET /api/ml/anomalies
# ---------------------------------------------------------------------------


def detect_anomalies(user_id: int, db: Session) -> list[dict]:
    """
    Detect unusual device activity by comparing recent commands against the 30-day baseline.

    Steps:
    1. Fetch all commands from the last 30 days and compute mean/std per (device, action).
    2. Fetch commands from the last 24 hours.
    3. For each recent command compute z-score = |hour - mean| / std.
    4. Commands with z-score > 2.0 are flagged as anomalies.

    Returns a list of anomaly dicts matching AnomalyResponse schema.
    """
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)

    # Baseline: all commands in the last 30 days
    baseline_commands = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.timestamp >= cutoff_30d,
        )
        .all()
    )

    if not baseline_commands:
        return []

    # Build distribution (mean, std) per (device_id, action)
    baseline_groups: dict[tuple, list[float]] = defaultdict(list)
    for cmd in baseline_commands:
        key = (cmd.device_id, cmd.action)
        hour_val = cmd.timestamp.hour + cmd.timestamp.minute / 60.0
        baseline_groups[key].append(hour_val)

    stats: dict[tuple, tuple[float, float]] = {}
    for key, hours in baseline_groups.items():
        arr = np.array(hours)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        stats[key] = (mean, std)

    # Recent commands: last 24 hours
    recent_commands = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.timestamp >= cutoff_24h,
        )
        .all()
    )

    anomalies = []

    for cmd in recent_commands:
        key = (cmd.device_id, cmd.action)
        if key not in stats:
            continue

        mean, std = stats[key]
        if std < 0.01:
            # Commands always at the same time — tiny std, skip to avoid division by zero
            continue

        cmd_hour = cmd.timestamp.hour + cmd.timestamp.minute / 60.0
        z_score = abs(cmd_hour - mean) / std

        if z_score <= 2.0:
            continue  # within normal range

        device = db.query(Device).filter(Device.id == cmd.device_id).first()
        device_name = device.name if device else f"Device {cmd.device_id}"

        # Format normal usage window: mean ± 1 std
        normal_start = _hours_to_time(max(0.0, mean - std))
        normal_end = _hours_to_time(min(23.99, mean + std))
        cmd_time = f"{cmd.timestamp.hour:02d}:{cmd.timestamp.minute:02d}"

        message = (
            f"Unusual: {device_name} {cmd.action.replace('_', ' ')} "
            f"at {cmd_time} (normally used {normal_start}-{normal_end})"
        )

        anomalies.append({
            "device_id": cmd.device_id,
            "device_name": device_name,
            "action": cmd.action,
            "time": cmd_time,
            "z_score": round(z_score, 2),
            "message": message,
        })

    logger.info("Found %d anomalies for user %s", len(anomalies), user_id)
    return anomalies


# ---------------------------------------------------------------------------
# Legacy DBSCAN routine detection (kept for existing /api/routines ML flow)
# ---------------------------------------------------------------------------


def detect_routines(
    db: Session,
    user_id: int,
    days_back: int = 30,
    min_occurrences: int = 5,
    time_epsilon_minutes: float = 15.0,
) -> list[dict]:
    """
    Analyze manual command history and detect repetitive patterns using DBSCAN.

    Groups commands by (device_id, action, value) and clusters their times-of-day.
    Returns suggested routines sorted by confidence descending.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    commands = (
        db.query(Command)
        .filter(
            Command.user_id == user_id,
            Command.source == "app",
            Command.timestamp >= cutoff,
        )
        .all()
    )

    if len(commands) < min_occurrences:
        logger.info("Not enough data for user %s (%d commands)", user_id, len(commands))
        return []

    groups: dict[tuple, list[Command]] = defaultdict(list)
    for cmd in commands:
        groups[(cmd.device_id, cmd.action, cmd.value)].append(cmd)

    detected = []

    for (device_id, action, value), group in groups.items():
        if len(group) < min_occurrences:
            continue

        time_minutes = np.array(
            [cmd.timestamp.hour * 60 + cmd.timestamp.minute for cmd in group],
            dtype=float,
        ).reshape(-1, 1)

        weekdays = [cmd.timestamp.isoweekday() for cmd in group]
        labels = DBSCAN(eps=time_epsilon_minutes, min_samples=min_occurrences).fit_predict(time_minutes)

        for label in set(labels):
            if label == -1:
                continue

            idx = [i for i, lbl in enumerate(labels) if lbl == label]
            times = time_minutes[idx].flatten()
            days = [weekdays[i] for i in idx]

            trigger_time = _minutes_to_time(float(np.mean(times)))
            active_days = sorted(set(days))
            days_of_week = ",".join(str(d) for d in active_days)

            expected = days_back * len(active_days) / 7
            confidence = min(1.0, max(0.0, len(idx) / expected))

            device = db.query(Device).filter(Device.id == device_id).first()
            device_name = device.name if device else f"Device {device_id}"

            days_en = _days_to_english(days_of_week)
            name = f"{action.capitalize()} {device_name} at {trigger_time} - {days_en}"

            detected.append({
                "device_id": device_id,
                "device_name": device_name,
                "action": action,
                "value": value,
                "trigger_time": trigger_time,
                "days_of_week": days_of_week,
                "confidence": round(confidence, 3),
                "name": name,
            })

    detected.sort(key=lambda r: r["confidence"], reverse=True)
    logger.info("Detected %d routines for user %s", len(detected), user_id)
    return detected


# ---------------------------------------------------------------------------
# Synthetic data generator for ML demo
# ---------------------------------------------------------------------------


def generate_test_data(db: Session, user_id: int, device_id: int) -> int:
    """
    Generate 30 days of synthetic commands with 3 clear patterns, for ML demo.

    Patterns:
    - Pattern 1: power ON at ~18:00, Monday-Friday
    - Pattern 2: power OFF at ~23:00, every day
    - Pattern 3: color RED at ~19:30, Saturday-Sunday

    Returns the total number of commands created.
    """
    now = datetime.now(timezone.utc)
    count = 0

    for days_back in range(1, 31):
        day = now - timedelta(days=days_back)
        weekday = day.isoweekday()

        # Pattern 1: turn on on weekdays
        if weekday <= 5:
            offset = random.randint(-10, 10)
            ts = day.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(device_id=device_id, user_id=user_id, action="power", value="ON", source="app", timestamp=ts))
            count += 1

        # Pattern 2: turn off every day
        offset = random.randint(-8, 8)
        ts = day.replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(minutes=offset)
        db.add(Command(device_id=device_id, user_id=user_id, action="power", value="OFF", source="app", timestamp=ts))
        count += 1

        # Pattern 3: color on weekends
        if weekday >= 6:
            offset = random.randint(-5, 5)
            ts = day.replace(hour=19, minute=30, second=0, microsecond=0) + timedelta(minutes=offset)
            db.add(Command(device_id=device_id, user_id=user_id, action="color", value="RED", source="app", timestamp=ts))
            count += 1

    db.commit()
    logger.info("Generated %d test commands for user %s, device %s", count, user_id, device_id)
    return count

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.db import ActivityLog, Command, Device, Routine, Scene, User, get_db
from models.schemas import ActivityLogResponse, DashboardStats
from services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returnează statisticile agregate pentru dashboard-ul aplicației.
    Toate datele sunt filtrate pentru user-ul curent.
    """
    acum = datetime.now(timezone.utc)
    azi_start = acum.replace(hour=0, minute=0, second=0, microsecond=0)
    treizeci_zile = acum - timedelta(days=30)
    sapte_zile = acum - timedelta(days=7)

    # -----------------------------------------------------------------------
    # Conturi simple
    # -----------------------------------------------------------------------
    total_devices = db.query(func.count(Device.id)).filter(
        Device.owner_id == current_user.id
    ).scalar() or 0

    total_commands_today = db.query(func.count(Command.id)).filter(
        Command.user_id == current_user.id,
        Command.timestamp >= azi_start,
    ).scalar() or 0

    total_routines_active = db.query(func.count(Routine.id)).filter(
        Routine.user_id == current_user.id,
        Routine.is_active == True,  # noqa: E712
    ).scalar() or 0

    total_scenes = db.query(func.count(Scene.id)).filter(
        Scene.owner_id == current_user.id
    ).scalar() or 0

    # -----------------------------------------------------------------------
    # Comenzi din ultimele 30 de zile (pentru analize)
    # -----------------------------------------------------------------------
    comenzi_30_zile = (
        db.query(Command)
        .filter(
            Command.user_id == current_user.id,
            Command.timestamp >= treizeci_zile,
        )
        .all()
    )

    # Cel mai folosit dispozitiv
    if comenzi_30_zile:
        device_counts = Counter(cmd.device_id for cmd in comenzi_30_zile)
        top_device_id = device_counts.most_common(1)[0][0]
        top_device = db.query(Device).filter(Device.id == top_device_id).first()
        most_used_device = top_device.name if top_device else None
    else:
        most_used_device = None

    # Ora de vârf (0–23)
    if comenzi_30_zile:
        ora_counts = Counter(cmd.timestamp.hour for cmd in comenzi_30_zile)
        peak_hour = int(ora_counts.most_common(1)[0][0])
    else:
        peak_hour = None

    # -----------------------------------------------------------------------
    # Comenzi per zi — ultimele 7 zile
    # -----------------------------------------------------------------------
    comenzi_7_zile = (
        db.query(Command)
        .filter(
            Command.user_id == current_user.id,
            Command.timestamp >= sapte_zile,
        )
        .all()
    )

    zi_counts = Counter(cmd.timestamp.date().isoformat() for cmd in comenzi_7_zile)
    commands_by_day = [
        {
            "date": (acum - timedelta(days=i)).date().isoformat(),
            "count": zi_counts.get((acum - timedelta(days=i)).date().isoformat(), 0),
        }
        for i in range(6, -1, -1)
    ]

    # -----------------------------------------------------------------------
    # Top 5 dispozitive după număr de comenzi (30 zile)
    # -----------------------------------------------------------------------
    top5 = (
        db.query(Device.name, func.count(Command.id).label("cnt"))
        .join(Command, Command.device_id == Device.id)
        .filter(Command.user_id == current_user.id, Command.timestamp >= treizeci_zile)
        .group_by(Device.id)
        .order_by(func.count(Command.id).desc())
        .limit(5)
        .all()
    )
    commands_by_device = [{"device_name": row.name, "count": row.cnt} for row in top5]

    # -----------------------------------------------------------------------
    # Distribuție tipuri de dispozitive
    # -----------------------------------------------------------------------
    distributie = (
        db.query(Device.device_type, func.count(Device.id).label("cnt"))
        .filter(Device.owner_id == current_user.id)
        .group_by(Device.device_type)
        .all()
    )
    device_type_distribution = [{"type": row.device_type, "count": row.cnt} for row in distributie]

    return DashboardStats(
        total_devices=total_devices,
        total_commands_today=total_commands_today,
        total_routines_active=total_routines_active,
        total_scenes=total_scenes,
        most_used_device=most_used_device,
        peak_hour=peak_hour,
        commands_by_day=commands_by_day,
        commands_by_device=commands_by_device,
        device_type_distribution=device_type_distribution,
    )


@router.get("/activity", response_model=list[ActivityLogResponse])
def get_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează ultimele 50 activități ale user-ului pentru timeline în app."""
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
        .all()
    )

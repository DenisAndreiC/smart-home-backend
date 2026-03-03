from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import Device, Routine, User, get_db
from models.schemas import RoutineCreate, RoutineResponse, RoutineToggle
from services.auth_service import get_current_user
from services.ml_service import detect_routines, generate_test_data
from services.notification_service import notify_ml_routines_detected
from utils.constants import ML_DAYS_BACK, ML_MIN_OCCURRENCES, ML_TIME_EPSILON
from utils.exceptions import DeviceNotFoundException

router = APIRouter(prefix="/routines", tags=["Rutine"])


def _get_owned_routine(routine_id: int, current_user: User, db: Session) -> Routine:
    """Helper: returnează rutina dacă aparține user-ului curent, altfel 404."""
    rutina = db.query(Routine).filter(
        Routine.id == routine_id,
        Routine.user_id == current_user.id,
    ).first()
    if not rutina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rutina nu a fost găsită")
    return rutina


@router.get("/", response_model=List[RoutineResponse])
def list_routines(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează toate rutinele user-ului curent (manuale + sugerate de ML)."""
    return db.query(Routine).filter(Routine.user_id == current_user.id).all()


@router.post("/", response_model=RoutineResponse, status_code=status.HTTP_201_CREATED)
def create_routine(
    date: RoutineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creează o rutină manuală. Dispozitivul trebuie să aparțină user-ului curent."""
    device = db.query(Device).filter(
        Device.id == date.device_id,
        Device.owner_id == current_user.id,
    ).first()
    if not device:
        raise DeviceNotFoundException()

    rutina_noua = Routine(
        user_id=current_user.id,
        name=date.name,
        device_id=date.device_id,
        action=date.action,
        value=date.value,
        trigger_time=date.trigger_time,
        days_of_week=date.days_of_week,
        is_ml_suggested=False,
        is_active=True,
    )
    db.add(rutina_noua)
    db.commit()
    db.refresh(rutina_noua)
    return rutina_noua


@router.get("/detect")
def detect_ml_routines(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Endpoint demo ML: detectează tipare repetitive și salvează rutinele noi.
    Trimite notificare dacă sunt rutine noi detectate.
    """
    rutine_detectate = detect_routines(
        db,
        current_user.id,
        days_back=ML_DAYS_BACK,
        min_occurrences=ML_MIN_OCCURRENCES,
        time_epsilon_minutes=ML_TIME_EPSILON,
    )

    rutine_noi = 0
    for rutina in rutine_detectate:
        exista = db.query(Routine).filter(
            Routine.user_id == current_user.id,
            Routine.device_id == rutina["device_id"],
            Routine.action == rutina["action"],
            Routine.value == rutina["value"],
            Routine.trigger_time == rutina["trigger_time"],
        ).first()

        if not exista:
            rutina_db = Routine(
                user_id=current_user.id,
                name=rutina["name"],
                device_id=rutina["device_id"],
                action=rutina["action"],
                value=rutina["value"],
                trigger_time=rutina["trigger_time"],
                days_of_week=rutina["days_of_week"],
                is_ml_suggested=True,
                is_active=False,
                confidence=rutina["confidence"],
            )
            db.add(rutina_db)
            rutine_noi += 1

    # Notificăm utilizatorul dacă ML-ul a găsit rutine noi
    if rutine_noi > 0:
        notify_ml_routines_detected(db, current_user.id, rutine_noi)
        db.commit()

    return {
        "routines_detected": len(rutine_detectate),
        "routines_saved": rutine_noi,
        "data": rutine_detectate,
    }


@router.put("/{routine_id}/toggle", response_model=RoutineResponse)
def toggle_routine(
    routine_id: int,
    date: RoutineToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activează sau dezactivează o rutină (inclusiv cele sugerate de ML)."""
    rutina = _get_owned_routine(routine_id, current_user, db)
    rutina.is_active = date.is_active
    db.commit()
    db.refresh(rutina)
    return rutina


@router.delete("/{routine_id}")
def delete_routine(
    routine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Șterge o rutină (manuală sau sugerată de ML)."""
    rutina = _get_owned_routine(routine_id, current_user, db)
    db.delete(rutina)
    db.commit()
    return {"message": "Rutina a fost ștearsă"}


@router.post("/generate-test-data")
def generate_demo_data(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generează 30 de zile de comenzi sintetice pentru demo ML."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.owner_id == current_user.id,
    ).first()
    if not device:
        raise DeviceNotFoundException()

    count = generate_test_data(db, current_user.id, device_id)
    return {"message": f"Generate {count} comenzi de test", "count": count}

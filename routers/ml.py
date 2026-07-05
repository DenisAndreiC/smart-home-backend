# Router for ML-powered recommendations and anomaly detection.
# All endpoints require JWT authentication.

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.db import User, get_db
from models.schemas import (
    AnomalyResponse,
    MLSettingsRequest,
    MLSettingsResponse,
    RecommendationResponse,
)
from services.auth_service import get_current_user
from services.ml_service import detect_anomalies, detect_routines
from utils.constants import ML_DAYS_BACK, ML_TIME_EPSILON

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


@router.get("/recommendations")
def get_recommendations(
    min_occurrences: int | None = Query(default=None, ge=1, le=50, description="Minimum times a pattern must repeat"),
    min_distinct_days: int | None = Query(default=None, ge=1, le=30, description="Minimum distinct calendar days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return routine-pattern recommendations for the authenticated user.

    Uses the SAME detect_routines() function (and thus the same DBSCAN clustering
    and min_occurrences/min_distinct_days filters) as GET /api/routines/detect, so
    the dashboard and the "Select Routines to Create" dialog always show identical
    candidates for identical parameter values.

    Query params:
        min_occurrences:   minimum cluster size (defaults to the user's saved ML setting, or 5).
        min_distinct_days: minimum distinct calendar days a pattern must span (defaults to
                            the user's saved ML setting, or 2). Filters out single-day bursts.
    """
    # Use the user's saved Settings-screen sliders when the caller does not override them
    effective_min = min_occurrences if min_occurrences is not None else (current_user.ml_min_occurrences or 5)
    effective_days = min_distinct_days if min_distinct_days is not None else (current_user.ml_min_days or 2)

    from datetime import timedelta, timezone
    from datetime import datetime

    # Count total commands in the last 30 days for the metadata field
    from database.db import Command
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    total_commands = (
        db.query(Command)
        .filter(Command.user_id == current_user.id, Command.timestamp >= cutoff)
        .count()
    )

    recommendations = detect_routines(
        db,
        current_user.id,
        days_back=ML_DAYS_BACK,
        min_occurrences=effective_min,
        min_distinct_days=effective_days,
        time_epsilon_minutes=ML_TIME_EPSILON,
    )

    return {
        "recommendations": recommendations,
        "analyzed_days": ML_DAYS_BACK,
        "total_commands": total_commands,
    }


@router.get("/anomalies")
def get_anomalies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return anomalous device activity detected in the last 24 hours.

    Compares recent commands against the 30-day baseline using z-score.
    Commands more than 2 standard deviations from the mean time are flagged.
    """
    anomalies = detect_anomalies(current_user.id, db)
    return {
        "anomalies": anomalies,
        "checked_period": "24h",
    }


@router.post("/settings", response_model=MLSettingsResponse)
def update_ml_settings(
    body: MLSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the ML configuration for the authenticated user.

    Body:
        min_occurrences (int, 3-20): minimum repetitions to form a routine pattern.
    """
    current_user.ml_min_occurrences = body.min_occurrences
    current_user.ml_min_days = body.min_days
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return MLSettingsResponse(
        min_occurrences=current_user.ml_min_occurrences,
        min_days=current_user.ml_min_days,
    )


@router.get("/settings", response_model=MLSettingsResponse)
def get_ml_settings(
    current_user: User = Depends(get_current_user),
):
    """Return the current ML settings for the authenticated user."""
    return MLSettingsResponse(
        min_occurrences=current_user.ml_min_occurrences or 5,
        min_days=current_user.ml_min_days or 4,
    )

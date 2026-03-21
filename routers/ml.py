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
from services.ml_service import analyze_user_patterns, detect_anomalies

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


@router.get("/recommendations")
def get_recommendations(
    min_occurrences: int = Query(default=5, ge=1, le=50, description="Minimum times a pattern must repeat"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return DBSCAN-based routine recommendations for the authenticated user.

    Analyzes commands from the last 30 days and groups them by (device, action).
    Each recommendation represents a detected time-of-day pattern.

    Query params:
        min_occurrences: minimum cluster size (defaults to user's saved ML setting).
    """
    # Use user's saved setting when the caller does not override it
    effective_min = min_occurrences if min_occurrences != 5 else (current_user.ml_min_occurrences or 5)

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

    recommendations = analyze_user_patterns(current_user.id, db, effective_min)

    return {
        "recommendations": recommendations,
        "analyzed_days": 30,
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
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return MLSettingsResponse(min_occurrences=current_user.ml_min_occurrences)


@router.get("/settings", response_model=MLSettingsResponse)
def get_ml_settings(
    current_user: User = Depends(get_current_user),
):
    """Return the current ML settings for the authenticated user."""
    return MLSettingsResponse(min_occurrences=current_user.ml_min_occurrences or 5)

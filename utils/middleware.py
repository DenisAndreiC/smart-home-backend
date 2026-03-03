import json
import logging
import time
from typing import Callable

from jose import JWTError, jwt
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import settings
from database.db import ActivityLog, SessionLocal, User

logger = logging.getLogger(__name__)

# Path-uri excluse din logging (nu sunt relevante pentru audit)
_EXCLUDED_PATHS = {"/", "/docs", "/redoc", "/openapi.json"}


class ActivityMiddleware(BaseHTTPMiddleware):
    """
    Middleware care loghează acțiunile mutante (POST, PUT, DELETE, PATCH)
    în tabelul ActivityLog și adaugă header-ul X-Request-Duration.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()

        response = await call_next(request)

        duration_ms = int((time.time() - start) * 1000)
        response.headers["X-Request-Duration"] = f"{duration_ms}ms"

        # Logăm doar metodele care modifică date
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if request.url.path not in _EXCLUDED_PATHS:
                self._log_activity(request, response.status_code, duration_ms)

        return response

    def _log_activity(self, request: Request, status_code: int, duration_ms: int) -> None:
        """Salvează un ActivityLog în DB — erori de logging nu afectează request-ul."""
        try:
            user_id = self._extract_user_id(request)
            ip_address = request.client.host if request.client else None
            entity_type = self._extract_entity_type(request.url.path)
            details = json.dumps({
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": duration_ms,
            })

            db: Session = SessionLocal()
            try:
                log = ActivityLog(
                    user_id=user_id,
                    action=f"{request.method.lower()}.{entity_type or 'unknown'}",
                    entity_type=entity_type,
                    details=details,
                    ip_address=ip_address,
                )
                db.add(log)
                db.commit()
            except Exception as e:
                logger.warning("ActivityLog commit eșuat: %s", e)
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.warning("ActivityMiddleware eroare: %s", e)

    def _extract_user_id(self, request: Request) -> int | None:
        """Decodează JWT din header și returnează user_id (null dacă lipsește/expirat)."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            token = auth[7:]
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            email: str | None = payload.get("sub")
            if not email:
                return None
            # Facem un query rapid pentru user_id
            db: Session = SessionLocal()
            try:
                user = db.query(User).filter(User.email == email).first()
                return user.id if user else None
            finally:
                db.close()
        except (JWTError, Exception):
            return None

    @staticmethod
    def _extract_entity_type(path: str) -> str | None:
        """Deduce tipul entității din path-ul URL."""
        mapping = {
            "/devices": "device",
            "/commands": "command",
            "/routines": "routine",
            "/scenes": "scene",
            "/rooms": "room",
            "/auth": "auth",
            "/notifications": "notification",
        }
        for segment, entity in mapping.items():
            if segment in path:
                return entity
        return None

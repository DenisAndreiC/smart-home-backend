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

# Logger dedicat acestui modul pentru mesaje de debug/warning
logger = logging.getLogger(__name__)

# Path-uri excluse din logging (nu sunt relevante pentru audit trail)
_EXCLUDED_PATHS = {"/", "/docs", "/redoc", "/openapi.json"}


class ActivityMiddleware(BaseHTTPMiddleware):
    """
    Middleware Starlette care intercepteaza toate request-urile HTTP.
    Logheaza actiunile mutante (POST, PUT, DELETE, PATCH) in tabelul ActivityLog.
    Adauga headerul X-Request-Duration cu durata procesarii in milisecunde.
    Erorile de logging nu afecteaza niciodata request-ul principal.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Metoda principala apelata pentru fiecare request HTTP.
        Masoara durata, adauga headerul de timing si logheaza daca e cazul.
        """
        # Inregistreaza timestamp-ul de start pentru calculul duratei
        start = time.time()

        # Executa handler-ul urmator din lantul middleware (sau endpoint-ul final)
        response = await call_next(request)

        # Calculeaza durata in milisecunde
        duration_ms = int((time.time() - start) * 1000)

        # Adauga headerul de timing in raspuns (util pentru debugging si monitoring)
        response.headers["X-Request-Duration"] = f"{duration_ms}ms"

        # Logheaza doar metodele care modifica date (nu GET sau HEAD)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Exclude path-urile de sistem (docs, health check)
            if request.url.path not in _EXCLUDED_PATHS:
                self._log_activity(request, response.status_code, duration_ms)

        return response

    def _log_activity(self, request: Request, status_code: int, duration_ms: int) -> None:
        """
        Salveaza un ActivityLog in DB.
        Toate erorile sunt prinse intern - logging-ul nu blocheaza niciodata request-ul.
        """
        try:
            # Extrage user_id din token-ul JWT din header (None daca lipseste)
            user_id = self._extract_user_id(request)

            # Extrage IP-ul clientului (None daca nu e disponibil)
            ip_address = request.client.host if request.client else None

            # Determina tipul entitatii din URL (device, command, etc.)
            entity_type = self._extract_entity_type(request.url.path)

            # Construieste JSON-ul cu detaliile request-ului pentru audit
            details = json.dumps({
                "method": request.method,       # Metoda HTTP (POST, PUT, etc.)
                "path": request.url.path,       # Path-ul accesat
                "status": status_code,          # Codul de status HTTP returnat
                "duration_ms": duration_ms,     # Durata in milisecunde
            })

            # Deschide o sesiune DB separata (nu folosim Depends pentru middleware)
            db: Session = SessionLocal()
            try:
                # Creeaza inregistrarea in tabelul activity_logs
                log = ActivityLog(
                    user_id=user_id,
                    # Actiunea e compusa din metoda + tipul entitatii (ex: post.device)
                    action=f"{request.method.lower()}.{entity_type or 'unknown'}",
                    entity_type=entity_type,
                    details=details,
                    ip_address=ip_address,
                )
                db.add(log)
                db.commit()
            except Exception as e:
                # Eroarea de commit nu trebuie sa afecteze request-ul principal
                logger.warning("ActivityLog commit esuat: %s", e)
                db.rollback()
            finally:
                # Inchide sesiunea in orice caz
                db.close()
        except Exception as e:
            # Orice alta eroare e prinsa si logata, nu re-ridicata
            logger.warning("ActivityMiddleware eroare: %s", e)

    def _extract_user_id(self, request: Request) -> int | None:
        """
        Decodifica JWT din headerul Authorization si returneaza user_id.
        Returneaza None daca token-ul lipseste, este invalid sau a expirat.
        """
        # Citeste headerul Authorization (gol daca lipseste)
        auth = request.headers.get("Authorization", "")

        # Token-ul JWT trebuie sa inceapa cu "Bearer "
        if not auth.startswith("Bearer "):
            return None

        try:
            # Extrage token-ul fara prefixul "Bearer " (primele 7 caractere)
            token = auth[7:]

            # Decodifica si valideaza token-ul JWT cu secretul din settings
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

            # Extrage email-ul din campul "sub" al payload-ului JWT
            email: str | None = payload.get("sub")
            if not email:
                return None

            # Cauta utilizatorul in DB dupa email pentru a obtine ID-ul numeric
            db: Session = SessionLocal()
            try:
                user = db.query(User).filter(User.email == email).first()
                # Returneaza ID-ul daca userul exista, None altfel
                return user.id if user else None
            finally:
                db.close()
        except (JWTError, Exception):
            # Orice eroare de decodificare returneaza None (nu ridica exceptie)
            return None

    @staticmethod
    def _extract_entity_type(path: str) -> str | None:
        """
        Deduce tipul entitatii din path-ul URL pentru categorisirea in ActivityLog.
        Exemplu: '/api/devices/5' -> 'device'
        """
        # Tabela de mapare segment URL -> tip entitate
        mapping = {
            "/devices": "device",
            "/commands": "command",
            "/routines": "routine",
            "/scenes": "scene",
            "/rooms": "room",
            "/auth": "auth",
            "/notifications": "notification",
        }

        # Cauta primul segment recunoscut in path-ul URL
        for segment, entity in mapping.items():
            if segment in path:
                return entity

        # Returneaza None daca path-ul nu corespunde niciunui tip cunoscut
        return None

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from database.db import Command, Routine, SessionLocal
from services.mqtt_service import mqtt_service

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None

    def start(self):
        """Pornește scheduler-ul async și adaugă job-ul de verificare rutine."""
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._check_routines,
            trigger="interval",
            minutes=1,
            id="check_routines",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Scheduler pornit — rutinele active vor fi verificate la fiecare minut")

    def stop(self):
        """Oprește scheduler-ul la închiderea aplicației."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler oprit")

    def _check_routines(self):
        """
        Job executat la fiecare minut.
        Verifică rutinele active și le execută dacă trigger_time == ora curentă.
        Salvează comenzile cu source='routine' și creează notificări.
        """
        acum = datetime.now(timezone.utc)
        ora_curenta = acum.strftime("%H:%M")
        zi_curenta = str(acum.isoweekday())

        db: Session = SessionLocal()
        try:
            rutine = (
                db.query(Routine)
                .filter(Routine.is_active == True, Routine.trigger_time == ora_curenta)  # noqa: E712
                .all()
            )

            for rutina in rutine:
                zile_active = rutina.days_of_week.split(",")
                if zi_curenta not in zile_active:
                    continue

                try:
                    mqtt_service.publish_command(
                        rutina.device.mqtt_topic,
                        rutina.action,
                        rutina.value,
                    )
                except Exception as e:
                    logger.error("Eroare MQTT pentru rutina %s: %s", rutina.id, e)

                comanda = Command(
                    device_id=rutina.device_id,
                    user_id=rutina.user_id,
                    action=rutina.action,
                    value=rutina.value,
                    source="routine",
                )
                db.add(comanda)

                # Notificare pentru utilizator (import local pentru a evita circular imports)
                try:
                    from services.notification_service import notify_routine_executed
                    notify_routine_executed(db, rutina.user_id, rutina.name)
                except Exception as e:
                    logger.warning("Notificare rutină eșuată: %s", e)

                logger.info(
                    "Rutina %s executată: %s → %s=%s",
                    rutina.id,
                    rutina.device.mqtt_topic,
                    rutina.action,
                    rutina.value,
                )

            if rutine:
                db.commit()

        except Exception as e:
            logger.error("Eroare la verificarea rutinelor: %s", e)
            db.rollback()
        finally:
            db.close()


scheduler_service = SchedulerService()

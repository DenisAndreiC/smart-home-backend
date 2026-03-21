import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from database.db import Command, Routine, SessionLocal
from services.mqtt_service import mqtt_service

# Logger dedicat serviciului de scheduling
logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Serviciu singleton pentru executia automata a rutinelor programate.
    Foloseste APScheduler cu AsyncIOScheduler pentru integrare cu event loop-ul FastAPI.
    Job-ul principal ruleaza la fiecare minut si verifica rutinele active.
    """

    def __init__(self):
        # Scheduler-ul este None pana la apelul start()
        # Tipul AsyncIOScheduler | None permite oprire sigura fara erori
        self._scheduler: AsyncIOScheduler | None = None

    def start(self):
        """
        Porneste scheduler-ul async si adauga job-ul de verificare rutine.
        Apelat la startup-ul aplicatiei din lifespan context manager.
        """
        # Creeaza o instanta noua de AsyncIOScheduler
        self._scheduler = AsyncIOScheduler()

        # Adauga job-ul care verifica rutinele la fiecare minut
        self._scheduler.add_job(
            self._check_routines,   # functia de executat
            trigger="interval",     # trigger bazat pe interval de timp
            minutes=1,              # frecventa: o data pe minut
            id="check_routines",    # ID unic pentru a evita duplicate
            replace_existing=True,  # inlocuieste job-ul daca exista deja
        )

        # Porneste scheduler-ul (se ataseaza la event loop-ul asyncio curent)
        self._scheduler.start()
        logger.info("Scheduler pornit - rutinele active vor fi verificate la fiecare minut")

    def stop(self):
        """
        Opreste scheduler-ul la inchiderea aplicatiei.
        wait=False inseamna ca nu asteapta terminarea job-urilor in curs.
        """
        # Verifica daca scheduler-ul exista si este in stare running
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler oprit")

    def _check_routines(self):
        """
        Job executat la fiecare minut de APScheduler.
        Verifica rutinele active si le executa daca trigger_time == ora curenta.
        Salveaza comenzile cu source='routine' si creeaza notificari pentru user.
        """
        # Obtine ora si ziua curenta in UTC pentru comparatie cu rutinele
        acum = datetime.now(timezone.utc)
        ora_curenta = acum.strftime("%H:%M")       # format HH:MM (ex: "18:30")
        zi_curenta = str(acum.isoweekday())        # ziua saptamanii 1=Luni...7=Duminica

        # Deschide o sesiune DB separata (scheduler nu are acces la Depends)
        db: Session = SessionLocal()
        try:
            # Interogheaza DB pentru rutinele active cu trigger_time egal cu ora curenta
            rutine = (
                db.query(Routine)
                .filter(
                    Routine.is_active == True,          # doar rutinele activate
                    Routine.trigger_time == ora_curenta,  # trigger la ora exacta
                )
                .all()                                  # noqa: E712
            )

            # Itereaza fiecare rutina candidata
            for rutina in rutine:
                # Verifica daca ziua curenta este in lista de zile ale rutinei
                zile_active = rutina.days_of_week.split(",")
                if zi_curenta not in zile_active:
                    continue  # sari rutina daca nu e programata pentru ziua de azi

                try:
                    # Trimite comanda MQTT catre topic-ul dispozitivului tinta
                    mqtt_service.publish_command(
                        rutina.device.mqtt_topic,   # topic-ul dispozitivului
                        rutina.action,              # actiunea de executat
                        rutina.value,               # valoarea parametrului
                    )
                except Exception as e:
                    # Eroarea MQTT nu opreste executia celorlalte rutine
                    logger.error("Eroare MQTT pentru rutina %s: %s", rutina.id, e)

                # Salveaza comanda in istoricul ML cu source='routine'
                comanda = Command(
                    device_id=rutina.device_id,
                    user_id=rutina.user_id,
                    action=rutina.action,
                    value=rutina.value,
                    source="routine",   # sursa 'routine' pentru filtrare in ML
                )
                db.add(comanda)

                # Notificare pentru utilizator (import local pentru a evita circular imports)
                try:
                    from services.notification_service import notify_routine_executed
                    notify_routine_executed(db, rutina.user_id, rutina.name)
                except Exception as e:
                    # Eroarea la notificare nu blocheaza executia rutinei
                    logger.warning("Notificare rutina esuata: %s", e)

                logger.info(
                    "Rutina %s executata: %s -> %s=%s",
                    rutina.id,
                    rutina.device.mqtt_topic,
                    rutina.action,
                    rutina.value,
                )

            # Comite toate comenzile si notificarile dintr-o singura tranzactie
            if rutine:
                db.commit()

        except Exception as e:
            logger.error("Eroare la verificarea rutinelor: %s", e)
            # Rollback pentru a elibera tranzactia blocata
            db.rollback()
        finally:
            # Inchide sesiunea in orice caz (succes sau eroare)
            db.close()


# Instanta singleton pornita si oprita din lifespan-ul aplicatiei
scheduler_service = SchedulerService()

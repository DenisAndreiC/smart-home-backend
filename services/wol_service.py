import logging
import re

from wakeonlan import send_magic_packet

# Logger dedicat serviciului Wake-on-LAN
logger = logging.getLogger(__name__)

# Pattern regex pentru validarea adresei MAC (format AA:BB:CC:DD:EE:FF)
# Accepta atat litere mari cat si mici pentru cifrele hex (A-F / a-f)
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def wake_device(mac_address: str) -> bool:
    """
    Trimite un magic packet Wake-on-LAN catre adresa MAC specificata.
    Pachetul UDP este trimis pe portul 9 (broadcast) catre reteaua locala.
    Returneaza True daca pachetul a fost trimis cu succes, False in caz de eroare.
    """
    # Valideaza formatul adresei MAC inainte de a trimite pachetul
    if not _MAC_PATTERN.match(mac_address):
        logger.warning("Adresa MAC invalida: %s", mac_address)
        return False

    try:
        # Trimite magic packet-ul UDP (255.255.255.255:9) cu adresa MAC
        send_magic_packet(mac_address)
        logger.info("Magic packet trimis catre %s", mac_address)
        return True

    except Exception as e:
        # Orice eroare de retea returneaza False (nu ridica exceptie catre caller)
        logger.error("Eroare la trimiterea magic packet catre %s: %s", mac_address, e)
        return False

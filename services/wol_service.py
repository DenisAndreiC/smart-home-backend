import logging
import re

from wakeonlan import send_magic_packet

logger = logging.getLogger(__name__)

# Pattern pentru validarea adresei MAC (format AA:BB:CC:DD:EE:FF)
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def wake_device(mac_address: str) -> bool:
    """
    Trimite un magic packet Wake-on-LAN către adresa MAC specificată.
    Returnează True dacă pachetul a fost trimis cu succes, False altfel.
    """
    if not _MAC_PATTERN.match(mac_address):
        logger.warning("Adresă MAC invalidă: %s", mac_address)
        return False

    try:
        send_magic_packet(mac_address)
        logger.info("Magic packet trimis către %s", mac_address)
        return True
    except Exception as e:
        logger.error("Eroare la trimiterea magic packet către %s: %s", mac_address, e)
        return False

import serial
from utils.logger import logger

class SerialReader:
    """Classe pour lire depuis un port série (utilisée par VMA405)."""

    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.serial = serial.Serial(port, baudrate, timeout=1)
        logger.info(f"Port série ouvert: {port} ({baudrate} bauds).")

    def read_line(self):
        """Lit une ligne depuis le port série."""
        try:
            line = self.serial.readline().decode('utf-8').strip()
            return line
        except Exception as e:
            logger.error(f"Erreur lecture série: {str(e)}")
            return None

    def close(self):
        """Fermeture du port série."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info("Port série fermé.")

import os
import time
from dotenv import load_dotenv
from mfrc522 import MFRC522
from utils.logger import logger
from utils.exceptions import RFIDInitError, RFIDReadError
from utils.serial_tools import SerialReader
from config.settings import RC522_SPI_DEVICE, RC522_SPI_SPEED

load_dotenv()


class RFIDReader:
    def __init__(self):
        # Récupération du type de lecteur depuis le fichier .env
        self.reader_type = os.getenv("RFID_TYPE", "RC522").upper()
        self.reader = None
        self.serial = None
        self.acr_connection = None

        logger.info(f"Initialisation du lecteur RFID type: {self.reader_type}")

        if self.reader_type == "RC522":
            self._init_rc522()
        elif self.reader_type == "VMA405":
            self._init_vma405()
        elif self.reader_type == "ACR122U":
            self._init_acr122u()
        else:
            logger.error(
                f"Type RFID inconnu: {self.reader_type}. Utilisez RC522, VMA405 ou ACR122U."
            )

    def _init_rc522(self):
        """Initialise le lecteur SPI RC522."""
        try:
            # RC522_SPI_DEVICE et RC522_SPI_SPEED sont lus depuis .env (défaut : SPI0 à 1 MHz)
            self.reader = MFRC522(device=RC522_SPI_DEVICE, spd=RC522_SPI_SPEED)
            logger.info("Lecteur RC522 prêt.")
        except Exception as e:
            logger.error(f"Erreur init RC522: {e}")
            raise RFIDInitError(f"Impossible d'initialiser le RC522 : {e}") from e

    def _init_vma405(self):
        """Initialise le lecteur Série VMA405."""
        port = os.getenv("RFID_SERIAL_PORT", "/dev/ttyUSB0")
        baud = int(os.getenv("RFID_BAUDRATE", 9600))
        try:
            self.serial = SerialReader(port, baud)
            logger.info(f"Lecteur VMA405 prêt sur {port}")
        except Exception as e:
            logger.error(f"Erreur init VMA405: {e}")
            raise RFIDInitError(
                f"Impossible d'initialiser le VMA405 sur {port} : {e}"
            ) from e

    def _init_acr122u(self):
        """Initialise le lecteur USB ACR122U via PC/SC (pyscard).
        Nécessite : pcscd actif + pyscard installé.
        """
        try:
            from smartcard.System import readers as pcsc_readers
        except ImportError:
            raise RFIDInitError(
                "Bibliothèque pyscard manquante. Installez : pip install pyscard"
            )
        try:
            lecteurs = pcsc_readers()
            # On cherche un lecteur dont le nom contient ACR122
            acr = [r for r in lecteurs if "ACR122" in str(r)]
            if not acr:
                raise RFIDInitError(
                    "ACR122U non trouvé. Vérifiez que pcscd est actif et le lecteur branché."
                )
            self.acr_connection = acr[0]
            logger.info(f"Lecteur ACR122U prêt : {acr[0]}")
        except RFIDInitError:
            raise
        except Exception as e:
            logger.error(f"Erreur init ACR122U: {e}")
            raise RFIDInitError(f"Impossible d'initialiser l'ACR122U : {e}") from e

    def read_uid(self):
        """Méthode unifiée pour lire un tag selon le type configuré."""
        if self.reader_type == "RC522":
            return self._read_rc522()
        elif self.reader_type == "VMA405":
            return self._read_vma405()
        elif self.reader_type == "ACR122U":
            return self._read_acr122u()
        return None

    def _read_rc522(self):
        """Lecture spécifique RC522."""
        try:
            # 1. Requête
            (status, TagType) = self.reader.Request(self.reader.PICC_REQIDL)

            if status == self.reader.MI_OK:
                # 2. Anticollision
                (status, uid) = self.reader.Anticoll()

                if status == self.reader.MI_OK:
                    return self._uid_to_hex(uid)
        except Exception as e:
            # On évite de spammer les logs sur des erreurs de lecture VIDES
            pass
        return None

    def _read_vma405(self):
        """Lecture spécifique VMA405 (UART) via SerialReader."""
        if not self.serial:
            return None
        try:
            # SerialReader.read_line() retourne une str déjà décodée et strippée, ou None
            uid_str = self.serial.read_line()
            return uid_str if uid_str else None
        except Exception as e:
            logger.error(f"Erreur lecture VMA405: {e}")
            raise RFIDReadError(f"Erreur lecture VMA405 : {e}") from e

    def _read_acr122u(self):
        """Lecture spécifique ACR122U via APDU PC/SC.
        Commande FF CA 00 00 00 = GET UID (standard ISO 14443).
        Réponse : octets UID + SW1=0x90 + SW2=0x00 si succès.
        """
        # Commande APDU standard pour lire l'UID d'un tag NFC
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        try:
            conn = self.acr_connection.createConnection()
            conn.connect()
            data, sw1, sw2 = conn.transmit(GET_UID)
            conn.disconnect()
            # sw1=0x90 = succès PC/SC
            if sw1 == 0x90 and data:
                return "".join([f"{b:02X}" for b in data])
        except Exception:
            # Pas de carte présente ou badge retiré trop vite — silence voulu
            pass
        return None

    def _uid_to_hex(self, uid):
        """
        Convertit la liste d'entiers [116, 30, 204, 42, 140] en String '741ECC2A'.
        Gère le retrait du Checksum (5ème octet).
        """
        if not uid:
            return None

        # RC522 renvoie souvent 5 octets (4 octets UID + 1 octet Checksum)
        if len(uid) == 5:
            # On vérifie si c'est bien le checksum (XOR des 4 premiers)
            uid = uid[:4]

        # Formatage Hex Majuscule
        return "".join([f"{x:02X}" for x in uid])

    def cleanup(self):
        """Nettoyage des ressources."""
        if self.reader_type == "VMA405" and self.serial:
            self.serial.close()
        # MFRC522 gère son propre SPI, pas de cleanup critique nécessaire ici
        # ACR122U : pas de ressource persistante à fermer (connexion créée à chaque lecture)
        logger.info("Lecteur RFID nettoyé")

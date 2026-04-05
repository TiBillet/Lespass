import os
from dotenv import load_dotenv
from pathlib import Path

# --- Chargement des variables d'environnement ---
load_dotenv()

BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "changeme")
TIREUSE_BEC = os.getenv("TIREUSE_BEC", "CHANGER_CI")
NOM_TIREUSE = os.getenv("NOM_TIREUSE", "Tireuse")
# --- Chemins et répertoires ---
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path("~/tibeer/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)  # Crée le répertoire si inexistant

# --- Configuration RFID ---
RFID_DEVICE = os.getenv("RFID_DEVICE", "serial0")  # Port série pour VMA405
RFID_TIMEOUT = float(os.getenv("RFID_TIMEOUT", "1.0"))  # Timeout en secondes
# RC522 uniquement : bus SPI (0 = SPI0, 1 = SPI1) et vitesse en Hz
RC522_SPI_DEVICE = int(os.getenv("RC522_SPI_DEVICE", "0"))
RC522_SPI_SPEED  = int(os.getenv("RC522_SPI_SPEED", "1000000"))

# --- Configuration Vanne ---
# Utilise GPIO_VANNE pour correspondre au nom lu par hardware/valve.py
GPIO_VANNE = int(os.getenv("GPIO_VANNE", "12"))
VALVE_ACTIVE_HIGH = os.getenv("VALVE_ACTIVE_HIGH", "False").lower() == "true"

# --- Configuration Débitmètre ---
FLOW_CALIBRATION_FACTOR = float(
    os.getenv("FLOW_CALIBRATION_FACTOR", "6.5")
)  # Impulsions/L
# Utilise GPIO_FLOW_SENSOR pour correspondre au nom lu par hardware/flow_meter.py
GPIO_FLOW_SENSOR = int(os.getenv("GPIO_FLOW_SENSOR", "16"))

# --- Configuration Backend ---
BACKEND_HOST = os.getenv("BACKEND_HOST", "localhost")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/rfid/event/"
NETWORK_TIMEOUT = float(os.getenv("NETWORK_TIMEOUT", "5.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# --- Configuration Systemd ---
SYSTEMD_NOTIFY = os.getenv("SYSTEMD_NOTIFY", "False").lower() == "true"

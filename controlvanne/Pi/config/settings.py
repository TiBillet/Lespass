"""
Configuration du client Pi — charge les variables depuis .env.
/ Pi client configuration — loads variables from .env.

LOCALISATION : controlvanne/Pi/config/settings.py

Variables recues de discovery (generees par install.sh) :
- SERVER_URL : URL du tenant Django (ex: https://lespass.mondomaine.tld)
- API_KEY : TireuseAPIKey unique (ex: xxxxxxx.yyyyyyy)
- TIREUSE_UUID : UUID de la TireuseBec (ex: abc123-...)

Variables hardware (configurees par install.sh) :
- RFID_TYPE, GPIO_VANNE, GPIO_FLOW_SENSOR, FLOW_CALIBRATION_FACTOR, etc.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Discovery (recus de POST /api/discovery/claim/) ---
SERVER_URL = os.getenv("SERVER_URL", "https://localhost")
API_KEY = os.getenv("API_KEY", "changeme")
TIREUSE_UUID = os.getenv("TIREUSE_UUID", "")

# Mettre a False pour un serveur de dev avec certificat auto-signe.
# Set to False for a dev server with a self-signed certificate.
SSL_VERIFY = os.getenv("SSL_VERIFY", "True").lower() != "false"

# --- RFID ---
RFID_TYPE = os.getenv("RFID_TYPE", "RC522")
RC522_SPI_DEVICE = int(os.getenv("RC522_SPI_DEVICE", "0"))
RC522_SPI_SPEED = int(os.getenv("RC522_SPI_SPEED", "1000000"))
RFID_SERIAL_PORT = os.getenv("RFID_SERIAL_PORT", "/dev/ttyUSB0")
RFID_BAUDRATE = int(os.getenv("RFID_BAUDRATE", "9600"))

# --- Hardware ---
GPIO_VANNE = int(os.getenv("GPIO_VANNE", "18"))
GPIO_FLOW_SENSOR = int(os.getenv("GPIO_FLOW_SENSOR", "23"))
FLOW_CALIBRATION_FACTOR = float(os.getenv("FLOW_CALIBRATION_FACTOR", "6.5"))
VALVE_ACTIVE_HIGH = os.getenv("VALVE_ACTIVE_HIGH", "True").lower() == "true"

# --- Logs ---
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.getenv("LOG_DIR", "~/tibeer/logs")).expanduser()
LOG_DIR.mkdir(parents=True, exist_ok=True)

# --- Systemd ---
SYSTEMD_NOTIFY = os.getenv("SYSTEMD_NOTIFY", "False").lower() == "true"

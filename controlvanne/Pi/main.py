#!/usr/bin/env python3
"""
Point d'entree du client Pi tireuse connectee.
/ Entry point for the connected tap Pi client.

LOCALISATION : controlvanne/Pi/main.py

Demarrage :
1. Init hardware (RFID, vanne, debitmetre)
2. Ping serveur (verif connectivite + config tireuse)
3. Auth kiosk (cookie session pour Chromium)
4. Lancer Chromium kiosk en arriere-plan
5. Boucle controleur (lecture RFID + controle vanne + API)
"""

import os
import sys
import subprocess
import time
import sqlite3

from dotenv import load_dotenv
load_dotenv()

from utils.logger import logger
from config.settings import SERVER_URL, TIREUSE_UUID, SYSTEMD_NOTIFY
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from controllers.tibeer_controller import TibeerController


def inject_session_cookie(session_key, domain):
    """
    Écrit le cookie sessionid dans la base SQLite de Chromium avant son lancement.
    S'adapte dynamiquement au schéma de la version de Chromium installée.
    Chromium est lancé par kiosk.service/.xinitrc après le signal /tmp/tibeer_cookie_ready.
    / Writes sessionid cookie into Chromium's SQLite store before launch.
    Dynamically adapts to the installed Chromium version's schema.
    Chromium is launched by kiosk.service/.xinitrc after the /tmp/tibeer_cookie_ready signal.
    """
    profile_dir = "/home/sysop/.config/chromium-kiosk"
    db_dir = os.path.join(profile_dir, "Default")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "Cookies")

    # Chromium time = microsecondes depuis 1601-01-01 / Chromium time = microseconds since 1601-01-01
    epoch_diff = 11644473600
    now = (int(time.time()) + epoch_diff) * 1_000_000
    expires = (int(time.time()) + 86400 * 30 + epoch_diff) * 1_000_000  # 30 jours / 30 days

    # Valeurs connues pour toutes les versions de Chromium rencontrées
    # / Known values for all encountered Chromium versions
    known_values = {
        "creation_utc": now,
        "host_key": domain,
        "top_frame_site_key": "",
        "name": "sessionid",
        "value": session_key,
        "encrypted_value": b"",
        "path": "/",
        "expires_utc": expires,
        "is_secure": 1,
        "is_httponly": 1,
        "last_access_utc": now,
        "has_expires": 1,
        "is_persistent": 1,
        "priority": 1,
        "samesite": 0,
        "source_scheme": 2,
        "source_port": 443,
        "last_update_utc": now,
        "source_type": 0,
        "has_cross_site_ancestor": 0,
    }

    conn = sqlite3.connect(db_path)

    # Lire les colonnes réellement présentes dans cette version de Chromium
    # / Read columns actually present in this Chromium version
    cursor = conn.execute("PRAGMA table_info(cookies)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    # Garder uniquement les colonnes qui existent dans ce DB
    # / Keep only columns that exist in this DB
    cols = [c for c in known_values if c in existing_cols]
    vals = [known_values[c] for c in cols]

    placeholders = ",".join(["?" for _ in vals])
    col_list = ",".join(cols)

    conn.execute("DELETE FROM cookies WHERE host_key=? AND name='sessionid'", (domain,))
    conn.execute(f"INSERT INTO cookies ({col_list}) VALUES ({placeholders})", vals)
    conn.commit()
    conn.close()
    logger.info(f"Cookie sessionid injecté pour {domain} ({len(cols)} colonnes)")

    # Signal pour .xinitrc : le cookie est prêt, Chromium peut démarrer
    # / Signal for .xinitrc: cookie is ready, Chromium can start
    open("/tmp/tibeer_cookie_ready", "w").close()


def main():
    """Point d'entree du programme.
    / Program entry point."""
    logger.info("Demarrage TiBeer...")

    # 1. Init hardware / Init hardware
    logger.info("Init hardware...")
    rfid = RFIDReader()
    valve = Valve()
    flow_meter = FlowMeter()
    client = BackendClient()

    # 2. Ping serveur / Ping server
    logger.info("Ping serveur...")
    try:
        ping_result = client.ping()
        if ping_result.get("status") == "pong":
            tireuse_config = ping_result.get("tireuse", {})
            nom = tireuse_config.get("nom", "?")
            logger.info(f"Serveur OK. Tireuse: {nom}")

            # Mettre a jour le facteur de calibration depuis la config serveur
            # / Update calibration factor from server config
            calibration = tireuse_config.get("calibration_factor")
            if calibration:
                flow_meter.set_calibration_factor(calibration)
                logger.info(f"Facteur calibration mis a jour: {calibration}")
        else:
            logger.warning(f"Ping: {ping_result.get('message', 'erreur')}")
    except Exception as e:
        logger.warning(f"Ping echoue (on continue): {e}")

    # 3. Auth kiosk + injection cookie / Auth kiosk + cookie injection
    logger.info("Auth kiosk...")
    try:
        session_key = client.auth_kiosk()
        from urllib.parse import urlparse
        domain = urlparse(SERVER_URL).hostname
        inject_session_cookie(session_key, domain)
    except Exception as e:
        logger.warning(f"Auth kiosk echoue (kiosk indisponible): {e}")

    # 4. Chromium est lancé par kiosk.service/.xinitrc après le signal /tmp/tibeer_cookie_ready
    # /  Chromium is launched by kiosk.service/.xinitrc after the /tmp/tibeer_cookie_ready signal
    kiosk_url = f"{SERVER_URL}/controlvanne/kiosk/{TIREUSE_UUID}/"
    logger.info(f"Kiosk URL : {kiosk_url}")

    # 5. Notification systemd / Systemd notification
    if SYSTEMD_NOTIFY:
        try:
            import systemd.daemon
            systemd.daemon.notify("READY=1")
        except ImportError:
            logger.warning("Module python-systemd manquant.")

    # 6. Boucle controleur / Controller loop
    controller = TibeerController(rfid, valve, flow_meter, client)
    try:
        controller.run()
    except KeyboardInterrupt:
        logger.info("Arret signal (CTRL+C).")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        sys.exit(1)
    finally:
        controller.cleanup()
        logger.info("Processus termine.")


if __name__ == "__main__":
    main()

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
    Chromium est lancé par kiosk.service/.xinitrc — cette fonction prépare le cookie
    à l'avance pour que Chromium le trouve dès le démarrage.
    / Writes the sessionid cookie into Chromium's SQLite store before launch.
    Chromium is launched by kiosk.service/.xinitrc — this function prepares the cookie
    in advance so Chromium finds it on startup.
    """
    profile_dir = "/home/sysop/.config/chromium-kiosk"
    db_dir = os.path.join(profile_dir, "Default")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "Cookies")

    # Chromium time = microsecondes depuis 1601-01-01 / Chromium time = microseconds since 1601-01-01
    epoch_diff = 11644473600
    now = (int(time.time()) + epoch_diff) * 1_000_000
    expires = (int(time.time()) + 86400 * 30 + epoch_diff) * 1_000_000  # 30 jours / 30 days

    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS cookies (
        creation_utc INTEGER NOT NULL UNIQUE PRIMARY KEY,
        host_key TEXT NOT NULL, top_frame_site_key TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL, value TEXT NOT NULL, encrypted_value BLOB DEFAULT '',
        path TEXT NOT NULL, expires_utc INTEGER NOT NULL,
        is_secure INTEGER NOT NULL, is_httponly INTEGER NOT NULL,
        last_access_utc INTEGER NOT NULL, has_expires INTEGER NOT NULL DEFAULT 1,
        is_persistent INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 1,
        samesite INTEGER NOT NULL DEFAULT -1, source_scheme INTEGER NOT NULL DEFAULT 0,
        source_port INTEGER NOT NULL DEFAULT -1, last_update_utc INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("DELETE FROM cookies WHERE host_key=? AND name='sessionid'", (domain,))
    conn.execute(
        """INSERT INTO cookies
        (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value,
         path, expires_utc, is_secure, is_httponly, last_access_utc,
         has_expires, is_persistent, priority, samesite, source_scheme, source_port, last_update_utc)
        VALUES (?,?,'',' sessionid',?,'',' /',?,1,1,?,1,1,1,0,2,443,?)""",
        (now, domain, session_key, expires, now, now),
    )
    conn.commit()
    conn.close()
    logger.info(f"Cookie sessionid injecté pour {domain}")

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

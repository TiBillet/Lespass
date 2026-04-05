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

from dotenv import load_dotenv
load_dotenv()

from utils.logger import logger
from config.settings import SERVER_URL, TIREUSE_UUID, SYSTEMD_NOTIFY
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from controllers.tibeer_controller import TibeerController


def launch_chromium_kiosk(kiosk_url):
    """
    Lance Chromium en mode kiosk sur l'ecran HDMI du Pi.
    / Launches Chromium in kiosk mode on the Pi's HDMI screen.

    Le cookie session est gere par Chromium — le Set-Cookie de auth-kiosk
    est stocke automatiquement pour le domaine du serveur.
    / The session cookie is managed by Chromium — the Set-Cookie from auth-kiosk
    is stored automatically for the server domain.
    """
    try:
        subprocess.Popen(
            [
                "chromium-browser",
                "--kiosk",
                "--noerrdialogs",
                "--disable-infobars",
                "--disable-translate",
                "--disable-features=TranslateUI",
                "--check-for-update-interval=31536000",
                f"--app={kiosk_url}",
            ],
            env={**os.environ, "DISPLAY": ":0"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Chromium kiosk lance sur {kiosk_url}")
    except FileNotFoundError:
        logger.warning("Chromium non trouve — kiosk non demarre (mode headless?)")
    except Exception as e:
        logger.warning(f"Erreur lancement Chromium: {e}")


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

    # 3. Auth kiosk / Auth kiosk
    logger.info("Auth kiosk...")
    try:
        session_key = client.auth_kiosk()
        logger.info("Session kiosk obtenue.")
    except Exception as e:
        logger.warning(f"Auth kiosk echoue (kiosk indisponible): {e}")
        session_key = None

    # 4. Lancer Chromium kiosk / Launch Chromium kiosk
    kiosk_url = f"{SERVER_URL}/controlvanne/kiosk/{TIREUSE_UUID}/"
    launch_chromium_kiosk(kiosk_url)

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

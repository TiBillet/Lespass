#!/usr/bin/env python3
"""
Point d'entree du client Pi tireuse connectee.
/ Entry point for the connected tap Pi client.

LOCALISATION : controlvanne/Pi/main.py

Demarrage :
1. Verif credentials — si absents, mode appairage PIN (port 8080)
2. Init hardware (RFID, vanne, debitmetre)
3. Ping serveur (verif connectivite + config tireuse)
4. Auth kiosk : obtenir un token a usage unique
5. Ecrire l'URL de demarrage kiosk dans /tmp/tibeer_kiosk_url
6. Signaler a xinitrc que Chromium peut demarrer (/tmp/tibeer_cookie_ready)
7. Boucle controleur (lecture RFID + controle vanne + API)
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from utils.logger import logger
from config.settings import SERVER_URL, API_KEY, TIREUSE_UUID, SYSTEMD_NOTIFY
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from controllers.tibeer_controller import TibeerController


def main():
    """Point d'entree du programme. / Program entry point."""
    logger.info("Demarrage TiBeer...")

    # 1. Si le Pi n'est pas appaire (API_KEY ou TIREUSE_UUID absents),
    #    demarrer le serveur de pairing PIN sur le port 8080.
    #    .xinitrc ouvrira Chromium sur http://localhost:8080/
    #    L'admin saisit le PIN depuis l'admin Django, le Pi sauvegarde
    #    les credentials dans .env et redémarre automatiquement.
    # / If the Pi is not paired (API_KEY or TIREUSE_UUID missing),
    #   start the PIN pairing server on port 8080.
    if API_KEY in ("changeme", "", None) or not TIREUSE_UUID:
        logger.warning("Pi non appaire — mode appairage PIN (port 8080)")
        from first.pairing_server import demarrer
        demarrer(logger=logger)
        return

    # 2. Init hardware / Init hardware
    logger.info("Init hardware...")
    rfid = RFIDReader()
    valve = Valve()
    flow_meter = FlowMeter()
    client = BackendClient()

    # 3. Ping serveur / Ping server
    logger.info("Ping serveur...")
    try:
        ping_result = client.ping()
        if ping_result.get("status") == "pong":
            tireuse_config = ping_result.get("tireuse", {})
            nom = tireuse_config.get("nom", "?")
            logger.info(f"Serveur OK. Tireuse: {nom}")
            calibration = tireuse_config.get("calibration_factor")
            if calibration:
                flow_meter.set_calibration_factor(calibration)
                logger.info(f"Facteur calibration mis a jour: {calibration}")
        else:
            logger.warning(f"Ping: {ping_result.get('message', 'erreur')}")
    except Exception as e:
        logger.warning(f"Ping echoue (on continue): {e}")

    # 4. Auth kiosk : obtenir un token a usage unique
    logger.info("Auth kiosk...")
    kiosk_url = f"{SERVER_URL}/controlvanne/kiosk/{TIREUSE_UUID}/"
    try:
        session_key, kiosk_token = client.auth_kiosk()
        kiosk_start_url = f"{kiosk_url}?kiosk_token={kiosk_token}"
        logger.info("Auth kiosk OK")
    except Exception as e:
        logger.warning(f"Auth kiosk echoue (kiosk sans auth): {e}")
        kiosk_start_url = kiosk_url

    # 5. Ecrire l'URL de demarrage pour xinitrc
    try:
        with open("/tmp/tibeer_kiosk_url", "w") as f:
            f.write(kiosk_start_url)
    except Exception as e:
        logger.warning(f"Impossible d'ecrire /tmp/tibeer_kiosk_url: {e}")

    # 6. Signal pour .xinitrc : le kiosk peut demarrer
    open("/tmp/tibeer_cookie_ready", "w").close()
    logger.info(f"Kiosk URL finale : {kiosk_url}")

    # 7. Notification systemd
    if SYSTEMD_NOTIFY:
        try:
            import systemd.daemon
            systemd.daemon.notify("READY=1")
        except ImportError:
            logger.warning("Module python-systemd manquant.")

    # 8. Boucle controleur
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

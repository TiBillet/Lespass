#!/usr/bin/env python3
import sys
import time
import os
import signal
import requests
from dotenv import load_dotenv
from ui.ui_server import run_server
import threading

# Charge les variables d'environnement
load_dotenv()

# Imports projet
from utils.logger import logger
from config.settings import SYSTEMD_NOTIFY
from controllers.tibeer_controller import TibeerController
from network.backend_client import BackendClient

# --- Debug Permissions (Utile pour SystemD) ---
def debug_environment():
    print("--- ENVIRONNEMENT ---")
    print(f"UID: {os.getuid()}, GID: {os.getgid()}")
    if os.path.exists("/dev/gpiochip0"):
        import stat, pwd, grp
        st = os.stat("/dev/gpiochip0")
        print(f"Permissions /dev/gpiochip0: {stat.filemode(st.st_mode)}")
        try:
            print(f"Proprio: {pwd.getpwuid(st.st_uid).pw_name} / Groupe: {grp.getgrgid(st.st_gid).gr_name}")
        except KeyError:
            print("Utilisateur/Groupe ID inconnu au système")
    else:
        print("ATTENTION: /dev/gpiochip0 introuvable!")
# ---------------------------------------------

def _attendre_serveur_ui(timeout_secondes=10):
    """Attend que le serveur Flask UI réponde sur le port 5000.

    Interroge http://localhost:5000 toutes les 0.3 secondes jusqu'à ce qu'il
    réponde ou que le délai maximum soit dépassé. Non bloquant : en cas de
    timeout on logue un avertissement et on continue quand même.
    """
    url = "http://localhost:5000"
    delai_entre_tentatives = 0.3
    temps_debut = time.time()

    while time.time() - temps_debut < timeout_secondes:
        try:
            reponse = requests.get(url, timeout=1)
            if reponse.status_code < 500:
                duree = time.time() - temps_debut
                logger.info(f"Serveur UI prêt en {duree:.1f}s (HTTP {reponse.status_code})")
                return
        except requests.exceptions.ConnectionError:
            # Serveur pas encore démarré, on attend
            pass
        except Exception as erreur_inattendue:
            logger.warning(f"Erreur inattendue lors du test du serveur UI : {erreur_inattendue}")
            return
        time.sleep(delai_entre_tentatives)

    logger.warning(f"Serveur UI non disponible après {timeout_secondes}s — poursuite du démarrage")


def main():
    """Point d'entrée du programme."""
    debug_environment()
    
    logger.info("Démarrage de TiBeer Main...")
    controller = None

    # TODO mettre en service debian sur le pi
    # 1. Démarrer l'interface Web (Flask) dans un thread séparé
    ui_thread = threading.Thread(target=run_server)
    ui_thread.daemon = True # S'arrêtera quand le programme principal s'arrête
    ui_thread.start()
    logger.info("Serveur UI démarré sur le port 5000")
    # TODO: Tester le port 5000 s'il répond
    _attendre_serveur_ui(timeout_secondes=10)

    # Notification Systemd (Ready)
    if SYSTEMD_NOTIFY:
        try:
            import systemd.daemon
            systemd.daemon.notify("READY=1")
        except ImportError:
            logger.warning("Module python-systemd manquant, notification ignorée.")

    # Tentative d'auto-enregistrement auprès de Django
    # Silencieux si le serveur a désactivé le mode (cas normal en production)
    try:
        client = BackendClient()
        resultat = client.register()
        if resultat.get("status") == "created":
            logger.info(f"Tireuse auto-enregistrée sur Django.")
        elif resultat.get("status") == "already_exists":
            logger.info(f"Tireuse déjà connue de Django.")
    except Exception as e:
        logger.warning(f"Auto-enregistrement non critique : {e}")

    try:
        # Création et lancement du contrôleur
        controller = TibeerController()
        controller.run()

    except KeyboardInterrupt:
        logger.info("Arrêt signal (CTRL+C).")
    except Exception as e:
        logger.error(f"Erreur fatale dans le main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Nettoyage final
        if controller:
            logger.info("Exécution du nettoyage final...")
            controller.cleanup()
        logger.info("Processus terminé.")

if __name__ == "__main__":
    main()
# FAIT TODO voir kiosk.env

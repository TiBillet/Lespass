#!/usr/bin/env python3
"""
Vérification complète du matériel connecté au Pi.
Lance : python3 check_hardware.py
Détecte : GPIO/pigpio, lecteurs RFID (SPI/Série/USB), débitmètre, vanne, écran, USB.
"""

import os
import sys
import subprocess

# Chargement du .env si présent, pour lire les pins configurés
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
except ImportError:
    pass

GPIO_VANNE       = int(os.getenv("GPIO_VANNE", "18"))
GPIO_FLOW_SENSOR = int(os.getenv("GPIO_FLOW_SENSOR", "23"))
RFID_TYPE        = os.getenv("RFID_TYPE", "RC522").upper()

OK  = "✅"
NOK = "❌"
WAR = "⚠️ "

resultats = []

def ligne(statut, categorie, detail):
    resultats.append((statut, categorie, detail))
    print(f"  {statut}  {categorie:<28} {detail}")


print()
print("=" * 60)
print("  VÉRIFICATION MATÉRIEL TIBEER")
print("=" * 60)
print()

# ─────────────────────────────────────────────
# 1. SYSTÈME
# ─────────────────────────────────────────────
print("── Système ──────────────────────────────────────")

# Modèle du Pi
try:
    with open("/proc/device-tree/model", "r") as f:
        modele = f.read().strip().replace("\x00", "")
    ligne(OK, "Modèle Pi", modele)
except Exception:
    ligne(WAR, "Modèle Pi", "non détecté (pas un Pi ?)")

# pigpiod
try:
    import pigpio
    pi = pigpio.pi()
    if pi.connected:
        ligne(OK, "pigpiod", f"connecté — version {pi.get_pigpio_version()}")
        pi.stop()
    else:
        ligne(NOK, "pigpiod", "non joignable — sudo systemctl start pigpiod")
except ImportError:
    ligne(NOK, "pigpiod", "bibliothèque pigpio manquante")

print()

# ─────────────────────────────────────────────
# 2. LECTEUR RFID
# ─────────────────────────────────────────────
print("── Lecteur RFID ─────────────────────────────────")
ligne(OK if RFID_TYPE in ("RC522", "VMA405", "ACR122U") else NOK,
      "RFID_TYPE configuré", RFID_TYPE)

# RC522 — SPI
spi_present = os.path.exists("/dev/spidev0.0")
ligne(OK if spi_present else WAR, "SPI /dev/spidev0.0",
      "présent" if spi_present else "absent (SPI désactivé ?)")

# VMA405 — ports série disponibles
ports_serie = []
for dev in sorted(os.listdir("/dev")):
    if dev.startswith(("ttyUSB", "ttyAMA", "ttyS")):
        ports_serie.append(f"/dev/{dev}")

if ports_serie:
    ligne(OK, "Ports série disponibles", ", ".join(ports_serie))
else:
    ligne(WAR, "Ports série disponibles", "aucun")

# ACR122U — PC/SC
try:
    from smartcard.System import readers as pcsc_readers
    lecteurs_pcsc = pcsc_readers()
    acr = [str(r) for r in lecteurs_pcsc if "ACR122" in str(r)]
    if acr:
        ligne(OK, "ACR122U (PC/SC)", acr[0])
    elif lecteurs_pcsc:
        ligne(WAR, "ACR122U (PC/SC)", f"non trouvé — autres lecteurs : {[str(r) for r in lecteurs_pcsc]}")
    else:
        ligne(WAR, "ACR122U (PC/SC)", "aucun lecteur PC/SC détecté")
except ImportError:
    ligne(WAR, "ACR122U (PC/SC)", "pyscard non installé")

print()

# ─────────────────────────────────────────────
# 3. GPIO — VANNE ET DÉBITMÈTRE
# ─────────────────────────────────────────────
print("── GPIO ─────────────────────────────────────────")

try:
    import pigpio
    pi = pigpio.pi()
    if pi.connected:
        # Lecture du mode actuel de chaque pin
        mode_vanne = pi.get_mode(GPIO_VANNE)
        mode_flow  = pi.get_mode(GPIO_FLOW_SENSOR)

        # Mode 0 = INPUT, 1 = OUTPUT
        noms_modes = {0: "INPUT", 1: "OUTPUT", 2: "ALT5", 3: "ALT4",
                      4: "ALT0", 5: "ALT1", 6: "ALT2", 7: "ALT3"}

        ligne(OK, f"GPIO {GPIO_VANNE} (vanne)",
              f"accessible — mode actuel : {noms_modes.get(mode_vanne, mode_vanne)}")
        ligne(OK, f"GPIO {GPIO_FLOW_SENSOR} (débitmètre)",
              f"accessible — mode actuel : {noms_modes.get(mode_flow, mode_flow)}")
        pi.stop()
    else:
        ligne(NOK, "GPIO", "pigpiod non connecté — impossible de lire les pins")
except ImportError:
    ligne(NOK, "GPIO", "pigpio manquant")

print()

# ─────────────────────────────────────────────
# 4. PÉRIPHÉRIQUES USB
# ─────────────────────────────────────────────
print("── USB ──────────────────────────────────────────")

try:
    resultat_lsusb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
    lignes_usb = [l.strip() for l in resultat_lsusb.stdout.splitlines() if l.strip()]
    if lignes_usb:
        for l in lignes_usb:
            # Mise en évidence des périphériques connus
            if "ACR122" in l or "ACS" in l:
                ligne(OK, "USB", f"🏷️  {l}")
            elif "Linux Foundation" in l or "hub" in l.lower():
                ligne(OK, "USB", f"🔌 {l}")
            else:
                ligne(OK, "USB", l)
    else:
        ligne(WAR, "USB", "aucun périphérique détecté")
except FileNotFoundError:
    ligne(WAR, "USB", "lsusb non disponible")
except Exception as e:
    ligne(WAR, "USB", f"erreur lsusb : {e}")

print()

# ─────────────────────────────────────────────
# 5. ÉCRAN
# ─────────────────────────────────────────────
print("── Écran ────────────────────────────────────────")

# Détection via /sys/class/drm (fonctionne sans X11)
drm_path = "/sys/class/drm"
ecrans_connectes = []
if os.path.exists(drm_path):
    for entree in sorted(os.listdir(drm_path)):
        status_file = os.path.join(drm_path, entree, "status")
        if os.path.exists(status_file):
            try:
                with open(status_file) as f:
                    statut = f.read().strip()
                if statut == "connected":
                    ecrans_connectes.append(entree)
                    ligne(OK, f"Écran DRM", f"{entree} → {statut}")
                else:
                    ligne(WAR, f"Écran DRM", f"{entree} → {statut}")
            except Exception:
                pass

if not ecrans_connectes:
    ligne(WAR, "Écran DRM", "aucun écran connecté détecté")

# Vérification DISPLAY (si X11 est démarré)
display = os.getenv("DISPLAY")
if display:
    ligne(OK, "DISPLAY (X11)", f"variable DISPLAY={display}")
else:
    ligne(WAR, "DISPLAY (X11)", "variable DISPLAY absente (X11 non démarré ?)")

print()

# ─────────────────────────────────────────────
# 6. RÉSUMÉ
# ─────────────────────────────────────────────
nb_ok  = sum(1 for s, _, _ in resultats if s == OK)
nb_nok = sum(1 for s, _, _ in resultats if s == NOK)
nb_war = sum(1 for s, _, _ in resultats if s == WAR)

print("=" * 60)
print(f"  RÉSUMÉ : {nb_ok} OK  |  {nb_war} avertissements  |  {nb_nok} erreurs")
print("=" * 60)
print()

if nb_nok > 0:
    sys.exit(1)

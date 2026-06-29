#!/usr/bin/env python3
"""
Test autonome du lecteur RFID ACR122U (USB PC/SC).
Lance : python3 test_rfid_acr122u.py
Prérequis : pcscd actif (sudo systemctl start pcscd), pyscard installé.
"""

import time

print("=" * 50)
print("  TEST LECTEUR ACR122U (USB PC/SC)")
print("=" * 50)

# Vérification que pcscd est actif
import subprocess
resultat = subprocess.run(
    ["systemctl", "is-active", "pcscd"],
    capture_output=True, text=True
)
if resultat.stdout.strip() != "active":
    print("❌ Le service pcscd n'est pas actif.")
    print("   Lancez : sudo systemctl start pcscd")
    exit(1)
print("✅ Service pcscd actif")

# Import pyscard
try:
    from smartcard.System import readers as pcsc_readers
    from smartcard.Exceptions import CardConnectionException, NoCardException
except ImportError:
    print("❌ pyscard non installé. Lancez : pip install pyscard")
    exit(1)

# Listage des lecteurs PC/SC disponibles
lecteurs = pcsc_readers()
if not lecteurs:
    print("❌ Aucun lecteur PC/SC détecté.")
    print("   Vérifiez que l'ACR122U est bien branché.")
    exit(1)

print(f"✅ {len(lecteurs)} lecteur(s) PC/SC détecté(s) :")
for lecteur in lecteurs:
    print(f"     - {lecteur}")

# Sélection de l'ACR122U
acr = [r for r in lecteurs if "ACR122" in str(r)]
if not acr:
    print("❌ Aucun ACR122U dans la liste des lecteurs.")
    exit(1)

lecteur_acr = acr[0]
print(f"✅ ACR122U sélectionné : {lecteur_acr}")
print()
print("📡 En attente d'un badge... (Ctrl+C pour quitter)")
print()

# Commande APDU standard pour lire l'UID d'un tag NFC (ISO 14443)
GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

dernier_uid = None

try:
    while True:
        try:
            conn = lecteur_acr.createConnection()
            conn.connect()
            data, sw1, sw2 = conn.transmit(GET_UID)
            conn.disconnect()

            if sw1 == 0x90 and data:
                uid = "".join([f"{b:02X}" for b in data])
                # Affiche seulement si c'est un nouveau badge (évite le spam)
                if uid != dernier_uid:
                    print(f"✅ Badge détecté — UID : {uid}  (SW: {sw1:02X} {sw2:02X})")
                    dernier_uid = uid
        except Exception:
            # Pas de carte présente — on réinitialise l'UID mémorisé
            if dernier_uid is not None:
                print("   Badge retiré.")
                dernier_uid = None

        time.sleep(0.3)

except KeyboardInterrupt:
    print("\n👋 Test arrêté.")

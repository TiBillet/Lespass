#!/usr/bin/env python3
"""
Test autonome du lecteur RFID RC522 (SPI).
Lance : python3 test_rfid_rc522.py
Prérequis : SPI activé (raspi-config), pigpio installé.
"""

import time

print("=" * 50)
print("  TEST LECTEUR RC522 (SPI)")
print("=" * 50)

# Vérification de la présence du périphérique SPI
import os
if not os.path.exists("/dev/spidev0.0"):
    print("❌ /dev/spidev0.0 introuvable. Activez le SPI via raspi-config.")
    exit(1)
print("✅ /dev/spidev0.0 présent")

# Import de la bibliothèque RC522
try:
    from mfrc522 import MFRC522
except ImportError:
    print("❌ mfrc522 non installé. Lancez : pip install mfrc522-python")
    exit(1)

# Initialisation du lecteur
try:
    reader = MFRC522(device=0, spd=1000000)
    print("✅ RC522 initialisé sur SPI0")
except Exception as e:
    print(f"❌ Erreur d'initialisation RC522 : {e}")
    exit(1)

print()
print("📡 En attente d'un badge... (Ctrl+C pour quitter)")
print()

try:
    while True:
        status, tag_type = reader.Request(reader.PICC_REQIDL)

        if status == reader.MI_OK:
            status, uid = reader.Anticoll()

            if status == reader.MI_OK:
                # RC522 renvoie 5 octets : 4 UID + 1 checksum XOR
                uid_propre = uid[:4]
                uid_hex = "".join([f"{x:02X}" for x in uid_propre])
                print(f"✅ Badge détecté — UID : {uid_hex}")
                # Petite pause pour éviter les lectures multiples du même badge
                time.sleep(1)

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n👋 Test arrêté.")

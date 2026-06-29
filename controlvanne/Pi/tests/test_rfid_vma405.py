#!/usr/bin/env python3
"""
Test autonome du lecteur RFID VMA405 (UART/Série).
Lance : python3 test_rfid_vma405.py [port] [baudrate]
Exemple : python3 test_rfid_vma405.py /dev/ttyUSB0 9600
Prérequis : user dans le groupe dialout (sudo usermod -aG dialout $USER).
"""

import sys
import time

print("=" * 50)
print("  TEST LECTEUR VMA405 (UART/Série)")
print("=" * 50)

# Lecture du port et baudrate depuis les arguments ou le .env
import os

# Arguments en ligne de commande prioritaires sur .env
if len(sys.argv) >= 2:
    port = sys.argv[1]
else:
    # Tentative de lecture depuis .env si présent
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    except ImportError:
        pass
    port = os.getenv("RFID_SERIAL_PORT", "/dev/ttyUSB0")

if len(sys.argv) >= 3:
    baudrate = int(sys.argv[2])
else:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    except ImportError:
        pass
    baudrate = int(os.getenv("RFID_BAUDRATE", "9600"))

print(f"   Port     : {port}")
print(f"   Baudrate : {baudrate}")

# Vérification de la présence du port série
if not os.path.exists(port):
    print(f"❌ Port {port} introuvable.")
    print("   Ports série disponibles :")
    for dev in sorted(os.listdir("/dev")):
        if dev.startswith("ttyUSB") or dev.startswith("ttyAMA") or dev.startswith("ttyS"):
            print(f"     /dev/{dev}")
    exit(1)
print(f"✅ Port {port} présent")

# Import pyserial
try:
    import serial
except ImportError:
    print("❌ pyserial non installé. Lancez : pip install pyserial")
    exit(1)

# Ouverture du port série
try:
    ser = serial.Serial(port, baudrate, timeout=1)
    print(f"✅ Port série ouvert ({baudrate} baud)")
except Exception as e:
    print(f"❌ Impossible d'ouvrir {port} : {e}")
    print("   Vérifiez que votre user est dans le groupe dialout.")
    exit(1)

print()
print("📡 En attente d'un badge... (Ctrl+C pour quitter)")
print()

try:
    while True:
        ligne = ser.readline()
        if ligne:
            uid = ligne.decode("utf-8", errors="ignore").strip()
            if uid:
                print(f"✅ Badge détecté — UID : {uid}")

except KeyboardInterrupt:
    print("\n👋 Test arrêté.")
finally:
    ser.close()

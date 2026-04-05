#!/usr/bin/env python3
"""
Test autonome de l'électrovanne (GPIO).
Lance : python3 test_vanne.py [pin_gpio] [active_high]
Exemple : python3 test_vanne.py 18 false
Prérequis : pigpiod actif (sudo systemctl start pigpiod).
"""

import sys
import time
import os

print("=" * 50)
print("  TEST ÉLECTROVANNE (GPIO)")
print("=" * 50)

# Lecture des paramètres depuis les arguments ou le .env
if len(sys.argv) >= 2:
    gpio_pin = int(sys.argv[1])
else:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    except ImportError:
        pass
    gpio_pin = int(os.getenv("GPIO_VANNE", "18"))

if len(sys.argv) >= 3:
    active_high = sys.argv[2].lower() == "true"
else:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    except ImportError:
        pass
    active_high = os.getenv("VALVE_ACTIVE_HIGH", "False").lower() == "true"

# Niveau logique selon la polarité du relais
niveau_ouvert = 1 if active_high else 0
niveau_ferme = 0 if active_high else 1

print(f"   Pin GPIO (BCM) : {gpio_pin}")
print(f"   Active HIGH    : {active_high}")
print(f"   Niveau OUVERT  : {niveau_ouvert}")
print(f"   Niveau FERMÉ   : {niveau_ferme}")

# Import pigpio
try:
    import pigpio
except ImportError:
    print("❌ pigpio non installé. Lancez : pip install pigpio")
    exit(1)

# Connexion au daemon pigpiod
pi = pigpio.pi()
if not pi.connected:
    print("❌ Impossible de se connecter à pigpiod.")
    print("   Lancez : sudo systemctl start pigpiod")
    exit(1)
print("✅ pigpiod connecté")

# Configuration du pin en sortie, vanne fermée par défaut
pi.set_mode(gpio_pin, pigpio.OUTPUT)
pi.write(gpio_pin, niveau_ferme)
print(f"✅ GPIO {gpio_pin} configuré — Vanne FERMÉE")
print()


def ouvrir():
    pi.write(gpio_pin, niveau_ouvert)
    print(f"🟢 Vanne OUVERTE  (GPIO {gpio_pin} = {niveau_ouvert})")


def fermer():
    pi.write(gpio_pin, niveau_ferme)
    print(f"🔴 Vanne FERMÉE   (GPIO {gpio_pin} = {niveau_ferme})")


print("Commandes : [o] Ouvrir  [f] Fermer  [t] Test cycle auto  [q] Quitter")
print()

try:
    while True:
        choix = input(">>> ").strip().lower()

        if choix == "o":
            ouvrir()

        elif choix == "f":
            fermer()

        elif choix == "t":
            # Cycle automatique : ouverture 3s, fermeture 3s, répété 3 fois
            print("🔄 Cycle de test : 3 ouvertures/fermetures de 3 secondes...")
            for i in range(3):
                ouvrir()
                time.sleep(3)
                fermer()
                time.sleep(3)
            print("✅ Cycle terminé.")

        elif choix == "q" or choix == "quit":
            break

        else:
            print("   Commandes valides : o / f / t / q")

except KeyboardInterrupt:
    pass
finally:
    # Sécurité : toujours fermer la vanne en quittant
    pi.write(gpio_pin, niveau_ferme)
    pi.stop()
    print("\n👋 Vanne fermée. Test arrêté.")

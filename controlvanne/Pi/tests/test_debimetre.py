#!/usr/bin/env python3
"""
Test autonome du débitmètre (capteur à effet Hall).
Lance : python3 test_debimetre.py [pin_gpio] [facteur_calibration]
Exemple : python3 test_debimetre.py 23 6.5
Prérequis : pigpiod actif (sudo systemctl start pigpiod).
"""

import sys
import time
import os

print("=" * 50)
print("  TEST DÉBITMÈTRE (Capteur Hall)")
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
    gpio_pin = int(os.getenv("GPIO_FLOW_SENSOR", "23"))

if len(sys.argv) >= 3:
    facteur = float(sys.argv[2])
else:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    except ImportError:
        pass
    facteur = float(os.getenv("FLOW_CALIBRATION_FACTOR", "6.5"))

print(f"   Pin GPIO (BCM) : {gpio_pin}")
print(f"   Facteur        : {facteur} impulsions/(L/min)")

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
print(f"✅ Écoute sur GPIO {gpio_pin}")
print()

# Compteur d'impulsions (modifié dans le callback GPIO)
compteur_impulsions = {"total": 0, "depuis_derniere_mesure": 0}
temps_derniere_mesure = time.time()

def callback_impulsion(gpio, niveau, tick):
    """Appelé à chaque impulsion du capteur Hall."""
    compteur_impulsions["total"] += 1
    compteur_impulsions["depuis_derniere_mesure"] += 1

# Configuration du pin en entrée avec résistance pull-up
pi.set_mode(gpio_pin, pigpio.INPUT)
pi.set_pull_up_down(gpio_pin, pigpio.PUD_UP)
cb = pi.callback(gpio_pin, pigpio.FALLING_EDGE, callback_impulsion)

print("💧 Faites couler de l'eau pour tester (Ctrl+C pour quitter)")
print()
print(f"{'Débit (cl/min)':>16}  {'Volume total (cl)':>18}  {'Impulsions':>12}")
print("-" * 52)

try:
    while True:
        time.sleep(1.0)

        maintenant = time.time()
        duree = maintenant - temps_derniere_mesure

        # Calcul du débit : fréquence / facteur = L/min
        impulsions_intervalle = compteur_impulsions["depuis_derniere_mesure"]
        frequence_hz = impulsions_intervalle / duree
        debit_l_min = frequence_hz / facteur
        debit_cl_min = debit_l_min * 100

        # Calcul du volume total : impulsions_totales / (facteur * 60) = litres
        volume_total_l = compteur_impulsions["total"] / (facteur * 60)
        volume_total_cl = volume_total_l * 100

        print(f"{debit_cl_min:>14.1f}  {volume_total_cl:>18.1f}  {compteur_impulsions['total']:>12}")

        # Réinitialisation du compteur d'intervalle
        compteur_impulsions["depuis_derniere_mesure"] = 0
        temps_derniere_mesure = maintenant

except KeyboardInterrupt:
    print()
    print(f"👋 Test arrêté.")
    print(f"   Volume total mesuré : {compteur_impulsions['total'] / (facteur * 60) * 100:.1f} cl")
    print(f"   Impulsions totales  : {compteur_impulsions['total']}")
finally:
    cb.cancel()
    pi.stop()

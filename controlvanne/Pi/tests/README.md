# Tests matériel TiBeer

Scripts autonomes pour valider le câblage et les périphériques, **sans lancer le service tibeer**.

Tous les scripts lisent les valeurs par défaut depuis `../  .env` si présent, et acceptent des arguments en ligne de commande pour surcharger.

## Prérequis communs

```bash
source /home/sysop/tibeer/.venv/bin/activate
cd /home/sysop/tibeer/tests
```

## Scripts disponibles

### `check_hardware.py` — Diagnostic global

Vérifie tout d'un coup : pigpiod, SPI, ports série, ACR122U, GPIO vanne/débitmètre, USB, écran.

```bash
python3 check_hardware.py
```

---

### `test_rfid_rc522.py` — Lecteur RC522 (SPI)

```bash
python3 test_rfid_rc522.py
```

---

### `test_rfid_vma405.py` — Lecteur VMA405 (UART)

```bash
python3 test_rfid_vma405.py                      # utilise .env
python3 test_rfid_vma405.py /dev/ttyUSB0 9600    # surcharge
```

---

### `test_rfid_acr122u.py` — Lecteur ACR122U (USB PC/SC)

```bash
sudo systemctl start pcscd   # si pas encore actif
python3 test_rfid_acr122u.py
```

---

### `test_debimetre.py` — Débitmètre (capteur Hall)

Affiche débit (cl/min) et volume cumulé en temps réel.

```bash
python3 test_debimetre.py                # utilise .env
python3 test_debimetre.py 23 6.5         # pin GPIO, facteur calibration
```

---

### `test_vanne.py` — Électrovanne (GPIO)

Mode interactif : ouvrir / fermer / cycle automatique.

```bash
python3 test_vanne.py                    # utilise .env
python3 test_vanne.py 18 false           # pin GPIO, polarité
```

Commandes : `o` ouvrir · `f` fermer · `t` cycle 3×3s · `q` quitter

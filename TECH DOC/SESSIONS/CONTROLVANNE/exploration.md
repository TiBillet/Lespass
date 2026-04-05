Voilà un récap complet et structuré pour Claude Code.

---

# Contexte projet — TiHeure / TiBillet cashless bière pression

## Ce qu'on est en train de construire

**TiHeure** est une nouvelle application de l'écosystème TiBillet. C'est une tireuse à bière connectée avec paiement cashless par badge NFC. Le code source est déjà initié : `https://github.com/TiBillet/tiheureuse`

Architecture deux parties :
- **Pi** — client embarqué sur Raspberry Pi (Python), gère le NFC, l'électrovanne, le débitmètre
- **Django** — serveur central (LaBoutik/TiBillet), gère les cartes, les soldes, les historiques

---

## Matériel retenu et validé

| Composant | Référence | Rôle | Tension |
|---|---|---|---|
| Raspberry Pi | **3B+** (pas 3B ni Zero) | Cerveau — PoE natif via header 4 broches | 5V via PoE HAT |
| PoE HAT | **Waveshare PoE HAT (C)** | Alimentation depuis RJ45 — sort 5V (Pi) + 12V (header 2P) | Budget 25W |
| Lecteur NFC | **MFRC522 RC522** | Lecture badges Mifare 13,56 MHz via SPI | 3,3V strictement |
| Débitmètre | **DIGMESA 934-6550** | Turbine à effet Hall, sortie open-collector NPN, impulsions | 3,3–24V DC |
| Module relais | **Handsontec 1 canal optocouplé** | Commutation 12V vers électrovanne | 5V bobine / 3,3V signal |
| Électrovanne | **ASCO SCG283A012V** | 12V DC, normalement fermée | 12V DC ~800mA |
| Diode protection | **1N4007** | Flyback sur bobine électrovanne (côté bornes à vis relais) | — |

**⚠️ Notes matériel importantes :**
- Le Pi 3B+ a le connecteur PoE 4 broches — pas le 3B ni le 3A+ ni le Zero
- Le PoE HAT (C) est pour Pi 3B+/4B — le HAT (F) est pour Pi 5 uniquement
- Le budget puissance total est ~12,8W sur 25W max — très confortable
- La diode flyback du module relais protège sa propre bobine (intégrée) mais PAS la bobine de l'électrovanne — la 1N4007 externe est nécessaire côté ASCO

---

## Câblage GPIO validé (BCM, Pi 3B+)

| Pin physique | GPIO BCM | Fonction | Périphérique |
|---|---|---|---|
| Pin 1 | — | 3,3V | VCC NFC + VCC débitmètre + VCC signal relais |
| Pin 2 | — | 5V | JD-VCC bobine relais |
| Pin 6 | — | GND | NFC + débitmètre + relais |
| Pin 11 | **GPIO 17** | Entrée interrupt pull-up | Débitmètre DIGMESA — impulsions |
| Pin 19 | **GPIO 10** | SPI0 MOSI | MFRC522 |
| Pin 21 | **GPIO 9** | SPI0 MISO | MFRC522 |
| Pin 22 | **GPIO 25** | Sortie RST | MFRC522 reset |
| Pin 23 | **GPIO 11** | SPI0 SCLK | MFRC522 horloge |
| Pin 24 | **GPIO 8** | SPI0 CE0 | MFRC522 chip select |
| Pin 37 | **GPIO 26** | Sortie relais | Module relais — commande électrovanne |

**⚠️ Attention au README existant** : le README du repo utilise GPIO 18 pour la vanne et GPIO 23 pour le débitmètre — à mettre à jour avec les valeurs ci-dessus si on garde ce câblage.

**⚠️ Jumper VCC–JD-VCC** du module relais : à retirer impérativement avant tout branchement.

---

## Ce qu'on a découvert sur le terrain

La cave du bar où sera installé TiHeure contient un **système professionnel existant** composé de :
- Une **carte contrôleur avec port Ethernet** (fabricant en faillite, code source inaccessible)
- Des **Cellarbuoy FOB détecteurs** (deux modèles : un avec cosses externes vertes/oranges, un intégré référence M2400667 daté 05-24)
- Les Cellarbuoys ont un **capteur électrique** (probablement reed switch magnétique couplé au flotteur) qui envoie un signal à la carte quand un fût est vide
- Ce système gère uniquement le **monitoring cave** (alertes fût vide, comptage par fût) — il n'a **pas** d'électrovanne ni de débitmètre
- L'électrovanne ASCO 12V DC et le débitmètre DIGMESA seront installés **au bar**, sur le circuit de tirage, complètement indépendants du système cave

**Piste future explorée** : reverse engineering du protocole réseau de la carte contrôleur cave (tcpdump/nmap sur le trafic Ethernet) pour récupérer les infos "fût vide" et les intégrer dans TiHeure. Pas encore implémenté.

---

## Architecture logicielle

```
Badge NFC (MFRC522)
    │ UID carte
    ▼
Pi 3B+ — main.py
    │ HTTP/WebSocket
    ▼
Django (LaBoutik/TiBillet)
    │ → vérif solde
    │ → autorisation tirage
    ▼
Pi reçoit "OK + volume autorisé"
    │
    ├── GPIO 26 → relais → ASCO → ouvre la bière
    ├── GPIO 17 → débitmètre → compte les mL
    └── Quand volume atteint → ferme relais → arrête la bière
    │
    ▼
Django ← volume réel consommé → débite le solde
```

---

## Stack technique

**Pi (Python) :**
- `pigpio` — gestion GPIO (déjà dans le install.sh)
- `mfrc522` — lecture RFID
- `python-dotenv` — config via `.env`
- `systemd-python` — intégration service
- `requests` / WebSocket — communication Django
- Services systemd : `tibeer.service` + `kiosk.service`

**Serveur Django :**
- Django + Django Channels (WebSocket)
- `uv` comme gestionnaire de dépendances
- Django Unfold pour l'admin
- Daphne comme serveur ASGI
- Modèles : `Card`, `TireuseBec`, `Fut`, `RfidSession`

**Kiosque :**
- Openbox + Chromium en mode kiosk
- `xinit` lancé par systemd
- URL : `http://<django>/?tireuse_bec=<uuid>`

---

## Fichiers clés du repo

```
tiheureuse/
├── Pi/
│   ├── main.py                    # Point d'entrée orchestrateur
│   ├── controllers/tibeer_controller.py
│   ├── hardware/
│   │   ├── rfid_reader.py         # RC522 SPI
│   │   ├── valve.py               # Électrovanne GPIO
│   │   └── flow_meter.py          # Débitmètre impulsions
│   ├── network/backend_client.py  # API Django
│   ├── install.sh                 # Script install complet
│   └── .env                       # Config générée à l'install
├── controlvanne/
│   ├── models.py
│   ├── views.py                   # API Pi (authorize, events)
│   ├── consumers.py               # WebSocket Channels
│   └── admin.py                   # Unfold
└── vanneweb/                      # Settings Django
```

---

## Points de vigilance pour Claude Code

1. **GPIO 17 vs GPIO 23** : le `.env` du install.sh dit `GPIO_FLOW_SENSOR=23` mais notre câblage validé utilise GPIO 17 (Pin 11). À harmoniser.

2. **GPIO 18 vs GPIO 26** : le `.env` dit `GPIO_VANNE=18` mais notre câblage utilise GPIO 26 (Pin 37). À harmoniser.

3. **Le débitmètre DIGMESA** est en open-collector NPN — il faut activer le pull-up interne : `GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)` ou l'équivalent pigpio.

4. **Logique active LOW** sur le relais Handsontec — `GPIO LOW = relais fermé = électrovanne ouverte`. Le `.env` a `VALVE_ACTIVE_HIGH=False` ce qui est correct.

5. **SPI doit être activé** dans raspi-config avant que le MFRC522 fonctionne — le install.sh le fait via `sudo raspi-config nonint do_spi 0`.

6. **Calibration débitmètre** : le DIGMESA 934-6550 génère un nombre d'impulsions par litre à calibrer empiriquement — le `.env` a `FLOW_CALIBRATION_FACTOR=6.5` comme valeur par défaut à ajuster.

7. **Velxio** (simulateur open-source AGPLv3 auto-hébergeable via Docker) peut être utile pour tester la logique GPIO sans matériel : `docker run -d -p 3080:80 ghcr.io/davidmonterocrespo24/velxio:master` — supporte Pi 3 via QEMU mais la console Python est encore en beta.



Parfait, c'est la bonne décision architecturale. Voici le contexte complet à donner à Claude Code pour l'audit.

---

# Brief Claude Code — Audit `controlvanne` + intégration Lespass

## Objectif

Auditer l'app Django `controlvanne` (issue du repo `tiheureuse`) puis la déplacer et l'intégrer dans **Lespass** (le frontend/backend principal de TiBillet).

---

## Contexte écosystème TiBillet

```
Lespass          — Django, frontend e-commerce, landing pages, memberships
LaBoutik         — Django, POS cashless, paiements NFC
Fedow            — Django, portefeuille fédéré, transactions inter-instances
controlvanne     — NOUVELLE app à intégrer dans Lespass
```

Lespass utilise :
- **django-tenants** (multi-tenancy PostgreSQL)
- **DRF** (Django REST Framework)
- **Django Unfold** pour l'admin
- **AGPLv3**
- Stack Docker-based

---

## Ce que fait `controlvanne`

Gestion de tireuses à bière connectées avec paiement cashless NFC :

- Autorisation de tirage via badge RFID (solde wallet Fedow)
- Contrôle électrovanne GPIO (Pi 3B+ → relais → ASCO 12V DC)
- Comptage de débit en temps réel (débitmètre DIGMESA impulsions Hall)
- Interface kiosk HDMI (Chromium plein écran)
- WebSocket temps réel (Django Channels)
- Admin : cartes, fûts, historiques, calibration, exports CSV

---

## Matériel Pi côté terrain

| Composant | Détail |
|---|---|
| Pi 3B+ | GPIO 40 broches, PoE natif |
| Waveshare PoE HAT (C) | 5V Pi + 12V header 2P |
| MFRC522 RC522 | SPI — GPIO 8/9/10/11/25 |
| DIGMESA 934-6550 | Débitmètre Hall — GPIO 17, pull-up interne |
| Relais Handsontec 1ch | GPIO 26, actif LOW |
| ASCO SCG283A012V | Électrovanne 12V DC |

---

## Ce qu'on demande à Claude Code

### Étape 1 — Audit de l'existant

Lire et analyser le contenu de `tiheureuse/controlvanne/` :
- `models.py` — quels modèles existent, sont-ils compatibles avec les modèles Lespass (Card, Wallet, Organisation...) ?
- `views.py` — API Pi : quels endpoints, quelle auth ?
- `consumers.py` — WebSocket : quel protocole, quels events ?
- `admin.py` — Unfold : quels ModelAdmin, quels inline ?
- Dépendances manquantes vs ce qui est déjà dans Lespass

### Étape 2 — Plan de déplacement

Proposer comment intégrer `controlvanne` dans Lespass :
- Compatibilité django-tenants (les tireuses sont-elles par tenant ?)
- Liens avec les modèles existants de Lespass (Membership, Card, etc.)
- Ce qui est à garder, ce qui est à réécrire, ce qui est redondant

### Étape 3 — Plan d'implémentation

Une fois l'audit fait, produire un plan ordonné pour Claude Code :
- Ordre des fichiers à créer/modifier
- Migrations à prévoir
- Endpoints API Pi à valider
- Tests à écrire

---

## Repo sources

- `tiheureuse` : `https://github.com/TiBillet/tiheureuse`
- `Lespass` : dépôt local TiBillet (à cloner si pas déjà là)

---

## Philosophie de code TiBillet (FALC)

- Code **très verbeux**, noms de variables **explicites**
- Commentaires **bilingues FR/EN**
- **DRF** plutôt que Django Forms
- Pas de magie, pas d'abstraction inutile
- **Readable by a human first**
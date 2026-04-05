# 🍺 TiHeure — Tireuse à boissons connectée

> Transformez n'importe quelle tireuse en un système cashless connecté : badge RFID, comptage de débit en temps réel, interface kiosk sur écran, et administration web complète.

TiHeure est composé de deux parties :
- **Pi** — le client embarqué sur Raspberry Pi (Python)
- **Django** — le serveur central (gestion des cartes, des tireuses, des historiques)

Projet open source — licence AGPLv3 — fabriqué par la [Coopérative Code Commun](https://codecommun.coop), membre de l'écosystème [TiBillet](https://tibillet.org).

---

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 🏷️ **Badge RFID** | Lecture de cartes Mifare via RC522 |
| 🚰 **Contrôle de vanne** | Ouverture/fermeture GPIO selon solde et stock |
| 📏 **Débitmétrie** | Comptage d'impulsions Hall, calibration depuis l'admin |
| 📡 **Temps réel** | Synchronisation via WebSocket (Django Channels) |
| 🖥️ **Kiosk** | Chromium plein écran, jauge de fût, grille de prix |
| 🔧 **Maintenance** | Cartes dédiées pour le rinçage, historique de nettoyage |
| 📊 **Admin** | Interface Django Unfold : cartes, fûts, historiques, exports CSV |
| 🍻 **Multi-tireuses** | Gestion de plusieurs tireuses indépendantes |

---

## 🛠️ Matériel requis

### Électronique

| Composant | Détail |
|---|---|
| Raspberry Pi | Testé sur Pi 3B+ (tout modèle avec GPIO) |
| Hat GPIO | Bornier pour connexions sans soudure |
| Lecteur RFID | Module RC522 (SPI) |
| Débitmètre | Capteur à effet Hall, 3 fils (ex : YF-S201, FS300A) |
| Électrovanne | 12V ou 24V pilotée via relais |
| Relais | Isolation circuit de puissance |
| Écran | HDMI ou tactile |

### Logiciel (poste de préparation)

- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) pour flasher la carte SD
- Votre clé SSH publique (à injecter via Imager pour l'accès SSH au Pi)

---

## 🔌 Câblage GPIO (BCM, valeurs par défaut)

| Composant | Pin BCM | Rôle |
|---|:---:|---|
| Électrovanne | GPIO 18 | Commande du relais |
| Débitmètre | GPIO 23 | Entrée impulsions |
| RFID SDA | GPIO 8 (CE0) | SPI Chip Select |
| RFID SCK | GPIO 11 | SPI Clock |
| RFID MOSI | GPIO 10 | SPI MOSI |
| RFID MISO | GPIO 9 | SPI MISO |
| RFID RST | GPIO 25 | Reset RC522 |

> Toutes ces valeurs sont modifiables dans `/home/sysop/tibeer/.env` après installation.

![Schéma de câblage](Pi/asset/Cnx%20Pi.png)

---

## ⚙️ Installation du Pi

### 1. Préparer la carte SD

Dans **Raspberry Pi Imager** :
- OS : `Raspberry Pi OS (Other)` → `Raspberry Pi OS (Legacy, 32-bit) Lite`
- Activer SSH, injecter votre clé publique
- Nom d'utilisateur : **`sysop`**

### 2. Lancer l'installation

Connectez-vous en SSH au Pi, puis exécutez cette commande unique :

```bash
wget https://raw.githubusercontent.com/TiBillet/tiheureuse/master/Pi/install.sh && chmod +x install.sh && ./install.sh
```

> Le dépôt est public — **aucune clé SSH GitHub n'est requise**.

### 3. Répondre aux questions du script

Le script est interactif et ne demande que l'essentiel :

```
🔹 Adresse du serveur Django   →  http://192.168.1.10:8000
🔹 UUID de la tireuse          →  (visible dans l'admin Django)
🔹 Branche Git                 →  master  (Entrée pour valider)
🔹 Clé API partagée            →  (AGENT_SHARED_KEY dans settings.py)
```

### 4. Ce que le script fait automatiquement

- Mise à jour système et installation des dépendances
- Clonage du dépôt via HTTPS
- Création de l'environnement virtuel Python
- Génération du fichier `.env`
- Configuration GPIO, affichage kiosk (Openbox + Chromium)
- Activation des services systemd `tibeer.service` et `kiosk.service`
- Mise à jour automatique du code à chaque démarrage (`git pull`)

---

## 🖥️ Installation du serveur Django

### Prérequis

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (gestionnaire d'environnements et de dépendances)

### Lancer le serveur

```bash
# Cloner le dépôt
git clone https://github.com/TiBillet/tiheureuse.git
cd tiheureuse

# Créer l'environnement virtuel et installer les dépendances
uv sync

# Migrations
uv run python manage.py migrate

# Créer un superutilisateur
uv run python manage.py createsuperuser

# Lancer avec Daphne (WebSocket requis)
uv run daphne -b 0.0.0.0 -p 8000 vanneweb.asgi:application
```

> L'interface d'administration est accessible sur `http://<ip>:8000/admin/`

---

## 📝 Configuration `.env` (Pi)

Généré automatiquement par le script, situé dans `/home/sysop/tibeer/.env` :

```env
TIREUSE_BEC=<uuid-de-la-tireuse>
API_URL=http://192.168.1.10:8000
BACKEND_API_KEY=votre_cle_partagee

# GPIO (BCM)
GPIO_VANNE=18
GPIO_FLOW_SENSOR=23
RC522_RST_PIN=22
RC522_SDA_PIN=24

# Git (mise à jour auto au démarrage)
GIT_REPO=https://github.com/TiBillet/tiheureuse.git
GIT_BRANCH=master
```

> L'UUID de la tireuse se trouve dans l'admin Django : **Exploitation → Tireuses**.

---

## 📂 Structure du projet

```
tiheureuse/
├── Pi/                         # Code embarqué Raspberry Pi
│   ├── main.py                 # Point d'entrée (orchestrateur)
│   ├── controllers/
│   │   └── tibeer_controller.py   # Détection des événements carte
│   ├── hardware/
│   │   ├── rfid_reader.py         # Lecteur RC522
│   │   ├── valve.py               # Contrôle électrovanne
│   │   └── flow_meter.py          # Débitmètre (impulsions Hall)
│   ├── network/
│   │   └── backend_client.py      # Communication avec Django
│   ├── install.sh                 # Script d'installation automatique
│   └── git-update.sh              # Mise à jour au démarrage
│
├── controlvanne/               # Application Django principale
│   ├── models.py               # Card, TireuseBec, Fut, RfidSession…
│   ├── views.py                # API pour le Pi (authorize, events)
│   ├── consumers.py            # WebSocket (Django Channels)
│   ├── admin.py                # Interface d'administration (Unfold)
│   └── calibration_views.py   # Wizard de calibration débitmètre
│
├── templates/
│   ├── controlvanne/           # Interface kiosk (panel Bootstrap)
│   └── calibration/            # Wizard HTMX de calibration
│
└── vanneweb/                   # Configuration Django (settings, urls, asgi)
```

---

## 🖥️ Commandes utiles

### Sur le Pi

```bash
# Voir les logs en temps réel
sudo journalctl -u tibeer -f

# Redémarrer les services
sudo systemctl restart tibeer.service kiosk.service

# Arrêter les services
sudo systemctl stop tibeer.service kiosk.service

# Accéder à l'environnement virtuel
source /home/sysop/tibeer/.venv/bin/activate
```

### Sur le serveur Django

```bash
# Lancer le serveur (développement)
uv run daphne -b 0.0.0.0 -p 8000 vanneweb.asgi:application

# Appliquer les migrations
uv run python manage.py migrate

# Reconstruire les fichiers statiques
uv run python manage.py collectstatic --no-input

# Ajouter une dépendance
uv add <package>
```

---

## 🤝 Contribution

Projet membre de l'écosystème **TiBillet** (Lespass, LaBoutik, Fedow).
Licence **AGPLv3** — contributions bienvenues via pull request.

- Issues : [github.com/TiBillet/tiheureuse/issues](https://github.com/TiBillet/tiheureuse/issues)
- Coopérative : [codecommun.coop](https://codecommun.coop)

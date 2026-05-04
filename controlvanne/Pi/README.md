# TiBeer Pi — Client Raspberry Pi

Client pour tireuse à bière connectée au système cashless TiBillet.  
Gère la lecture NFC, le contrôle de vanne et la communication avec le serveur Lespass.

## Prérequis matériels

- Raspberry Pi (testé sur Bookworm 64-bit)
- Lecteur RFID : RC522 (SPI), VMA405 (UART) ou ACR122U (USB)
- Électrovanne (GPIO 18 par défaut)
- Débitmètre (GPIO 23 par défaut)
- Écran HDMI pour le kiosk Chromium

## Installation sur Pi vierge

Un seul prérequis côté serveur : créer un `PairingDevice` lié à une `TireuseBec` dans l'admin TiBillet pour obtenir un **code PIN à 6 chiffres**.

```bash
curl -O https://raw.githubusercontent.com/TiBillet/Lespass/V2/controlvanne/Pi/install_pi.sh
bash install_pi.sh
```

Le script pose quelques questions puis délègue à `make`. À la fin, redémarrer le Pi.

### Ce que fait `install_pi.sh`

1. Installe les prérequis minimaux (`git`, `make`, `python3`)
2. Clone uniquement `controlvanne/Pi/` via git sparse-checkout dans `/home/sysop/tibeer/`
3. Lance `make all` (claim → install → deploy → start)

### Structure sur le Pi après installation

```
/home/sysop/tibeer/          ← dépôt git sparse (seul controlvanne/Pi/ est présent)
  .git/
  controlvanne/
    Pi/                      ← répertoire de travail des services
      main.py
      .env                   ← généré par make claim (non versionné)
      .venv/                 ← virtualenv Python
      config/                ← fichiers de configuration source
      ...
```

## Utilisation de make

```
make help
```

| Commande | Description |
|----------|-------------|
| `make all PIN=123456 [SERVER=...] [RFID=RC522]` | Installation complète |
| `make claim PIN=123456 [SERVER=...] [RFID=...]` | Appairage : génère `.env` |
| `make install [RFID=RC522]` | Dépendances système + virtualenv |
| `make deploy` | Copie les services systemd et fichiers de config |
| `make start` | Active et démarre `tibeer` + `kiosk` |
| `make update` | `git pull` + `pip install` + redémarrage |
| `make logs` | Logs en direct (`journalctl -u tibeer -f`) |
| `make status` | État des services `tibeer` et `kiosk` |
| `make test-rfid` | Test du lecteur défini dans `.env` (RC522/VMA405/ACR122U) |
| `make test-hardware` | Diagnostic global du matériel |
| `make clean` | Désactive les services et supprime le virtualenv |

Lecteurs RFID supportés : `RC522` (défaut), `VMA405`, `ACR122U`.

> `make test-rfid` et `make test-hardware` utilisent directement le virtualenv — pas besoin de l'activer manuellement. Pour lancer les scripts à la main, voir `tests/README.md`.

## Services systemd

| Service | Rôle |
|---------|------|
| `tibeer` | Boucle principale RFID + vanne + API. Démarre avec le Pi. |
| `kiosk` | Lance Chromium en mode kiosk sur l'URL de la tireuse. |
| `pigpiod` | Daemon GPIO (requis par tibeer). |

```bash
sudo systemctl status tibeer
sudo systemctl status kiosk
journalctl -u tibeer -f
```

## Mise à jour du code

```bash
make update
```

Effectue un `git pull` sur le dépôt sparse (seul `controlvanne/Pi/` est mis à jour), réinstalle les dépendances Python si nécessaire, et redémarre `tibeer`.

Le service `tibeer` fait aussi un `git pull` automatique à chaque démarrage via `git-update.sh`.

## Variables d'environnement (`.env`)

Généré par `make claim`, jamais modifié manuellement. Variables principales :

| Variable | Rôle |
|----------|------|
| `SERVER_URL` | URL du tenant Lespass |
| `API_KEY` | Clé d'API `TireuseAPIKey` |
| `TIREUSE_UUID` | UUID de la `TireuseBec` |
| `RFID_TYPE` | `RC522`, `VMA405` ou `ACR122U` |
| `GPIO_VANNE` | Pin GPIO de l'électrovanne (défaut : 18) |
| `GPIO_FLOW_SENSOR` | Pin GPIO du débitmètre (défaut : 23) |

## Dépannage

**Aucune lecture de carte :**
```bash
make test-rfid
# Vérifier que SPI est activé
ls /dev/spidev0.0
```

**Kiosk non authentifié :**
```bash
journalctl -u tibeer | grep "cookie\|Auth kiosk"
```

**Réinstaller sans re-cloner :**
```bash
make deploy
make start
sudo reboot
```

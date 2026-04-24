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

Un seul prérequis côté serveur : créer une `TireuseBec` dans **Admin → Tireuses → Taps** — le code PIN à 6 chiffres s'affiche directement dans la colonne **PIN code** de la liste.

```bash
wget https://raw.githubusercontent.com/TiBillet/Lespass/dev_vps/controlvanne/Pi/install_pi.sh && chmod +x install_pi.sh && ./install_pi.sh
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
| `VALVE_ACTIVE_HIGH` | `True` si GPIO HIGH = vanne ouverte (défaut : `True`) |
| `SSL_VERIFY` | `True` pour vérifier le certificat TLS (défaut : `True`, mettre `False` en dev local) |
| `GIT_BRANCH` | Branche git tirée au démarrage du service (ex: `dev_vps`, `V2`) |
| `GIT_REPO` | URL du dépôt git (défaut : `https://github.com/TiBillet/Lespass`) |

## Dépannage

**Aucune lecture de carte :**
```bash
# IMPORTANT : arrêter le service tibeer avant le test (deux processus ne peuvent pas
# accéder simultanément au bus SPI — cela corrompt les lectures et fausse les résultats)
sudo systemctl stop tibeer
make test-rfid
# Vérifier que SPI est activé
ls /dev/spidev0.0
```

**Pi non appairé (tibeer s'arrête au démarrage) :**
```bash
journalctl -u tibeer -n 20
# Si le message est "Pi non appaire", relancer depuis le Pi en SSH :
# Le PIN est visible dans Admin → Tireuses → Taps, colonne "PIN code"
make claim PIN=<code> SERVER=https://votre-domaine.tld
```

**Kiosk non authentifié :**
```bash
journalctl -u tibeer | grep "Auth kiosk"
```

**Vanne qui se ferme ~3 secondes après le badge :**

Le délai `CARD_GRACE_PERIOD_S` (défaut : 3s dans `controllers/tibeer_controller.py`) détermine combien de temps sans lecture RFID avant de considérer la carte retirée. Si les appels réseau `authorize()` + `pour_start` durent ~3s, le timer peut expirer pendant ces appels. Le correctif (`last_seen_ts = time.time()` après `_handle_new_session`) est déjà appliqué. Si le problème persiste, vérifier la latence réseau vers le serveur.

**Réinstaller sans re-cloner :**
```bash
make deploy
make start
sudo reboot
```

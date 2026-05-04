# Installation Raspberry Pi - LaBoutik Client v2

## Prérequis matériels

- Raspberry Pi (3B+, 4 ou plus récent)
- Lecteur NFC RC522 (VMA405) sur bus SPI logiciel (SoftSPI)
- Carte SD avec Raspberry Pi OS Lite (32-bit)
- Écran tactile 1024x600 (optionnel)

## Fichiers d'installation

Tous les scripts et fichiers de configuration pour le Pi se trouvent dans le dossier `install_pi/` :

```
install_pi/
├── setup-laboutik-pi         # Script d'installation système (étape 1)
├── install-modules-nodejs    # Script d'installation des modules Node.js (étape 3)
├── debug-chromium.sh         # Gestion du mode débogage Chromium
└── src/
    ├── 40-libinput.conf      # Configuration tactile X11
    └── 99-fbturbo.conf       # Configuration fbturbo (Pi 3 et inférieur)
```

---

## Étape 1 : Installation du système et des dépendances système

Cette étape installe Node.js, configure le système et prépare le hardware.

### Installation rapide (paramètres par défaut)

```bash
cd install_pi
chmod +x setup-laboutik-pi
sudo ./setup-laboutik-pi
```

### Installation personnalisée

```bash
sudo ./setup-laboutik-pi <nfc_type> <rotate>
```

**Paramètres :**

| Paramètre | Description | Valeur par défaut |
|-----------|-------------|-------------------|
| `nfc_type` | Type de lecteur NFC (`gpio` ou `usb`) | `gpio` |
| `rotate` | Rotation de l'écran (0-3) | `3` |

**Exemple :**
```bash
sudo ./setup-laboutik-pi gpio 0
```

### Ce que fait le script

1. **Mise à jour du système**
2. **Installation de Node.js 24.x** (inclut npm)
3. **Installation des outils de compilation** (gcc, g++, make, node-gyp)
4. **Configuration du lecteur NFC**
   - Activation du bus SPI
   - Configuration des droits GPIO/SPI
   - Installation de `libpcsclite-dev` (pour compiler les modules natifs)
5. **Configuration de l'écran**
   - Rotation, résolution HDMI, calibration tactile
6. **Installation de Chromium** (navigateur en mode kiosk)
7. **Configuration du démarrage automatique** (Openbox + autologin)

### Vérification après installation

```bash
node --version   # Doit afficher v24.x.x
npm --version    # Doit afficher 10.x.x
```

---

## Étape 2 : Configuration du hardware NFC

### Brochage RC522 (VMA405) - Câblage physique

| RC522 | Raspberry Pi GPIO | Fonction |
|-------|-------------------|----------|
| SDA (CS) | GPIO 24 (Pin 18) | Chip Select |
| SCK | GPIO 23 (Pin 16) | Horloge SPI |
| MOSI | GPIO 19 (Pin 35) | Données vers le RC522 |
| MISO | GPIO 21 (Pin 40) | Données depuis le RC522 |
| IRQ | Non connecté | - |
| GND | Ground | Masse |
| RST | GPIO 22 (Pin 15) | Reset |
| 3.3V | 3.3V (Pin 1) | Alimentation |

**Note** : Le module utilise `rpi-softspi` (SPI logiciel) avec `rpio` pour le GPIO, adapté au câblage physique soudé.

### Vérification du SPI

```bash
ls /dev/spi*   # Doit afficher /dev/spidev0.0 et /dev/spidev0.1
```

### Vérification des droits GPIO

```bash
groups   # Doit contenir gpio, spi, netdev
ls -l /dev/gpiomem   # Doit appartenir à root:gpio
```

---

## Étape 3 : Installation des modules Node.js de l'application

Cette étape installe les dépendances npm spécifiques à la plateforme.

### Préparation

Le script `install-modules-nodejs` se trouve à la racine du projet :

```bash
cd /home/sysop/laboutik_client_pi_desktop_v2
chmod +x install-modules-nodejs
```

### Installation pour Raspberry Pi

```bash
./install-modules-nodejs pi
```

**Ce que fait le script :**
1. Supprime `node_modules/` et `package-lock.json`
2. Copie `install_pi/package.json` à la racine
3. Configure `env.js` avec `type_app: 'pi'`
4. Lance `npm install`

### Modules installés pour le Pi

| Module | Utilisation |
|--------|-------------|
| `socket.io` | Communication temps réel avec le front-end |
| `rpi-softspi` | SPI logiciel pour le RC522 |
| `rpio` | Contrôle GPIO (reset, buzzer) |
| `nfc-pcsc` | Support lecteur USB (compilation nécessaire) |

### Vérification

```bash
ls node_modules/   # Vérifier que les modules sont présents
```

---

## Étape 4 : Configuration de l'écran et du tactile

### Rotation de l'écran

Éditer `/boot/config.txt` :
```bash
sudo nano /boot/config.txt
```

Ajouter/modifier :
```
display_rotate=0  # 0=Normal, 1=90°, 2=180°, 3=270°
```

### Configuration X11 (tactile)

```bash
sudo mkdir -p /etc/X11/xorg.conf.d
sudo cp install_pi/src/40-libinput.conf /etc/X11/xorg.conf.d/40-libinput.conf
```

**Matrices de calibration selon la rotation :**

| Rotation | CalibrationMatrix | Description |
|----------|-------------------|-------------|
| 0° (Normal) | `1 0 0 0 1 0 0 0 1` | Aucune transformation |
| 90° | `0 -1 1 1 0 0 0 0 1` | 90° horaire |
| 180° | `-1 0 1 0 -1 1 0 0 1` | Retournement 180° |
| 270° (défaut) | `0 -1 1 1 0 0 0 0 1` | 270° horaire (90° anti-horaire) |

### Configuration HDMI (écran 1024x600)

Dans `/boot/config.txt` :
```
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt 1024 600 60 6 0 0 0
hdmi_drive=1
config_hdmi_boost=7
max_usb_current=1
```

### Désactiver le driver VC4 (Pi 4)

```bash
sudo sed -i 's/^dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/' /boot/config.txt
```

### Configuration fbturbo (Pi 3 et inférieur)

```bash
sudo cp install_pi/src/99-fbturbo.conf /usr/share/X11/xorg.conf.d/99-fbturbo.conf
```

**Note** : Sur Pi 4, supprimer ce fichier :
```bash
sudo rm /usr/share/X11/xorg.conf.d/99-fbturbo.conf
```

### Redémarrage

```bash
sudo reboot
```

---

## Étape 5 : Lancement de l'application

Après le redémarrage, l'application démarre automatiquement :
- Le serveur Node.js se lance via Openbox
- Chromium s'ouvre en mode kiosk sur `http://localhost:3000`

### Lancement manuel (si besoin)

```bash
cd /home/sysop/laboutik_client_pi_desktop_v2
node nfcServer.js
```

---

## Débogage distant de Chromium

### Activer/désactiver le débogage

```bash
cd install_pi
chmod +x debug-chromium.sh

# Voir l'état actuel
sudo ./debug-chromium.sh status

# Activer le débogage
sudo ./debug-chromium.sh on

# Désactiver le débogage
sudo ./debug-chromium.sh off
```

**Note** : Nécessite un redémarrage après activation/désactivation.

### Se connecter au débogage distant

#### Méthode 1 : Tunnel SSH depuis le PC (recommandée)

**⚠️ IMPORTANT : Cette commande doit être exécutée sur votre PC (ordinateur de développement), PAS sur le Raspberry Pi.**

Sur votre **PC** (ordinateur de développement) :
```bash
ssh -L 9222:localhost:9222 sysop@<ip-du-pi>
```

**Explication :**
- `ssh -L` : Crée un tunnel local (port forwarding)
- `9222` : Port sur votre PC (ordinateur de développement)
- `localhost:9222` : Port du debug Chromium sur le Pi (côté Pi)
- Le trafic est chiffré via SSH
- **Cette commande ouvre une connexion SSH depuis votre PC vers le Pi**

Puis ouvrir dans votre navigateur sur votre **PC** :
```
http://localhost:9222
```

**Schéma du tunnel :**
```
PC (navigateur)          Tunnel SSH chiffré           Pi (Chromium debug)
localhost:9222    ←────────────────────────→    localhost:9222
     ↑                                                           ↑
  http://localhost:9222                               --remote-debugging-port=9222
```

#### Méthode 2 : Tunnel depuis le Pi (alternative)

**⚠️ Cette commande doit être exécutée sur le Raspberry Pi.**

Sur le **Pi** (dans un screen/tmux pour qu'il tourne en arrière-plan) :
```bash
ssh -R 9222:localhost:9222 utilisateur@<ip-de-votre-pc>
```

**Explication :**
- `ssh -R` : Crée un tunnel inverse (reverse SSH)
- Le Pi ouvre une connexion SSH vers votre PC
- Le PC peut alors accéder au port 9222 du Pi via `localhost:9222`

Puis sur votre **PC** :
```
http://localhost:9222
```

### Fonctionnalités du débogage

- **Inspecter** les éléments de la page
- **Voir la console** JavaScript (erreurs, logs)
- **Déboguer** le code front-end (breakpoints)
- **Analyser** les performances réseau
- **Modifier** le CSS/JS en temps réel

**Important** : 
- La connexion SSH doit rester ouverte pour maintenir le tunnel actif
- **Méthode 1** : Laissez le terminal ouvert sur votre PC
- **Méthode 2** : Laissez le screen/tmux actif sur le Pi

---

## Récapitulatif des étapes

| Étape | Action | Commande |
|-------|--------|----------|
| 1 | Installation système | `sudo ./install_pi/setup-laboutik-pi` |
| 2 | Vérifier hardware | `ls /dev/spi*`, `groups` |
| 3 | Installer modules Node.js | `./install-modules-nodejs pi` |
| 4 | Configurer écran | Modifier `/boot/config.txt` |
| 5 | Redémarrer | `sudo reboot` |

---

## Dépannage

### Problème de compilation nfc-pcsc

Si `npm install` échoue avec `winscard.h: No such file or directory` :
```bash
sudo apt-get install libpcsclite-dev
```

### Reconstruction manuelle des dépendances

```bash
rm -rf node_modules package-lock.json
./install-modules-nodejs pi
```

### Vérification des logs

```bash
# Logs du serveur Node.js
tail -f /var/log/syslog | grep node

# Logs de Chromium
cat ~/.config/chromium/chrome_debug.log
```

### Redémarrage des services

```bash
# Redémarrer le serveur NFC
sudo pkill -f nfcServer.js
cd /home/sysop/laboutik_client_pi_desktop_v2 && node nfcServer.js &
```

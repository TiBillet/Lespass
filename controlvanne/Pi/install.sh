#!/bin/bash
set -e

# ==========================================
#  INSTALLATION COMPLÈTE TIBEER (RPI BOOKWORM)
# ==========================================

# Vérif root
if [ "$EUID" -eq 0 ]; then
  echo "❌ Ne lance pas ce script en root/sudo."
  echo "👉 Lance-le avec : ./install.sh"
  exit 1
fi

SYSUSER="sysop"
TARGET_DIR="/home/$SYSUSER/tibeer"
VENV_DIR="$TARGET_DIR/.venv"
# ==========================================
# Valeurs exemple par defaut
# ==========================================
DEFAULT_PUBLIC_URL="https://tibillet.mondomaine.tld"
DEFAULT_GIT_REPO="https://github.com/TiBillet/tiheureuse.git"
DEFAULT_GIT_BRANCH="master"


echo "🍻 INSTALLATION TIBEER "
echo "---------------------------------------"
# ==========================================
# ÉTAPE 1 : Système de base
# ==========================================

echo "[1/10] 📦 Installation dépendances système..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  git nano locales fontconfig curl ca-certificates \
  python3 python3-venv python3-pip python3-dev \
  pigpio python3-pigpio \
  xserver-xorg xinit openbox unclutter x11-apps \
  chromium-browser chromium-chromedriver \
  fonts-dejavu-core xfonts-base \
  upower xserver-xorg-input-libinput

# Locale FR
sudo sed -i 's/^# *fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen
sudo locale-gen || true

# ==========================================
# ÉTAPE 2 : Configuration & Clonage HTTPS
# ==========================================
echo "[2/10] 📝 Configuration..."

echo "🔹 URL publique TiBillet (ex: https://tibillet.mondomaine.tld)"
read -p "   (Défaut: $DEFAULT_PUBLIC_URL) : " PUBLIC_URL
PUBLIC_URL=${PUBLIC_URL:-$DEFAULT_PUBLIC_URL}
PUBLIC_URL=${PUBLIC_URL%/}
echo "   -> Utilisation de : $PUBLIC_URL"

read -p "🔹 Code PIN à 6 chiffres (affiché dans l'admin TiBillet) : " PIN_CODE
while [ -z "$PIN_CODE" ]; do
    echo "   ⚠️  Le PIN ne peut pas être vide."
    read -p "🔹 Code PIN : " PIN_CODE
done

echo "Appairage en cours..."
CLAIM_RESPONSE=$(curl -s -X POST "${PUBLIC_URL}/api/discovery/claim/" \
  -H "Content-Type: application/json" \
  -d "{\"pin_code\": \"${PIN_CODE}\"}")

SERVER_URL=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_url'])")
API_KEY=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")
TIREUSE_UUID=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['tireuse_uuid'])")

if [ -z "$SERVER_URL" ] || [ -z "$API_KEY" ]; then
  echo "ERREUR: Appairage echoue. Verifiez le PIN et l'URL."
  exit 1
fi
echo "Appairage reussi ! Tenant: $SERVER_URL, Tireuse: $TIREUSE_UUID"

read -p "🔹 Depot Git [Défaut: $DEFAULT_GIT_REPO] : " GIT_REPO
read -p "🔹 Branche Git [Défaut: $DEFAULT_GIT_BRANCH] : " GIT_BRANCH
GIT_BRANCH=${GIT_BRANCH:-$DEFAULT_GIT_BRANCH}
GIT_REPO=${GIT_REPO:-$DEFAULT_GIT_REPO}

echo ""
echo "🔹 Type de lecteur RFID :"
echo "   1) RC522   (SPI — défaut, le plus courant)"
echo "   2) VMA405  (UART/Série USB)"
echo "   3) ACR122U (USB PC/SC)"
read -p "   Choix [1/2/3, Défaut: 1] : " RFID_CHOICE
if [ "$RFID_CHOICE" = "2" ]; then
    RFID_TYPE="VMA405"
    read -p "🔹 Port série VMA405 [Défaut: /dev/ttyUSB0] : " RFID_SERIAL_PORT
    RFID_SERIAL_PORT=${RFID_SERIAL_PORT:-/dev/ttyUSB0}
    read -p "🔹 Baudrate VMA405 [Défaut: 9600] : " RFID_BAUDRATE
    RFID_BAUDRATE=${RFID_BAUDRATE:-9600}
elif [ "$RFID_CHOICE" = "3" ]; then
    RFID_TYPE="ACR122U"
else
    RFID_TYPE="RC522"
fi

echo ""
echo "--- 📥 Clonage du dépôt (HTTPS, sans clé SSH) ---"
echo "   Repo   : $GIT_REPO"
echo "   Branche: $GIT_BRANCH"

TEMP_DIR="/tmp/tibeer_temp_clone"
rm -rf "$TEMP_DIR"

# Backup si le dossier cible existe déjà
if [ "$(ls -A $TARGET_DIR 2>/dev/null)" ]; then
    echo "⚠️  Le dossier $TARGET_DIR n'est pas vide. Sauvegarde..."
    mv "$TARGET_DIR" "${TARGET_DIR}_bak_$(date +%s)"
    mkdir -p "$TARGET_DIR"
fi

git clone -b "$GIT_BRANCH" "$GIT_REPO" "$TEMP_DIR"

if [ $? -ne 0 ]; then
    echo "❌ Échec du clonage. Vérifiez l'URL et votre connexion internet."
    exit 1
fi

# Extraction du sous-dossier Pi vers le répertoire cible
SOURCE_SUBDIR="$TEMP_DIR/controlvanne/Pi"

if [ -d "$SOURCE_SUBDIR" ]; then
    echo "📂 Installation des fichiers vers $TARGET_DIR..."
    cp -a "$SOURCE_SUBDIR/." "$TARGET_DIR/"
    rm -rf "$TEMP_DIR"
    chmod +x "$TARGET_DIR/git-update.sh"
    echo "✅ Fichiers installés."
else
    echo "❌ Erreur : dossier 'Pi' introuvable dans la branche $GIT_BRANCH."
    rm -rf "$TEMP_DIR"
    exit 1
fi


# ==========================================
# ÉTAPE 3 : Boot & Display (Mode Legacy)
# ==========================================
echo ""
echo "[3/10] 📺 Configuration Vidéo (FKMS/Legacy)..."
CFG_BOOT_DIR="/boot/firmware"
[ -d /boot/firmware ] || CFG_BOOT_DIR="/boot"
CFG_CONFIG_TXT="${CFG_BOOT_DIR}/config.txt"
CFG_CMDLINE_TXT="${CFG_BOOT_DIR}/cmdline.txt"

# Force FKMS
sudo sed -i '/^dtoverlay=vc4/d;/^hdmi_force_hotplug=/d' "${CFG_CONFIG_TXT}"
echo "dtoverlay=vc4-fkms-v3d" | sudo tee -a "${CFG_CONFIG_TXT}" >/dev/null
echo "hdmi_force_hotplug=1" | sudo tee -a "${CFG_CONFIG_TXT}" >/dev/null

# Consoleblank=0
if [ -f "${CFG_CMDLINE_TXT}" ]; then
  sudo sed -i 's/ consoleblank=[0-9]\+//g' "${CFG_CMDLINE_TXT}"
  grep -q 'consoleblank=0' "${CFG_CMDLINE_TXT}" || sudo sed -i 's/$/ consoleblank=0/' "${CFG_CMDLINE_TXT}"
fi

# SPI ON
sudo raspi-config nonint do_spi 0 || true

# ==========================================
# ÉTAPE 4 : Permissions
# ==========================================
echo ""
echo "[4/10] 🔐 Permissions Utilisateur & Xorg..."
sudo usermod -aG sudo,video,input,render,gpio,spi,dialout,tty "$SYSUSER"

# Xwrapper (Autoriser n'importe qui à lancer X)
echo "allowed_users=anybody" | sudo tee /etc/X11/Xwrapper.config >/dev/null
echo "needs_root_rights=yes" | sudo tee -a /etc/X11/Xwrapper.config >/dev/null

# ==========================================
# ÉTAPE 5 : Projet Python & Dépendances
# ==========================================
echo ""
echo "[5/10] 🐍 Clonage et Installation Python..."

# Installation des dépendances système pour ACR122U avant la compilation de pyscard
if [ "$RFID_TYPE" = "ACR122U" ]; then
    echo "   📦 Installation pcscd + libpcsclite-dev + swig (requis pour compiler pyscard)..."
    sudo apt-get install -y --no-install-recommends pcscd libpcsclite-dev swig
fi

# Création Venv
echo "Création de l'environnement virtuel dans $VENV_DIR..."
cd "$TARGET_DIR"
python3 -m venv "$VENV_DIR"

# Installation packages
echo "Installation des dépendances Python..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
# LES LIBS DEMANDÉES EXPLICITEMENT :
pip install pyserial requests pigpio mfrc522 python-dotenv systemd-python

# pyscard uniquement pour ACR122U (nécessite libpcsclite-dev pour compiler)
if [ "$RFID_TYPE" = "ACR122U" ]; then
    pip install pyscard
fi

# Si requirements.txt existe, on l'installe aussi pour être sûr
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi
deactivate

# ==========================================
# ÉTAPE 6 : Variables d'environnement
# ==========================================
echo ""
echo "[6/10] ⚙️ Création fichier .env..."

cat << EOF > "$TARGET_DIR/.env"
# Généré par le script d'installation
SERVER_URL=$SERVER_URL
API_KEY=$API_KEY
TIREUSE_UUID=$TIREUSE_UUID
DEBUG=False
# Lecteur RFID
RFID_TYPE=$RFID_TYPE
# GPIO Settings
GPIO_VANNE=18
VALVE_ACTIVE_HIGH=False
GPIO_FLOW_SENSOR=23
FLOW_CALIBRATION_FACTOR=6.5
# Réseau
NETWORK_TIMEOUT=5.0
MAX_RETRIES=3
# Systemd
SYSTEMD_NOTIFY=True
# Git Settings (pour mise à jour auto au démarrage)
GIT_REPO=${GIT_REPO:-$DEFAULT_GIT_REPO}
GIT_BRANCH=${GIT_BRANCH:-$DEFAULT_GIT_BRANCH}
EOF

# Ajout des paramètres série si VMA405
if [ "$RFID_TYPE" = "VMA405" ]; then
cat << EOF >> "$TARGET_DIR/.env"
# VMA405 Série
RFID_SERIAL_PORT=$RFID_SERIAL_PORT
RFID_BAUDRATE=$RFID_BAUDRATE
EOF
fi


chmod 600 "$TARGET_DIR/.env"

# ==========================================
# ÉTAPE 7 : Configuration Affichage (Xinitrc)
# ==========================================
echo ""
echo "[7/10] 🖥️ Configuration .xinitrc (Openbox)..."

# Configuration Ant-Veille X11
sudo mkdir -p /etc/X11/xorg.conf.d
cat << 'EOF' | sudo tee /etc/X11/xorg.conf.d/10-dpms.conf >/dev/null
Section "Monitor"
    Identifier "HDMI-1"
    Option "DPMS" "false"
EndSection
Section "ServerFlags"
    Option "BlankTime"   "0"
    Option "OffTime"     "0"
EndSection
EOF

# .xinitrc
cat << 'EOF' > "/home/$SYSUSER/.xinitrc"
#!/bin/bash
exec > /home/sysop/.xinitrc.log 2>&1
set -x

# Locale FR
export LANG=fr_FR.UTF-8
export LANGUAGE=fr_FR:fr
export LC_ALL=fr_FR.UTF-8

# URL kiosque - lit directement depuis .env
set -a; [ -f /home/sysop/tibeer/.env ] && . /home/sysop/tibeer/.env; set +a
if [ -n "$TIREUSE_UUID" ]; then
    URL="${SERVER_URL}/controlvanne/kiosk/${TIREUSE_UUID}/"
else
    URL="${SERVER_URL}/"
fi

# Trouver Chromium
CHROMIUM_BIN="$(command -v chromium-browser || command -v chromium || true)"
[ -n "$CHROMIUM_BIN" ] || { echo "Chromium introuvable — on affiche xclock"; exec xclock; }

# Anti-veille X11 + watchdog
xset -dpms
xset s off
xset s noblank
( while true; do xset s reset; sleep 50; done ) &

# Curseur caché (après 1s)
(unclutter -idle 1 -root || true) &

# WM minimal
(openbox --startup "/bin/true" || true) & sleep 1

PROFILE_DIR="/home/sysop/.config/chromium-kiosk"
mkdir -p "$PROFILE_DIR/Default"
touch "$PROFILE_DIR/First Run"

# Boucle de relance Chromium (X reste actif si Chromium crash)
while true; do
  "$CHROMIUM_BIN" \
    --user-data-dir="$PROFILE_DIR" \
    --force-device-scale-factor=2.0 \
    --lang=fr --accept-lang=fr-FR,fr \
    --no-first-run --no-default-browser-check \
    --kiosk "$URL" --incognito --start-fullscreen \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --disable-gpu --use-gl=swiftshader --disable-dev-shm-usage \
    --noerrdialogs --disable-session-crashed-bubble --disable-translate \
    --enable-features=UseOzonePlatform --ozone-platform=x11
  rc=$?
  echo "[KIOSK] Chromium terminé (rc=$rc), relance dans 2s…"
  sleep 2
done

EOF
chmod +x "/home/$SYSUSER/.xinitrc"
chown "$SYSUSER:$SYSUSER" "/home/$SYSUSER/.xinitrc"

# ==========================================
# ÉTAPE 8 : Services Systemd
# ==========================================
echo ""
echo "[8/10] 🔧 Création des Services..."

# Pigpiod
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

# Pcscd (requis pour ACR122U)
if [ "$RFID_TYPE" = "ACR122U" ]; then
    sudo systemctl enable pcscd
    sudo systemctl start pcscd
fi

# Service Kiosk
cat << EOF | sudo tee /etc/systemd/system/kiosk.service
[Unit]
Description=Chromium Kiosk
After=systemd-user-sessions.service network-online.target
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
User=sysop
WorkingDirectory=/home/sysop/tibeer
StandardInput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
PAMName=login
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/sysop/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=/bin/sh -c 'setterm -blank 0 -powersave off -powerdown 0 </dev/tty1; \\
                         mkdir -p /run/user/1000; chown 1000:1000 /run/user/1000; \\
                         chvt 1 || true; sleep 0.2'
# Log Xorg dédié verbeux (utile au debug)
ExecStart=/usr/bin/xinit /home/sysop/.xinitrc -- /usr/lib/xorg/Xorg :0 -nolisten tcp -logverbose 6 -verbose 6 -logfile /home/sysop/Xorg.kiosk.log vt1 -keeptty
Restart=on-failure
RestartSec=8

[Install]
WantedBy=multi-user.target
EOF

# Service Tibeer
cat << EOF | sudo tee /etc/systemd/system/tibeer.service
[Unit]
Description==Agent RFID + Vanne (tibeer)
After=network-online.target pigpiod.service
Wants=network-online.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=sysop
WorkingDirectory=$TARGET_DIR
EnvironmentFile=$TARGET_DIR/.env
# Mise à jour git au démarrage
ExecStartPre=$TARGET_DIR/git-update.sh
# Utilisation du python dans le .venv qu'on vient de créer
ExecStart=$VENV_DIR/bin/python $TARGET_DIR/main.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# ==========================================
# ÉTAPE 9 : Activation
# ==========================================
echo ""
echo "[9/10] 🚀 Activation des services..."
sudo systemctl daemon-reload
sudo systemctl enable kiosk
sudo systemctl enable tibeer
sudo systemctl disable --now getty@tty1.service || true

# ==========================================
# ÉTAPE 10 : Fin
# ==========================================
echo ""
echo "---------------------------------------"
echo "✅ INSTALLATION TERMINÉE"
echo "---------------------------------------"
echo "👉 Kiosk URL : ${SERVER_URL}/controlvanne/kiosk/${TIREUSE_UUID}/"
echo "⚠️  REDÉMARRAGE NÉCESSAIRE (Prise en compte GPU Legacy)"
echo ""
read -p "Redémarrer maintenant ? (o/n) " REBOOT_NOW
if [[ "$REBOOT_NOW" =~ ^[oO]$ ]]; then
    sudo reboot
fi

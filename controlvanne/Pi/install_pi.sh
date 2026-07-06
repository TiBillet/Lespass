#!/bin/bash
set -e

# ==========================================
#  BOOTSTRAP TIBEER — clone le dépôt Lespass
#  puis délègue à make (controlvanne/Pi/).
# ==========================================

if [ "$EUID" -eq 0 ]; then
    echo "Ne lance pas ce script en root/sudo."
    echo "Lance-le avec : bash install_pi.sh"
    exit 1
fi

SYSUSER="sysop"
REPO_DIR="/home/$SYSUSER/tibeer"
TARGET_DIR="$REPO_DIR/controlvanne/Pi"

DEFAULT_REPO="https://github.com/TiBillet/Lespass.git"
# NOTE : à repointer vers la branche stable après merge de main-fedow-import.
# / NOTE: re-target to the stable branch once main-fedow-import is merged.
DEFAULT_BRANCH="main-fedow-import"

echo "=== INSTALLATION TIBEER ==="
echo ""

# ── Questions ──────────────────────────────────────────────
# L'adresse RACINE du serveur TiBillet (pas le sous-domaine tenant).
# Elle sera conservée dans le .env (CLAIM_SERVER_URL) et modifiable ensuite.
# / The TiBillet server ROOT address (not the tenant subdomain).
# Stored in .env (CLAIM_SERVER_URL), editable afterwards.
read -p "URL publique TiBillet (ex: https://tibillet.mondomaine.tld) : " SERVER
while [ -z "$SERVER" ]; do
    echo "L'URL du serveur ne peut pas être vide."
    read -p "URL publique TiBillet : " SERVER
done
SERVER="${SERVER%/}"

read -p "Code PIN à 6 chiffres (affiché dans l'admin) : " PIN_CODE
while [ -z "$PIN_CODE" ]; do
    echo "Le PIN ne peut pas être vide."
    read -p "Code PIN : " PIN_CODE
done

echo ""
echo "Type de lecteur RFID :"
echo "  1) RC522   (SPI — défaut)"
echo "  2) VMA405  (UART/Série USB)"
echo "  3) ACR122U (USB PC/SC)"
read -p "Choix [1/2/3, Défaut: 1] : " RFID_CHOICE
case "$RFID_CHOICE" in
    2) RFID_TYPE="VMA405"  ;;
    3) RFID_TYPE="ACR122U" ;;
    *) RFID_TYPE="RC522"   ;;
esac

read -p "Dépôt Git [Défaut: $DEFAULT_REPO] : " GIT_REPO
GIT_REPO="${GIT_REPO:-$DEFAULT_REPO}"

read -p "Branche Git [Défaut: $DEFAULT_BRANCH] : " GIT_BRANCH
GIT_BRANCH="${GIT_BRANCH:-$DEFAULT_BRANCH}"

# ── Prérequis minimaux ─────────────────────────────────────
echo ""
echo "[1/3] Prérequis (git, make, python3)..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends git make python3 curl ca-certificates

# ── Clone complet du dépôt dans REPO_DIR ───────────────────
# Clone complet (tout le contenu de la branche). --depth=1 : on ne
# télécharge pas l'historique git, inutile sur le Pi.
# / Full clone (the branch's whole content). --depth=1: git history
# is not downloaded, useless on the Pi.
echo ""
echo "[2/3] Clonage du dépôt Lespass ($GIT_BRANCH)..."

REPO_DIR="/home/$SYSUSER/tibeer"

if [ -d "$REPO_DIR/.git" ]; then
    echo "Dépôt existant — mise à jour..."
    git -C "$REPO_DIR" pull
else
    if [ "$(ls -A $REPO_DIR 2>/dev/null)" ]; then
        echo "Dossier $REPO_DIR non vide — sauvegarde..."
        mv "$REPO_DIR" "${REPO_DIR}_bak_$(date +%s)"
    fi
    git clone \
        --depth=1 \
        -b "$GIT_BRANCH" \
        "$GIT_REPO" \
        "$REPO_DIR"
fi

TARGET_DIR="$REPO_DIR/controlvanne/Pi"
chmod +x "$TARGET_DIR/git-update.sh" 2>/dev/null || true

# ── Délégation à make ──────────────────────────────────────
echo ""
echo "[3/3] Lancement de l'installation via make..."
cd "$TARGET_DIR"

make claim PIN="$PIN_CODE" SERVER="$SERVER" RFID="$RFID_TYPE" REPO="$GIT_REPO" BRANCH="$GIT_BRANCH"
make install RFID="$RFID_TYPE"
make deploy
make start

# ── Fin ────────────────────────────────────────────────────
echo ""
echo "=== INSTALLATION TERMINÉE ==="
echo "Kiosk URL : $(grep SERVER_URL $TARGET_DIR/.env | cut -d= -f2)/controlvanne/kiosk/$(grep TIREUSE_UUID $TARGET_DIR/.env | cut -d= -f2)/"
echo ""
read -p "Redémarrer maintenant ? (o/n) : " REBOOT_NOW
if [[ "$REBOOT_NOW" =~ ^[oO]$ ]]; then
    sudo reboot
fi

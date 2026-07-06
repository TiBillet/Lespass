#!/bin/bash
# Appairage TiBeer : récupère les credentials depuis le serveur et génère .env
# / TiBeer pairing: fetches credentials from server and generates .env
#
# Usage : bash claim.sh <pin> <server> <rfid_type> <git_repo> <git_branch>
# <server> = adresse RACINE du serveur TiBillet (pas le sous-domaine tenant).
# / <server> = TiBillet server ROOT address (not the tenant subdomain).

set -e

PIN_CODE="$1"
SERVER="$2"
RFID_TYPE="${3:-RC522}"
GIT_REPO="${4:-https://github.com/TiBillet/Lespass.git}"
# NOTE : à repointer vers la branche stable après merge de main-fedow-import.
# / NOTE: re-target to the stable branch once main-fedow-import is merged.
GIT_BRANCH="${5:-main-fedow-import}"

# Dossier Pi/ = parent du dossier config/ où vit ce script.
# / Pi/ folder = parent of the config/ folder where this script lives.
TARGET_DIR="$(cd "$(dirname "$0")/.." && pwd)"

[ -n "$PIN_CODE" ] || { echo "Usage: bash claim.sh <pin> <server> [rfid_type] [git_repo] [git_branch]"; exit 1; }
[ -n "$SERVER"   ] || { echo "SERVER manquant."; exit 1; }
SERVER="${SERVER%/}"

echo "Appairage en cours avec $SERVER..."
# -k : ignore SSL auto-signe en dev / ignore self-signed SSL in dev
RESPONSE=$(curl -skf -X POST "${SERVER}/api/discovery/claim/" \
    -H "Content-Type: application/json" \
    -d "{\"pin_code\": \"${PIN_CODE}\"}")

SERVER_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_url'])")
API_KEY=$(echo    "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")
TIREUSE_UUID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tireuse_uuid', ''))")

[ -n "$SERVER_URL" ] || { echo "Appairage échoué. Vérifiez le PIN et l'URL."; exit 1; }

sed \
    -e "s|__SERVER_URL__|${SERVER_URL}|g" \
    -e "s|__CLAIM_SERVER_URL__|${SERVER}|g" \
    -e "s|__API_KEY__|${API_KEY}|g" \
    -e "s|__TIREUSE_UUID__|${TIREUSE_UUID}|g" \
    -e "s|__RFID_TYPE__|${RFID_TYPE}|g" \
    -e "s|__GIT_REPO__|${GIT_REPO}|g" \
    -e "s|__GIT_BRANCH__|${GIT_BRANCH}|g" \
    "${TARGET_DIR}/config/env_example" > "${TARGET_DIR}/.env"

chmod 600 "${TARGET_DIR}/.env"
echo "Appairage reussi. Tenant: ${SERVER_URL} — Tireuse: ${TIREUSE_UUID}"

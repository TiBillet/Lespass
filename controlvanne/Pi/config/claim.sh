#!/bin/bash
# Appairage TiBeer : récupère les credentials depuis le serveur et génère .env
# / TiBeer pairing: fetches credentials from server and generates .env
#
# Usage : bash claim.sh <pin> <server> <rfid_type> <git_repo> <git_branch>

set -e

PIN_CODE="$1"
SERVER="$2"
RFID_TYPE="${3:-RC522}"
GIT_REPO="${4:-https://github.com/TiBillet/Lespass.git}"
GIT_BRANCH="${5:-V2}"

TARGET_DIR="/home/sysop/tibeer/controlvanne/Pi"

[ -n "$PIN_CODE" ] || { echo "Usage: bash claim.sh <pin> <server> [rfid_type] [git_repo] [git_branch]"; exit 1; }
[ -n "$SERVER"   ] || { echo "SERVER manquant."; exit 1; }

echo "Appairage en cours avec $SERVER..."
RESPONSE=$(curl -sf -X POST "${SERVER}/api/discovery/claim/" \
    -H "Content-Type: application/json" \
    -d "{\"pin_code\": \"${PIN_CODE}\"}")

SERVER_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_url'])")
API_KEY=$(echo    "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")
TIREUSE_UUID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tireuse_uuid', ''))")

[ -n "$SERVER_URL" ] || { echo "Appairage échoué. Vérifiez le PIN et l'URL."; exit 1; }

sed \
    -e "s|__SERVER_URL__|${SERVER_URL}|g" \
    -e "s|__API_KEY__|${API_KEY}|g" \
    -e "s|__TIREUSE_UUID__|${TIREUSE_UUID}|g" \
    -e "s|__RFID_TYPE__|${RFID_TYPE}|g" \
    -e "s|__GIT_REPO__|${GIT_REPO}|g" \
    -e "s|__GIT_BRANCH__|${GIT_BRANCH}|g" \
    "${TARGET_DIR}/config/env_example" > "${TARGET_DIR}/.env"

chmod 600 "${TARGET_DIR}/.env"
echo "Appairage reussi. Tenant: ${SERVER_URL} — Tireuse: ${TIREUSE_UUID}"

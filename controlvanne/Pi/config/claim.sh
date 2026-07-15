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

# On NE met PAS -f (--fail) : il ferait sortir curl sans nous laisser lire la reponse.
# Or c'est justement le corps de la reponse qui dit POURQUOI l'appairage echoue — et le
# cas le plus frequent est un code PIN expire (il ne vit qu'une heure).
# -k : ignore le certificat auto-signe en dev / ignore self-signed SSL in dev
# / We do NOT use -f (--fail): it would exit before we can read the body, and the body is
# exactly what tells us WHY it failed — most often an expired PIN (they live one hour).
HTTP_ET_CORPS=$(curl -sk -w "\n%{http_code}" -X POST "${SERVER}/api/discovery/claim/" \
    -H "Content-Type: application/json" \
    -d "{\"pin_code\": \"${PIN_CODE}\"}")

CODE_HTTP=$(echo "$HTTP_ET_CORPS" | tail -n 1)
RESPONSE=$(echo "$HTTP_ET_CORPS" | sed '$d')

if [ "$CODE_HTTP" != "200" ]; then
    echo
    echo "Appairage echoue (HTTP $CODE_HTTP)."
    echo "Reponse du serveur : $RESPONSE"
    echo
    case "$CODE_HTTP" in
        400)
            echo "Causes possibles :"
            echo "  - le code PIN a EXPIRE (il ne vit qu'une heure) ;"
            echo "  - le code PIN a deja ete utilise ;"
            echo "  - le code PIN est faux."
            echo
            echo "Regenerez-en un : Admin > Terminaux materiels > Terminaux"
            echo "                  > cocher la ligne > « Generer un nouveau code PIN »."
            ;;
        429)
            echo "Trop de tentatives. Attendez une minute avant de reessayer."
            ;;
        *)
            echo "Verifiez l'adresse du serveur : $SERVER"
            echo "(C'est l'adresse RACINE de TiBillet, PAS le sous-domaine du lieu.)"
            ;;
    esac
    exit 1
fi

SERVER_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_url'])")
API_KEY=$(echo    "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")
TIREUSE_UUID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tireuse_uuid', ''))")

[ -n "$SERVER_URL" ] || { echo "Appairage echoue : reponse du serveur illisible."; exit 1; }
[ -n "$TIREUSE_UUID" ] || { echo "Appairage echoue : le serveur n'a renvoye aucune tireuse. Le code PIN correspond-il bien a une tireuse ?"; exit 1; }

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

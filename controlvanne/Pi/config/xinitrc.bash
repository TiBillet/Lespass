#!/bin/bash
exec > /home/sysop/.xinitrc.log 2>&1
set -x

# Locale FR
export LANG=fr_FR.UTF-8
export LANGUAGE=fr_FR:fr
export LC_ALL=fr_FR.UTF-8

# URL de secours calculée depuis .env (utilisée si tibeer ne fournit pas d'URL)
# / Fallback URL computed from .env (used if tibeer provides no URL)
set -a; [ -f /home/sysop/tibeer/controlvanne/Pi/.env ] && . /home/sysop/tibeer/controlvanne/Pi/.env; set +a
if [ -n "$TIREUSE_UUID" ]; then
    FALLBACK_URL="${SERVER_URL}/controlvanne/kiosk/${TIREUSE_UUID}/"
else
    FALLBACK_URL="${SERVER_URL}/"
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

# Attendre que tibeer ait injecté le cookie sessionid (max 30s)
# / Wait for tibeer to inject the sessionid cookie (max 30s)
WAIT=0
while [ ! -f /tmp/tibeer_cookie_ready ] && [ $WAIT -lt 60 ]; do
    sleep 0.5
    WAIT=$((WAIT + 1))
done
rm -f /tmp/tibeer_cookie_ready

# Lire l'URL fournie par tibeer (kiosk avec token d'auth)
# / Read the URL provided by tibeer (kiosk with auth token)
if [ -f /tmp/tibeer_kiosk_url ]; then
    URL="$(cat /tmp/tibeer_kiosk_url)"
    rm -f /tmp/tibeer_kiosk_url
else
    URL="$FALLBACK_URL"
fi

# Boucle de relance Chromium (X reste actif si Chromium crash)
while true; do
  "$CHROMIUM_BIN" \
    --user-data-dir="$PROFILE_DIR" \
    --force-device-scale-factor=2.0 \
    --lang=fr --accept-lang=fr-FR,fr \
    --no-first-run --no-default-browser-check \
    --kiosk "$URL" --start-fullscreen \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --disable-gpu --use-gl=swiftshader --disable-dev-shm-usage \
    --noerrdialogs --disable-session-crashed-bubble --disable-translate \
    --enable-features=UseOzonePlatform --ozone-platform=x11
  rc=$?
  echo "[KIOSK] Chromium terminé (rc=$rc), relance dans 2s…"
  sleep 2
  # Après crash/redémarrage : repasser sur l'URL kiosk réelle (le cookie de session
  # est déjà dans le profil Chromium, pas besoin de recharger le token)
  # / After crash/restart: switch back to real kiosk URL (session cookie already
  # in Chromium profile, no need to reload the token)
  URL="$FALLBACK_URL"
done

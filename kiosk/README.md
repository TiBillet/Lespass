# App `kiosk` — Borne de recharge cashless (TPE Stripe)

Borne **libre-service** de rechargement de carte cashless NFC, sur terminal Android (Cordova)
ou Raspberry Pi (Chromium). Paiement par carte bancaire sur un **TPE Stripe WisePOS**, crédit de
la carte assuré **côté Fedow distant** (coexistence V1, via webhook Stripe).

> Spec de conception complète : `TECH_DOC/SESSIONS/KIOSK/SPEC.md`
> Recette manuelle : `A TESTER et DOCUMENTER/kiosk-tpe-borne.md`

---

## 1. Ce que fait l'application

Parcours client sur la borne :

1. **Choix du montant** — boutons additifs `+1 / +5 / +10 / +20 / +50 €`.
2. **Scan de la carte** NFC TiBillet.
3. **Paiement CB** sur le TPE Stripe physique.
4. **Fedow crédite** la carte (webhook Stripe → crédit).
5. Écran **succès / annulation**, retour accueil.

Un mode **DEMO** simule le TPE (aucun hardware, aucun crédit réel).

---

## 2. Architecture

L'app `kiosk` est **TENANT_APPS** (une instance par tenant). Elle contient le **backend** (modèles,
vues, WebSocket, admin) et le **front** (templates + static) servi à `/kiosk/`. Le TPE et le crédit
sont pilotés côté serveur ; le client (Android ou Pi) n'est qu'un **écran + lecteur NFC**.

```
┌─────────────────────┐        ┌───────────────────────────────┐        ┌──────────────────┐
│  Borne (client)     │        │  Lespass — app kiosk (tenant) │        │  Fedow (distant) │
│  Android / Pi       │        │                               │        │                  │
│  - écran /kiosk/    │──HTTP──▶│  KioskViewSet (HTMX)          │        │                  │
│  - lecteur NFC      │        │  - refill_with_wisepos        │        │                  │
│  - (TPE à proximité)│◀─WS────│  TerminalConsumer ws/terminal │        │                  │
└─────────┬───────────┘        │  PaymentsIntent.send_to_terminal        │                  │
          │                    │        │  (metadata NON signées)│        │                  │
          │                    └────────┼───────────────────────┘        │                  │
          │                             │ Stripe PaymentIntent (card_present)                │
          │                             ▼        compte Stripe Root partagé                  │
          │                    ┌───────────────────────┐   webhook Stripe   ┌────────────────┤
          └───tap CB──────────▶│  TPE Stripe WisePOS   │───────────────────▶│ crédit carte   │
                               └───────────────────────┘                    └────────────────┘
```

### Composants (dans `kiosk/`)

| Fichier | Rôle |
|---|---|
| `models.py` | `StripeLocation`, `Terminal` (`term_user` OneToOne = 1 borne = 1 TPE), `PaymentsIntent` |
| `admin.py` | Admin Unfold : appairage du TPE Stripe, historique des paiements |
| `views.py` | `KioskViewSet` — `list`, `check_request_card`, `refill_with_wisepos`, `cancel` (garde `terminal_role == KI`) |
| `validators.py` | `RefillWisePoseValidator` (vérifie la carte via Fedow) |
| `tasks.py` | `poll_payment_intent_status` — tâche Celery qui suit le statut Stripe et pousse le résultat par WebSocket |
| `urls.py` | Montée sous `/kiosk/` (dans `TiBillet/urls_tenants.py`) |
| `templates/kiosk/`, `static/kiosk/` | Front HTMX + Bootstrap + SweetAlert |

### Hors de `kiosk/` (branchements)

- `fedow_connect/fedow_api.py` → `NFCcardFedow.retrieve(tag_id)` (lecture carte).
- `wsocket/consumers.py` + `routing.py` → `TerminalConsumer` sur `ws/terminal/<payment_intent_id>/`.
- `laboutik/views.py` → le **bridge d'auth** route les terminaux `KI` vers `/kiosk/`.
- `BaseBillet/models.py` (`module_kiosk`) + `Administration/admin/dashboard.py` (module + sidebar).
- **Fedow** (`../Fedow`) → route webhook TPE étendue pour accepter une place Lespass **sans signature**.

### Sécurité — pourquoi pas de signature

Contrairement à LaBoutik (plusieurs serveurs cashless partageant un compte Stripe → signature RSA
pour s'isoler), Lespass est **mono-serveur par fédération** avec une clé Stripe **Root exclusive**.
La place Lespass ne signe donc pas les metadata TPE ; la route webhook Fedow l'accepte (miroir de
l'« EXTENSION S6 »), l'idempotence anti-rejeu étant durcie (`unique` + `IntegrityError`).
**Hypothèse portante : le compte Stripe Root n'est détenu que par le serveur + Fedow.**
Détails : `TECH_DOC/SESSIONS/KIOSK/SPEC.md` §8bis.

---

## 3. Deux cibles clientes

| Cible | NFC | Statut |
|---|---|---|
| **Android / Cordova** (borne Sunmi) | plugin Cordova natif (`laboutik_client_android_v2`) | **Complet** — c'est la cible de référence |
| **Raspberry Pi** (Chromium kiosk) | serveur socket.io local (voir §5.4) | **Complet** |

Le **TPE Stripe** fonctionne dans les deux cas : il est piloté par le serveur (`process_payment_intent`
sur le reader), indépendamment du client.

---

## 4. Déploiement du backend (serveur)

1. **Migrations** : `migrate_schemas` (tables `kiosk` 0001-0003, `BaseBillet` 0227).
2. **Activer le module** : admin tenant → dashboard → activer **Kiosk** (`Configuration.module_kiosk`).
3. **Appairer le TPE Stripe** : admin → *Kiosk → Terminaux* → renseigner `name` + `registration_code`
   (code d'enregistrement du reader Stripe). L'appairage crée le reader côté Stripe (compte Root).
   En `DEMO=1`, l'appel réseau est sauté.
4. **Créer une borne** : admin *discovery* → `PairingDevice` en rôle **KI (Kiosque)** → PIN 6 chiffres.
5. **Fedow** : déployer la modif de `fedow_core` — ⚠️ **rebuild d'image** `tibillet/fedow` (le code est
   baké dans l'image, un restart ne suffit pas) + `migrate` (0025).

---

## 5. Installation sur un Raspberry Pi

Le Pi est un **écran plein-écran** qui ouvre `/kiosk/` dans Chromium, appairé à un tenant. Le modèle
suit le pattern éprouvé de `controlvanne/Pi/` (systemd + Chromium kiosk). Le TPE Stripe est un lecteur
réseau à côté de la borne (piloté par le serveur).

### 5.1 Prérequis
- Raspberry Pi (Pi 4 recommandé), Raspberry Pi OS Lite 64-bit.
- Utilisateur dédié (ex. `sysop`).
- Paquets : `xserver-xorg xinit openbox unclutter chromium-browser`.
  ```bash
  sudo apt update && sudo apt install -y xserver-xorg xinit openbox unclutter chromium-browser jq curl
  ```

### 5.2 Appairage (PIN → credentials)
Créer un `PairingDevice` **en rôle KI** dans l'admin (étape 4 du §4), noter le PIN. Sur le Pi :

```bash
SERVER="https://tibillet.mondomaine.tld"    # adresse RACINE (pas le sous-domaine tenant)
PIN="586573"

RESP=$(curl -sf -X POST "$SERVER/api/discovery/claim/" \
        -H "Content-Type: application/json" -d "{\"pin_code\":\"$PIN\"}")
SERVER_URL=$(echo "$RESP" | jq -r .server_url)   # ex: https://lespass.mondomaine.tld
API_KEY=$(echo    "$RESP" | jq -r .api_key)
echo "SERVER_URL=$SERVER_URL"; echo "API_KEY=$API_KEY"
# À conserver dans /home/sysop/kiosk.env (chmod 600)
```

### 5.3 Ouverture de la session (bridge)
⚠️ **Point d'attention** : l'authentification du kiosk cashless passe par un **POST** vers
`{SERVER_URL}/laboutik/auth/bridge/` (`api_key` + `type_app`), qui pose le cookie `sessionid` puis
redirige vers `/kiosk/`. Ce flux est conçu pour la WebView Cordova (formulaire auto-soumis).

Sur le Pi, le plus simple est de servir une **petite page locale d'amorçage** qui auto-soumet ce
formulaire ; Chromium démarre dessus, exécute le POST, reçoit le cookie et suit la redirection vers
`/kiosk/`. Exemple `~/kiosk-bootstrap.html` (les valeurs sont injectées depuis `kiosk.env`) :

```html
<!doctype html><meta charset="utf-8"><title>Kiosk…</title>
<body onload="document.forms[0].submit()">
  <form method="POST" action="__SERVER_URL__/laboutik/auth/bridge/">
    <input type="hidden" name="api_key"  value="__API_KEY__">
    <input type="hidden" name="type_app" value="pi">
  </form>
</body>
```
Générer le fichier réel : `sed -e "s|__SERVER_URL__|$SERVER_URL|" -e "s|__API_KEY__|$API_KEY|" kiosk-bootstrap.template.html > ~/kiosk-bootstrap.html`.

### 5.4 Lecteur NFC sur Pi — branché (CHANTIER-05)
Le front (`kiosk/static/kiosk/js/nfc.js`) gère deux modes hardware, choisis automatiquement depuis
`type_app` (exposé au JS par `base.html` via `window.KIOSK.type_app`, lui-même mémorisé en session par
`KioskViewSet.list` au premier appel du bridge) :

- **`type_app=cordova`** (borne Android/Sunmi) → mode `NFCMC`, plugin NFC natif Cordova.
- **`type_app=pi`** (ou toute autre valeur ≠ `cordova`) → mode `NFCLO`, lecture via **socket.io local**
  (`http://localhost:3000`), événements `nfcStartListening` (demande) / `nfcMessage` (réponse
  `{ tagId, data }`) / `nfcStopListening` (arrêt) — protocole de `nfcServer.js`.

Sur le Pi, réutiliser tel quel le client **`laboutik_client_pi_desktop_v2`** (déjà présent dans le
dépôt) : son `nfcServer.js` lance le serveur socket.io local qui pilote un lecteur RC522 ou ACR122U et
répond aux demandes de lecture. Procédure :

1. Déployer `laboutik_client_pi_desktop_v2/` sur le Pi (voir son propre README pour l'installation
   Node/dépendances).
2. Configurer sa propre `configLaboutik.json` (ou `env.js`) avec `type_app: "pi"` : `nfcServer.js`
   choisit alors le driver **RC522** (`modules/devices/vma405-rfid-rc522.js`, GPIO/SPI) plutôt que
   l'**ACR122U** USB (`type_app: "desktop"`) — ⚠️ ce `type_app` local au client Pi/desktop est un
   réglage distinct du `type_app` transmis par le bridge Lespass (cordova/pi), à ne pas confondre.
3. Lancer `nfcServer.js` en service (systemd, à l'image de `kiosk.service` §5.5) — il écoute sur le port
   `3000` par défaut (`PORT` dans sa config), celui que `nfc.js` attend (`this.socketPort = 3000`).
4. Le Chromium kiosk (bootstrap §5.3) charge `/kiosk/` normalement : `base.html` charge `socket.io` puis
   `nfc.js`, qui se connecte à `localhost:3000` dès qu'un scan est demandé (bouton Valider →
   `rfid.startLecture()`).

Aucune adaptation du front côté Lespass n'est nécessaire : `nfc.js` (copie propre au kiosque, distincte
du `nfc.js` de la caisse LaBoutik) gère déjà `NFCMC`/`NFCLO`/`simule()`.

**Mode DEMO** : si `window.DEMO` est défini (page rendue avec `settings.DEMO=True`), `startLecture()`
ignore le hardware et affiche directement le **simulateur de cartes** (overlay plein écran, boutons
`primary`/`client1`/`client2`/`client3`/`unknown`) — identique au comportement LaBoutik. Voir le
scénario de recette dans `A TESTER et DOCUMENTER/kiosk-tpe-borne.md`.

### 5.5 Chromium en mode kiosk (systemd)
S'inspirer de `controlvanne/Pi/config/`. Fichiers types à adapter :

`/etc/systemd/system/kiosk.service` :
```ini
[Unit]
Description=Kiosk Cashless (Chromium)
After=network-online.target
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
User=sysop
Environment=DISPLAY=:0
ExecStart=/usr/bin/xinit /home/sysop/.xinitrc -- /usr/lib/xorg/Xorg :0 vt1 -keeptty -nolisten tcp
Restart=on-failure
RestartSec=8

[Install]
WantedBy=multi-user.target
```

`/home/sysop/.xinitrc` :
```bash
#!/bin/bash
export LANG=fr_FR.UTF-8
set -a; . /home/sysop/kiosk.env; set +a   # SERVER_URL, API_KEY
xset -dpms; xset s off; xset s noblank
(unclutter -idle 1 -root &) ; (openbox &) ; sleep 1

CHROMIUM="$(command -v chromium-browser || command -v chromium)"
# Démarre sur la page d'amorçage (POST bridge → cookie → redirection /kiosk/)
exec "$CHROMIUM" --user-data-dir=/home/sysop/.config/chromium-kiosk \
  --kiosk "file:///home/sysop/kiosk-bootstrap.html" --start-fullscreen \
  --no-first-run --no-default-browser-check --noerrdialogs \
  --disable-translate --autoplay-policy=no-user-gesture-required \
  --use-gl=swiftshader --disable-gpu
```

Activer :
```bash
sudo systemctl enable --now kiosk
journalctl -u kiosk -f          # logs
```

Après le premier démarrage, le cookie de session reste dans le profil Chromium ; en cas de crash,
Chromium peut redémarrer directement sur `${SERVER_URL}/kiosk/`.

---

## 6. Développement & tests

```bash
# Serveur : le module kiosk doit être activé, DEMO=1 pour simuler le TPE
# Tests DB-only (16 tests)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_kiosk_models.py tests/pytest/test_kiosk_flow.py \
  tests/pytest/test_kiosk_branchements.py -v --api-key dummy
```

En `DEMO=1`, `send_to_terminal` simule le PaymentIntent et `get_from_stripe` tire le statut au sort
(80 % attente / 10 % annulé / 10 % succès). **Aucun webhook → aucun crédit réel côté Fedow.**

---

## 7. Références
- Conception : `TECH_DOC/SESSIONS/KIOSK/SPEC.md` (+ `INDEX.md`, `CHANTIER-01..04`).
- Recette manuelle : `A TESTER et DOCUMENTER/kiosk-tpe-borne.md`.
- Client Android complet : `laboutik_client_android_v2/`.
- Pattern Pi de référence : `controlvanne/Pi/`.

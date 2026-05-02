# Feature patches — dev_vps → V2

Patches de fonctionnalités de la branche `dev_vps` à soumettre au mainteneur de la branche `V2`.

Chaque fichier `.patch` est un `git diff` pur : pas de paramètres d'environnement, pas d'adresse IP,
pas de nom de container. Applicable directement sur un clone local de `V2` avec `git apply`.

---

## Application

```bash
# Cloner V2
git clone https://github.com/TiBillet/Lespass.git -b V2 lespass_v2
cd lespass_v2

# Appliquer un patch
git apply Install_vps/Patch_v2/feature_patches/01_asgi_app_registry_fix.patch

# Appliquer tous les patches
for p in Install_vps/Patch_v2/feature_patches/*.patch; do
    echo "==> $p"
    git apply "$p"
done
```

> **Vérifier avant apply** : `git apply --check <patch>` — signale les conflits sans modifier les fichiers.

---

## Patches par fonctionnalité

### 01 — `asgi_app_registry_fix` · `TiBillet/asgi.py`

**Problème :** `get_asgi_application()` appelé *après* les imports `channels`/`wsocket`.
Django levait `AppRegistryNotReady` au démarrage de Daphne → WebSockets non disponibles
→ le kiosk Pi ne recevait pas les mises à jour en temps réel.

**Fix :** `os.environ.setdefault` + `get_asgi_application()` déplacés *avant* tout import applicatif.

---

### 02 — `laboutik_discovery_csrf` · `Administration/admin/configuration.py` · `discovery/views.py` · `TiBillet/urls_tenants.py`

**Pourquoi :** l'APK LaBoutik mobile (Cordova) n'avait pas de mécanisme d'appairage avec le serveur —
seul le pairing LaBoutik tablette existait. Ajout du flow PIN discovery pour l'APK.

**3 changements :**

1. **CSRF** — `configuration.py` : suppression du `csrf_token` injecté manuellement dans le contexte
   du modal (déjà fourni par le context processor Django).

2. **PinCodeLaBoutikView** — `discovery/views.py` : nouvel endpoint `POST /pin_code/`.
   L'APK LaBoutik envoie `pin_code + hostname + username` → crée une `LaBoutikAPIKey`
   liée au tenant, consomme le `PairingDevice`, retourne `{server_url, server_public_pem, locale}`.

3. **WvLoginHardwareView** — `discovery/views.py` + `urls_tenants.py` : vue WebView qui initialise
   `localStorage.laboutik` (mode_nfc=NFCMC) et redirige vers `/laboutik/caisse/`.
   En DEBUG : auto-login de l'admin du tenant.

---

### 03 — `scan_qr_rsa1024` · `AuthBillet/models.py` · `BaseBillet/tasks.py` · `BaseBillet/views_scan.py` · `laboutik/static/js/tibilletUtils.js` · `laboutik/templates/laboutik/views/ask_primary_card.html`

**Pourquoi :** les QR codes générés avec des clés RSA 2048 bits produisaient des QR trop denses
(version 40+) — illisibles par les caméras d'entrée de gamme et les lecteurs NFC Android au format QR.
Passage à 1024 bits pour rester dans une version QR raisonnable.

Nouveau format QR code pour les cartes cashless et billets :
- Clé RSA 1024 bits (vs 2048) pour tenir dans un QR lisible par les lecteurs Android
- Format scan unifié entre l'ancienne API et le nouveau flow pairing/discovery

---

### 04 — `nfc_external_page` · `laboutik/static/js/nfc.js` · `laboutik/templates/laboutik/base.html`

**Problème :** l'APK LaBoutik charge `/laboutik/caisse/` depuis le serveur Django (HTTPS).
Sur ces pages *externes* (origine ≠ `http://localhost`), `cordova.exec()` ne fonctionnait pas
→ `enableForegroundDispatch()` jamais appelé → Android NFC silencieux.

**Fixes :**
- `cordova.js` déplacé dans `<head>` avant `nfc.js`
- `NfcReader.start()` lit `mode_nfc` depuis `localStorage` (plus de `nfcPlugin.available()`)
- `gestionModeLectureNfc NFCMC` : pose `window._nfcTagDiscovered` pour recevoir le tag injecté nativement
- `stop()` : `window._nfcTagDiscovered = null` au lieu de `nfcPlugin.stopListening()` (évite
  de désactiver le foreground dispatch Android)

> **Note APK :** `NfcPlugin.kt` et `plugin.xml` (cordova_local_plugins) ont aussi besoin
> de changements natifs Android (handleTag toujours injecter via WebView JS, onload=true).
> Ces fichiers ne sont pas dans le repo Django principal — voir `patch_nfc_external_page_v2.sh`.

---

### 05 — `controlvanne_tireuse` · 16 fichiers controlvanne

Fonctionnalités tireuses à bière (controlvanne) :

| Fichier | Changement |
|---------|-----------|
| `signals.py` | `terminal_role=ROLE_TIREUSE` à la création du `PairingDevice` — sans ça, le claim Pi retourne une clé LaBoutik au lieu d'une clé tireuse |
| `admin.py` | Lien `calibration_url` dans la page de changement admin |
| `urls.py` | Routes `/calibration/<uuid>/`, `/kiosk-token/<token>/` |
| `viewsets.py` | Cascade TNF→TLF→FED, logique carte maintenance, `KioskTokenView`, WS push enrichis, `card_removed` sans session active |
| `billing.py` | `calculer_solde_total_cascade` : débit TNF → TLF → FED en cascade, `AssetService` |
| `calibration_views.py` | Page calibration débit complète (HTMX) — était un placeholder désactivé en V2 |
| `templates/calibration/*` | Templates HTMX calibration (page, partial sessions, série, résultat, confirmation, récap) |
| `templates/controlvanne/*` | Templates kiosk (list + detail) |
| `Administration/templates/…/tireusebec_before.html` | Lien calibration dans l'admin tireuse |
| `static/controlvanne/js/panel_kiosk.js` | JS kiosk enrichi |

---

### 06 — `pi_tibeer` · 11 fichiers `controlvanne/Pi/`

Mise à jour du code embarqué sur le Raspberry Pi (service `tibeer`) :

| Fichier | Changement |
|---------|-----------|
| `config/settings.py` | Ajout `SSL_VERIFY` (vrai SSL en prod, self-signed en dev) |
| `config/env_example` | `VALVE_ACTIVE_HIGH=True` (était False) |
| `config/claim.sh` | `curl -k` pour les certs auto-signés en dev |
| `config/xinitrc.bash` | Lit `/tmp/tibeer_kiosk_url` (URL avec token) au lieu de calculer l'URL |
| `hardware/flow_meter.py` | `set_glitch_filter(5000µs)` — antiparasite débitmètre au déclenchement |
| `hardware/valve.py` | Support `VALVE_ACTIVE_HIGH` (relais actif-haut ou actif-bas) |
| `hardware/rfid_reader.py` | Documentation problème RC522 |
| `main.py` | Suppression injection SQLite ; auth kiosk via token ; vérification appairage au démarrage |
| `network/backend_client.py` | `SSL_VERIFY` sur tous les appels HTTP ; `auth_kiosk()` retourne un token |
| `controllers/tibeer_controller.py` | Grace period 3s ; ping calibration après session maintenance ; `card_removed` toujours envoyé ; reset `last_seen_ts` |
| `first/__init__.py` | Supprimé (fichier vide inutile) |

---

### 07 — `nginx_websocket` · `nginx_prod/lespass_prod.conf`

**Pourquoi :** les connexions WebSocket `/ws/` arrivaient sur Gunicorn (WSGI) qui ne les supporte pas
→ le kiosk Pi ne recevait jamais les push serveur (statut session, ouverture vanne).

Routing Nginx : proxying `/ws/` → Daphne (ASGI) pour les WebSockets controlvanne kiosk.

---

### 08 — `register_form_simplified` · `BaseBillet/templates/reunion/views/register.html`

Formulaire `/qr/<uuid>/` simplifié : suppression du champ `emailConfirmation` (masqué `d-none` +
auto-copie JS) et de la case CGU bloquante. L'utilisateur ne saisit que son email.

**Raison :** sur mobile, le tooltip HTML5 sur le champ manquant est discret → soumission silencieusement
bloquée → abandon de l'association carte.

---

### 09 — `laboutik_auth_bridge_post` · `laboutik/views.py`

**Problème :** `LaBoutikAuthBridgeView` recevait la clé API via le header `Authorization`.
Les WebViews Cordova bloquent `fetch + credentials:include` depuis une page Django externe
(preflight CORS + restriction navigateur) → la session n'était jamais établie.

**Fix :** lecture depuis `request.POST.get('api_key')` + `return HttpResponseRedirect('/laboutik/caisse/')`.
L'APK soumet un formulaire HTML natif (`form.submit()`) qui n'est pas soumis aux restrictions CORS.

> **Note APK :** `utils.js` (APK) doit aussi être modifié pour soumettre un form au lieu d'un fetch.
> Ce fichier n'est pas dans le repo Django — voir `patch_authBridge_pos_form_v2.sh` Patch 2.

---

### 10 — `reservoir_illimite` · `controlvanne/models.py` · `controlvanne/viewsets.py` · `controlvanne/admin.py` · migration 0004

**Pourquoi :** `reservoir_ml` vaut `0` par défaut sur une nouvelle `TireuseBec`. Sans stock
configuré, la tireuse refuse toutes les cartes avec "Empty keg" ou "Insufficient funds"
(le calcul `min(volume_solde, reservoir_disponible=0)` retourne 0 même avec du solde).

Ajout d'un switch `reservoir_illimite` (défaut `True`) qui :
- court-circuite le check "fût vide"
- passe `9 999 000 ml` à `calculer_volume_autorise_ml` pour que le calcul ne soit pas
  plafonné par le réservoir
- affiche `∞` dans la liste admin au lieu de `0 cl`

Script de déploiement : `patch_reservoir_illimite_v2.sh` (inclut la migration).

---

## Fichiers hors scope (APK Android uniquement)

Les changements suivants touchent le code source de l'APK LaBoutik
(`laboutit_client_android_v2/mobile-app/`) qui n'est pas tracké dans ce dépôt :

| Fichier | Changement | Patch source |
|---------|-----------|-------------|
| `assets/js/modules/utils.js` | `localStorage` fallback pour `readConfFile`/`writeFile` | `patch_LaBoutik_vps_v2.sh` |
| `assets/js/modules/utils.js` | `form.submit()` au lieu de `fetch+credentials` | `patch_authBridge_pos_form_v2.sh` Patch 2 |
| `cordova_local_plugins/…/NfcPlugin.kt` | `handleTag` injecte toujours via WebView JS | `patch_nfc_external_page_v2.sh` Patch 2 |
| `cordova_local_plugins/…/plugin.xml` | `onload=true` pour `NfcPlugin` | `patch_nfc_external_page_v2.sh` Patch 1 |
| `assets/css/index.css` + `sizes.css` | UI mise à jour | `patch_authBridge_pos_form_v2.sh` Patch 3 |

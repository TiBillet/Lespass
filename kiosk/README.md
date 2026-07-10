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

Un mode **DEMO** simule la carte NFC (aucun lecteur requis). Le TPE, lui, parle toujours à Stripe.

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


---

## 3. Deux cibles clientes

| Cible | NFC | Statut |
|---|---|---|
| **Android / Cordova** (borne Sunmi) | plugin Cordova natif (`laboutik_client_android_v2`) | **Complet** — c'est la cible de référence |
| **Raspberry Pi** (Chromium kiosk) | serveur socket.io local (voir §5.3) | **Complet** |

Le **TPE Stripe** fonctionne dans les deux cas : il est piloté par le serveur (`process_payment_intent`
sur le reader), indépendamment du client.

---

## 4. Déploiement du backend (serveur)

1. **Migrations** : `migrate_schemas` (tables `kiosk` 0001-0003, `BaseBillet` 0227).
2. **Activer le module** : admin tenant → dashboard → activer **Kiosk** (`Configuration.module_kiosk`).
3. **Créer une borne** : admin *discovery* → `PairingDevice` en rôle **KI (Kiosque)** → PIN 6 chiffres,
   puis appairer la borne Android avec ce PIN. Tant qu'aucune borne KI n'existe, le sélecteur
   « Borne (terminal appairé)» du TPE est vide.
4. **Appairer le TPE Stripe** : admin → *Kiosk → TPE Bancaires* → renseigner `name` + `registration_code`
   (code d'enregistrement affiché par le reader) + la borne. L'appairage crée le reader côté Stripe
   (compte Root). L'appel réseau a **toujours** lieu, y compris en `DEMO=1` : la clé Stripe est alors
   une clé de test, et le code `simulated-wpe` crée un lecteur simulé chez Stripe.
5. **Fedow** : déployer la modif de `fedow_core` — ⚠️ **rebuild d'image** `tibillet/fedow` (le code est
   baké dans l'image, un restart ne suffit pas) + `migrate` (0025).

---

## 5. Installation sur un Raspberry Pi

**Une borne kiosk, c'est un Pi LaBoutik.** Même carte, même lecteur NFC RC522, même écran tactile.
On installe donc **la stack LaBoutik telle quelle** (`laboutik_client_pi_desktop_v2/`), sans y toucher
ni en écrire une autre. Ce qui distingue les deux bornes n'est pas sur le Pi : c'est le **rôle du
`PairingDevice`**, choisi dans l'admin au moment de générer le PIN.

| | Caisse LaBoutik | Borne kiosk |
|---|---|---|
| Rôle du `PairingDevice` | `LB` | **`KI`** |
| Le bridge redirige vers | `/laboutik/caisse/` | **`/kiosk/`** |
| Installation sur le Pi | identique | identique |

Aucun script propre au kiosk. Pas de `curl … | bash`, pas de service `kiosk.service`, pas de fichier
de configuration à poser sur la carte SD.

### 5.1 Installer la stack LaBoutik

Procédure de référence : [`laboutik_client_pi_desktop_v2/readme_laboutik_client_pi_v2.md`](../laboutik_client_pi_desktop_v2/readme_laboutik_client_pi_v2.md).

Résumé, sur un Raspberry Pi OS Lite 32 bits :

```bash
# 1. Système, Node.js, NFC, écran, Chromium — « 0 » = écran en mode PAYSAGE
#    (le défaut « 3 » est le portrait 270°, utilisé par les caisses)
cd laboutik_client_pi_desktop_v2/install_pi
chmod +x setup-laboutik-pi
sudo ./setup-laboutik-pi gpio 0

# 2. Modules Node du client (place aussi type_app: 'pi' dans env.js)
cd ..
./install-modules-nodejs pi
```

Le script installe et configure tout : Node.js, le RC522 sur SPI, la rotation et la calibration
tactile, l'autologin console, Openbox, et Chromium en mode kiosk sur `http://localhost:3000/` —
c'est-à-dire sur le serveur Node local, qui sert sa propre page d'accueil.

### 5.2 Appairer la borne

Depuis l'écran tactile de la borne, sur la page d'accueil du client Node :

1. Renseigner le **serveur pin-code** : l'adresse **racine** du serveur TiBillet (pas le sous-domaine
   du lieu). C'est `env.server_pin_code`, modifiable directement dans l'interface.
2. Saisir le **PIN à 6 chiffres** du `PairingDevice` **de rôle `KI`** créé à l'étape 3 du §4.

Le client relaie le PIN vers `/api/discovery/claim/` (`modules/proxyDiscovery.js`), enregistre
`server_url` + `api_key` dans son `configLaboutik.json`, et affiche le serveur dans sa liste.

En cliquant dessus, `goServer()` (`www/assets/js/modules/utils.js`) soumet un formulaire POST vers
`{server_url}/laboutik/auth/bridge/` avec `api_key` et `type_app`. Le bridge pose le cookie `sessionid`,
lit le `terminal_role` de la borne, et **redirige un rôle `KI` vers `/kiosk/`** — un rôle `LB` irait
vers `/laboutik/caisse/`. C'est le seul aiguillage.

### 5.3 Lecteur NFC — rien à faire

Le `nfcServer.js` du client LaBoutik est déjà le serveur socket.io que le front kiosk attend.

Le front (`kiosk/static/kiosk/js/nfc.js`) choisit son mode hardware d'après `type_app`, exposé au JS par
`base.html` via `window.KIOSK.type_app` (mémorisé en session par `KioskViewSet.list` au premier appel du
bridge) :

- **`type_app=cordova`** (borne Android/Sunmi) → mode `NFCMC`, plugin NFC natif Cordova.
- **`type_app=pi`** → mode `NFCLO`, lecture via **socket.io local** (`http://localhost:3000`), événements
  `nfcStartListening` (demande) / `nfcMessage` (réponse `{ tagId, data }`) / `nfcStopListening` (arrêt).
  C'est exactement le protocole de `nfcServer.js`.

Comme `install-modules-nodejs pi` a écrit `type_app: 'pi'` dans `env.js`, le client transmet `pi` au
bridge : le front kiosk part donc en `NFCLO`, et `nfcServer.js` pilote le RC522 en SPI.

⚠️ **Deux `type_app` homonymes, deux rôles.** Celui d'`env.js` (`pi` / `desktop`) choisit le driver NFC
côté client : RC522 GPIO (`modules/devices/vma405-rfid-rc522.js`) ou ACR122U USB. Celui transmis au
bridge (`pi` / `cordova`) choisit le mode de lecture côté front Lespass. Ils portent la même valeur `pi`,
mais ne servent pas à la même chose.

Aucune adaptation du front Lespass n'est nécessaire : `nfc.js` (copie propre au kiosque, distincte du
`nfc.js` de la caisse) gère déjà `NFCMC` / `NFCLO` / `simule()`.

**Mode DEMO** : si `window.DEMO` est défini (page rendue avec `settings.DEMO=True`), `startLecture()`
ignore le hardware et affiche le **simulateur de cartes** (overlay plein écran, boutons
`primary`/`client1`/`client2`/`client3`/`unknown`) — identique au comportement LaBoutik. Voir le
scénario de recette dans `A TESTER et DOCUMENTER/kiosk-tpe-borne.md`.

### 5.4 Le TPE Stripe n'est pas sur le Pi

Le TPE (BBPOS WisePOS E) est un lecteur **réseau**, piloté par le serveur (`process_payment_intent` sur
le reader). Il est posé à côté de la borne, appairé dans l'admin (§4, étape 4). Le Pi ne le voit jamais.

---

## 6. Développement & tests

```bash
# Serveur : le module kiosk doit être activé. DEMO=1 simule seulement la carte NFC.
# Tests DB-only (16 tests)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_kiosk_models.py tests/pytest/test_kiosk_flow.py \
  tests/pytest/test_kiosk_branchements.py -v --api-key dummy
```

`DEMO=1` ne simule **que la carte NFC** (simulateur de tags côté front). Le TPE, lui, parle toujours
à Stripe : `send_to_terminal` crée un vrai `PaymentIntent` et `get_from_stripe` lit le vrai statut.
En mode test Stripe, utiliser le lecteur simulé (`registration_code = simulated-wpe`).

---

## 7. Références
- Conception : `TECH_DOC/SESSIONS/KIOSK/SPEC.md` (+ `INDEX.md`, `CHANTIER-01..04`).
- Recette manuelle : `A TESTER et DOCUMENTER/kiosk-tpe-borne.md`.
- Client Android complet : `laboutik_client_android_v2/`.
- Client Pi (identique à la caisse LaBoutik) : `laboutik_client_pi_desktop_v2/`.

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
| **Raspberry Pi** (Chromium kiosk) | serveur socket.io local (voir §5.5) | Installation validée, **lecture NFC non testée** (cf. §5.8) |

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

### 5.1 Matériel et image

| | |
|---|---|
| Carte | Raspberry Pi 3B+ (testé), Pi 4 |
| Image | **`2023-05-03-raspios-bullseye-arm64-lite.img.xz`** |
| Écran | Waveshare HDMI LCD, tactile, **en paysage** (7" `1024x600` ou 13,3" `1920x1080`) |
| NFC | RC522 (VMA405) sur GPIO, SPI logiciel |

⚠️ **Le tactile est un périphérique USB, distinct du HDMI.** Sur les Waveshare HDMI LCD, il faut relier
le port `Touch` de l'écran à un port USB du Pi, en plus du câble HDMI. Aucun pilote à installer : la
dalle se présente comme un HID (`lsusb` → `222a:0001 ILI Technology Multi-Touch Screen`), pris en charge
par `xserver-xorg-input-libinput` que le script installe.

💡 Si ni le tactile ni un clavier n'apparaissent (`lsusb` ne montre que le root hub) et qu'`eth0` est
absent : sur un Pi 3B+, les quatre ports USB **et** l'Ethernet sont portés par la même puce (LAN7515).
Si elle n'énumère pas, la carte est défectueuse — pas le HAT, pas l'alimentation. Vérifier avec
`dmesg | grep -c 'new .* USB device'` (doit être > 0) et `lsusb | grep 0424:`.

L'image se télécharge sur
[downloads.raspberrypi.org](https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/) :
Bullseye a disparu de `rpi-imager` (remplacé par Bookworm en octobre 2023).

⚠️ **Ne pas utiliser Bookworm.** La partition boot y est montée sur `/boot/firmware`, et `/boot/config.txt`
n'est plus qu'un fichier de renvoi (`The file you are looking for has moved to…`). `setup-laboutik-pi`
y écrit `dtparam=spi=on`, la rotation et les réglages HDMI : **rien ne serait appliqué**, `/dev/spidev*`
n'existerait pas et le NFC serait mort.

⚠️ **Ne pas utiliser une image 32 bits.** Node 24 (imposé par `setup-laboutik-pi`) n'existe plus en
`armhf` : Node.js a rétrogradé armv7 en « expérimental » et ne publie plus de binaires 32 bits
([release 24.0.0](https://nodejs.org/en/blog/release/v24.0.0)). En `arm64`, le paquet existe.

Dans `rpi-imager` : utilisateur `sysop`, SSH activé, Wi-Fi si besoin.

### 5.2 Installer — `make conf` puis `make install`

Tout passe par [`kiosk/Pi/Makefile`](./Pi/Makefile). Il **n'installe rien lui-même** : il appelle le
script officiel du client LaBoutik
([`readme_laboutik_client_pi_v2.md`](../laboutik_client_pi_desktop_v2/readme_laboutik_client_pi_v2.md)),
puis applique les correctifs nécessaires. Le code du client n'est pas modifié.

```bash
# make et curl ne sont pas dans l'image Lite
sudo apt-get update && sudo apt-get install -y make curl

curl -O https://raw.githubusercontent.com/TiBillet/Lespass/main-fedow-import/kiosk/Pi/Makefile

make conf     # écrit tibillet.conf avec les valeurs par défaut, puis l'affiche
make install  # clone + système + correctifs + écran + node + service
sudo reboot   # la borne démarre sur la page d'appairage
```

`make conf` crée le fichier s'il n'existe pas ; sinon il ne touche à rien. À éditer avant `make install`,
ou à surcharger en ligne de commande (`make install SCREEN_WIDTH=1024 SCREEN_HEIGHT=600`) :

```ini
SERVER=https://tibillet.coop   # adresse RACINE du serveur (pas le sous-domaine du lieu)
SCREEN_WIDTH=1920              # Waveshare 7" : 1024x600 — 13" : 1920x1080
SCREEN_HEIGHT=1080
ROTATE=0                       # 0 = paysage. Pilote aussi la calibration du tactile
NFC=gpio                       # gpio (RC522 sur les broches) ou usb (ACR122U)
GIT_BRANCH=main-fedow-import
```

**Le code PIN n'est pas dans ce fichier** : il se saisit sur l'écran tactile de la borne (§5.4).

Autres cibles : `make status` (état de la borne), `make logs` (journal du serveur NFC), et chaque étape
isolément (`clone`, `system`, `fix`, `screen`, `node`, `service`) — toutes rejouables.

#### Ce que `make install` corrige, et pourquoi

Quatre écarts constatés sur un Pi 3B+ neuf. Ils sont traités ici plutôt que dans le dépôt du client, qui
n'est pas maintenu par l'équipe Lespass.

**`sudo env USER=… HOME=…`** (cible `system`) — `sudo`, avec `env_reset` (défaut Debian), impose
`USER=root` et `HOME=/root`. Or le script fait `usermod -a -G gpio $USER` et écrit la ligne `startx` dans
`$HOME/.bashrc`. Sans ce contournement, les droits GPIO vont à *root* et le `startx` atterrit dans
`/root/.bashrc`, alors que l'autologin vise l'utilisateur : **X ne démarre jamais**.

**`reboot` neutralisé** (cible `system`) — le script se termine par un `reboot` en dur, ce qui couperait
l'installation en deux. Le Makefile place un faux `reboot` (`exit 0`) en tête de `PATH` le temps de
l'appel. Un seul redémarrage, à la fin, suffit : `dtparam=spi=on`, le bloc `hdmi_*` et l'autologin ne
prennent effet qu'au boot.

**`fbturbo` purgé** (cible `fix`) — l'`apt upgrade` du script monte `xorg-server` en
`2:1.20.11-1+rpt3+deb11u16`, qui ne fournit plus le symbole `shadowUpdatePackedWeak` réclamé par
`fbturbo_drv.so`. X meurt à l'ouverture du driver (`symbol lookup error: …`), `xinit` abandonne, donc **ni
Openbox ni Chromium**. Ce driver ne sert à rien : X fonctionne sur `fbdev`. Diagnostic difficile, car la
sortie de `startx` part sur `tty1`, invisible en SSH comme dans `/var/log/Xorg.0.log`.

**Cache npm et `env.js`** (cibles `fix` et `node`) — le `npm install -g` du script tourne en root avec
`HOME=/home/<user>` et laisse un `~/.npm` appartenant à root. Et `env.js` est absent du dépôt (seul
`env-example.js` y est), alors qu'`install-modules-nodejs` fait un `sed -i … env.js` : sans la copie, il
s'arrête net (`set -e`).

N'installez **pas** `pcscd` : il n'est utile qu'au driver ACR122U USB (`type_app: 'desktop'`), dont le
binding natif `nfc-pcsc` meurt sans le démon — sans même lever d'exception JavaScript.

### 5.3 Le serveur NFC au démarrage

**Rien ne lance `nfcServer.js`.** Le script `laboutik_launcher` (`clear && node nfcServer.js`) n'est
appelé par personne, et l'`autostart` d'Openbox ne lance que Chromium sur `http://localhost:3000/` —
c'est-à-dire sur un port que rien ne sert. La cible `make service` pose donc une unité systemd
(`tibillet-nfc.service`) qui démarre avant l'autologin, donc avant Chromium.

En `type_app: 'pi'`, `startBrowser()` est inerte (encadré par `if (env.type_app === 'desktop')`), donc le
serveur n'a besoin d'aucun `DISPLAY`.

```bash
make status                      # nfc: active, port 3000: en écoute
make logs                        # « Client connecté ! » quand Chromium se connecte
```

### 5.4 Appairer la borne

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

⚠️ **Un appareil déjà appairé sur ce tenant repart sur la caisse.** `goServer()` fait
`state.servers.find(item => item.server_url === url)` et `managedPinCode()` fait `state.servers.push(…)`
sans dédoublonner : si le même serveur figure déjà dans la liste (appairé auparavant en rôle `LB`), le
clic réutilise **la première `api_key` enregistrée**, donc l'ancienne, et le bridge redirige vers
`/laboutik/caisse`. Les deux entrées sont indiscernables à l'écran (`renderHtml.js` n'affiche que le
hostname). **Supprimer le serveur de la liste** (le bouton *Delete* retire toutes les entrées de cette
`server_url`) avant de saisir le PIN kiosk.

### 5.5 Lecteur NFC (RC522)

Le `nfcServer.js` du client LaBoutik est le serveur socket.io que le front kiosk attend. Câblage : voir
le tableau de `readme_laboutik_client_pi_v2.md`.

> ⚠️ Le README du client annonce « SDA (CS) → GPIO 24 (Pin 18) », alors que le driver initialise
> `rpi-softspi` avec `{clock: 23, mosi: 19, miso: 21, client: 24}` et `setResetPin(22)` — or `rpio`
> numérote par défaut les broches **physiques**, pas les GPIO BCM. Suivre le tableau du README ; en cas
> de lecteur muet, c'est la première piste.

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

#### Correctif du driver RC522 (2026-07-10)

Le commit `b294e695` (6 mai 2026) a fait passer `nfcServer.js` à l'API
`{ startListening, stopListening, getStatus }` et a mis à jour le driver **desktop** — sans toucher au
driver **Pi**. Depuis, `type_app: 'pi'` meurt au démarrage sur
`TypeError: nfc.startListening is not a function`, avant même que le port 3000 n'écoute.

`modules/devices/vma405-rfid-rc522.js` a donc été aligné sur le contrat :

- export de `startListening(socket, data)`, `stopListening()`, `getStatus(socket)` (`initNfcReader` reste
  en alias) ;
- l'`setInterval` de polling est mémorisé dans `pollingTimer` — il était jeté, `stopListening()` ne
  pouvait rien arrêter ;
- `emit({ tagId, data })` renvoie le `data` de la demande : le front vérifie `retour.data?.uuidConnexion`
  et **rejette toute lecture** dont l'`uuidConnexion` ne correspond pas ;
- lecture unique (arrêt du polling après un tag), comme `acr122u-u9.js`.

Validé sur matériel : une carte réelle ressort en `{"tagId":"0BE31636","data":{"uuidConnexion":"…"}}`.
À faire relire par l'auteur du client (`filaos974`).

#### Mode DEMO — simulateur **et** lecteur, en parallèle

Si `window.DEMO` est défini (page rendue avec `settings.DEMO=True`), `startLecture()` affiche le
**simulateur de cartes** *et* démarre le lecteur physique, comme le fait l'app Android. On peut donc
cliquer une carte simulée *ou* poser une vraie carte sur le RC522 : le premier des deux qui répond gagne.

Le simulateur est un **panneau discret, replié en bas de l'écran** (`#nfc-reader-simu-panel`) : on clique
son en-tête pour déplier les cartes `primary`/`client1`/`client2`/`client3`/`unknown`. Même principe que
le bouton `.nfc-toggle-simu` de la caisse (`laboutik/static/js/nfc.js`). Il ne masque pas le modal
SweetAlert : le message « scannez votre carte » reste lisible, et le lecteur reste l'action évidente.

C'est l'événement `nfcResult` qui tranche. Il ferme le modal, dont le `willClose` appelle
`rfid.stopLecture()` : le panneau est retiré et le lecteur arrêté (`nfcStopListening` + `disconnect`). Le
nettoyage est commun aux deux chemins, il n'y a donc pas de scan fantôme après coup.

Un `startLecture({simulation: true})` explicite n'allume pas le lecteur (simulateur seul).

Il n'est donc **plus nécessaire de basculer `DEMO=False`** pour tester le RC522. Scénario de recette :
`A TESTER et DOCUMENTER/kiosk-tpe-borne.md`.

⚠️ `nfc.js` est servi par **Django**, depuis `STATIC_ROOT` (`www/static/`, ignoré par git). Après un
déploiement, **`collectstatic` est obligatoire** : sans lui la borne continue de recevoir l'ancien script.

### 5.6 Le TPE Stripe n'est pas sur le Pi

Le TPE (BBPOS WisePOS E) est un lecteur **réseau**, piloté par le serveur (`process_payment_intent` sur
le reader). Il est posé à côté de la borne, appairé dans l'admin (§4, étape 4). Le Pi ne le voit jamais.

### 5.7 Vérifications

```bash
make status
```

Il affiche l'architecture, le système, la présence du dépôt et d'`env.js`, l'état de fbturbo, les groupes
`gpio`/`spi`, `/dev/spidev0.0`, le service `tibillet-nfc`, le port 3000 et les processus X/Openbox/Chromium.

En cas d'**écran noir**, la cause est presque toujours X, et sa sortie n'est visible ni en SSH ni dans
`/var/log/Xorg.0.log` : la rediriger depuis `~/.bashrc`
(`… && startx -- -nocursor > ~/startx.log 2>&1`), puis `sudo reboot` et lire `~/startx.log`. Éviter
d'enchaîner les `systemctl restart getty@tty1` : chaque cycle laisse un `/tmp/.X<n>-lock` et `startx`
incrémente le numéro d'écran (`:0`, `:1`, `:2`…), ce qui brouille le diagnostic.

Pour tester le **lecteur RC522 seul**, sans serveur ni navigateur, un script de quelques lignes suffit :
importer le driver, appeler `startListening(fauxSocket, {uuidConnexion: 'test'})` et afficher les
`nfcMessage`. Un tag valide ressort sous la forme
`{"tagId":"0BE31636","data":{"uuidConnexion":"test"}}`.

### 5.8 Statut de validation

Vérifié sur Pi 3B+ (Bullseye arm64, 2026-07-10), à la main, étape par étape : installation système,
Node 24, session X, Openbox, Chromium en kiosk, serveur Node en écoute, page d'appairage servie,
socket.io connecté, proxy de claim atteignant la préprod, **et lecture d'une vraie carte sur le RC522**
(`tagId` + `data.uuidConnexion` correctement réémis par le driver patché).

**Non vérifié à ce jour** : le `Makefile` de bout en bout (ses cibles reprennent une à une des commandes
validées à la main, mais l'enchaînement complet — notamment le shim `reboot` — n'a pas encore tourné),
l'appairage jusqu'à `/kiosk/`, le simulateur et le lecteur en parallèle (§5.5, nécessite le déploiement
de la préprod et un `collectstatic`), et le paiement TPE.

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

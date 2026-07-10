# Changelog / Journal des modifications

## Kiosk : refonte du front (design « Signalétique ») + 5 correctifs / Kiosk: front redesign + 5 bug fixes

**Date :** 2026-07-10
**Migration :** Non / No

**Quoi / What :** refonte complète des templates et du CSS de l'app `kiosk`, plus la correction de
cinq bugs découverts en relisant le HTML. Le front est désormais pensé comme un **distributeur**
(automate de titres de transport) et non comme une page web : plus d'ombre portée, plus de carte
flottante, plus d'effet de survol sur un écran tactile. Le montant devient un **afficheur** géant
toujours visible, et les 5 montants + « Effacer » forment un **pavé de 6 touches**.

**Pourquoi / Why :** le CSS reprenait la palette Bootstrap par défaut (`#0d6efd`, `#198754`,
`#dc3545`), `border-radius: 10px` et `box-shadow: 0 4px 8px` sur tout, `translateY(-3px)` au survol
d'une borne tactile, et des emoji (`💳 ➡️`, `⬆️⬆️⬆️`) en guise d'illustration. Le mode nuit était
piloté par des styles inline injectés en JS, qui écrasaient la feuille de style et cassaient l'i18n.

### Bugs corrigés / Fixed bugs

| # | Bug | Correctif |
|---|---|---|
| 1 | **Double compte à rebours** sur les écrans finaux : l'IIFE du template ET `main.js:initializePage()` (rappelé par `htmx:afterSwap`) lançaient chacun un `setInterval` sur `#countdown`. Redirection à ~7,5 s au lieu de 15 s. | Un seul minuteur, dans `partial/state_screen.html`, avec garde `clearInterval` avant démarrage. Retiré de `main.js`. |
| 2 | **`id="tb-kiosque"` en double dans le DOM** : `waiting_credit_card_terminal.html` déclarait cet id alors qu'il est swappé en `innerHTML` **dans** `#tb-kiosque`. Le swap OOB du websocket ne tombait sur le bon élément que par chance. | Le partial ne déclare plus l'id. |
| 3 | **Spinner « paiement en cours » invisible en mode jour** : seul `.dark-mode .spinner_bootstrap` existait, sans règle de base. `.spinner-box` n'était pas défini non plus. | `.spinner-inline`, stylé dans les deux thèmes. |
| 4 | **Overlay de chargement mal positionné** : `position: absolute` cale le voile en haut du *document*, pas du viewport. | `position: fixed`. |
| 5 | **Mode nuit cassait l'i18n** : `main.js` faisait `button.innerHTML = 'Mode Jour'` en français codé en dur. | Les deux libellés sont dans le HTML, traduits ; le CSS montre le bon selon `data-theme`. |

### Design

- **Thème custom « Signalétique »** : papier chaud `oklch(96.6% .006 85)`, encre froide
  `oklch(17% .014 258)`, accent ambre `oklch(74% .155 68)` (couleur des afficheurs d'automates,
  lisible sur clair **et** sur sombre). États pleine page : pin et brique, plus le vert/rouge Bootstrap.
- **Polices déjà présentes dans le dépôt** : **Luciole** (dessinée pour la basse vision — le bon choix
  pour une borne publique lue de loin) en UI, chiffres tabulaires ; **Staatliches** pour les mots d'état.
  Zéro nouvel asset, zéro CDN.
- **Bootstrap retiré de la borne** : aucun composant JS Bootstrap n'était utilisé et SweetAlert2 injecte
  sa propre feuille de style. ~250 Ko économisés sur un Android de festival.
- **Emoji remplacés par du SVG dessiné à la main** : carte → TPE, et chevrons montants vers le lecteur NFC.
- **Motion tactile** : plus de `:hover` (guardé par `@media (hover:hover)`), enfoncement `scale(.97)` à
  90 ms. `prefers-reduced-motion` respecté.
- **Durcissement borne** : `touch-action: manipulation`, `overscroll-behavior: none`,
  `-webkit-tap-highlight-color: transparent`, `user-select: none`, `env(safe-area-inset-*)`, `100svh`.

### Responsive

Une **seule** media query, sur le **ratio** de l'écran (`min-aspect-ratio: 5/4`), bascule entre une
colonne (téléphone portrait, action collée au pouce) et deux colonnes (kiosque paysage). Les tailles
suivent `vmin` — la dimension *contrainte* de l'écran — donc aucune media query de taille.
Vérifié sans débordement ni libellé replié en **1920×1080, 1280×720, 1024×600, 375×667 et 320×568**,
en mode jour et en mode nuit.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `kiosk/static/kiosk/css/tokens.css` | **Neuf** — jetons OKLCH, `@font-face` Luciole/Staatliches, échelle 4 pt, thème sombre |
| `kiosk/static/kiosk/css/kiosk.css` | Réécrit — mise en page, 12 sections, aucune valeur brute |
| `kiosk/static/kiosk/js/main.js` | Réécrit — thème via `data-theme`, ~160 lignes de JS mort supprimées |
| `kiosk/templates/kiosk/base.html` | Bootstrap retiré, amorçage du thème avant premier rendu, `lang` via i18n, `viewport-fit=cover` |
| `kiosk/templates/kiosk/partial/topbar.html` | **Neuf** — bandeau + bascule jour/nuit (libellés traduits dans le HTML) |
| `kiosk/templates/kiosk/partial/state_screen.html` | **Neuf** — écran d'état partagé + compte à rebours unique |
| `kiosk/templates/kiosk/select_amount_content.html` | Afficheur + pavé de 6 touches, microdata invalide retirée |
| `kiosk/templates/kiosk/sweet_scan_button.html` | Bouton restructuré, `tag-id` → `data-tag-id`, chevrons SVG |
| `kiosk/templates/kiosk/waiting_credit_card_terminal.html` | `#tb-kiosque` retiré, styles inline retirés, illustration SVG |
| `kiosk/templates/kiosk/success.html` / `cancel.html` | Réduits à un `{% include %}` du partial commun |
| `kiosk/templates/kiosk/spinner.html` | `<style>` déplacé dans `kiosk.css`, `position: fixed` |
| `kiosk/templates/kiosk/select_amount.html` | Commentaire sur l'unicité de `#tb-kiosque` |

### i18n

Nouvelles chaînes à traduire (`makemessages` + `compilemessages` à lancer par le mainteneur) :
`Recharge`, `Paiement`, `Montant à recharger`, `euros`, `Choisir un montant`, `Mode nuit`,
`Mode jour`, `Kiosque TiBillet`, `Kiosque TiBillet pour recharger votre carte ou enregistrer vos
informations`, `Vous pouvez appuyer plusieurs fois sur une touche pour additionner.`

`Mode Nuit` (ancienne casse) et `Vous pouvez cliquer plusieurs fois sur les boutons pour additionner
le montant. :)` deviennent obsolètes.

---

## Kiosk : installation Pi via la stack LaBoutik + admin TPE / Kiosk: Pi install via the LaBoutik stack + terminal admin

**Date :** 2026-07-09
**Migration :** Oui / Yes — `kiosk` 0004 (renommage d'affichage uniquement, `AlterModelOptions`)

**Quoi / What :** la borne kiosk sur Raspberry Pi s'installe avec **la stack LaBoutik existante**
(`laboutik_client_pi_desktop_v2/`), sans script ni configuration propres au kiosk. Même matériel, même
lecteur NFC, même client Node. Le seul aiguillage est le **rôle du `PairingDevice`** : un rôle `KI` est
redirigé vers `/kiosk/` par le bridge d'auth, un rôle `LB` vers `/laboutik/caisse/`. §5 du
`kiosk/README.md` réécrite : image Bullseye **arm64**, contournements `sudo env` / `fbturbo` / `env.js`,
service systemd pour `nfcServer.js`, écran en paysage (`setup-laboutik-pi gpio 0`).

**`kiosk/Pi/Makefile`** : `sudo apt install make curl`, `curl -O …/Makefile`, `make conf`, `make install`,
`sudo reboot`. Le Makefile n'installe rien lui-même — il appelle `setup-laboutik-pi` puis applique les
correctifs (fbturbo purgé, cache npm, `env.js`, définition d'écran, service systemd). Il neutralise le
`reboot` en dur du script (faux `reboot` en tête de `PATH`) pour n'avoir qu'un seul redémarrage, à la fin.
`tibillet.conf` (auto-généré, commenté) porte `SERVER`, `SCREEN_WIDTH/HEIGHT`, `ROTATE`, `NFC`, `GIT_BRANCH` —
**pas le code PIN**, qui se saisit sur l'écran tactile.

**Correctif du driver RC522** (`vma405-rfid-rc522.js`) : depuis `b294e695` (6 mai 2026), `nfcServer.js`
attend `{ startListening, stopListening, getStatus }` — le driver Pi n'exposait que `initNfcReader`, donc
`type_app: 'pi'` mourait au démarrage. Le driver expose désormais le contrat, mémorise l'ID du polling
(`stopListening` ne pouvait rien arrêter), renvoie `{ tagId, data }` (le front rejette les lectures dont
`data.uuidConnexion` ne correspond pas) et s'arrête après un tag. **Validé sur matériel** (lecture d'une
carte réelle sur RC522). À relire par `filaos974`.

**Simulateur et lecteur en parallèle** (`kiosk/static/kiosk/js/nfc.js`) : en `DEMO`, `startLecture()`
faisait `simule(); return` et le lecteur physique n'était jamais interrogé. Il affiche désormais le
simulateur **et** démarre le lecteur, comme l'app Android : le premier des deux qui répond gagne, et
`stopLecture()` (appelé par le `willClose` du modal) nettoie les deux.

Côté admin : `Terminal` s'affiche désormais « TPE Bancaire », `StripeLocation` sort de l'admin (créée
automatiquement à l'appairage, comme dans LaBoutik), et le champ « Borne » affiche le nom de la borne au
lieu de son email synthétique, filtré sur le rôle `KI`.

**Pourquoi / Why :** ne pas maintenir deux procédures d'installation pour un matériel identique, et
lever la confusion entre le TPE bancaire Stripe et les terminaux Pi/Sunmi de LaBoutik.

**Non vérifié / Not verified :** lecture NFC réelle sur RC522, appairage complet jusqu'à `/kiosk/`,
paiement TPE. Installation, session X, serveur Node et proxy de claim validés sur Pi 3B+.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/README.md` | §5 réécrite : image arm64, contournements, service systemd, statut de validation |
| `laboutik_client_pi_desktop_v2/modules/devices/vma405-rfid-rc522.js` | Aligné sur le contrat de `nfcServer.js` (cf. ci-dessus) |
| `kiosk/models.py` | `Terminal.Meta` : `verbose_name = "TPE Bancaire"` |
| `kiosk/admin.py` | `StripeLocationAdmin` supprimé ; `term_user` filtré sur `KI` et affiché par son nom |
| `discovery/views.py` | `TermUser.first_name = pairing_device.name` à l'appairage |
| `Administration/admin/dashboard.py` | Sidebar : « TPE Bancaires », entrée « Emplacements Stripe » retirée |

---

## Kiosk : borne de recharge cashless TPE Stripe / Kiosk: self-service cashless top-up terminal (Stripe TPE)

**Date :** 2026-07-07
**Migration :** Oui / Yes — `kiosk` 0001-0003, `BaseBillet` 0227 (Lespass) ; `fedow_core` 0025 (Fedow)

**Quoi / What :** nouvelle app `kiosk` (borne libre-service Android/Cordova + TPE Stripe WisePOS),
portée depuis LaBoutik et rebranchée sur Lespass. Le crédit de la carte reste **côté Fedow distant**
(coexistence V1, webhook Stripe). Modèles TPE (`StripeLocation`/`Terminal`/`PaymentsIntent`), admin
Unfold, `KioskViewSet`, front HTMX, WebSocket `TerminalConsumer`, module Groupware `module_kiosk`,
routage du bridge d'auth (rôle `KI` → `/kiosk/`).

**Pourquoi / Why :** offrir la recharge cashless en autonomie sur borne, sans caisse.

**Décision sécurité :** une place Lespass **ne signe pas** les metadata TPE ; la route webhook Fedow
est étendue (miroir « EXTENSION S6 ») pour l'accepter, l'idempotence anti-rejeu étant durcie
(`unique` + `IntegrityError`). Repose sur l'hypothèse : compte Stripe Root exclusif au serveur de la
fédération (voir `TECH_DOC/SESSIONS/KIOSK/SPEC.md` §8bis).

### Fichiers principaux / Main files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/` (app) | Modèles, admin, viewset, validators, tasks, urls, templates, static |
| `fedow_connect/fedow_api.py` | `NFCcardFedow.retrieve(tag_id)` (+ fix `self.config`→`self.fedow_config`) |
| `wsocket/consumers.py`, `routing.py` | `TerminalConsumer` + `ws/terminal/<pi_id>/` |
| `laboutik/views.py` | Bridge routé selon `terminal_role` (KI → `/kiosk/`) |
| `BaseBillet/models.py`, `Administration/admin/dashboard.py` | `module_kiosk` + sidebar |
| **Fedow** `fedow_core/views.py`, `models.py` | Extension route TPE place Lespass + idempotence |

### Déploiement / Deployment
- **Fedow : rebuild d'image** (code baké) + `migrate` (0025) — un restart ne suffit pas.
- `makemessages`/`compilemessages` pour les `{% translate %}` du front.

## Controlvanne : fixes de la review critique — double facturation, reconnexion kiosk, refus propres / Controlvanne: critical review fixes — double billing, kiosk reconnection, clean refusals

**Date :** 2026-07-06
**Migration :** Non / No

Tour critique complet de l'app (3 reviewers : circuit monétaire, stock/
signaux, vues/JS — findings contre-vérifiés) puis correction TDD des
findings bloquants. **C1** : deux `pour_end` concurrents (retry réseau du Pi)
facturaient DEUX FOIS le même tirage — prouvé par un test à 2 threads —
corrigé par verrou `select_for_update` sur la session + transaction atomique
englobant fermeture/réservoir/facturation (**I1** : compteurs cohérents) ;
le push WS du signal passe sous `on_commit`. **C2** : le kiosk 24/7 gelait
en silence à la première coupure — reconnexion automatique avec backoff
(1 s→30 s) + bandeau « connexion perdue ». **C3** : carte sans wallet
résoluble → refus propre au lieu d'un 500 (décision : pas de wallet éphémère
créé à la tireuse, une carte sans wallet n'a aucun token). **I2** : swap de
fût sans Stock → réservoir remis à 0. **I3** : volume négatif rejeté à la
validation. **I4** : volume affiché correct sur tirage court. 5 tests de
garde (`test_controlvanne_review_fixes.py`), 52 tests controlvanne+discovery
verts. Findings Minor en dette : `TECH_DOC/SESSIONS/CONTROLVANNE/REVIEW-2026-07-06-tour-critique.md`.

/ Full critical review of the app (3 reviewers, findings re-verified) then
TDD fixes. **C1**: two concurrent `pour_end` (Pi network retry) billed the
same pour TWICE — proven by a 2-thread test — fixed with a
`select_for_update` session lock + one atomic transaction around close/
reservoir/billing (**I1**); the signal's WS push now uses `on_commit`.
**C2**: the 24/7 kiosk froze silently on any disconnection — automatic
reconnection with backoff + "connection lost" banner. **C3**: card without
a resolvable wallet → clean refusal instead of a 500. **I2/I3/I4**: keg-swap
reservoir reset, negative volume rejected, correct short-pour display.

### Fichiers modifiés / Modified files
| Fichier / File | Fix |
|---|---|
| `controlvanne/viewsets.py` | C1+I1 : verrou session + atomic |
| `controlvanne/signals.py` | on_commit sur le push WS ; I2 swap de fût |
| `controlvanne/billing.py` | C3 refus propre |
| `controlvanne/serializers.py` | I3 min_value=0 |
| `controlvanne/models.py` | I4 dernier_volume_ml |
| `controlvanne/static/.../panel_kiosk.js` + `templates/base.html` | C2 reconnexion + bandeau |
| `tests/pytest/test_controlvanne_review_fixes.py` | 5 tests de garde (créé) |

## WebSockets en production : supervisord mono-conteneur / Production WebSockets: single-container supervisord

**Date :** 2026-07-06
**Migration :** Non / No — mais **rebuild de l'image requis** (paquet supervisor) / but **image rebuild required** (supervisor package)

En production, rien ne servait les WebSockets (gunicorn est WSGI) : le POS
laboutik et les tireuses controlvanne n'avaient pas de temps réel. Décision
(pattern LaBoutik, un seul conteneur) : **supervisord** orchestre gunicorn
(HTTP :8002), **daphne** (WebSockets :7999) et celery (worker + beat) dans le
conteneur `lespass_django`. nginx prod route `/(wss|ws)/` vers daphne. Le
service `lespass_celery` du compose pre-prod disparaît. Au passage, fix du
bug dormant `AppRegistryNotReady` dans `TiBillet/asgi.py`
(`get_asgi_application()` avant les imports applicatifs — fatal sous daphne
standalone). Testé : handshake WS 101 sous supervisord, 403 sans Origin
(validateur actif), dev intact. Détail et tests :
`A TESTER et DOCUMENTER/supervisor-websockets-prod.md`.

/ In production nothing served WebSockets (gunicorn is WSGI). Single-container
decision (LaBoutik pattern): **supervisord** orchestrates gunicorn (:8002),
**daphne** (:7999, WebSockets) and celery (worker + beat) inside
`lespass_django`. Prod nginx routes `/(wss|ws)/` to daphne. The separate
`lespass_celery` service is removed. Also fixes the dormant
`AppRegistryNotReady` bug in `TiBillet/asgi.py`. Tested: WS handshake 101
under supervisord, dev untouched.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `supervisor/supervisord.conf` + `conf.d/{gunicorn,daphne,celery}.conf` | Créés / Created |
| `start.sh` | supervisord + tail (plus de gunicorn direct) |
| `dockerfile` | + paquet supervisor |
| `nginx_prod/lespass_prod.conf` | location `/(wss\|ws)/` → daphne :7999 |
| `docker-compose.pre-prod.yml` | django → `start.sh`, nginx → conf prod, service celery supprimé |
| `TiBillet/asgi.py` | Fix AppRegistryNotReady (ordre des imports) |
| `launch_ws.sh` | Supprimé (remplacé par conf.d/daphne.conf) |
| `flush.sh` | Conscient de supervisord : `stop all` avant le dropdb (sinon les connexions PG le bloquent), `start all` à la fin au lieu du runserver (collision :8002). Dev inchangé. |
| `dockerfile` (fix build) | `apt-get update &&` sur la ligne d'install : le cache Docker rejouait l'install sur des index apt périmés (404, exit 100) |

## Controlvanne branchée : tireuses connectées + appairage terminaux dans l'admin / Controlvanne wired: connected taps + terminal pairing in the admin

**Date :** 2026-07-06
**Migration :** Oui / Yes — `migrate_schemas` (controlvanne 0001→0004 + BaseBillet 0226)

L'app `controlvanne` (tireuse à bière connectée, version mergée par Mike) est
câblée : TENANT_APPS, URLs `/controlvanne/`, routes WebSocket `ws/rfid/`,
migrations (dépendance BaseBillet réécrite 0205→0222 + 0004 générée pour
`reservoir_illimite`). L'appairage TI est réactivé dans discovery (claim PIN →
`TireuseAPIKey` + `tireuse_uuid`). `SaleOrigin.TIREUSE` ajouté (requis par la
facturation tireuse). Fix `TermUserManager` : filtre par `client_source` (le
champ que le claim remplit et que les permissions vérifient) au lieu de
`client_admin` — les terminaux appairés étaient invisibles dans l'admin, et un
terminal ne doit jamais passer `is_tenant_admin()`. Le menu « Terminaux
hardware » pointe vers la changelist PairingDevice (process d'appairage
complet : création du PIN avec choix du rôle LB/KI, suivi des PIN en attente
et des appareils réclamés — TI exclu du formulaire manuel, auto-créé avec sa
TireuseBec). Carte dashboard « Connected taps » activée. 47 tests portés/écrits
(controlvanne models/api/billing + discovery pairing). Suite complète :
689 passed, 0 failed.

/ The `controlvanne` app (connected beer tap, Mike's merged version) is wired:
TENANT_APPS, `/controlvanne/` URLs, `ws/rfid/` WebSocket routes, migrations.
TI pairing re-enabled in discovery (PIN claim → `TireuseAPIKey`).
`SaleOrigin.TIREUSE` added. `TermUserManager` fixed to filter by
`client_source` (paired terminals were invisible; a terminal must never pass
`is_tenant_admin()`). The "Hardware terminals" menu now targets the
PairingDevice changelist (full pairing process, LB/KI role choice, TI
auto-created with its TireuseBec). "Connected taps" dashboard card enabled.
47 tests ported/written; full suite: 689 passed, 0 failed.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | TENANT_APPS += `controlvanne` |
| `TiBillet/urls_tenants.py` | `path('controlvanne/', ...)` |
| `TiBillet/asgi.py` | Routes WS controlvanne décommentées |
| `controlvanne/migrations/0001_initial.py` | Dépendance BaseBillet 0205→0222 |
| `controlvanne/migrations/0004_*.py` | Générée : reservoir_illimite/reservoir_ml |
| `BaseBillet/models.py` + migration 0226 | `SaleOrigin.TIREUSE` |
| `discovery/views.py` | Flow claim TI réactivé |
| `discovery/admin.py` | `terminal_role` exposé, TI exclu du form, rôle figé |
| `AuthBillet/models.py` | `TermUserManager` → filtre `client_source` |
| `Administration/admin_tenant.py` | `TermUserAdmin` : 4 permissions, last_login |
| `Administration/admin/dashboard.py` | Menu Terminals → PairingDevice ; carte `module_tireuse` activée |
| `tests/pytest/test_controlvanne_*.py` (×3) | Portés (36 tests) |
| `tests/pytest/test_discovery_*.py` (×2) | Portés + 2 tests TI (TDD) |

**Tuto Pi remis à jour / Pi tutorial refreshed** : `controlvanne/README.md` +
`Pi/README.md` (champs réels du form tireuse, comptes de tests, E2E non portés
signalés) ; `install_pi.sh` passe en **clone complet** (`--depth=1`, plus de
sparse-checkout) ; plus d'adresse de dev en dur — le `Makefile` lit ses défauts
dans le **`.env`** (`CLAIM_SERVER_URL` = adresse racine pour ré-appairer,
`SERVER_URL` = tenant, `GIT_REPO`/`GIT_BRANCH`) : l'adresse du serveur se
change en éditant le `.env`. Branche par défaut : `main-fedow-import`
(à repointer au merge, action notée dans le hub CONTROLVANNE). Chaîne
`make claim` testée en réel contre le serveur dev (avec et sans `SERVER=`).

Voir `A TESTER et DOCUMENTER/controlvanne-cablage.md` pour les scénarios de
test manuels et les dettes signalées (WebSocket prod → chantier supervisor,
PRs déférées de Mike, bugs préexistants découverts).

## Statics : fin des namespaces reunion/ et faire_festival hors de leur app / Statics: reunion/ namespace removed, faire_festival moved to its app

**Date :** 2026-07-06
**Migration :** Non / No

Les templates avaient migré mais pas les statics. Nettoyage vérifié par
références :
- **Déplacés vers `commun/js/`** (5 réfs template mises à jour) :
  form-spinner.mjs, booking-calculator.mjs, qrcode.min.js,
  qr-scanner.min.js + worker (+ source maps, déplacés ensemble : le worker
  est importé en chemin relatif).
- **`static/faire_festival/` → app pages** (`pages/static/faire_festival/`),
  namespace d'URL inchangé → zéro référence à modifier (templates ff et
  seeders continuent de pointer `faire_festival/...`).
- **Supprimés (zéro référence)** : reunion/leaflet/ (remplacé par
  pages/vendor/leaflet), reunion/js/htmx.min.1.9.12.js (tout le monde charge
  mvt_htmx/js/), reunion/media/*.jpg (3 photos orphelines). Le dossier
  `BaseBillet/static/reunion/` n'existe plus.
- **Vérifié** : findstatic sur chaque fichier migré, statuts HTTP 200 sur
  les URLs servies, page événement (réservation) chargeant commun/js/*,
  home ff chargeant ses statics — et suite pytest complète : 368 passed.

## Fil d'ariane : plus de lien vers un parent brouillon / Breadcrumb: no more link to a draft parent

**Date :** 2026-07-06
**Migration :** Non / No

Backlog re-vérifié (3 points) : jsonld_page dans ff/page.html ✅ déjà réglé ;
références motif/*.svg fantômes ✅ parties avec static/reunion ; restait le
fil d'ariane d'une sous-page dont le PARENT est dépublié — lien visible ET
maillon BreadcrumbList JSON-LD pointaient vers un brouillon (→ 404, et
signal SEO incohérent). Le maillon parent est désormais conditionné à
`parent.publie` aux 3 endroits (page.html classic + ff, jsonld_page), le
fil retombe sur « Accueil › page ». Test pytest aller-retour
(brouillon → masqué, republié → maillon de retour).

## Admin : éditeur Markdown EasyMDE pour le bloc MARKDOWN / Admin: EasyMDE Markdown editor for the MARKDOWN block

**Date :** 2026-07-05
**Migration :** Non / No

Le bloc MARKDOWN s'éditait dans le WYSIWYG Trix (qui produit du HTML) —
pénible et destructeur pour de la source Markdown. Après étude des options
(ToastUI trop lourd, Milkdown/MDXEditor exigent un bundler, TinyMDE plus
maintenu), choix : **EasyMDE 2.21.0** (release mai 2026, activement
maintenu), VENDORISÉ (`pages/static/pages/vendor/easymde/`, ~330 Ko,
zéro CDN, zéro dépendance pip).
- **Deux champs de formulaire pour un champ modèle** : `texte` garde Trix
  (types HTML), le nouveau champ de FORMULAIRE `texte_markdown` (affiché
  seulement pour MARKDOWN via conditional_fields) porte EasyMDE ; la valeur
  vit toujours dans `Bloc.texte` (initial au chargement, recopie APRÈS
  sanitize dans save_model — retours à la ligne préservés, aller-retour
  testé en shell).
- Éditeur : coloration markdown live, barre d'outils essentielle (sans
  upload d'image — les images passent par l'encart + `galerie:N`), aperçu,
  côte-à-côte, plein écran ; correcteur anglais désactivé.
- `editeur_markdown.js` : init + PIÈGE géré — CodeMirror mesuré dans le
  conteneur caché par Alpine se dessine à 0px → refresh au changement de
  type et après chargement. `editeur_markdown.css` : accordage clair/sombre
  (classe .dark d'Unfold).
- Vérifié en capture authentifiée (fiche de l'article de démo).
- **Plein écran / côte-à-côte au-dessus de l'admin** : les calques
  position:fixed d'EasyMDE (z-index 8-9) passaient DERRIÈRE les menus
  d'Unfold (z-40) → remontés à z-60 (un plein écran couvre tout l'écran,
  menus compris). Signalé par le mainteneur, vérifié par capture avec clic
  réel sur le bouton côte-à-côte.
- **Aperçu fidèle** : `previewRender` résout `![légende](galerie:N)` vers
  les vraies URLs (table position→URL embarquée par le formulaire en
  data-attribute — même règle que le rendu serveur) au lieu d'une image
  cassée ; typographie de l'aperçu restaurée (le reset Tailwind de l'admin
  aplatissait titres, listes et citations).

## Admin blocs : filtres avancés Unfold / Blocks admin: Unfold advanced filters

**Date :** 2026-07-05
**Migration :** Non / No

La liste des blocs passe aux filtres avancés Unfold (pattern
« driverwithfilters » de la démo), affichés SUR la page
(`list_filter_sheet = False`) :
- **Par Page** : liste de LIENS cliquables (préférence mainteneur, réitérée
  contre l'autocomplete d'abord proposé) ;
- **Par Page parente** : autocomplete — tous les blocs des sous-pages d'une
  page (ex. tous les blocs des articles du Journal) ;
- **Par Type de bloc** : menu déroulant compact (16 types).
NOTE responsive : l'affichage sur la page n'existe qu'à partir du breakpoint
2xl (fenêtre ≥ 1536 px) — en dessous, Unfold retombe automatiquement sur le
bouton « Filtres » + tiroir latéral (mêmes filtres). Vérifié en captures
authentifiées 1440/1720 px (Playwright + force_login E2E).

## Admin pages : tri par glisser-déposer / Pages admin: drag-and-drop sorting

**Date :** 2026-07-05
**Migration :** Non / No

La liste des Pages passe au sortable Unfold (comme les blocs) : poignée de
glisser-déposer à la place de la colonne `position` — l'ordre enregistré
pilote directement l'ordre de la navbar.

## Blog : images d'illustration dans les articles Markdown / Blog: illustration images in Markdown articles

**Date :** 2026-07-05
**Migration :** Non (réutilise ImageGalerie) / No (reuses ImageGalerie)

Un article Markdown peut désormais être illustré avec de VRAIES images
uploadées (proposition mainteneur : « inline image + balise dans le
markdown ») :
- **L'inline « Images »** (le même que la galerie, avec son tri par
  glisser-déposer) apparaît aussi sur les blocs MARKDOWN
  (`BlocAdmin.get_inlines`).
- **Dans le texte** : syntaxe markdown standard `![légende](galerie:N)` —
  N = position de l'image dans l'inline. Le nouveau filtre
  `rendre_bloc_markdown` résout la référence vers l'URL réelle (variation
  `med`, non croppée) AVANT le rendu markdown+nh3. Alt vide → la légende de
  l'inline ; référence inconnue → marqueur texte visible
  « [image galerie:N introuvable] » (jamais de trou silencieux).
- **Aide dans l'admin** : note contextuelle sur la fiche du bloc MARKDOWN
  (même mécanisme Alpine que l'aide HERO) documentant la syntaxe.
- **Fixture** : l'article « fresque participative » du blog de démo est
  illustré (image dans l'inline + référence dans le texte) — rendu vérifié.
- Les images externes `![alt](https://…)` fonctionnent aussi (nh3 conserve
  `<img src=https>`). Tests : résolution, fallback légende, réf inconnue.

## Admin bloc : l'inline « Images de galerie » n'apparaît que sur un bloc GALERIE / Block admin: the gallery-images inline only shows on GALERIE blocks

**Date :** 2026-07-05
**Migration :** Non / No

`ImageGalerie` ne sert qu'au bloc GALERIE (modèle porteur de ses images) mais
l'inline s'affichait sur TOUS les types de blocs (bruit dans le formulaire).
`BlocAdmin.get_inlines` ne le retourne plus que pour un bloc GALERIE
enregistré ; à la création (type inconnu côté serveur), il apparaît après le
premier enregistrement — flux Django standard.

## Bloc IMAGE : champ explicite `affichage_image` (fin de l'interrupteur caché) / IMAGE block: explicit `affichage_image` field (no more hidden toggle)

**Date :** 2026-07-05
**Migration :** Non pour la branche (champ plié dans `pages/0001` régénérée ; colonne posée à la main sur la base dev) / Folded into the regenerated `pages/0001`

Le skin faire_festival choisissait le rendu du bloc IMAGE selon la PRÉSENCE
du titre (interrupteur caché, jugé mauvais pattern par le mainteneur) : une
photo titrée devenait une vignette minuscule (« Notre démarche »). Désormais :
- **`Bloc.affichage_image`** (choices, pattern `image_position`) :
  `PLEINE_LARGEUR` (défaut, photos) ou `VIGNETTE_TITRE` (petite image-titre
  dessinée, centrée à taille naturelle). Le champ `titre` redevient un simple
  texte alternatif.
- Honoré par les DEUX skins : ff (les 2 modes historiques, choisis
  explicitement) et classic (nouvelle variante `--vignette`).
- Intégré partout : catalogue API v2, openapi, admin (`conditional_fields`
  sur le type IMAGE), seeder ff (les 2 images-titres dessinées passent en
  VIGNETTE_TITRE, la photo d'en-tête de notre-démarche en pleine largeur —
  reseedé et vérifié par captures : home ff inchangée au pixel).

## Grille des blocs homogénéisée + position hors du formulaire bloc / Unified block grid + position removed from the block form

**Date :** 2026-07-05
**Migration :** Non / No

**Audit visuel (captures Playwright pleine page avant/après)** — chaque bloc
vivait sur sa propre grille : gouttières différentes, cartes « plus à
l'intérieur » que les titres, trous verticaux géants entre un titre et sa
grille. Corrections dans `tb-blocs.css` :
- **Jeton unique `--tb-gouttiere`** (clamp 1.25rem→4rem) : les 6 gouttières
  codées en dur basculent dessus (blocs, grille, fil d'ariane, leaflet, FAQ).
- **Jeton `--tb-largeur-boite`** = largeur-max + 2×gouttière : les boîtes
  AUTONOMES (grille de cartes, fil d'ariane, infos/carte leaflet, colonnes
  FAQ, titre/signature de page) portaient `max-width + padding gouttière` →
  leur contenu était décalé de +gouttière par rapport aux sections (le
  « cartes plus à l'intérieur » signalé). Le calc les aligne au pixel.
- **Rythme vertical titre→grille** : une section-titre (évènements,
  liste-sous-pages, paragraphe) suivie d'une grille lui colle désormais
  (avant : padding bas + padding haut s'additionnaient ≈ 2× l'espace de
  section de vide).
- **`text-wrap: balance`** sur les titres de blocs, de cartes et de page
  (règle /ui : pas de mot orphelin).
- Le h1/la signature de page (ajoutés à l'audit SEO) rejoignent le système
  (ils étaient sur 72ch + 1rem, collés au bord gauche).
- **Gouttière ALIGNANTE (2e passe, tous les blocs)** : deux logiques
  coexistaient — contenu centré dans largeur-max (titres, textes → bord à
  144px sur un écran de 1440) vs contenu calé à gauche de sa section (CTA
  « Rejoignez la coopérative », témoignage, grande image, image+texte,
  médias → gouttière brute à 64px). Le padding des sections devient
  `max(gouttière, (100% − largeur-max)/2)` : chaque section contraint son
  contenu dans le conteneur commun quel que soit son alignement interne.
  Vérifié par captures Playwright pleine page : grande image, embed vidéo,
  CTA (filet à 144), témoignage, Soutenir, FAQ, infos/Leaflet — tous sur la
  même verticale que les titres. Le fond des bandes (hero, CTA) reste
  pleine largeur.
- **Bloc IMAGE_TEXTE réparé (« Une salle modulable »)** : le bloc se
  double-conteneurisait (max-width + margin auto sur une section qui porte
  déjà la gouttière alignante) → colonnes rétrécies, images timbre-poste,
  décalées d'une gouttière. Double contrainte supprimée : l'image occupe
  toute sa moitié, bord posé sur le conteneur, la quinconce gauche/droite
  (image_position) est conservée.
- **Skin faire_festival vérifié** (home, infos-pratiques, notre-démarche) :
  cohérent par design (grille Bootstrap centrée, brutalisme voulu) — h1 de
  secours et fil d'ariane tombent dans le même container. Seul point
  signalé, non corrigé (choix de maquette) : le bloc IMAGE *avec titre* est
  rendu en « image-titre de section » (~50 %, centrée) — peu adapté aux
  photos d'en-tête comme celle de la démo notre-démarche.

**Admin** : le champ `position` disparaît aussi du FORMULAIRE du bloc
(l'ordre se règle au glisser-déposer dans la liste ; à la création,
save_model place le bloc en fin de page).

## Admin blocs : tri par glisser-déposer (sortable Unfold) / Blocks admin: drag-and-drop sorting (Unfold sortable)

**Date :** 2026-07-05
**Migration :** Non / No

La liste des Blocs (`/admin/pages/bloc/`) et l'inline des images de galerie
utilisent le **sortable d'Unfold** (comme la démo formula/circuit) :
`ordering_field = "position"` + `hide_ordering_field = True` — poignée de
glisser-déposer à la place de la saisie manuelle du nombre, positions
enregistrées dans l'ordre affiché. Conseil d'usage : filtrer par page avant
de trier (sinon les blocs de toutes les pages se mélangent dans la liste).

## Champ `Page.est_blog` + fix z-index des dropdowns sur l'agenda / `Page.est_blog` field + agenda dropdowns z-index fix

**Date :** 2026-07-05
**Migration :** Non pour la branche (champ plié dans `pages/0001` régénérée, non committée ; colonne ajoutée à la main sur la base dev) / Folded into the regenerated, uncommitted `pages/0001`

- **`Page.est_blog` (typage EXPLICITE, décision mainteneur)** : le critère
  implicite « le parent porte un bloc LISTE_SOUS_PAGES » posait problème — le
  bloc doit rester de la pure présentation (posable sur l'accueil pour vitrine
  ses rubriques, sans transformer ses sous-pages en articles). Le champ
  booléen (pattern `est_accueil`, case à cocher dans l'admin) pilote désormais
  les trois comportements : sous-pages = ARTICLES (JSON-LD Article + signature
  date/auteur) et PAS de menu déroulant dans la navbar — le clic sur la page
  blog mène directement à l'index en cartes. Seeder : `journal` est_blog=True.
- **Fix z-index (bug signalé)** : les sections sticky de l'agenda classic
  (description + barre de recherche, `sticky-top` = z-index 1020 Bootstrap)
  passaient DEVANT les menus déroulants de la navbar (dropdown = 1000).
  `z-index: 999` posé sur les deux sections — les dropdowns repassent devant,
  la barre reste au-dessus du contenu qui défile.

## SEO éditorial : JSON-LD Article + date/auteur visibles sur les pages de blog / Editorial SEO: Article JSON-LD + visible date/author on blog pages

**Date :** 2026-07-05
**Migration :** Non — `Page.created_at`/`updated_at` existaient déjà, l'auteur est l'Organization / No — the date fields already existed, the author is the Organization

Critère « article » : une page dont le PARENT porte un bloc LISTE_SOUS_PAGES
(l'index d'un blog). Pour ces pages :
- **JSON-LD `Article`** (au lieu de WebPage) dans `jsonld_page` : headline,
  datePublished/dateModified (champs du modèle), author + publisher =
  Organization du lieu, image de partage en URL absolue.
- **Signature visible** (E-E-A-T — Google veut VOIR qui publie et quand) :
  « Publié le … par … (· mis à jour le …) » sous le titre, dans les 2 skins
  (`data-testid="page-signature"`), et date de publication en surtitre des
  cartes du bloc LISTE_SOUS_PAGES.
- Les autres sous-pages (ex. « Notre histoire ») restent des WebPage sans
  signature — critère vérifié dans les deux sens en live et par pytest.

## Blog dans la fixture de démo + zéro CDN (Leaflet et Plotly vendorisés) / Demo fixture blog + zero CDN (Leaflet and Plotly vendored)

**Date :** 2026-07-05
**Migration :** Non / No

- **Blog de démo** : `charger_site_lespass` construit désormais une page
  « Journal » (blocs PARAGRAPHE + LISTE_SOUS_PAGES) et 2 articles complets en
  blocs MARKDOWN (fresque participative, bilan repair café — titres, listes,
  citation, tableau, liens internes), avec images de partage et
  meta_description. Vitrine du duo CHANTIER-09 dans la démo. Les 2 pages de
  démo manuelles (`demo-journal`/`demo-article-1`) sont supprimées, la fixture
  fait foi.
- **Plus aucun CDN dans les templates publics** :
  - Leaflet du détail événement classic (`evenement_geoloc.html`) : unpkg →
    `pages/vendor/leaflet/` (déjà vendorisé pour le bloc CARTE_LEAFLET et
    l'explorer), avec `L.Icon.Default.imagePath` local.
  - Plotly du sankey crowds : cdn.plot.ly → `crowds/static/crowds/vendor/
    plotly-2.27.0.min.js` (3,5 Mo, chargé paresseusement uniquement quand un
    diagramme s'affiche — comportement inchangé).

## Audit SEO : rich results Event réparés, h1 partout, sitemap propre / SEO audit: Event rich results fixed, h1 everywhere, clean sitemap

**Date :** 2026-07-05
**Migration :** Non / No

Suite à l'audit SEO complet (2 agents + contre-vérifications), 6 lots corrigés :
1. **JSON-LD Event** : l'ancien JSON écrit à la main dans `vues/evenement.html`
   était INVALIDE (retours à la ligne non échappés, virgule traînante, virgule
   décimale française dans geo) → Google rejetait tout, zéro rich snippet sur
   les pages les plus importantes. Nouveau tag `jsonld_event` (json.dumps,
   pattern `jsonld_page`) — et `offers` est enfin rendu (l'ancien
   `event.price_min` n'existait pas : prix jamais émis). Vérifié : JSON valide,
   geo en float, offers avec prix et disponibilité.
2. **og:image/twitter:image ABSOLUES** sur le détail événement (2 skins) et la
   page adhésions (les crawlers sociaux exigent une URL complète — les partages
   d'événements n'avaient AUCUNE image).
3. **Sitemap** : `ProductSitemap` retiré — il listait 63 fragments HTMX
   `/memberships/<uuid>/` (formulaires de tunnel sans `<html>`), pas des pages.
4. **h1 partout** : titre de secours visible sur les pages CMS sans bloc HERO
   (`page.html` ×2 + flag `page_a_un_bloc_hero` dans `rendre_page`), h1
   `visually-hidden` sur les agendas (2 skins), et DÉMOTION des titres
   markdown d'un niveau (`#` → h2 : le h1 appartient à la Page, jamais au
   contenu — fini le double h1). Avant : 6 pages sur 10 sans aucun h1.
5. **Skin ff aligné** : `ff/page.html` émet enfin JSON-LD WebPage/FAQPage/
   Breadcrumb + fil d'Ariane + twitter/og_image/noindex (vieux backlog) ;
   vues ff agenda/adhésions : metas complètes (avant : title seul, description
   dupliquée avec la home).
6. **`srcset=""` éradiqué** : gardes sur chaque `<source>` de
   `commun/partials/picture.html` (avant : 86 vides sur /event/, 317 sur
   /memberships/) + alt du wizard événement.

Vérifié en live sur les 2 tenants : 1 h1 exact partout, JSON-LD 100 % parsables
(WebPage+FAQPage sur les pages ff !), 0 srcset vide, sitemap sans fragments.
Rapport complet : audit dans la conversation du 2026-07-05 ; à re-vérifier
après déploiement avec Google Rich Results Test sur une page événement.

## Blocs MARKDOWN + LISTE_SOUS_PAGES : une page devient un blog / MARKDOWN + LISTE_SOUS_PAGES blocks: a page becomes a blog

**Date :** 2026-07-05
**Migration :** Non (choices intégrées dans `pages/0001_initial` régénérée, non committée) / No (choices folded into the regenerated, uncommitted `pages/0001_initial`)

Deux nouveaux types dans le catalogue de blocs (16 désormais) :
- **MARKDOWN** (`titre` + `texte` = source MD, zéro nouveau champ) : rendu par
  le filtre `rendre_markdown` — `markdown` (extensions extra + sane_lists)
  puis **`nh3.clean()`** sur le HTML produit (XSS stocké neutralisé, testé).
  Exception dans `BlocAdmin.save_model` : la source MD n'est PAS passée dans
  `clean_html` au save (elle serait mutilée) — la sécurité se fait au rendu.
  Styles `.tb-markdown` dans tb-blocs.css (titres, listes, code, citations,
  tableaux), surchargeables par skin.
- **LISTE_SOUS_PAGES** (`titre` + `nombre_max`) : cartes des sous-pages
  publiées de la page courante (tag `sous_pages_publiees`, tri position/titre,
  brouillons exclus). Parent = index du blog, enfants = articles.

Intégré partout : `blocs_catalogue.CHAMPS_PAR_TYPE` (API v2), enum openapi,
`conditional_fields` admin Unfold, gabarits classic (ff par fallback).
Tests : `tests/pytest/test_blocs_markdown_sous_pages.py` (5 tests dont XSS).
Spec : `TECH_DOC/SESSIONS/SKINS/CHANTIER-09-BLOCS-MARKDOWN-SOUS-PAGES.md`.
Démo laissée en place sur lespass : `/demo-journal/` + `/demo-article-1/`.

## Squash des migrations de la branche main-pages / main-pages branch migrations squash

**Date :** 2026-07-05
**Migration :** Oui — 3 fichiers neufs, jamais déployés / Yes — 3 fresh files, never deployed

Les migrations intermédiaires de la branche (jamais passées en prod, qui
s'arrête à `BaseBillet/0220_lignearticle_idempotency_key` et `seo/0004`) ont
été supprimées et régénérées en UNE migration par app :
- **`pages/0001_initial`** (remplace 0001→0013) — app entière.
- **`BaseBillet/0221_remove_configuration_skin_configuration_module_pages_and_more`**
  (remplace 0220_configuration_module_pages→0225) — schéma (module_pages,
  externalapikey.page, retrait de Configuration.skin) + les 2 opérations de
  données pour les tenants de PROD : copie `skin` → `pages.ConfigurationSite`
  AVANT le RemoveField, et création de la home par défaut (idempotente, dans
  la langue du tenant via `translation.override`). L'ex-0222 (redondante avec
  la home 0225) n'est pas reprise.
- **`seo/0005_alter_seocache_unique_together_and_more`** (régénérée) —
  dédoublonnage RunPython AVANT les 2 contraintes uniques partielles.

Validé : `makemigrations --check` → « No changes detected », `migrate --plan`
sans erreur. Le `down -v` + flush repartira sur ce graphe propre ; en prod, la
chaîne s'ancre exactement sur l'état déployé.

## Dette de revue soldée : 404/500 skin-aware et parlantes sous HTMX + rangements / Review debt paid: skin-aware and HTMX-visible 404/500 + housekeeping

**Date :** 2026-07-05
**Migration :** Non / No

- **`handler404` (nouveau) + `handler500` enrichi** : les pages d'erreur
  passent par `get_context` → elles prennent le skin du tenant (fini la 404
  au look classic sur un tenant faire_festival) ET sont servies en fragment
  headless sous HTMX. Repli minimal si `get_context` échoue (une page
  d'erreur doit TOUJOURS s'afficher). Actifs quand DEBUG=0 — d'où le test
  direct `tests/pytest/test_handlers_erreur.py` (3 tests, RequestFactory).
- **Listener `htmx:beforeSwap` global (2 shells)** : par défaut htmx ignore
  les réponses non-2xx — un clic qui tombait en 404/500 ne produisait RIEN.
  Désormais la page d'erreur est swappée dans le body entier (HTML
  uniquement, les réponses JSON gardent leur traitement).
- **Rangements** : param `bloc` → `objet_cible` dans `_poser_fichier`
  (recevait aussi une Configuration), commentaire obsolète corrigé dans
  `seo/partials/tibillet_community_links.html`.
- **Finding retiré** : le `#paginator` « dupliqué en scroll infini » n'existe
  pas — les 4 emplacements (classic + ff) utilisent `hx-swap="outerHTML"`
  (remplacement, pas imbrication). L'agent d'audit avait supposé le swap par
  défaut sans lire l'attribut.

## Revue post-sessions : fix i18n CTA de la home auto-créée + vues ff sur base_template + test E2E skin ff / Post-sessions review: auto-home CTA i18n fix + ff views on base_template + ff skin E2E test

**Date :** 2026-07-05
**Migration :** Non (la 0225, non committée, est corrigée en place) / No (0225, uncommitted, fixed in place)

- **Fix i18n CTA (bug confirmé en base)** : `construire_page_accueil` fige les
  libellés CTA via `gettext()` non-lazy, mais la migration 0225 tournait sans
  langue activée → 22 tenants FR migrés avaient « Calendar »/« Subscriptions »
  gravés en anglais. Fix : `translation.override(config.language or 'fr')`
  autour de l'appel dans la migration ET au step 6ter d'`onboard/tasks.py`
  (l'`activate()` implicite de create_tenant était fragile). Les 22 tenants
  dev touchés ont été réparés (Agenda / Adhésions).
- **Vues faire_festival → `base_template`** : `accueil/agenda/evenement/
  adhesions.html` étendaient `shell.html` en dur → chaque navigation HTMX
  recevait le document COMPLET (htmx s'en sortait via DOMParser mais ~15 %
  de transfert en trop et incohérence avec classic). Elles étendent désormais
  `base_template` comme classic (fragment headless en HTMX). Iso-rendu
  vérifié : 0 diff sur les pages complètes (hors token CSRF).
- **Nouveau test E2E `test_skin_faire_festival_navigation.py`** : le skin ff
  n'était couvert par AUCUN test E2E (angle mort qui a laissé passer le bug
  des panneaux). Le test verrouille : swap HTMX → fragment headless (pas de
  document imbriqué, une seule navbar) + ouverture des panneaux contact et
  connexion après swap.

## Refonte du bloc HERO : bannière d'identité (image = config, actions → CTA) / HERO block redesign: identity banner (image from config, actions → CTA)

**Date :** 2026-07-05
**Migration :** Non / No

**Quoi / What :** Le bloc HERO devient une bannière d'identité pure (titre +
sous-titre) : plus de champ image ni de boutons sur le bloc.
- **Image** lue au rendu depuis la Configuration du lieu : `config.img`
  (fond photo en skin classic, image/logo centré en skin faire_festival).
  Le bloc ne porte plus de fichier → le risque `delete_orphans` disparaît.
- **Sans image** : le HERO passe en « recentré sobre » (titre + sous-titre
  centrés sur un fond neutre teinté accent ; ni filet décoratif, ni trou à droite).
- **Actions** : les boutons vivent désormais dans un bloc CTA séparé.
- **Image du HERO avec image** : centrée horizontalement ET verticalement
  (`background-position: center center`) + `min-height` (sur écran large et court,
  on ne voyait que le haut de l'image).
- **Home auto-générée** (onboarding) : HERO → PARAGRAPHE (**toujours créé**, avec
  la description longue saisie au wizard, ou vide pour être rempli plus tard) →
  CTA (module-aware, mêmes URL et libellés que la navbar). Créée **à la fin de la
  tâche d'onboarding** (`onboard/tasks.py::create_tenant_from_draft`, étape 6ter),
  une fois l'image et la description longue posées, juste avant l'email « espace
  prêt » — au lieu de `create_tenant()`.

**Pourquoi / Why :** simplifier l'objet bloc (1 bloc = 1 responsabilité),
corriger la « première rencontre » d'un tenant neuf (le HERO imageless laissait
~51 % de vide à droite) et brancher l'image de l'onboarding, qui n'apparaissait
nulle part sur la home.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/blocs_catalogue.py` | HERO = `["titre", "sous_titre"]` (retrait image/boutons) |
| `pages/templates/pages/classic/partials/bloc_hero.html` | Fond = `config.img`, sans boutons |
| `pages/templates/pages/faire_festival/partials/bloc_hero.html` | Image = `config.img`, sans badge date ni boutons |
| `pages/static/pages/css/tb-blocs.css` | HERO imageless recentré + fond teinté, retrait du filet ; image centrée H+V + min-height |
| `pages/admin.py` | `conditional_fields` (retrait HERO de image/boutons) + note d'aide |
| `pages/templates/admin/pages/bloc/hero_aide_before.html` | Note d'aide (Alpine, visible sur type HERO) |
| `pages/services.py` | `construire_page_accueil` : param `description_longue`, HERO sans image/boutons, PARAGRAPHE **toujours créé**, CTA module-aware |
| `onboard/tasks.py` | Création de la home en fin de tâche (étape 6ter), avant l'email |
| `BaseBillet/validators.py` | Ne crée plus la home dans `create_tenant` (déplacée dans la tâche) |
| `BaseBillet/migrations/0225_home_hero_paragraphe_cta_tous_tenants.py` | Migration data : home pour tous les tenants sans home (idempotente, préserve les homes existantes) |
| `pages/management/commands/{creer_page_demo,charger_demo_blocs,charger_site_lespass,charger_demo_faire_festival}.py` | HERO sans image/boutons ; image posée sur config ; CTA |
| `api_v2/openapi-schema.yaml` | Champs HERO + exemples mis à jour |
| `tests/pytest/test_pages.py` | 2 tests `construire_page_accueil` |

### Migration
- **Migration nécessaire / Migration required :** Oui — `BaseBillet 0225` (data,
  tenant-only). Crée la home HERO/PARAGRAPHE/CTA pour chaque tenant sans home ;
  **idempotente et non destructive** (n'écrase aucune home existante).
  `migrate_schemas`. Aucune migration de schéma (les colonnes image/bouton restent
  sur `Bloc`, utilisées par CTA, IMAGE_TEXTE, CARTE…).

### Suites manuelles / Manual follow-ups
- Re-jouer `charger_demo_faire_festival --schema=chantefrein` pour poser le logo « Faire » sur `config.img` (sinon chantefrein affiche l'image de fond actuelle).
- i18n : `makemessages` / `compilemessages` (nouvelles chaînes FR de la note d'aide admin ; `Calendar` / `Subscriptions` existent déjà).

## Fix : liens morts de la home ff de repli + nettoyage vues sans route / Fix: dead links in ff fallback home + dead views cleanup

**Date :** 2026-07-05
**Migration :** Non / No

Contexte (audit « que se passe-t-il si module_pages est désactivé ? ») : les
routes en dur `/infos-pratiques/` et `/le-faire-festival/` avaient été retirées
de `BaseBillet/urls.py` (remplacées par des pages CMS servies par le catch-all
`/<slug>/`), mais deux restes traînaient :
- **La vieille home ff** (`pages/faire_festival/vues/accueil.html`, gabarit de
  repli quand module_pages est off ou sans page d'accueil publiée) gardait ses
  deux boutons en dur → 404 garanti précisément quand cette home s'affiche.
  Fix : `index()` expose `slugs_pages_publiees` et les boutons ne s'affichent
  que si la page CMS correspondante est publiée.
- **Code mort** : vues `infos_pratiques()` / `le_faire_festival()` (plus aucune
  route) et gabarits `pages/faire_festival/vues/{infos_pratiques,le_faire_festival}.html`
  (jamais rendus — les 200 observés venaient des pages CMS homonymes) SUPPRIMÉS.

Comportement module_pages OFF (vérifié) : `/` → home de repli du skin,
`/<slug>/` → 404 (y compris préview admin), navbar sans pages, section admin
« Site web » masquée, carte du dashboard pour réactiver.

**Fix test fragile** : `test_bloc_evenements_liste_les_a_venir` échouait selon
l'état de la base dev (200+ évènements futurs accumulés par les suites E2E →
l'évènement du test à +3 jours sortait du slice `[:100]`). `nombre_max=32000`
dans le test = déterministe. À noter pour plus tard : les E2E ne nettoient pas
leurs évènements (~160 résidus E2E/API/Playwright/Refund/Smoke sur lespass).

## Fix : CSS des pages CMS perdu en navigation HTMX + ordre de la navbar / Fix: CMS pages CSS dropped on HTMX navigation + navbar ordering

**Date :** 2026-07-05
**Migration :** Non / No

**Bug CSS (tenant la-fourmiliere)** : `pages/classic/page.html` chargeait
`tb-blocs.css` dans le bloc `extra_meta`, qui n'existe QUE dans le `<head>` de
`shell.html`. En navigation HTMX (réponse headless, sans `<head>`), le CSS
n'arrivait jamais → page CMS sans style si la session avait commencé sur une
vue non-CMS ; un F5 (rendu complet) le réparait, d'où le côté insaisissable.
Fix : le `<link>` est chargé dans le bloc `main` (valide HTML5, présent dans
les deux rendus, dédupliqué par le cache navigateur). Règle ajoutée au
CONTRAT-DE-SKIN : **extra_meta = SEO uniquement, jamais d'asset nécessaire**.

**Navbar** : ordre unifié — pages de l'app pages d'abord, puis réseau/
crowdfunding, et en fin de menu : agenda, adhésions, contact (dans cet ordre).
Construction dans `get_context` (`navbar_pages + navbar`), le gabarit navbar
garde le contact en dernier.

**Audit HTMX complet (2 agents, templates + vues) — 4 fixes supplémentaires :**
- `pages/faire_festival/headless.html` : les panneaux `#contactPanel` et
  `#loginPanel` n'existaient PAS dans le fragment headless ff → après toute
  navigation HTMX sous ce skin, les boutons Contact/Connexion ne s'ouvraient
  plus (échec silencieux). Bloc `offcanvas_globaux` ajouté (dans
  `.skin-faire-festival` pour le CSS scopé), aligné sur classic.
- `fonctionnel/event_wizard/_base.html` : `wizard.css` chargé dans `extra_meta`
  (même famille que tb-blocs.css, dormant car le wizard n'est pas encore
  navigué en HTMX) → déplacé dans `main`.
- `MyAccount.dispatch` : session expirée pendant une navigation HTMX →
  `HX-Redirect: /?login=1` (vraie navigation + panneau de connexion) au lieu
  d'un 302 suivi en silence qui swappait la home DANS l'onglet du compte.
- `CrowdDetailView.retrieve` : pk invalide sous HTMX → `HX-Redirect: /contrib`
  au lieu d'un 302 qui laissait l'URL du navigateur sur `/crowd/<invalide>/`.

**Protection cache HTTP pour la prod (validée par le mainteneur, 3 mesures)** :
- Nouveau middleware `BaseBillet.middleware.ProtectionCacheHtmxMiddleware`
  (branché dans settings.py, après AuthenticationMiddleware) :
  `Vary: HX-Request` sur TOUTES les réponses (les caches indexent enfin les
  deux variantes shell/fragment séparément) + `Cache-Control` par défaut sur
  le HTML : `private, no-store` si connecté, `no-cache` sinon — uniquement si
  la vue n'a pas déjà posé le sien.
- Meta `htmx-config` dans les 2 shells : `historyCacheSize: 0` (plus de cliché
  DOM dans le localStorage → un « retour » ne peut plus restaurer une page
  d'un déploiement précédent) + `refreshOnHistoryMiss: true` (un « retour »
  fait un vrai rechargement complet).

**Restent documentés (non corrigés, non bloquants)** : 404/500 muets sous HTMX
(pas de feedback utilisateur sur erreur de swap), vues ff qui étendent
shell.html en dur (fonctionne via DOMParser htmx mais transfert lourd),
id `#paginator` dupliqué en scroll infini.

## Migration skins CHANTIERS-05→08 : fin de la migration — contrat de skin, `demarrer_skin`, suppression des anciennes arborescences / Skins migration C05→08: contract, scaffolding command, legacy trees removed

**Date :** 2026-07-04
**Migration :** Non / No

**CHANTIER-05** — dernières vues skin-aware → `pages/<skin>/vues/` :
`accueil.html` (ex home, 2 skins), `infos_pratiques.html` + `le_faire_festival.html`
(ff uniquement — jamais existé côté reunion, résolution identique),
`reseau.html` (ex federation/explorer). Plus AUCUN appelant de `get_skin_template`.

**CHANTIER-06** — plus rien de fonctionnel dans les arbos de skin :
- Habillage skinnable : navbar + footer des 2 skins → `pages/<skin>/partials/`.
- 39 templates fonctionnels → **`BaseBillet/templates/fonctionnel/`**
  (compte/, connexion/, qrcode_scan_pay/, event_wizard/, event/, adhesion/,
  register, account_base, blank_base) — ils héritent du shell via
  `base_template`, donc prennent le look du skin sans copie.
- Utilitaires partagés `field_errors.html`, `picture_url_string.html` →
  `commun/partials/`.
- Emails mal rangés → `emails/qrcode_scan_pay/` (+ maj `tasks.py` ×2) et
  `emails/legacy/welcome_email.html`.
- 41 fichiers de références réécrits (render(), includes, extends, tasks).

**CHANTIER-07** — le contrat :
- **`TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md` v1.0** : arborescence, blocs
  FIGÉS, ids du chrome, variables de contexte par vue, règle d'autonomie.
- Commande **`manage.py demarrer_skin <nom>`** : copie `pages/classic/` →
  `pages/<nom>/`, refus d'écrasement, marche à suivre FALC.
  Tests : `tests/pytest/test_demarrer_skin.py` (3 tests).

**CHANTIER-08** — nettoyage :
- `404.html`, `500.html`, `crowds/success.html` étendent
  `pages/classic/shell.html` en direct.
- `get_skin_template` SUPPRIMÉ (`gabarit_skin` est l'unique resolver).
- Arborescences `BaseBillet/templates/{reunion,faire_festival}/` SUPPRIMÉES
  (maquette ff archivée dans `TECH_DOC/SESSIONS/SKINS/maquette-faire-festival/`).
- Restent volontairement : `static/reunion/…` (qr-scanner, leaflet, media —
  namespace statics, hors périmètre du plan) et `static/faire_festival/…`.

**Vérifié** : 0 diff sur tous les snapshots publics (2 skins, pages + HTMX),
zéro référence template `reunion/`/`faire_festival/` restante hors statics,
404/500/crowds rendent via le shell, suites pytest + E2E complètes via agent,
vérification Chrome finale (voir rapport de session).

## Migration skins CHANTIER-04 : adhésions → `pages/<skin>/vues/adhesions.html` / Skins migration CHANTIER-04: memberships moved to `pages/<skin>/vues/`

**Date :** 2026-07-04
**Migration :** Non / No

**Quoi / What :** Même recette que le CHANTIER-03, pour les adhésions (spec :
`TECH_DOC/SESSIONS/SKINS/CHANTIER-04-ADHESIONS.md`).
- Vue liste des 2 skins → `pages/{classic,faire_festival}/vues/adhesions.html`
  (ff étend directement son shell) ; rendus de `MembershipMVT` sur
  `gabarit_skin()`, **y compris `embed`** (même correction qu'au C3 : l'iframe
  suit désormais le skin du tenant au lieu d'un chemin reunion en dur).
- Les 5 partiels HTMX du tunnel (`form`, `404`, `free_confirmed`,
  `pending_manual_validation`, `already_has_membership`) → `commun/adhesion/`
  (chrome). Conformément au piège 9.8 : ce sont des PARTIELS purs (pas de base
  template), chargés par HTMX dans `#offcanvas-membership` — contenu et ids
  strictement intacts.
- Blocs du contrat FIGÉS : `adhesions_entete`, `adhesions_tunnel`,
  `adhesions_grille`, `adhesions_federees`.
- Restent dans reunion (C6, pages fonctionnelles) : `formbricks.html` et les 3
  `payment_already_*` / `payment_link_invalid` (elles étendent `base_template`).

**Vérifié** : snapshots avant/après 0 diff de contenu (3 pages adhésions,
2 skins, page + HTMX), embed 200 ×2 skins, partiel form.html toujours pur
(`<form hx-post` sans base), tests + E2E via agent, parcours Chrome (voir
rapport de session).

## Migration skins CHANTIER-03 : agenda + détail événement → `pages/<skin>/vues/` / Skins migration CHANTIER-03: agenda + event detail moved to `pages/<skin>/vues/`

**Date :** 2026-07-04
**Migration :** Non / No

**Quoi / What :** Les vues agenda et détail événement des deux skins déménagent
vers `pages/<skin>/vues/` et les 5 sites de rendu d'`EventMVT` passent sur le
resolver unifié `gabarit_skin()` (spec :
`TECH_DOC/SESSIONS/SKINS/CHANTIER-03-AGENDA-EVENEMENT.md`).

- reunion → `pages/classic/` : `vues/agenda.html`, `vues/evenement.html`,
  `vues/agenda_liste.html`, `vues/agenda_liste_suite.html` + partials habillage
  (`carrousel_evenements`, `evenement_accordeon`, `evenement_geoloc`,
  `evenement_benevoles`, `reservation_declencheur`) ; la logique de recherche →
  `commun/agenda/filtres.html` (chrome).
- faire_festival → `pages/faire_festival/vues/{agenda,evenement,agenda_liste_suite}.html`
  (extends directement le shell ff).
- **Contrat de skin — premiers blocs FIGÉS** : `agenda_carrousel`,
  `agenda_description`, `agenda_filtres`, `agenda_liste` ; `evenement_entete`,
  `evenement_tags`, `evenement_description`, `evenement_reservation`,
  `evenement_complements` ; partial `carte_evenement.html` (dédoublonne la carte
  entre liste et « voir plus »).
- **`embed` corrigé** : l'iframe agenda suivait TOUJOURS le look reunion (chemin
  en dur) ; elle suit désormais le skin du tenant.
- Originaux supprimés (plus aucune référence) ; restent dans reunion :
  formbricks, reservation_ok, wizard (CHANTIER-06).

**Vérifié** : snapshots avant/après identiques (0 diff de contenu, 2 skins,
pages + HTMX), retrieve/embed/pagination 200, 33 pytest event/pages verts,
E2E complets (voir rapport de session).

## Migration skins CHANTIER-02 (lots A, B, C1) : extraction du commun — statics, templates partagés, offcanvas / Skins migration CHANTIER-02 (batches A, B, C1): shared assets extraction

**Date :** 2026-07-03
**Migration :** Non / No

**Quoi / What :** Tout ce qui est partagé entre les skins déménage vers `commun/`
(décisions P1-P4, spec `TECH_DOC/SESSIONS/SKINS/CHANTIER-02-EXTRACTION-COMMUN.md`).

**Lot A — statics** : 21 fichiers `static/reunion/` → `static/commun/` (5 CSS,
4 familles de polices, 6 JS, 2 images) ; références basculées dans 10 fichiers
(shells, seo/base, blank_base, footers, mails/base, redirection favicon urls.py).

**Lot B — templates partagés** : `forms/contact.html` et `forms/login.html` →
`commun/formulaires/`, `partials/toasts.html` → `commun/toasts.html`,
`loading.html` → `commun/loading.html`, `booking_form.html` →
`commun/formulaires/reservation.html`, `partials/picture.html` →
`commun/partials/picture.html` (utilisé aussi par crowds). 28 références basculées.
**Le skin faire_festival ne référence plus aucun fichier reunion** (règle P3).

**Lot C1 — offcanvas unifiés** : les 5 offcanvas publics extraits vers
`commun/offcanvas/{contact,connexion,adhesion_tunnel,reservation,filtres_agenda}.html`,
inclus au même endroit du DOM par les templates hôtes des deux skins (définitions
doublées unifiées). Formulaire de recherche → `commun/formulaires/
recherche_evenements.html`. Largeur responsive des tunnels factorisée en classe
`.offcanvas-tunnel` dans `tibillet.css` (4 blocs `<style>` inline supprimés).
Ids inchangés (contrat) : `#contactPanel`, `#loginPanel`, `#subscribePanel`,
`#offcanvas-membership`, `#bookingPanel`, `#filterPanel`.

**Lot C2 — blocs offcanvas dans les squelettes** : `pages/classic/shell.html` et
`headless.html` exposent désormais `{% block offcanvas_globaux %}` (contact +
connexion, inclus par le squelette en fin de body — retirés du partial navbar,
qui ne garde que les déclencheurs) et `{% block offcanvas %}` (rempli par les
vues : tunnels réservation/adhésion). Aligne le socle classic sur le pattern
faire_festival. Exception documentée : sur faire_festival, le panneau contact
reste DANS `.skin-faire-festival` (le CSS brutaliste y est scopé). Le headless
inclut les mêmes panneaux : ils survivent aux swaps HTMX `hx-target="body"`.
Diff HTML : déplacement pur des 2 panneaux (contenu identique, vérifié).

**Pourquoi / Why :** un skin ne doit référencer que lui-même, le socle classic et
`commun/` — préalable à la suppression de l'arborescence reunion (CHANTIER-08) et
à la création de skins tiers.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/static/commun/` | NOUVEAU — 21 statics partagés (+ règle `.offcanvas-tunnel` dans tibillet.css) |
| `BaseBillet/templates/commun/` | NOUVEAU — formulaires/, offcanvas/, partials/, toasts, loading |
| Shells `pages/{classic,faire_festival}/` + `seo/base.html` + `blank_base.html` + footers + `ApiBillet/mails/base.html` | chemins statics → `commun/` |
| `BaseBillet/urls.py` | redirection favicon → `commun/img/favicon.png` |
| `reunion/partials/navbar.html`, vues membership/event des 2 skins, `partial/search.html`, `partial/booking.html` | définitions offcanvas → includes `commun/offcanvas/` |
| `crowds/templates/` (detail, card) | include picture → `commun/partials/picture.html` |

## Seed : la démo faire_festival (chantefrein) est branchée au flush / Seed: the faire_festival demo (chantefrein) is now wired into the flush

**Date :** 2026-07-03
**Migration :** Non / No

**Quoi / What :** La commande `charger_demo_faire_festival` (vitrine brutaliste sur
le tenant chantefrein + skin forcé à faire_festival) existait mais n'était appelée
par personne : après un flush, tous les tenants restaient en skin reunion.
`demo_data_v2` l'appelle désormais en fin de seed (`_seed_site_pages_chantefrein()`,
même pattern try/except non bloquant que `_seed_site_pages_lespass()`).
**Pourquoi / Why :** chaque flush produit maintenant les DEUX skins de démo —
indispensable pour comparer les peaux pendant la migration skins.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/demo_data_v2.py` | + `_seed_site_pages_chantefrein()` appelé après le seed lespass |

## Fix : doublons SEOCache au flush (contrainte unique partielle) / Fix: SEOCache duplicates on flush (partial unique constraint)

**Date :** 2026-07-03
**Migration :** Oui / Yes — `seo/migrations/0005_alter_seocache_unique_together_and_more.py`
(dédoublonne puis pose les contraintes / dedupes then adds the constraints)

**Quoi / What :** Le flush crashait en fin de course sur
`SEOCache.MultipleObjectsReturned` (reproductible). Cause : `unique_together
(cache_type, tenant)` ne protège PAS les lignes d'agrégats globaux (`tenant=None`) —
PostgreSQL considère les NULL comme distincts dans un index unique. Deux rebuilds
concurrents (worker Celery déclenché par les signaux du seed + commande manuelle
`refresh_seo_cache` de flush.sh, qui bypasse le verrou debounce avec `force=True`)
créaient donc des doublons, et tous les rebuilds suivants crashaient.
**Fix :** remplacement de `unique_together` par deux `UniqueConstraint` partielles
(`tenant` non-null : couple unique ; `tenant` null : `cache_type` unique — compatible
PostgreSQL 13). En cas de course, `get_or_create` rattrape l'`IntegrityError` et
relit la ligne. Vérifié par deux `refresh_seo_cache` lancés en parallèle : zéro
crash, zéro doublon.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | `unique_together` → 2 `UniqueConstraint` partielles |
| `seo/migrations/0005_alter_seocache_unique_together_and_more.py` | Dédoublonnage (garde la plus récente) + contraintes |

## Migration skins CHANTIER-01 : resolver unifié `gabarit_skin` + squelettes déplacés vers `pages/<skin>/` / Skins migration CHANTIER-01: unified resolver + skeletons moved to `pages/<skin>/`

**Date :** 2026-07-03
**Migration :** Non / No (une migration de fusion technique a été créée à part :
`BaseBillet/migrations/0224_merge_20260703_0914.py`, exigée par les deux feuilles
0220/0223 issues du merge de `main` — vide, aucun changement de schéma)

**Quoi / What :** Première étape de la migration skins (plan :
`TECH_DOC/SESSIONS/SKINS/`). Nouveau resolver `pages.services.gabarit_skin(nom)` :
retourne `pages/<skin>/<nom>` si le skin fournit le gabarit, sinon fallback
automatique sur le socle `pages/classic/<nom>`. Les 4 squelettes (`base.html` et
`headless.html` des skins reunion et faire_festival) sont déplacés vers
`pages/templates/pages/{classic,faire_festival}/{shell,headless}.html`. Les anciens
fichiers deviennent des redirections d'héritage (`{% extends %}` une ligne) — une
seule source de vérité, zéro drift, et les `extends` en dur existants (404.html,
500.html, crowds/success.html, vues faire_festival) continuent de fonctionner.
`get_context()` branche `base_template` sur le nouveau resolver.

**Pourquoi / Why :** Unifier les deux systèmes de skin parallèles
(`get_skin_template`/reunion et app pages/classic) sous un seul mécanisme avec
filet de sécurité. **Iso-rendu prouvé** : snapshots curl normalisés identiques
avant/après sur `/`, `/event/`, `/memberships/` (+ variantes HTMX) pour un tenant
reunion ET un tenant faire_festival.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/services.py` | + `gabarit_skin()` (resolver unifié avec fallback classic) |
| `pages/templates/pages/classic/shell.html` | NOUVEAU — ex `reunion/base.html` (contenu intégral) |
| `pages/templates/pages/classic/headless.html` | NOUVEAU — ex `reunion/headless.html` |
| `pages/templates/pages/faire_festival/shell.html` | NOUVEAU — ex `faire_festival/base.html` |
| `pages/templates/pages/faire_festival/headless.html` | NOUVEAU — ex `faire_festival/headless.html` |
| `BaseBillet/templates/reunion/base.html` | Devient `{% extends "pages/classic/shell.html" %}` |
| `BaseBillet/templates/reunion/headless.html` | Devient `{% extends "pages/classic/headless.html" %}` |
| `BaseBillet/templates/faire_festival/base.html` | Devient `{% extends "pages/faire_festival/shell.html" %}` |
| `BaseBillet/templates/faire_festival/headless.html` | Devient `{% extends "pages/faire_festival/headless.html" %}` |
| `BaseBillet/views.py` | `get_context()` : `base_template` résolu par `gabarit_skin("shell.html"/"headless.html")` |
| `tests/pytest/test_gabarit_skin.py` | NOUVEAU — 4 tests (fallback reunion→classic, skin existant, gabarit manquant, chaîne d'héritage) |
| `BaseBillet/migrations/0224_merge_20260703_0914.py` | NOUVEAU — merge technique des feuilles 0220/0223 (vide) |

## Corrections : relance d'adhésion tronquée, tâche welcome morte, bouton fermer du panneau ticket / Fixes: truncated membership reminder, dead welcome task, ticket panel close button

**Date :** 2026-07-03
**Migration :** Non / No

**Quoi / What :** Trois corrections de bugs découverts pendant l'audit de la session skins.

**1. `membership_renewal_reminder` s'arrêtait au premier adhérent / stopped at the first member**
- Le `return mail.sended` était DANS la boucle `for membership` : seul le premier
  adhérent (du premier tenant) recevait l'email de relance, puis la tâche Celery
  se terminait. Le `return` est supprimé : chaque adhérent est traité, une erreur
  d'envoi est loggée et n'interrompt plus les suivants.
- Correction aussi du message de log copié-collé trompeur (« send_welcome_email »
  → « membership_renewal_reminder »).

**2. Suppression de la tâche morte `send_welcome_email` / dead task removed**
- Jamais appelée nulle part, et son template `emails/welcome/welcome_email.html`
  n'existe pas (l'erreur `TemplateDoesNotExist` était avalée par le `try/except`).
  Le seul `welcome_email.html` existant est l'email legacy de création d'instance
  (`reunion/views/tenant/emails/`), au contexte incompatible — remplacé depuis par
  `onboard/emails/ready.html`. La tâche est supprimée.

**3. Bouton fermer du panneau ticket inopérant / ticket panel close button broken**
- `data-bs-dismiss="ticketPanel"` (valeur invalide) → `data-bs-dismiss="offcanvas"`.
  Le bouton ✕ de l'offcanvas `#ticketPanel` (page « Mes réservations ») ferme
  désormais le panneau.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | Suppression `send_welcome_email` ; fix `return` dans la boucle de `membership_renewal_reminder` + log |
| `BaseBillet/templates/reunion/views/account/reservations.html` | `data-bs-dismiss="offcanvas"` sur le bouton close |



**Date :** 2026-06-30
**Migration :** Oui / Yes — `BaseBillet/migrations/0220_lignearticle_idempotency_key_and_more.py`

**Quoi / What :** Trois corrections sur l'API v2, remontées par un intégrateur.

**1. Partager un produit sur plusieurs événements / Share a product across several events**
- `isRelatedTo` accepte désormais une **liste** (UUID et/ou objets schema.org) au
  `POST /api/v2/products/` : le produit est attaché à tous les events listés.
  Avant, une liste renvoyait 201 mais n'attachait rien.
- Nouvelle route `POST /api/v2/events/{uuid}/link-product/` : attache un (ou
  plusieurs) produit(s) **déjà créé(s)** à un événement (M2M `Event.products`),
  sans en créer un nouveau. Accepte `productId`, `productIds`, `product`, `products`.

**2. Double ticket sur un sous-événement / Double ticket on a sub-event**
- Un sous-événement (avec `parent`) est forcé en catégorie `ACTION`. Le
  `TicketCreator` créait alors DEUX tickets quand l'event avait aussi un produit
  réservable : le bon, plus un ticket « bénévole » vide (sans `pricesold`, donc
  `identifier` vide en sortie). Désormais `method_A` n'est appelé que si aucun
  produit n'a été traité (`products_dict` vide).

**3. Sécurité idempotence de la recharge cadeau / Gift-refill idempotency hardening**
- `POST /api/v2/wallet-refills/` : l'`Idempotency-Key` est désormais **obligatoire**
  (400 si absente) et stockée en **base** (`LigneArticle.idempotency_key`,
  contrainte d'unicité = verrou atomique contre les requêtes concurrentes), au
  lieu d'un cache best-effort. Même clé + même corps → 208 ; même clé + corps
  **différent** → 409 ; une clé dont la tentative précédente a échoué (Fedow) peut
  être ré-essayée. Résout le risque de double-crédit (TOCTOU + réutilisation de clé).

**Pourquoi / Why :** Limites/risques signalés sur l'API v2 (réutilisation produit,
tickets parasites, double-crédit possible sur recharge).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/serializers.py` | `isRelatedTo` en liste (`_extract_event_uuids`), boucle d'attachement ; nettoyage ruff |
| `api_v2/views.py` | route `link_product` ; refonte idempotence wallet-refill (verrou DB, 208/409/retry) |
| `api_v2/openapi-schema.yaml` | doc route `link-product`, `isRelatedTo` liste, header `Idempotency-Key` requis + 409 |
| `api_v2/README.md` | doc idempotence en base, header obligatoire |
| `BaseBillet/validators.py` | `method_A` appelé seulement si `products_dict` vide |
| `BaseBillet/models.py` | `LigneArticle.idempotency_key` + `UniqueConstraint` conditionnelle |
| `tests/pytest/test_api_v2_product_link_event.py` | **nouveau** — 6 tests (multi-events + link-product) |
| `tests/pytest/test_reservation_subevent_tickets.py` | **nouveau** — 4 tests (1 ticket par cas) |
| `tests/pytest/test_api_v2_wallet_refill.py` | + 4 tests idempotence (208/409/400/retry), maj des tests existants |

### Migration
- **Migration nécessaire / Migration required :** Oui / Yes
- `migrate_schemas --executor=multiprocessing` (ajout colonne `idempotency_key`
  nullable + contrainte unique conditionnelle sur `LigneArticle` ; additif, sans risque).

### i18n
- Nouvelles chaînes `_()` à traduire (FR source) : `Idempotency-Key header is required.`,
  `Idempotency-Key already used with different parameters.`,
  `A refill with this key is already in progress.`,
  `No product identifier provided. Use productId or productIds.`
  → à passer au workflow `makemessages` / `compilemessages` (côté mainteneur).

## Test carte NFC ↔ wallet Fedow : rendu autonome (plus de skip) / Fedow card test made self-contained

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Le test d'intégration `test_membership_card_wallet_fedow` ne
**skippe plus** : sa fixture fabrique elle-même une carte NFC éphémère chez Fedow
si aucune n'est disponible. Il résiste désormais à un reset complet (`down -v`,
qui vide la base Fedow) et ne dépend plus d'une carte renseignée dans `.env`.

**Pourquoi / Why :** Les cartes NFC vivent dans le serveur Fedow (`fedow_django`),
dont le `start.sh` ne crée aucune carte au démarrage (les cartes de démo sont
dans `demo_data`, jamais lancé). Après un `down -v`, plus aucune carte → le test
skippait. Solution : créer la carte **via l'API Fedow** depuis Lespass.

**Fix / Fix :** nouvelle méthode `NFCcardFedow.create_cards(cards_data)` dans
`fedow_connect/fedow_api.py` — POST signé par la place du tenant vers l'endpoint
Fedow `card` (`CardAPI.create`, `HasKeyAndPlaceSignature`), idempotent (201/409).
La fixture `carte_fedow_ephemere` réutilise `FEDOW_TEST_CARD_NUMBER` s'il pointe
une carte encore éphémère, sinon **fabrique une carte fraîche** (numéro/tag
aléatoires). Prérequis : place Fedow signable (cas par défaut en dev).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | + `NFCcardFedow.create_cards()` (POST signé `card`) |
| `tests/pytest/test_membership_card_wallet_fedow.py` | fixture autonome + test `create_cards` (TDD) |

### Migration
- **Migration nécessaire / Migration required :** Non / No.

## Carte explorer : fond de carte MapTiler (style dataviz) avec repli OSM France / MapTiler basemap with OSM France fallback

**Date :** 2026-06-29
**Migration :** Non / No (front + variable d'env `MAPTILER_KEY`)

**Quoi / What :** Le fond de carte utilise **MapTiler** (style `dataviz-v4`, épuré)
quand une clé est configurée, sinon **repli** sur les tuiles **Humanitarian (HOT)
d'OpenStreetMap France**. La clé MapTiler vient de `MAPTILER_KEY` (`.env`), jamais
en dur dans le code.

**Pourquoi / Why :** CARTO Voyager affichait les régions françaises en anglais.
MapTiler offre un style épuré (idéal pour faire ressortir les markers) et des
garanties de prod ; OSM France reste le repli gratuit/sans clé (et le défaut en dev
si `MAPTILER_KEY` est vide). Branchement : `settings.MAPTILER_KEY` →
contexte des vues → `data-maptiler-key` sur `#explorer-root` → `explorer.js`.

**Limite langue / Language note :** sur les tuiles **raster** MapTiler, `?language=fr`
n'a **pas** d'effet (labels figés au rendu). Les villes françaises s'affichent en
français, mais les pays/villes étrangers restent en anglais (« Geneva »,
« Switzerland »). Pour un français complet : créer un style FR dans le dashboard
MapTiler (Customize → langue), ou passer au SDK vectoriel (MapLibre, `language: 'fr'`).

**Sécurité clé :** la clé MapTiler est exposée côté client (URL des tuiles) →
**à restreindre par domaine** dans le dashboard MapTiler (Allowed origins).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `MAPTILER_KEY = os.environ.get('MAPTILER_KEY', '')` |
| `seo/views.py` + `BaseBillet/views.py` | passent `maptiler_key` au contexte (explorer ROOT + federation tenant) |
| `seo/templates/seo/partials/explorer_widget.html` | `data-maptiler-key` sur `#explorer-root` |
| `seo/static/seo/explorer.js` | `tileLayer` : MapTiler `dataviz-v4` si clé, sinon repli HOT / OSM France |

### Migration
- **Migration nécessaire / Migration required :** Non / No. Renseigner `MAPTILER_KEY`
  dans `.env` (sinon repli HOT automatique) + redémarrer le conteneur pour charger l'env.

## Carte explorer : markers synchronisés au mode « Événements » + barre de recherche resserrée / Explorer map: markers synced with "Events" mode + tightened search bar

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Sur la carte explorer, en mode « Événements », les markers ne
montrent plus que les lieux ayant au moins un événement visible (les lieux sans
événement à venir disparaissent de la carte). La barre de recherche et le toggle
« Lieux / Événements » forment un groupe compact **centré** (au lieu d'une barre
pleine largeur avec les boutons collés au bord). Le fondu dégradé qui estompait à
tort le bouton « Événements » est retiré.

**Pourquoi / Why :** Les markers réagissaient déjà aux filtres texte et tag (via
`updateMapMarkersByPA`), mais le toggle Lieux/Événements ne changeait que la liste
de gauche, pas les markers. Côté layout, la barre s'étirait sur toute la largeur
(boutons collés au bord), puis une 1ʳᵉ tentative laissait un grand vide au milieu.

**Fix / Fix :** Dans `applyFilters()`, la source des markers visibles dépend du
mode : en mode « événement », `visiblePaIds` est construit depuis les `pa_id` des
événements visibles (`eventCards`) au lieu de toutes les PA. CSS : le groupe
`.explorer-search-row` est borné (`max-width: 760px`) et **centré** (`margin: 0 auto`),
la barre (`flex:1` + `min-width:0`) remplit jusqu'au toggle (plus de vide) ; retrait
du `mask-image` (fondu droit) sur `.explorer-pills` qui estompait le bouton
« Événements » (toggle à 2 boutons → jamais de scroll) ; responsive mobile conservé.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/static/seo/explorer.js` | `applyFilters` : markers = lieux avec events visibles en mode « événement » |
| `seo/static/seo/explorer.css` | groupe recherche+toggle borné et compact à gauche (responsive mobile conservé) |

### Migration
- **Migration nécessaire / Migration required :** Non / No (front statique).
- Note : vider le cache navigateur / hard reload pour récupérer les statiques.

## Infra : limite item Memcached relevée (1 Mo → 8 Mo) pour l'agrégat SEO / Memcached item size raised for the SEO aggregate

**Date :** 2026-06-29
**Migration :** Non / No (infra — recréation du conteneur memcached)

**Quoi / What :** Le service `lespass_memcached` est lancé avec `-I 8m -m 256`
(au lieu des défauts 1 Mo / 64 Mo).

**Pourquoi / Why :** L'agrégat SEO `AGGREGATE_EVENTS` pèse ~687 o/event et contient
tous les events futurs publiés du réseau. À ~1500 events futurs il atteint la limite
Memcached par défaut (1 Mo) ; au-delà le `set` L1 échoue silencieusement → la page
relit la DB à chaque fois (cache inutile). `-I 8m` repousse le mur à ~12 000 events
futurs ; `-m 256` donne la mémoire totale pour ces gros items sans évictions.
Alternative durable (non faite) : borner l'agrégat aux N prochains mois.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `docker-compose.yml` | `lespass_memcached` : `command: ["memcached", "-m", "256", "-I", "8m"]` |
| `docker-compose.pre-prod.yml` | idem |
| `docker-compose.v1.pre-prod.yml` | idem |

### Application / Apply
- **Recréer le conteneur** (vide le cache, reconstruit au prochain rebuild/MISS) :
  `docker compose up -d lespass_memcached` (et `-f docker-compose.pre-prod.yml` en prod).
- Ajuster `-m 256` selon la RAM du serveur.

## Agenda participatif : l'approbation d'une proposition ne rafraîchissait pas la carte / Proposal approval didn't refresh the map

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Approuver une proposition publique (agenda participatif) via
l'action admin « Approuver et publier les propositions sélectionnées » la publiait
bien, mais l'event **n'apparaissait sur la carte réseau qu'au beat 4 h**.

**Pourquoi / Why :** L'action utilisait `queryset.update(is_proposal=False,
published=True)`. Le `.update()` en masse **ne déclenche pas le signal
`post_save`** → `declencher_refresh_seo_cache` n'était jamais appelé → pas de
rebuild SEO. (Le toggle « Publier » de la liste et l'édition via le formulaire,
qui passent par `save()`, déclenchaient bien le signal — seule l'action bulk était
touchée.)

**Fix / Fix :** L'action publie désormais via `save(update_fields=["is_proposal",
"published"])` par instance (boucle), ce qui déclenche `post_save` → rebuild SEO
débouncé → l'event approuvé apparaît sur la carte en ~15-20 s. Vérifié par test +
en conditions réelles (Chrome) : toggle « Publier » → event présent dans
`AGGREGATE_EVENTS`, L1 cohérent cross-schema.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `approuver_propositions` : `save()` par instance au lieu de `queryset.update()` (déclenche le signal SEO) |
| `tests/pytest/test_seo_cache_fragments.py` | +1 test : l'approbation d'une proposition déclenche le rebuild SEO |

### Migration
- **Migration nécessaire / Migration required :** Non / No.

## Carte réseau : débounce du rebuild rendu global + plafond anti-famine / Global rebuild debounce + maxWait cap

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Le débounce du rebuild d'agrégats est désormais **global** (1 cycle
pour tout le réseau, plus 1 par tenant) et protégé contre la **famine** par un
plafond « maxWait ».

**Pourquoi / Why :** (1) Les clés de débounce passaient par le cache `default`
préfixé par schema (`make_key`) → le verrou « global » était en réalité **par
tenant** : sous un pic multi-lieux, on lançait N rebuilds redondants (chacun
recombine pourtant tout le réseau). (2) Le débounce *trailing* seul risquait la
**famine** : sous un flux continu de modifs (< 15 s d'intervalle : import, grosse
saison), l'échéance était repoussée indéfiniment et le rebuild ne partait jamais
avant le beat 4 h — recréant le symptôme corrigé.

**Fix / Fix :** Les 3 clés de débounce (`seo_rebuild_echeance`,
`seo_rebuild_plafond`, `seo_rebuild_planifie`) sont manipulées sous
`schema_context("public")` → **réellement globales**. Ajout d'un **plafond maxWait**
(`REBUILD_MAXWAIT = 60 s`) posé une seule fois au début d'une série : le rebuild
s'exécute au plus tôt entre l'échéance trailing (dernière modif + 15 s) et le
plafond (1ʳᵉ modif + 60 s). Conséquences : sous pic simultané → **1 rebuild** au
lieu de N ; sous flux dense → **≤ 1 rebuild / 60 s** (charge bornée, pas de famine),
objectif « 500 tenants » du CHANTIER-07 enfin tenu.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/tasks.py` | +`REBUILD_MAXWAIT` + constantes de clés ; `planifier_rebuild_agregats` (plafond + clés globales `schema_context("public")`) ; garde de `rebuild_seo_aggregates` : cible = min(échéance trailing, plafond maxWait) |
| `tests/pytest/test_seo_cache_fragments.py` | +2 tests : recombinaison au plafond maxWait, plafond posé une seule fois |

### Migration
- **Migration nécessaire / Migration required :** Non / No.

## Carte réseau : cache L1 SEO périmé par schema (cause racine du retard ~4h) / SEO L1 cache stale per-schema

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Cause racine confirmée du symptôme « les nouveaux events/adresses
n'apparaissent qu'au bout de plusieurs heures ». Le cache L1 Memcached lu par les
pages publiques restait **périmé jusqu'au TTL (4 h)** même après le recalcul.

**Pourquoi / Why :** `CACHES['default']` utilise
`KEY_FUNCTION = django_tenants.cache.make_key`, qui **préfixe chaque clé de cache
par le schema courant** (isolation cache par tenant). Or les agrégats SEO sont
**globaux** (`tenant=None`, partagés par tout le réseau). Le worker Celery exécute
le rebuild dans le schema du tenant déclencheur → il écrivait la clé sous
`lespass:…:seo:aggregate_lieux`, **invisible** depuis le schema `public` (page ROOT
`/explorer/`) et les autres tenants. Chaque schema avait sa propre copie L1 ; seule
celle du schema déclencheur était fraîche. Les autres lisaient du périmé jusqu'au
TTL 4 h (ou un MISS). Vérifié : L1 lu valait 19 en `public`/`lespass` mais 15 en
`le-coeur-en-or`/`chantefrein` pour la même donnée globale.

**Fix / Fix :** Les helpers L1 SEO (`set_memcached_l1` / `get_memcached_l1`)
épinglent désormais le schema `public` (`with schema_context("public")`) autour de
l'opération cache. La clé n'est donc plus préfixée par le schema d'exécution : une
**seule entrée L1 globale** est partagée par le worker, la page ROOT et chaque
tenant. Vérifié de bout en bout (Chrome) : après création d'un event, L1 identique
sur tous les schemas (public = lespass = le-coeur-en-or) et carte ROOT à jour en
~20 s, **sans rebuild manuel**.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `set_memcached_l1` / `get_memcached_l1` : `with schema_context("public")` autour du `cache.set` / `cache.get` (clé L1 globale, non préfixée par tenant) |
| `tests/pytest/test_seo_cache_fragments.py` | +1 test : agrégat global écrit dans un schema tenant lu identique depuis public + autre tenant |

### Migration
- **Migration nécessaire / Migration required :** Non / No. Les anciennes clés L1
  préfixées par tenant expirent seules (TTL 4 h) et ne sont plus lues.

## Carte réseau : events/adresses fraîchement sauvés n'apparaissaient pas / Network map: freshly saved events & addresses didn't show up

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Sur la carte ROOT (`/explorer/`), un nouvel évènement ou une
nouvelle adresse pouvait rester invisible jusqu'au prochain passage du beat
Celery (jusqu'à 4 h), alors que le tenant venait de sauvegarder.

**Pourquoi / Why :** Le rebuild de l'agrégat `AGGREGATE_POINTS` (lu par la carte)
était déclenché en **débounce « front montant »** : la tâche était planifiée à
`T_première_modif + 180 s`. Si une modif arrivait tard dans cette fenêtre, son
fragment `TENANT_POINTS` (countdown plus court) pouvait être recombiné **trop
tôt** — le rebuild figeait un agrégat à partir d'un fragment pas encore à jour —
et **aucun rebuild de rattrapage** n'était garanti. Seul le beat 4 h corrigeait.
Aggravé par une « fenêtre morte » du débounce fragment (countdown 30 s < TTL
verrou 60 s).

**Fix / Fix :** Passage à un **débounce « front descendant » (trailing)**. Chaque
`post_save`/`post_delete` Event/PostalAddress repousse une échéance
(`seo_rebuild_echeance = now + 15 s`) et planifie au plus une tâche rebuild par
fenêtre. À son réveil, `rebuild_seo_aggregates` recombine **seulement si**
l'échéance est atteinte ; sinon il se **replanifie** pile à l'échéance. Garantie :
un rebuild s'exécute **toujours après la dernière modif**, sur des fragments à
jour. Le beat 4 h appelle `rebuild_seo_aggregates(force=True)` (recombine
toujours, filet anti-dérive). Countdown du fragment réduit à 5 s et TTL du verrou
aligné (fin de la fenêtre morte). Latence perçue : ~20 s au lieu de 3 min → 4 h.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/tasks.py` | `planifier_rebuild_agregats()` (débounce trailing) ; garde + `force` dans `rebuild_seo_aggregates` ; beat en `force=True` ; constantes `REBUILD_TRAILING_WINDOW`/`REBUILD_MARGE` |
| `BaseBillet/signals.py` | `declencher_refresh_seo_cache` : fragment countdown 5 s (TTL aligné) ; rebuild via `planifier_rebuild_agregats()` (remplace le front montant 180 s) |
| `tests/pytest/test_seo_cache_fragments.py` | +4 tests : abstention/replanification, recombinaison à l'échéance, `force=True`, débounce du helper |

### Migration
- **Migration nécessaire / Migration required :** Non / No (logique Celery + cache uniquement).

## Admin réservation : fix crash `'TibilletUser' has no attribute 'lower'` / Admin reservation: fix crash on add

**Date :** 2026-06-26
**Migration :** Non / No

**Quoi / What :** L'ajout d'une réservation depuis l'admin
(`/admin/BaseBillet/reservation/add/`) plantait avec
`AttributeError: 'TibilletUser' object has no attribute 'lower'` dès qu'un
utilisateur était sélectionné (Sentry 7574740199).

**Pourquoi / Why :** un commit du 2026-06-03 avait transformé le champ `email`
d'un `forms.EmailField` (saisie d'une adresse) en
`forms.ModelChoiceField(queryset=TibilletUser.objects.all())` (Select2 pour
chercher un utilisateur existant) — **sans adapter `save()`**. `cleaned_data['email']`
renvoyait donc un objet `TibilletUser`, que `save()` passait toujours à
`get_or_create_user()`, lequel appelle `email.lower()` → crash. Bug introduit
le 3 juin, déclenché en prod le 25.

**Fix :** retour à un **input texte simple** (`forms.EmailField`), l'usage
historique. `save()` retrouve ou crée l'utilisateur via
`get_or_create_user(email, send_mail=False)` (pas de mail de validation : la
réservation est créée côté admin). Effet de bord positif : supprime la fuite
cross-tenant du `queryset=TibilletUser.objects.all()` (qui listait tous les
utilisateurs de la plateforme).

**Bonus — choix du tarif :** le champ tarif listait les `PriceSold`, qui
n'existent **qu'après une première vente** : les évènements payants à venir
jamais vendus n'apparaissaient pas (un seul tarif visible). Il liste désormais
**une option par couple (évènement, tarif)** (`ChoiceField`, valeur
`event_uuid:price_uuid`, libellé cherchable « date — évènement — tarif — prix »),
et `save()` **matérialise** le `ProductSold` + `PriceSold` au moment de la
création, comme le flow de vente.

Le couple est nécessaire car un même tarif (`Product`/`Price`) peut être
**partagé entre plusieurs évènements** — typiquement « Réservation gratuite »
(`views.py` ajoute le même produit FREERES à chaque évènement gratuit). Un
select listant les `Price` n'aurait montré qu'**une** option pour N évènements
et aurait réservé sur le mauvais évènement (le premier). Avec le couple, chaque
évènement a sa propre entrée et la réservation cible le bon évènement.

**Bonus — email manquant dans la liste des ventes :** la colonne « user_email »
de l'admin `LigneArticle` restait **vide** pour les ventes via l'admin.
`LigneArticle.user_email()` ne gérait que `membership` et `paiement_stripe`,
jamais `reservation`. Ajout du cas `reservation.user_commande` (en priorité).

**Bonus — champ « Prix par billet » :** nouveau champ `amount` (montant unitaire
**par billet**). Il se **pré-remplit** automatiquement à la sélection du tarif
(JS) et devient **obligatoire** pour un tarif à **prix libre** (`free_price`).
Un libellé « prix € × quantité = total € » rappelle que le montant est par billet.

**Bonus — moyen de paiement obligatoire :** le select `payment_method` est
désormais **requis** et commence par « Sélectionner un moyen de paiement »
(option vide). Avant, le 1er choix proposé était « Offert » (`FREE`) : une
validation distraite créait une **vente offerte par erreur**.

**Fix — double comptage du montant (bug pré-existant) :** `save()` stockait
`LigneArticle.amount = prix × quantité × 100`, or `amount` est le **montant
UNITAIRE en centimes** (le total est `amount × qty`, cf. `comptabilite/services.py`
et `LigneArticle.total()`). Une réservation admin de N billets était donc comptée
`× N` en trop (ex. 8 € × 3 affichait 72 € au lieu de 24 €). Corrigé en
`amount = prix_unitaire × 100`. **⚠️ Données : les `LigneArticle` payantes créées
via ce formulaire avant ce correctif (sale_origin = `ADMIN`, qty > 1) ont un
`amount` surévalué** — à vérifier/corriger en base si nécessaire.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `ReservationAddAdmin` : champ `email` → `EmailField` ; `save()` → `get_or_create_user(email, send_mail=False)` ; champ tarif `price` (`ChoiceField`, une option par couple évènement/tarif via `_build_event_price_options`) ; champ `amount` (prix par billet) + `clean()` (requis si prix libre) ; `save()`/`clean_payment_method` parsent `event_uuid:price_uuid` ; `class Media` (JS d'auto-remplissage) |
| `Administration/static/admin/js/reservation_price_autofill.js` | **Nouveau** : auto-remplissage du prix à la sélection du tarif, requis si prix libre, libellé total |
| `BaseBillet/models.py` | `LigneArticle.user_email()` : gère le cas `reservation.user_commande` (colonne email des ventes admin) |
| `tests/pytest/test_admin_reservation_add.py` | **Nouveau** : 7 tests (gratuit + payant, **tarif partagé → 2 options + bon event**, **prix par billet override**, **prix libre requis**, **moyen de paiement requis**, garde-fous), avec vérif `amount`/`total()` et `user_email()` |

## Wizard event public : fix email perdu via le chemin Tiers-Lieux / Public event wizard: fix email lost via the Tiers-Lieux path

**Date :** 2026-06-18
**Migration :** Non / No

**Quoi / What :** Un visiteur **anonyme** qui choisissait son lieu via le recensement national
**Tiers-Lieux** (bouton « Utiliser ce lieu ») voyait, à la soumission finale, son évènement
**rejeté** avec retour au début et le message « Merci d'indiquer votre adresse e-mail… », alors
que l'email était bien renseigné.

**Pourquoi / Why :** le bouton « Utiliser ce lieu » est un **formulaire distinct** du form principal
de l'étape 1 (imbriqué via HTMX). Le navigateur ne postait donc que les champs du lieu — **pas
l'email**, qui vit dans le form principal. L'action `use_tierslieux` ne stockait jamais
`email_proposeur` en session (contrairement au chemin classique `_wizard_etape_choix_lieu`), donc
la finalisation ne le retrouvait pas. Le chemin « adresse existante » / « nouveau lieu manuel »
n'était pas affecté (d'où le bug visible uniquement via l'API Tiers-Lieux).

**Fix :**
- JS (`_form_lieu.html`) : au **clic** sur « Utiliser ce lieu », l'email du proposeur est injecté
  dans un champ caché du form Tiers-Lieux avant l'envoi natif (et le clic est bloqué avec
  `preventDefault()` + `reportValidity()` si l'email est vide). On écoute le `click` et **pas** le
  `submit` : le `submit` d'un **formulaire imbriqué** ne remonte pas jusqu'à `document` (vérifié en
  navigateur), donc une délégation `submit` ne se déclencherait jamais.
- Serveur (`use_tierslieux`) : lecture de `email_proposeur` dans le POST et stockage en session pour
  les anonymes, exactement comme `_wizard_etape_choix_lieu`. Garde défensive : email vide → retour
  étape 1 avec le même message (POST forgé / session perdue).

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventWizard.use_tierslieux` : capture + stockage session de `email_proposeur` (anonyme) |
| `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html` | JS : injection de l'email dans le form Tiers-Lieux au submit |
| `tests/pytest/test_event_wizard_unifie.py` | `test_use_tierslieux_anonyme_garde_email_en_session` (régression) |

## i18n EN : sync + complétion des traductions manquantes + fix extraction f-string / i18n EN: sync + fill missing translations + f-string extraction fix

**Date :** 2026-06-18
**Migration :** Non / No

**Quoi / What :**
1. **Sync FR/EN** (mode SYNC du skill i18n-translate) : 9 chaînes fuzzy / fuites de langue corrigées.
2. **Complétion EN** : 74 chaînes de **source française** sans traduction anglaise (msgstr EN vide →
   français affiché sur le site anglais) traduites FR→EN. Surtout l'app **crowds/contrib**
   (`Filter by tags`, `venues & organisations`, `contributors`, etc.). Les ~1463 autres msgstr EN
   vides sont de **source anglaise** (repli correct) et restent intacts.
3. **Fix extraction f-string** dans `minutes_to_human` (`BaseBillet/templatetags/tibitags.py`) :
   les unités de durée `_('j')` / `_('h')` / `_('min')` étaient **à l'intérieur de f-strings**
   (`f"{n} {_('j')}"`) → `makemessages` (xgettext) **n'extrait pas** un `_()` dans une f-string,
   donc « j/h/min » restaient en français partout (ex. « 2 j » sur la page Contribuez). Les `_()`
   sont sortis dans des variables locales + commentaires `# Translators:`. **Nécessite un nouveau
   `makemessages`** pour extraire ces 3 unités, puis traduire « j » → « d » en anglais.

**Pourquoi / Why :** supprimer le français qui fuit sur le site anglais (chaînes externalisées mais
non traduites), et corriger un piège d'extraction qui rendait 3 unités invisibles à `makemessages`.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `locale/en/LC_MESSAGES/django.po` | 9 (sync) + 74 (complétion FR→EN) msgstr remplis ; intégrité blocs 2526=2526, `msgfmt` OK |
| `locale/fr/LC_MESSAGES/django.po` | corrections fuzzy du sync (FR inchangé pour la complétion EN) |
| `BaseBillet/templatetags/tibitags.py` | `minutes_to_human` : `_()` sortis des f-strings (extraction xgettext) + `# Translators:` |

## Admin clé API & asset : fix icônes asset cadeau, nettoyage assets démo BDG, UUID asset lisible / Admin API key & asset: gift-asset icon fix, BDG demo-asset cleanup, readable asset UUID

**Date :** 2026-06-18
**Migration :** Non / No

**Contexte / Context :** Remontée utilisateur sur **Admin → Outils externes → Clé API**. En changeant
l'asset cadeau (`gift_asset`) d'une clé puis en enregistrant, l'utilisateur croyait que le
changement n'était pas pris en compte et voyait une **erreur sur le nouvel asset**.

**Quoi / What :**
1. **Bug clé API expliqué et corrigé.** La sauvegarde de `gift_asset` **fonctionnait** (vérifié :
   la valeur change bien en base). L'erreur venait des **icônes crayon / œil / +** affichées à côté
   du menu déroulant : elles ouvrent l'admin des assets, qui **masque volontairement les assets
   badgeuse (BDG)** → clic = erreur « cet asset n'existe pas ». On retire ces icônes de gestion
   d'asset sur le champ `gift_asset` (`formfield_for_dbfield`) : on ne gère pas les assets depuis
   la page clé API, la sélection dans la liste suffit.
2. **Assets démo « [DEMO] Biere / Soft / Sandwich » (catégorie BDG) supprimés.** Origine : la
   fixture `_demo_data_v2_ventes.py` créait ces produits en `Product.BADGE` (mauvaise catégorie :
   ce sont des **ventes de comptoir**, pas des badgeuses). Le signal post_save
   `send_membership_and_badge_product_to_fedow` transformait alors chaque produit BADGE en asset
   BDG, qui polluait les listes d'assets (et le menu `gift_asset`). Fixture corrigée en
   `Product.NONE` + 3 assets BDG supprimés de la base dev + 3 produits démo repassés en `NONE`.
3. **UUID de l'asset en lecture seule** sur la page change d'un asset (`AssetAdmin`).
4. **Étanchéité multi-tenant sur `gift_asset` (faille corrigée).** `AssetFedowPublic` vit dans le
   schéma public partagé : le menu déroulant listait les assets de **tous les lieux**, un lieu
   pouvait donc choisir l'asset cadeau d'un autre. Le queryset est désormais restreint aux assets
   **dont le tenant courant est l'origine** (`origin = connection.tenant`), via
   `ExternalApiKeyAdmin.formfield_for_foreignkey`. Vérifié : un asset d'un autre tenant n'apparaît
   plus et est rejeté en validation. (Surfaces déjà sûres : `Price.fedow_reward_asset` filtre déjà
   `origin=client` ; `Initiative.asset` n'est pas un champ éditable.)
5. **Démo badgeuse retirée de `demo_data.py`.** Le bloc « Badgeuse co-working » (produit `BADGE` +
   tarif « Passage ») et la phrase qui l'annonçait dans la description de l'instance démo sont
   supprimés (« on n'utilise plus les badges »). Aucune donnée en base : ce bloc n'avait jamais été
   exécuté sur la base dev.

**Pourquoi / Why :** lever l'ambiguïté côté utilisateur (« on n'utilise plus les badges »), retirer
des données démo trompeuses, exposer l'identifiant technique de l'asset quand on en a besoin, et
**garantir l'isolation multi-tenant** sur le choix de l'asset cadeau.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin.formfield_for_foreignkey` : queryset `gift_asset` limité à `origin = tenant` + catégories rechargeables. `ExternalApiKeyAdmin.formfield_for_dbfield` : retire add/change/delete/view related sur `gift_asset`. `AssetAdmin` : `uuid` ajouté en `readonly_fields` + `fields` |
| `Administration/management/commands/_demo_data_v2_ventes.py` | Produits démo Biere/Soft/Sandwich : `Product.BADGE` → `Product.NONE` (évite la création d'assets BDG parasites) |
| `Administration/management/commands/demo_data.py` | Bloc « Badgeuse co-working » (produit BADGE + tarif) supprimé + phrase descriptive associée retirée |
| Base dev (one-shot, pas de code) | Suppression des 3 assets BDG `[DEMO] *` + produits démo repassés en `NONE` |

## API v2 recharge cadeau : traçabilité LigneArticle + fix 500 Fedow / API v2 gift refill: LigneArticle traceability + Fedow 500 fix

**Date :** 2026-06-18
**Migration :** Non / No

**Contexte / Context :** `POST /api/v2/wallet-refills/` ne fonctionnait **pas du tout** en réel
(500), mais les tests **mockaient Fedow** et le cachaient. L'endpoint Fedow réutilisé
(`refill_from_lespass_to_user_wallet`) est en fait celui de la **récompense d'adhésion** : son
serializer exige `ligne_article_uuid` + `membership_uuid` + `product_uuid` + `price_uuid`. Une
recharge cadeau directe n'a aucun de ces objets. De plus, aucune **trace comptable** n'était créée.

**Quoi / What :**
1. **Le fix Fedow (option C, sans toucher Fedow)** : le serializer Fedow prévoit un bypass via le
   flag `rewarded_from_ticket_scanned` (crédit direct sans contexte de vente, déjà utilisé pour les
   récompenses de scan de ticket). La vue le passe désormais dans le metadata → la recharge
   **crédite réellement** le wallet. Validé en intégration réelle (solde vérifié sur Fedow).
2. La vue crée une **LigneArticle de traçabilité** AVANT l'appel Fedow (un produit
   `RECHARGE_CASHLESS` par asset, tarif 0 €, `payment_method=FREE`) et passe son `uuid` dans le
   metadata. Comme une recharge offerte sur LaBoutik V1 : on trace tout ce qui est crédité.
3. Succès Fedow → ligne `VALID` ; échec → ligne `FAILED` + **502** propre (au lieu de la 500 brute).
   Pas de double-crédit (ligne `CREATED`, `_state.adding` → aucun trigger ; `trigger_R` commenté).
4. **Restriction d'assets alignée sur Fedow** : `REFILLABLE = {cadeau TNF, temps TIM, fidélité FID}`.
   **BADGE (BDG) retiré** (Fedow le refuse via `validate_asset`, et il n'est plus utilisé) ; euro
   (TLF) et fédéré (FED) rejetés en 422.
5. **Tests convertis en intégration RÉELLE** (plus de mock du crédit Fedow) : recharge de chaque
   type (cadeau/temps/fidélité) via l'API + **vérification du solde réel** sur Fedow, et idempotence
   réelle. La fixture crée les assets sur Fedow (comme l'admin : `wallet_origin = place.wallet` +
   `get_or_create_token_asset`). Mocks conservés uniquement pour simuler l'indisponibilité (503) et
   la panne Fedow (502), non reproductibles en réel.

**Pourquoi / Why :** auditer toute recharge (trou comptable) et rendre l'erreur Fedow propre et
traçable, **sans toucher au serveur Fedow** (option choisie par le mainteneur).

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `WalletRefillViewSet` : flag `rewarded_from_ticket_scanned` (bypass Fedow) + `_creer_ligne_article_recharge` + `ligne_article_uuid` dans metadata + succès/échec (VALID/FAILED, 502) |
| `fedow_public/models.py` | `REFILLABLE_CATEGORIES` : retrait de `BADGE` (aligné sur `validate_asset` côté Fedow) |
| `tests/pytest/test_api_v2_wallet_refill.py` | Rejet FED testé (422) ; **tests d'intégration réels** (recharge cadeau/temps/fidélité + vérif solde Fedow + idempotence) via fixture `fedow_real_setup` (assets créés sur Fedow) ; test échec Fedow → 502 + ligne FAILED |

## Tests : couverture du remboursement Stripe + helper Stripe Checkout multi-moyens / Tests: Stripe refund coverage + multi-method Checkout helper

**Date :** 2026-06-18
**Migration :** Non / No

**Quoi / What :**
1. **Nouveau `tests/pytest/test_stripe_refund.py`** (3 tests) — couvre le remboursement Stripe, jusqu'ici non testé : (a) `cancel_and_refund_resa()` — `stripe.Refund.create` (montant + `payment_intent`), paiement `REFUNDED`, avoir négatif, réservation + billets annulés ; (b) réservation gratuite → aucun refund ; (c) **remboursement partiel** `cancel_and_refund_ticket()` — 1 billet sur 4 (montant d'**un** billet, pas du panier ; avoir `qty=-1` ; paiement reste `VALID`). Le test (a) documente que `cancel_and_refund_resa` rembourse `amount_total` (le **paiement entier**) — à revoir pour les paniers.
2. **`tests/e2e/conftest.py` — `fill_stripe_card`** : déplie l'accordéon « Carte » de Stripe Checkout (`data-testid="card-accordion-item-button"`, `dispatch_event`) quand plusieurs moyens sont actifs (Carte + SEPA). Attend que le formulaire soit monté (accordéon **ou** champ carte). Reste compatible « carte seule » (no-op). Débloque `test_membership_manual_validation_stripe` après activation de SEPA sur le compte de test.

**Pourquoi / Why :** le chemin de remboursement Stripe n'avait aucune couverture (les tests d'avoir/annulation utilisent des objets gratuits) ; et l'activation de SEPA a changé la page Checkout (sélecteur de moyen de paiement), cassant le helper partagé.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_stripe_refund.py` | Nouveau — 2 tests (refund payé + gratuit sans refund) |
| `tests/e2e/conftest.py` | `fill_stripe_card` : sélection « Carte » sur Checkout multi-moyens |

## Adhésions SEPA : lien de paiement à usage unique (anti double prélèvement) / SEPA memberships: single-use payment link (duplicate debit fix)

**Date :** 2026-06-17
**Migration :** Oui / Yes — `BaseBillet/migrations/0219_alter_membership_status.py` (`migrate_schemas`)

**Contexte / Context :** pour une adhésion à validation manuelle (caisse sociale
alimentaire), l'admin valide l'adhésion (`ADMIN_VALID`) et un mail envoie un lien de
paiement. En carte bancaire, le paiement est immédiat → l'adhésion passe `ONCE` → le lien
devient inactif. En **prélèvement SEPA**, le débit prend 3 à 14 jours pendant lesquels
l'adhésion restait `ADMIN_VALID` : le lien restait actif. Recliquer dessus pouvait, via le
`except` réseau de la vue, **recréer un checkout** et donc un **2e prélèvement** (cas signalé
« Damien GARNIER »). De plus, une adhésion déjà payée renvoyait un **404 JSON brut** illisible.

**Quoi / What :**
1. **Nouveau statut `Membership.PAYMENT_PENDING` ('PP')** — « Paiement soumis, en attente de
   validation bancaire ». Posé dans `Paiement_stripe.update_checkout_status()` dès que le
   paiement ressort `PENDING` (checkout soumis mais non débité) ; déclenché par le webhook
   `checkout.session.completed` **et** par le retour navigateur. Le succès final repasse en
   `ONCE`/`AUTO` (inchangé), l'échec SEPA (`async_payment_failed`) réarme en `ADMIN_VALID`.
2. **`get_checkout_for_membership` route selon le statut** au lieu d'un `get_object_or_404` :
   `ADMIN_VALID` → checkout ; `PAYMENT_PENDING` → page « paiement en cours » ; `ONCE`/`AUTO`
   → page « adhésion déjà active » ; annulée/introuvable → page « lien invalide ». Plus aucun
   404 JSON brut.
3. **`except` Stripe bloquant** — en cas d'erreur API au moment de vérifier la session, on
   n'ouvre plus jamais de nouveau checkout : on affiche « paiement en cours ».
4. **Bug latent corrigé** — les templates membership utilisaient `{% block content %}` (le
   skin attend `{% block main %}`) et avaient `{% load %}` avant `{% extends %}` : ils
   rendaient une page vide. Corrigé sur `payment_already_pending.html` + 2 nouveaux templates.

**Pourquoi / Why :** matérialiser l'état « paiement soumis » sur l'adhésion elle-même rend la
protection fiable et locale (aucun appel Stripe nécessaire pour bloquer), et symétrique avec
le comportement déjà sûr de la carte bancaire.

**Hors périmètre / Out of scope :** le cas « deux adhésions distinctes pour la même personne »
(relève de `max_per_user`), non traité ici.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Statut `PAYMENT_PENDING` + bascule `ADMIN_VALID → PAYMENT_PENDING` dans `update_checkout_status` |
| `BaseBillet/migrations/0219_alter_membership_status.py` | Nouveau choix de statut (généré) |
| `BaseBillet/views.py` | `get_checkout_for_membership` : routage HTML par statut + `except` bloquant |
| `ApiBillet/views.py` | `async_payment_failed` : réarmement `PAYMENT_PENDING → ADMIN_VALID` |
| `Administration/admin_tenant.py` | Filtre « Attente de paiement » inclut `PAYMENT_PENDING` ; statut de l'adhésion affiché en lecture seule (badge couleur) sur la fiche détail |
| `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` | Bloc `main` + `{% extends %}` en tête |
| `BaseBillet/templates/.../payment_already_done.html` | Nouveau — page « adhésion déjà active » |
| `BaseBillet/templates/.../payment_link_invalid.html` | Nouveau — page « lien invalide » |
| `Administration/management/commands/backfill_membership_payment_pending.py` | Nouveau — régularise en prod les adhésions SEPA déjà soumises restées `ADMIN_VALID` (dry-run par défaut, `--apply`, `--verify-stripe`) |
| `tests/pytest/test_membership_sepa_payment_link.py` | Nouveau — 4 tests (routage + bascule de statut) |
| `tests/e2e/test_sepa_duplicate_protection.py` | Test 3 adapté au nouveau comportement (200 + page, plus de 404) ; force `ONCE` explicitement |
| `tests/e2e/conftest.py` | `fill_stripe_card` : déplie l'accordéon « Carte » (`data-testid="card-accordion-item-button"`, `dispatch_event`) quand plusieurs moyens sont actifs (Carte + SEPA) ; reste compatible carte seule (no-op) |

### i18n
Nouvelles chaînes FR à extraire/compiler (`makemessages` + `compilemessages`) — à faire par le mainteneur.

## Onboarding : fin de la cascade de mails OTP + durcissement de l'endpoint public / Onboarding: stop the OTP mail burst + harden the public endpoint

**Date :** 2026-06-15
**Migration :** Non / No

**Contexte / Context :** les mails « your TiBillet verification code » proviennent du wizard
de **création d'espace** (`onboard`, step `identity`), **pas** de la proposition d'évènement
(agenda participatif `proposition_anonyme_autorisee`). `onboard_otp_mailer` n'a qu'un seul
appelant : `onboard/views.py`. L'endpoint `/onboard/identity/` est **public** (`AllowAny`,
sur ROOT) et était la cible d'un **email-bombing** (un attaquant inonde la boîte d'une
victime via le formulaire d'inscription public) — observé : ~12 mails en ~3 s pour le même
email, chacun avec un `WaitingConfiguration` différent.

**Quoi / What :** trois protections, de la cause racine au durcissement.
1. **Dédup par email (cause racine)** — la step `identity` ne crée plus un nouveau brouillon
   + un nouvel OTP à chaque soumission : elle réutilise un brouillon **non confirmé** existant
   pour le même email (`email__iexact`, `email_confirmed=False`, le plus récent).
2. **Cooldown 60 s** — l'OTP n'est ré-envoyé que si aucun n'a été expédié à ce brouillon
   depuis 60 s (même seuil que `resend_otp`). Neutralise l'email-bombing mono-cible (1 mail
   / 60 s / email).
3. **Durcissement endpoint** — captcha arithmétique (`x + y == answer`, même mécanisme que le
   formulaire de contact) sur la step `identity` ; throttle IP abaissé de **20 → 10/min** et
   calé sur la **vraie IP** (`get_client_ip`/X-Forwarded-For) ; anti-double-submit du bouton
   « Continuer ».

**Pourquoi / Why :** les garde-fous existants ne couvraient pas ce cas : cooldown 60 s +
rate-limit 3/h ne s'appliquaient qu'à `resend_otp` (renvoi sur un brouillon retrouvé en
session), et le throttle 20/min/IP laissait passer les 12 envois (< 20).

**Limite connue / Known limit :** la dédup n'est pas atomique sous concurrence stricte
(POST réellement parallèles avant le 1er commit pourraient créer 2-3 brouillons). Le captcha
+ le throttle 10/min + l'anti-double-submit restent les filets de sécurité. Un abus
multi-IP/multi-email reste limité par le throttle et le captcha mais non éliminé.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `onboard/views.py` | `identity` (POST) : dédup brouillon non confirmé + envoi OTP conditionné au cooldown 60 s. `IdentityPostRateThrottle` : 20→10/min + `get_ident` sur la vraie IP |
| `onboard/serializers.py` | `OnboardIdentitySerializer` : champs captcha `x`/`y`/`answer` + validation `x+y==answer` |
| `onboard/templates/onboard/steps/01_identity.html` | Bloc captcha (label + hidden x/y + génération JS) + anti-double-submit du bouton « Continuer » |
| `onboard/tests/test_step_identity.py` | Captcha ajouté aux payloads ; `quota` 20→10 ; **2 nouveaux tests** : dédup (2 POST même email → 1 brouillon, 1 OTP) et captcha invalide → 422 |

### Note dev
- **i18n à régénérer** : nouveaux msgid FR sur la step identity (« Anti-spam », « Combien
  font », « Merci de répondre à cette question simple… », « Mauvaise réponse à la question
  anti-spam. »). Lancer `makemessages` + `compilemessages` (côté mainteneur).
- Warning ruff **préexistant** non corrigé (hors scope) : `F601` clé `"has_pending_otp"`
  dupliquée dans `onboard/views.py` (vue `verify`, ~ligne 1243).

## Vente de billet en caisse LaBoutik → réservation Lespass (API v2) / LaBoutik POS ticket sale → Lespass reservation (API v2)

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** l'API v2 `POST /api/v2/reservations/` accepte maintenant une vente de
billet déjà payée en caisse (`additionalProperty paymentMethod = "cash" | "card"`) :
réservation créée directement `VALID`, tickets `NOT_SCANNED`, `LigneArticle` `VALID`
avec le vrai moyen de paiement (`CASH`/`CC`) et `sale_origin=LABOUTIK`, **sans checkout
Stripe**. `reservationFor` devient optionnel : Lespass déduit l'évènement depuis le tarif
(prochain évènement publié qui propose le produit ; erreur claire si zéro ou plusieurs
candidats). Côté LaBoutik (dépôt séparé) : implémentation de `Commande.methode_BI` qui
appelait jusqu'ici un attribut inexistant (crash 500 en prod, cafeasso 2026-06-11).

**Pourquoi / Why :** un article `BILLET` synchronisé depuis Lespass était vendable en
caisse mais sans handler (`AttributeError: 'Commande' object has no attribute 'methode_BI'`)
et aucune remontée du billet vers Lespass n'existait.

**Pas de boucle / No loop :** la `LigneArticle` est créée directement en `VALID` :
la machine à état (`pre_save_signal_status`) ignore les créations (`_state.adding`),
donc pas de renvoi `send_sale_to_laboutik` vers la caisse.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/validators.py` | `TicketCreator` : mode `paid_externally` + `external_payment_method` (ligne de vente `VALID`, tickets `NOT_SCANNED`, pas de Stripe) ; `ReservationValidator` lit ces flags depuis le `context` |
| `api_v2/serializers.py` | `ReservationCreateSerializer` : `reservationFor` optionnel + `_resolve_event_from_prices()` ; `additionalProperty paymentMethod` (cash/card) → mode payé en caisse, `sale_origin=LABOUTIK` |
| `tests/pytest/test_api_v2_reservation_laboutik.py` | **Nouveau** — 5 tests : cash sans event, card avec event, paymentMethod inconnu, event ambigu, aucun event futur |
| `../LaBoutik/webview/billet_lespass.py` | **Nouveau** (dépôt LaBoutik) — `envoyer_reservation_billet()` : POST API v2, timeout (3, 5), erreurs lisibles |
| `../LaBoutik/webview/views.py` | **Nouveau** (dépôt LaBoutik) — `Commande.methode_BI` : espèce/CB only, email carte NFC sinon config, appel synchrone, rollback atomique si échec |

### Note dev
- La clé API LaBoutik (`Configuration.lespass_api_key`) doit avoir la permission
  **Bookings (`reservation`)** sur `ExternalApiKey` côté Lespass.
- Effet de bord assumé : la réservation passant à `VALID` envoie le billet PDF par mail —
  au client si carte NFC avec email, sinon à l'email de la Configuration LaBoutik.

## Test carte NFC → wallet (vérif Fedow réelle) + bugfix lien carte hors transaction / NFC card → wallet test (real Fedow check) + card-link transaction bugfix

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** nouveau test d'intégration `tests/pytest/test_membership_card_wallet_fedow.py` :
création d'adhésion via le formulaire admin avec un numéro de carte NFC, puis vérification
RÉELLE chez Fedow (wallet `has_user_card=True`, carte plus éphémère), nettoyage rejouable
(`lost_my_card`). Skip explicite si `FEDOW_TEST_CARD_NUMBER` absent de l'environnement.

**Bugfix découvert par le test :** `MembershipAddForm.save()` liait la carte chez Fedow
pendant `form.save()` — que l'admin Django appelle AVANT de valider les inlines. Si un
formset était invalide, la transaction DB était annulée mais l'appel HTTP déjà parti :
**carte liée chez Fedow sans adhésion côté Lespass**. Corrigé avec `transaction.on_commit`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | **Bugfix** : `linkwallet_card_number` déplacé dans `transaction.on_commit` (cohérence Lespass ↔ Fedow) |
| `tests/pytest/test_membership_card_wallet_fedow.py` | **Nouveau** — test d'intégration carte → wallet avec vrais appels Fedow |

### Note dev
- Pour rendre le test actif en permanence : ajouter `FEDOW_TEST_CARD_NUMBER=58515F52` au `.env`
  (une carte Fedow sans utilisateur ; voir le docstring du test pour en trouver une autre).
  Sans la variable, le test skip proprement.
- Piège documenté : un user créé dans un test pytest (transaction rollbackée) mais enregistré
  chez Fedow pendant la validation du formulaire laisse un FedowUser orphelin dont les clés de
  signature sont perdues — ses endpoints signés (dont `lost_my_card`) deviennent inaccessibles.
  Les cartes de démo consommées pendant la mise au point ont été libérées (opération identique
  à la vue `lost_my_card_by_signature` de Fedow, validée par le mainteneur).

## Vague 5 (finale) : la suite TypeScript n'existe plus / Wave 5 (final): TypeScript suite is gone

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** les 3 derniers specs TS (duplication produit complexe, event quick create,
explorer markers) convertis en Playwright Python — 5 tests verts. **`tests/playwright/tests/`
est vide : 42 specs TS → 0 en une journée.** La suite E2E est désormais 100 % Python
(~65 tests, ~6 min) ; suite backend pytest : 246 tests (~50 s).

**Pourquoi / Why :** une seule techno de test (pytest), login E2E instantané (force_login),
Stripe mocké pour la logique + smoke réels pour les parcours d'argent. Reste une décision
mainteneur : supprimer le dossier `tests/playwright/` (outillage Node/yarn mort) et les
`tests/scripts/verify_*.py` devenus inutiles — voir
`TECH_DOC/SESSIONS/TESTS/CHANTIER-05-vague-5-cloture.md`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_product_duplication_complex.py`, `test_event_quick_create_duplicate.py`, `test_explorer_markers_per_pa.py` | **Nouveaux** — conversions des 3 derniers specs TS |
| `tests/playwright/` | **Dossier supprimé entièrement** (specs, utils, configs, node_modules — plus aucune dépendance Node/yarn) |
| `tests/scripts/verify_*.py` (4 fichiers) | **Supprimés** — n'étaient appelés que par les specs TS ; `setup_test_data.py` conservé (fixture e2e) |
| `tests/README.md`, `GUIDELINES.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-05-*.md` | Documentation de clôture |

## Vague 4 migration tests TS→Python — specs adhésions / Wave 4 TS→Python test migration — membership specs

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 11 specs adhésions Playwright TS convertis en Playwright Python (workflow
d'agents Sonnet séquentiels) : création admin (simple, récurrente, validation, AMAP, solidaire,
manuelle), prix libre multi (Stripe réel ×4), annulation récurrente, cycle complet formulaire
dynamique (7 tests), protection doublon SEPA, validation manuelle + paiement Stripe réel —
22 tests Python, tous verts. **Suite TS : 14 → 3 specs.**

**Pourquoi / Why :** avant-dernière vague de la migration vers pytest unique. Après la vague 5
(3 specs restants : 25, 29, 40), le dossier `tests/playwright/` et l'outillage Node pourront
être supprimés.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_membership*.py`, `test_memberships_admin_create.py`, `test_sepa_duplicate_protection.py` (11 fichiers) | **Nouveaux** — conversions des specs TS 03-07, 14, 17, 22, 27, 36, 43 |
| `tests/playwright/tests/` | **Supprimés** : les 11 specs migrés |
| `BaseBillet/tasks.py` | **Bugfix** : `context_for_membership_email` crashait (`AttributeError`) quand `get_deadline()` ou `last_contribution` est `None` (adhésion en attente de validation) — les lignes de dates du mail ne sont ajoutées que si la date existe |
| `tests/e2e/test_membership_account_states.py` | Résilience : 1 reload si le runserver dev rend une page d'erreur transitoire (`OSError Bad file descriptor` sous charge) |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-04-*.md` | Documentation à jour (dont constat interop V1 `/api/salefromlespass`) |

## Vague 3 migration tests TS→Python — specs admin / Wave 3 TS→Python test migration — admin specs

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 8 specs admin Playwright TS convertis en Playwright Python par un workflow
d'agents Sonnet séquentiels (1 agent par spec, conversion + vérification + corrections) :
custom form edit, credit note, ajouter paiement, cancel membership, list status, adhésions
obligatoires M2M (x2), reservation cancel — 13 tests Python, tous verts. Suite TS : 22 → 14 specs.

**Pourquoi / Why :** poursuite de la migration vers une seule techno de test (pytest), avec un
coût réduit de ~40 % vs la vague 2 (1 agent au lieu de 2 par spec, modèle Sonnet, cheat-sheet
dans le prompt au lieu de relire conftest + PIEGES).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_admin_*.py` (6 fichiers), `test_event_adhesion_obligatoire_check.py` | **Nouveaux** — conversions des specs TS 26, 32, 33, 34, 35, 37, 38, 39 |
| `tests/playwright/tests/` | **Supprimés** : les 8 specs migrés |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-03-*.md` | Documentation à jour, dont un ⚠️ « formulaires imbriqués HTMX dans la fiche admin Membership » à vérifier manuellement |

## Vague 2 migration tests TS→Python + fix timeout fedow_api / Wave 2 TS→Python test migration + fedow_api timeout fix

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 8 specs Playwright TS supplémentaires convertis en Playwright Python via un
workflow multi-agents (login, admin-config, account-summary, reservation-limits,
account-states, crowds x2, theme/language — 11 tests Python, tous verts). Suite TS : 30 → 22 specs.
**Bugfix critique** : `timeout=30` sur les appels HTTP de `fedow_connect/fedow_api.py`.

**Pourquoi / Why :** sans timeout, un serveur Fedow muet gelait le runserver mono-thread pour
toujours (incident du 2026-06-11 : serveur bloqué 1h dans `send_membership_product_to_fedow`,
toutes les requêtes en 504, cascade de faux échecs E2E sur les specs 33-39).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | **Bugfix** : `timeout=30` sur `_post` et `_get` |
| `tests/e2e/test_login.py`, `test_admin_configuration.py`, `test_user_account_summary.py`, `test_reservation_limits.py`, `test_membership_account_states.py`, `test_crowds_participation.py`, `test_crowds_summary.py`, `test_theme_language.py` | **Nouveaux** — conversions des specs TS 01, 02, 16, 19, 21, 23, 24, 99 |
| `tests/playwright/tests/` | **Supprimés** : 01, 02, 16, 19, 21, 23, 24, 99 (migrés en Python) |
| `tests/playwright/tests/36-sepa-duplicate-protection.spec.ts` | **Bugfix** : import `Paiement_stripe` depuis `BaseBillet.models` (l'ancien import `PaiementStripe.models` échouait silencieusement → test flaky qui ne testait pas la protection doublon) |
| `tests/playwright/tests/26-admin-membership-custom-form-edit.spec.ts` | Timeout `execSync` 15 s → 60 s (boot `tenant_command shell` sous charge) |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/` | Tableau de migration et CHANTIER-02 à jour |

## Simplification des suites de tests + socle E2E Python (force_login) / Test suites simplification + Python E2E foundation

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** portage du socle E2E Python de la V2 (endpoint `force_login` triple-gated +
fixtures), migration de 3 specs TS vers Playwright Python, portage de 17 tests pytest Stripe
mockés + 2 smoke Stripe E2E réels depuis la V2, suppression de 12 specs TS redondants
(42 → 30 specs, suite TS ~11 min → ~7 min), renumérotation des doublons 21/35.

**Pourquoi / Why :** une seule techno de test (pytest), des tests Stripe 50× plus rapides
(mock au lieu de vrai checkout), et un login E2E en 100 ms au lieu de 5 s. Politique identique
à la V2 (`lespass-main`) pour faciliter la fusion future.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/views_test_only.py` | **Nouveau** — endpoint `force_login_for_e2e` (DEBUG + E2E_TEST_TOKEN + header X-Test-Token, copie V2) |
| `AuthBillet/urls.py` | Branchement de l'endpoint sous `if settings.DEBUG:` |
| `tests/pytest/conftest.py` | Fixtures partagées portées de la V2 : `api_client`, `auth_headers`, `admin_user`, `admin_client`, `tenant`, `mock_stripe`, `django_db_setup`, `_enable_db_access_for_all` |
| `tests/pytest/test_stripe_membership_simple.py` | **Nouveau** (V2) — 5 tests Stripe mockés adhésion |
| `tests/pytest/test_stripe_membership_complex.py` | **Nouveau** (V2) — 6 tests : multi prix libre, montant zéro, champs dynamiques |
| `tests/pytest/test_stripe_reservation.py` | **Nouveau** (V2) — 4 tests réservation (gratuit, payant, options, form dynamique) |
| `tests/pytest/test_stripe_crowds.py` | **Nouveau** (V2) — 2 tests contribution crowds |
| `tests/pytest/test_comptabilite_service.py` | 3 tests passés en assertions delta / filtre par produit (piège 9.60, DB partagée) |
| `tests/e2e/test_membership_validations.py` | **Nouveau** (V2, remplace spec TS 20) — assertion e-mail tolérante FR/EN |
| `tests/e2e/test_reservation_validations.py` | **Nouveau** (V2, remplace spec TS 18) |
| `tests/e2e/test_numeric_overflow_validation.py` | **Nouveau** (conversion du spec TS 28) |
| `tests/e2e/test_stripe_smoke.py` | **Nouveau** (V2) — 2 checkouts Stripe réels (adhésion + réservation) |
| `BaseBillet/templates/reunion/views/event/partial/booking_form.html` | **Bugfix** : `min="{{ price.prix\|unlocalize }}"` — en locale FR, `min="5,00"` est invalide et neutralisait la validation HTML5 |
| `BaseBillet/templates/reunion/views/membership/form.html` | Même bugfix `unlocalize` (2 occurrences) |
| `tests/playwright/tests/` | **Supprimés** (couverts par mock/smoke/Python) : 08, 09, 10, 11, 12, 13, 15, 18, 20, 28, 42, 44. **Renommés** : 21-event-quick-create→29, 35-admin-reservation-cancel→39, 35-explorer-markers→40 |
| `tests/README.md` | Réécriture complète (comptes à jour, 3 suites, politique Stripe, migration TS→Python) |
| `TECH_DOC/SESSIONS/TESTS/` | **Nouveau** hub : état des lieux, plan de simplification, tests restants |

## Remise au vert des suites de tests (baseline chantier FEDOW_IMPORT) / Test suites back to green (FEDOW_IMPORT baseline)

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** remise au vert complète des 3 suites (pytest 226, E2E Playwright TS ~66, E2E
Playwright Python 8) avant d'ouvrir le chantier S6 (caisse V2 + fedow_core). Aucun code applicatif
modifié — uniquement les tests et leur outillage.

**Pourquoi / Why :** baseline de non-régression exigée avant le lot C-A (copier-coller du socle).
Les échecs venaient de : (1) tests E2E non mis à jour après la refonte de l'admin produits en
proxys (`membershipproduct`/`ticketproduct`, inlines Unfold) ; (2) pollution de données entre tests
(fenêtre comptable de 5 min partagée, cache pytest persistant après `docker compose down -v`) ;
(3) outillage (clé API absente du conteneur, Playwright non installé, règle DNS Chromium sans
l'apex, `www.` non routé par le Traefik de dev).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/conftest.py` | Fallback en conteneur pour `test_api_key` (porté de lespass-main) — la commande documentée du README refonctionne |
| `tests/pytest/test_comptabilite_service.py` | 3 tests rendus hermétiques : assertions en DELTA (snapshot avant création) + cleanup en `try/finally` |
| `tests/pytest/test_crowd_budget_item_flow.py` | Vérifie que l'initiative en cache pytest existe encore (DB recréée) avant réutilisation |
| `tests/e2e/conftest.py` | Règle Chromium `MAP` : ajout du domaine apex (le wildcard `*.domaine` ne couvre pas le domaine nu) |
| `tests/e2e/test_explorer_ux_pills_tags.py` | Explorer testé sur l'apex (le Traefik de dev ne route pas `www.`) |
| `tests/playwright/tests/*.spec.ts` (19 fichiers) | Adaptation à la nouvelle UX admin : proxys produits, inlines Unfold (`#form_fields-group`, `a.add-row`, `options_csv`, `order` caché), assertions bilingues FR/EN, wizard event unifié, divers sélecteurs |

### Bugs applicatifs découverts puis CORRIGÉS le 2026-06-11 / App bugs found then FIXED on 2026-06-11
1. **Wizard event : doublon → HTTP 500 — CORRIGÉ.** La finalisation (`EventWizard.step2_event`,
   `BaseBillet/views.py`) enveloppe la création des brouillons dans `transaction.atomic()` et attrape
   l'`IntegrityError` de `unique_together('name','datetime')` → message warning + retour à l'étape des
   brouillons (conservés en session), création tout-ou-rien. Suite à la review externe : la suppression
   des images temporaires des brouillons est différée APRÈS le commit (un rollback DB n'annule pas une
   suppression de fichier — sinon retry sans images) + log de l'exception. Test E2E réactivé
   (`21-event-quick-create-duplicate.spec.ts`, plus de `fixme`).
2. **Signaux `post_save`/`pre_save` muets sur les proxys — CORRIGÉ.** Liste `PROXYS_PRODUCT`
   (`BaseBillet/models.py`) + connexions explicites des 4 receivers aux 4 proxys
   (`models.py` : post_save_Product ; `signals.py` : unpublish_if_archived,
   send_membership_and_badge_product_to_fedow, trigger_product_update). Test de garde
   `tests/pytest/test_signaux_proxys_product.py` (échoue si un nouveau proxy n'est pas connecté +
   rejoue le bug FREERES). Contournement du spec 37 retiré (le test prouve désormais l'auto-création).
   Bonus : retrait d'un import accidentel d'IDE `from jedi.inference.value import instance`
   (`signals.py:12`, inutilisé, dépendance dev-only en code de prod).
3. **Fixtures non déterministes (tenants `W` sans domaine)** : `test_comptabilite_exports.py` et
   `test_event_is_proposal_field.py` utilisaient `.exclude(public).first()` → tenant `waiting_config`
   sans Domain (créé par les E2E onboarding) → `AttributeError`. Tenant `lespass` explicite désormais.
4. **Celery `trigger_product_update_tasks` : flood d'ERROR `Product.DoesNotExist` — CORRIGÉ.**
   La tâche (1 s après le post_save) faisait un `get` sec : tout produit supprimé entre-temps
   (cleanup des tests, suppression admin rapide) levait une ERROR. Produit disparu = rien à
   notifier à LaBoutik → `try/except DoesNotExist` + log info (`BaseBillet/tasks.py:1756`).
   Worker celery redémarré pour charger le fix. Note : le volume de ces tâches augmente
   légitimement avec le fix n°2 (les saves via proxys notifient désormais LaBoutik, comme prévu).
5. **Infra dev (non corrigé, à arbitrer) :** `www.tibillet.localhost` n'est pas routé par Traefik
   (404 text/plain avant Django). Et noté : courses pymemcache (`'NoneType'... 'recv'`) quand les
   deux suites de tests tournent en parallèle (cf. tests/PIEGES.md, session 2026-06-11).

## Fix race « mail de connexion » dispatché avant COMMIT / Fix "login email" task dispatched before COMMIT

**Date :** 2026-06-07
**Migration :** Non / No

**Quoi / What :** la tâche Celery `connexion_celery_mailer` plantait par intermittence avec
`TibilletUser.DoesNotExist` (vu dans le conteneur `lespass_celery`). En cause : `sender_mail_connect()`
appelait `connexion_celery_mailer.delay(...)` **pendant** une transaction encore ouverte. Le worker
Celery, sur sa propre connexion DB, lisait l'utilisateur **avant le COMMIT** → introuvable.

**Pourquoi / Why :** la création d'utilisateur déclenche le mail dès `get_or_create_user()`. Hors
admin, on est en autocommit : l'user est committé immédiatement, pas de souci. **Mais l'admin Django
enveloppe ses vues `changeform` dans `transaction.atomic()`** : quand une adhésion (`MembershipForm.save`)
ou une réservation (form admin) est créée pour un **nouvel** email, l'user est créé dans la transaction
admin et le `.delay()` part avant le COMMIT. L'utilisateur **n'est pas supprimé** : il était simplement
pas encore committé au moment où la tâche tournait (il existe après le COMMIT).

**Correctif / Fix :** dispatch différé via `transaction.on_commit(...)`. Hors transaction, le callback
s'exécute immédiatement (comportement public inchangé) ; dans une transaction, il s'exécute après le
COMMIT (l'user est alors visible par le worker). Bonus : si la transaction admin rollback, aucun mail
orphelin n'est envoyé. Comportement prouvé en dev (autre connexion : `DoesNotExist` pendant la tx →
`TROUVE` après COMMIT).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/utils.py` | Import `transaction` ; `connexion_celery_mailer.delay(...)` enveloppé dans `transaction.on_commit(...)` dans `sender_mail_connect()` |

### Migration
- **Migration nécessaire / Migration required :** Non / No

## Recensement Tiers-Lieux + restructuration des étapes dans l'onboarding / Tiers-Lieux directory + step restructuring in onboarding

**Date :** 2026-06-05
**Migration :** Oui (`MetaBillet 0017` : ajout du choix `venue` sur `WaitingConfiguration.current_step` — pas de SQL, juste l'état Django)

**Quoi / What :** le wizard de création d'espace (`/onboard/`) passe de **6 à 7 étapes** et
intègre le **recensement national Tiers-Lieux** :

1. **Identité allégée** : on retire le **nom du lieu** et le **choix du domaine** de la 1ʳᵉ page
   (qui ne demande plus que prénom, nom, email, CGU). Le brouillon est créé avec un nom vide.
2. **Nouvelle étape « Votre lieu »** (après la vérification email) : recherche du lieu dans le
   recensement Tiers-Lieux (débounce + spinner) → « Utiliser ce lieu » pré-remplit le **nom** et
   garde l'**adresse** pour l'étape suivante. Sinon saisie manuelle du nom. Le **domaine** se
   choisit ici : **slug éditable pré-rempli depuis le nom** (live) + suffixe **.coop / .re** +
   aperçu.
3. **Étape « Adresse » optionnelle** (ex-« Votre lieu ») : carte pré-remplie depuis la fiche
   Tiers-Lieux, avec un bouton **« Je ne renseigne pas d'adresse »** qui passe l'étape.

Le check d'unicité du nom (« déjà pris ») est déplacé de l'identité vers l'étape « Votre lieu ».

**Pré-remplissage carte par GPS direct (au lieu du géocodage Nominatim) :** quand une fiche
Tiers-Lieux a des coordonnées, on passe au widget carte la **géoloc** + l'**adresse structurée**
(rue / CP / ville) de l'API. Le widget **pose le marqueur** et **remplit les champs directement**,
sans repasser par Nominatim — qui échouait sur les libellés complexes (ex :
« MIETE (Maison des Initiatives…) 150 Rue du 4 Août 1789 69100 Villeurbanne »). La recherche
Nominatim reste le **repli** pour les fiches sans GPS et la saisie manuelle. La même logique est
appliquée au **wizard de création d'évènement** (`/event/wizard/`) et au widget réutilisable
`widgets/widget_carte_adresse` (nouvelles `data-rue/cp/ville-initiale`).

**Robustesse du pré-remplissage (2 correctifs) :**
- **Clés du `prefill` toujours présentes** : en saisie manuelle, le `prefill` est vide ; or
  `valeur|default:prefill.latitude` dans un template Django lève `VariableDoesNotExist` si la clé
  manque (la résolution d'un *argument* de filtre ne tolère pas une clé absente). Les vues passent
  désormais un dict aux clés garanties (vides → le widget bascule sur Nominatim avec le nom du lieu).
- **Pas de GPS résiduel** : si on choisit une fiche puis qu'on revient en arrière pour saisir le
  lieu à la main, on oublie la fiche (purge des clés `tierslieux_*` côté serveur pour l'event wizard,
  reset des hidden `tl_*` côté JS pour l'onboard), sinon le marqueur se posait sur l'ancien lieu.

Deux **tests de non-régression** couvrent ce cas : `GET /event/wizard/map/` et `GET /onboard/place/`
en saisie manuelle (sans fiche en session) doivent rendre 200 (avant : `VariableDoesNotExist`).

**Source des données :** les résultats du recensement national affichent désormais leur source —
*Grand recensement des tiers-lieux 2026*, en open data sur
[comite-data.tiers-lieux.fr](https://comite-data.tiers-lieux.fr/) (event wizard + onboard).

**Création d'instance sans adresse :** confirmée — l'étape « Adresse » de l'onboard est optionnelle
(bouton « Je ne renseigne pas d'adresse ») et `TenantCreateValidator.create_tenant` n'utilise aucun
champ adresse (tous nullable sur `WaitingConfiguration`). Une instance se crée sans adresse.

### Revue de sécurité / robustesse (event wizard + onboard, mêmes correctifs)

- **Bug coordonnées localisées (corrigé) :** avec `USE_L10N` + locale FR, Django rendait les floats
  GPS avec une **virgule** (`44,05`), ce qui cassait `float()` côté serveur et `parseFloat` côté JS
  → marqueur mal placé / pré-remplissage perdu. Fix : `|unlocalize` sur toutes les coordonnées des
  templates (`_tierslieux_resultats.html`, `venue_tierslieux.html`, widget `widget_carte_adresse`) +
  `valider_coordonnees()` tolère la virgule. Vérifié sur les deux flux.
- **Validation des entrées :** nouvelle fonction `valider_coordonnees()` (float + bornes terrestres,
  rejette texte/None) appelée par `use_tierslieux` (event) et `venue` (onboard) ; terme de recherche
  borné (`LONGUEUR_MAX_TERME`) ; nom/adresse tronqués avant mise en session (anti-pollution).
- **Remontée Sentry :** la normalisation des fiches API est protégée (skip des entrées non-dict) et
  journalise en `logger.error` toute anomalie de traitement (→ issue Sentry) sans casser le wizard ;
  un simple échec réseau de l'API reste en `logger.warning` (transitoire, pas de bruit Sentry).
- **XSS :** aucune faille — Django auto-échappe texte et attributs, les écritures JS passent par
  `.value` (jamais `innerHTML`), HTMX injecte du HTML rendu serveur (aucun `|safe`), clé de cache md5.
- Tests ajoutés : `valider_coordonnees` (virgule/garbage/bornes), POST coordonnées invalides ignorées.

### Revue de design / accessibilité (event wizard + onboard)

- **Cohérence couleur d'accent :** le toggle « Utiliser une adresse existante / Créer un nouveau
  lieu » passait de bleu (`btn-outline-primary`) à vert (`btn-outline-success`), cohérent avec les
  boutons d'action « Utiliser ce lieu ». Override **local** uniquement (pas de modif du thème global).
- **Responsive des fiches de résultats :** sur mobile (`<576px`) le nom du lieu et le bouton
  « Utiliser ce lieu » s'empilent (`flex-column flex-sm-row`) au lieu de se serrer
  (`_tierslieux_resultats.html` + `venue_tierslieux.html`).
- **Switch CGU trop petit (bug CSS corrigé) :** le style qui agrandissait le switch
  (`.onboard-cgu-switch .form-check-input`, 2.75em) était **mort** — `wizard.css` est chargé AVANT
  `bootstrap.css`, et à spécificité égale (0,2,0) Bootstrap gagnait, ramenant le switch à 2em (32px).
  Préfixe `.onboard-wizard` ajouté → spécificité 0,3,0 → le switch retrouve sa taille (44×24px),
  sans `!important` ni changement d'ordre de chargement.
- **Accessibilité vérifiée :** police *luciole*, contraste texte 15:1 / bouton vert 5:1 / bleu 4.5:1
  (≥ WCAG AA), touch targets ≥ 44px, viewport zoomable, body 16px.
- **Note (non corrigé) :** le bloc CSS `.onboard-dns-radio*` de `wizard.css` est **mort** (le template
  utilise `btn-outline-success`) — à supprimer ou rebrancher selon le look voulu pour les pills DNS.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `MetaBillet/models.py` | `STEP_VENUE` + libellé `STEP_PLACE` → « Address » |
| `onboard/serializers.py` | identity sans name/dns ; nouveau `OnboardVenueSerializer` (name + slug + dns + check unicité) |
| `onboard/views.py` | vues `venue`/`venue_search`, routage OTP→venue, place optionnelle + pré-remplissage |
| `onboard/urls.py` | routes `onboard-venue` / `onboard-venue-search` |
| `onboard/templatetags/onboard_steps.py` | `STEP_ORDER` + `venue` |
| `…/steps/01_identity.html` | retrait nom + domaine, compteur 1/7 |
| `…/steps/03_venue.html` (nouveau) + `partials/venue_tierslieux.html` (nouveau) | étape recherche + slug DNS |
| `…/steps/03_place.html` | « Adresse » 4/7, optionnelle, pré-remplie, bouton « passer » |
| `…/partials/progress_panel.html` + compteurs steps | flux 7 étapes |
| `templates/widgets/widget_carte_adresse.html` + `static/widgets/widget_carte_adresse.js` | `data-rue/cp/ville-initiale` : marqueur + champs remplis directement depuis le GPS de l'API (sans Nominatim) |
| `BaseBillet/views.py` (`use_tierslieux`, `_wizard_etape_carte_lieu`) | wizard event : stocke GPS + adresse de la fiche en session, les passe au widget |
| `…/wizard/_tierslieux_resultats.html` + `_form_carte.html` | hidden `latitude`/`longitude` + pré-remplissage GPS du widget |
| `…/steps/03_venue.html` + `partials/venue_tierslieux.html` | hidden `tl_lat/tl_lng/tl_street/tl_cp/tl_ville`, masquage de la recherche après choix |
| `onboard/tests/*` | tests adaptés (OTP→venue, check nom→serializer venue, prefill GPS en session) |
| `…/wizard/_form_lieu.html` | toggle existant/nouveau : bleu → vert (`btn-outline-success`) |
| `…/wizard/_tierslieux_resultats.html` + `partials/venue_tierslieux.html` | fiches `flex-column flex-sm-row` (responsive mobile) |
| `static/onboard/wizard.css` | fix spécificité switch CGU (préfixe `.onboard-wizard`) → taille restaurée 44×24px |

### Migration
- **Migration nécessaire :** Oui — `MetaBillet/migrations/0017_*` (à générer via `makemigrations`).
  Pas d'opération SQL (changement de `choices`), la DB tourne déjà avec la nouvelle valeur.

### i18n
- Nombreux nouveaux `{% translate %}` (étape venue, libellés) → `makemessages` (texte source FR).

---

## Intégration du recensement Tiers-Lieux dans le wizard d'évènement / Tiers-Lieux directory integration in the event wizard

**Date :** 2026-06-05
**Migration :** Non

**Quoi / What :** à l'étape 1 du wizard de proposition d'évènement (visiteur anonyme), on
enrichit la saisie du lieu avec l'**API publique du recensement national Tiers-Lieux**
(https://api.tiers-lieux.fr/) et la détection d'instance :
1. **Détection d'instance** : si l'email saisi correspond à un compte qui administre déjà une
   instance TiBillet (`User.client_admin`), un encart **non-bloquant** invite le proposeur à
   créer son évènement chez lui + à ajouter le(s) tag(s) que ce tenant fédère + à proposer son
   espace à la fédération.
2. **Recherche nationale unifiée** : à chaque recherche (≥ 3 car., débounce), le recensement
   Tiers-Lieux est interrogé et **affiché sous les adresses locales**, avec un texte « Vous ne
   trouvez pas votre lieu ci-dessus ? Élargissez au recensement national ». Un **spinner**
   remplace la loupe de l'input pendant l'appel. Une fiche trouvée pré-remplit le nouveau lieu
   et passe à l'étape carte (géocodage de l'adresse complète) pour **validation**. Le message
   « aucun lieu trouvé + créer » ne s'affiche que si la liste locale est aussi vide (sinon
   réponse vide, pas de bruit).
3. **UX étape 1 fiabilisée** : plus de **pré-cochage automatique** de l'adresse principale
   (corrige un bug : « Continuer » partait avec une sélection fantôme). Le bouton **Continuer
   est grisé** tant qu'aucun choix réel n'est fait (adresse cochée *et visible*, ou nom de
   nouveau lieu saisi), avec un indice explicite. Si rien n'est trouvé (local + national), un
   **CTA « Créer « terme » comme nouveau lieu »** bascule en mode nouveau lieu avec le nom
   pré-rempli. ⚠️ Le pré-cochage retiré concerne aussi le wizard staff (le formulaire est
   unifié) : l'adresse doit désormais être choisie explicitement.

**Comment / How :**
- Service isolé `BaseBillet/services/tiers_lieux.py` : `rechercher_tiers_lieux(terme)` avec
  **timeout 4 s + try/except → []** (le wizard ne casse jamais si l'API est lente/down) et cache
  mémoire 1 h. L'API ne sait PAS chercher par email (testé) → la clé de recherche est le **nom/
  ville/CP**, l'email ne sert qu'à la détection d'instance.
- 3 `@action` sur `EventWizard` : `check-instance` (GET, HTMX au blur de l'email),
  `search-tierslieux` (GET, HTMX débounce), `use-tierslieux` (POST → session → étape carte).
- Le filtre JS local existant pilote le déclenchement de la recherche nationale (HTMX) uniquement
  si 0 adresse locale et terme ≥ 3 caractères.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services/tiers_lieux.py` (+`__init__.py`) | Client API : recherche + normalisation + timeout + cache |
| `BaseBillet/views.py` | 3 `@action` (`check-instance`, `search-tierslieux`, `use-tierslieux`) + pré-remplissage `_wizard_etape_carte_lieu` |
| `…/wizard/_form_lieu.html` | conteneurs `#wizard-instance-result` / `#wizard-tierslieux-result` + câblage HTMX + JS débounce |
| `…/wizard/_form_carte.html` | `adresse_initiale=adresse_recherche` (géocodage de l'adresse complète) |
| `…/wizard/_instance_trouvee.html`, `…/wizard/_tierslieux_resultats.html` | nouveaux partials |
| `tests/pytest/test_tiers_lieux.py` | 11 tests (service mocké + endpoints) |

### Sécurité
- ⚠️ `check-instance` permet à un anonyme de tester un email et savoir s'il administre une
  instance (+ son nom) → **énumération email→instance**. Risque limité (emails de contact souvent
  publics), **accepté pour le MVP**. Rate-limit par IP possible en évolution.
- API externe : timeout court + dégradation gracieuse (jamais d'exception vers le wizard).

### i18n
- Nouveaux `{% translate %}` / `{% blocktranslate %}` (encarts) → `makemessages` (texte source FR).

---

## Jauge ouverte aux proposeurs dans le wizard d'évènement / Gauge available to proposers in the event wizard

**Date :** 2026-06-05
**Migration :** Non

**Quoi / What :** dans le wizard de proposition d'évènement (agenda participatif), le champ
**« Jauge max »** était réservé au staff. Il est désormais proposé à **tout le monde** (anonyme,
membre connecté, staff). Une proposition non-staff qui renseigne une jauge la voit **appliquée à
l'identique du staff** : `jauge_max` + `show_gauge=True` + produit **FREERES** (billetterie de
réservation gratuite). L'évènement **reste une proposition modérée** (`is_proposal=True`) jusqu'à
validation admin. Sans jauge saisie : défaut du modèle (`50`) intact, `show_gauge=False`, aucune
billetterie greffée. La logique des **tags** (staff = création libre ; public = sélection parmi
l'existant) est **inchangée**.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/reunion/views/event/wizard/_events_inner.html` | Champ jauge + badge jauge affichés pour tous ; layout tags en `col-md-6` ; logique tags inchangée (`show_admin_fields`) |
| `BaseBillet/views.py` | `_creer_event_depuis_brouillon` : jauge appliquée pour tous (plus de `if est_staff else None`) |
| `BaseBillet/validators.py` | Docstring `WizardEventSerializer` mis à jour (jauge commune à tous) |
| `tests/pytest/test_event_wizard_unifie.py` | +1 test de non-régression (jauge non-staff appliquée + cas sans jauge) |

### i18n
- Aucune nouvelle chaîne (`« Jauge max (optionnel) »` / `« Jauge »` existaient déjà). Pas de `makemessages`.

---

## Fédération automatique des évènements par tags (agenda + carto, en cache)

**Date :** 2026-06-03
**Migration :** Oui (`BaseBillet 0218` : M2M `FederationConfiguration.tags_federation`)

**Quoi / What :** un tenant peut s'abonner à des **tags** (`FederationConfiguration.tags_federation`,
M2M) : les évènements de **tout le réseau TiBillet** portant un de ces tags apparaissent dans son
**agenda** (`/event/`) ET sur sa **carte** (`/federation/`), **en plus** de sa fédération habituelle
(voisins `FederatedPlace`). Liste vide = comportement inchangé.

**Comment / How :**
- Identification « qui dans le réseau porte ce tag » **100% cache** : nouveau helper
  `seo.services.get_tenant_uuids_with_event_tags(slugs)` lit `AGGREGATE_EVENTS` (zéro requête
  cross-schema), match par **slug**, **veto `private` respecté**.
- **Agenda** : `federated_events_filter` ajoute les tenants thématiques à sa boucle existante
  (rendu en objets `Event`, `private=False` appliqué d'office aux non-voisins).
- **Carto** : `FederationViewset.list` ajoute ces tenants à `all_uuids`.
- **Cache enrichi** : `get_events_for_tenants` expose désormais `private` ; `build_aggregate_points`
  exclut les events `private` des popups → **carto nettoyée partout** (corrige un trou existant où
  des events privés pouvaient apparaître sur la carte réseau).
- Changer `tags_federation` régénère le token du cache agenda (`FederationConfiguration.save()`) → effet immédiat.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `FederationConfiguration.tags_federation` (M2M) + `save()` invalide le cache agenda |
| `BaseBillet/migrations/0218_*` | AddField M2M |
| `seo/services.py` | `get_events_for_tenants` → `private` ; `build_aggregate_points` exclut `private` ; helper `get_tenant_uuids_with_event_tags` |
| `BaseBillet/views.py` | agenda (`federated_events_filter`) + carto (`FederationViewset.list`) étendus au réseau via cache |
| `Administration/admin_tenant.py` | fieldset « Fédération automatique par tags » + autocomplete |
| `tests/pytest/test_federation_auto_tags.py` | 4 tests helper (slug + veto private) |
| `tests/pytest/test_federation_view_integration.py` | mock `_fake_config` complété (`tags_federation`) |

### Migration
- **Migration nécessaire / Migration required :** Oui — `BaseBillet/migrations/0218_*`
- Commande : `migrate_schemas --executor=multiprocessing`

### Déploiement / Deployment
- ⚠️ Après déploiement : **redémarrer le worker Celery** puis **relancer `refresh_seo_cache`**. Le
  champ `private` n'entre dans le cache que si la task tourne avec le nouveau code. Tant que le cache
  ne porte pas `private`, le filtrage formel du veto n'est pas actif (pas de fuite tant qu'aucun event
  privé n'existe, mais à régénérer pour être correct).

### i18n
- Nouveaux `_()` (verbose_name/help_text de `tags_federation`, fieldset admin) → `makemessages` (texte source FR).

---

## Redirection des anciens liens de la doc Docusaurus v2 → doc v3 / Redirect old Docusaurus v2 docs links to v3

**Date :** 2026-06-02
**Migration :** Non

**Quoi / What :** l'ancienne documentation (Docusaurus v2) était servie sur `tibillet.org`
avec des chemins `/docs/…`, `/fr/…`, `/en/…`, `/roadmap/`, `/search/`, `/cgucgv/`. Ces chemins
n'existent plus dans Lespass : les vieux liens (indexés, partagés) tombaient en 404.
`CanonicalDomainRedirectMiddleware` les redirige désormais (302) vers la nouvelle doc
(`documentation_v3` sur `tibillet.github.io`).

**Pourquoi / Why :** le middleware canonique ne faisait que `tibillet.org → tibillet.coop` en
gardant le chemin → le 404 était simplement déplacé sur `.coop`, jamais corrigé. On rattrape
maintenant les anciens chemins de doc avant la redirection canonique.

**Comportement / Behavior :**
- Page de démonstration (`/docs/presentation/demonstration/` et variante `/fr/…`) → page démo
  précise de la doc v3.
- CGU/CGV (`/cgucgv/`, `/fr/cgucgv/`) → page CGU/CGV de la doc v3.
- Tout autre `/docs/…`, `/fr/…`, `/en/…`, `/roadmap/…`, `/search/…` → racine de la doc v3.
- **ROOT uniquement** (`schema_name == "public"`) : zéro impact sur les sous-domaines tenants.
- **302 temporaire** (cohérent avec le canonical, table pas encore figée). GET/HEAD seulement.
- Pas d'`i18n_patterns` dans Lespass → `/fr` et `/en` sont des préfixes libres (aucune collision
  vérifiée avec `seo.urls`, `onboard.urls`, `BaseBillet.urls`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Customers/middleware.py` | + fonction pure `url_doc_v3_pour_chemin_herite()` + méthode `_redirection_doc_heritee()` appelée avant la redirection canonique |
| `tests/pytest/test_middleware_doc_redirect.py` | Nouveau : 26 cas (démo, CGU, préfixes hérités, routes Lespass non touchées) |

## Agenda participatif → Fédération + récolte e-mail du proposeur anonyme

**Date :** 2026-06-02
**Migration :** Oui (`BaseBillet 0217` : déplace 3 champs `Configuration` → `FederationConfiguration`)

**Quoi / What :** les réglages de l'agenda participatif quittent `Configuration` (et le
dashboard des modules) pour vivre sur **`FederationConfiguration`** (admin « Options de
fédération ») :
- `module_agenda_participatif` (activation) + `proposition_anonyme_autorisee` + `tag_auto_proposition`
  sont **déplacés** vers `FederationConfiguration`.
- La **carte « Agenda participatif » du dashboard est supprimée** ; la carte fédération est
  renommée **« Fédération et agenda participatif »** avec une description FALC.
- La migration `0217` **recopie** la valeur existante par tenant (les tenants qui avaient
  activé l'agenda le gardent activé).

**Récolte e-mail (proposeur anonyme) / Anonymous proposer email :** à l'**étape 1** du wizard,
un visiteur **non connecté** doit désormais saisir un **e-mail obligatoire**. À la finalisation,
`get_or_create_user(email, send_mail=False)` crée (ou récupère) un compte **non validé**
(`email_valid=False`, inactif) **sans déclencher l'OTP** ; l'évènement est lié à ce compte
(`created_by`) et reste une **proposition modérée**. Si l'e-mail correspond à un compte déjà en
erreur (`email_error`), la proposition est **refusée** avec un message.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | 3 champs déplacés `Configuration` → `FederationConfiguration` |
| `BaseBillet/migrations/0217_*` | AddField ×3 → recopie par tenant (guard `public`) → RemoveField ×3 |
| `Administration/admin_tenant.py` | fieldset « Agenda participatif » : `ConfigurationAdmin` → `FederationConfigurationAdmin` |
| `Administration/admin/dashboard.py` | carte agenda supprimée ; carte fédération renommée + description FALC |
| `BaseBillet/views.py` | `_garde_acces`, `_creer_event_depuis_brouillon`, `EventMVT.list` → `FederationConfiguration` ; étape 1 + finalisation : récolte e-mail + `get_or_create_user(send_mail=False)` |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` : champ `email_proposeur` (obligatoire si anonyme) |
| `.../event/wizard/_form_lieu.html` | champ e-mail conditionnel (visiteur anonyme) |
| `.../event/list.html` | bouton « Proposer » lit `federation_config.*` |
| `tests/pytest/test_event_wizard_unifie.py` | 2 tests adaptés + 2 nouveaux (récolte e-mail) |

### Migration
- **Migration nécessaire / Migration required :** Oui — `BaseBillet/migrations/0217_*`
- Commande : `migrate_schemas --executor=multiprocessing`

### i18n
- Nouveaux textes `_()` (label/aide du champ e-mail, messages, libellé + description de la carte
  dashboard fédération) — à extraire via `makemessages` (texte source FR).

---

## Formulaire event unifié (front) + fix image + options config / Unified front event wizard

**Date :** 2026-06-01
**Migration :** Oui (`BaseBillet 0216` : 2 champs `Configuration`)

**Quoi / What :** un **seul** formulaire/wizard event sur le front (`EventWizard`) remplace les
deux boutons « Ajouter » (staff) et « Proposer » (public) de `/event`. Le formulaire s'adapte
au contexte :
- **Staff** (droits de création) → event **publié**, champs `jauge_max` + `tags`.
- **Public** (connecté ou anonyme autorisé) → **proposition modérée** (`is_proposal=True`) +
  **tag automatique** ; tags limités aux **tags existants** (anti-spam).
- Champs communs : nom, date, description, image, **tags**. `jauge_max` reste staff-only.

Corrige aussi le **bug image** (#1) : l'image uploadée n'apparaissait pas dans `/event` car le
fichier temp n'était jamais migré (`event.img.name = draft["image"]`) → désormais recopié dans
`images/` via `event.img.save(...)` puis temp supprimé.

Ajoute le **flux « Envoyer »** (#4) : si un évènement est en cours de saisie (sous-form non
ajouté), une popup SweetAlert propose « Ajouter d'abord / Envoyer sans / Annuler » — rien n'est
perdu sans confirmation.

**Config (« déplacer dans la config ») :** `proposition_anonyme_autorisee` (Bool, défaut False)
+ `tag_auto_proposition` (FK Tag), dans le fieldset « Agenda participatif ». L'admin Django
**n'est pas touché**.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Configuration` : `proposition_anonyme_autorisee` + `tag_auto_proposition` |
| `Administration/admin_tenant.py` | fieldset « Agenda participatif » |
| `BaseBillet/views.py` | `EventWizard` (unifié) + helpers `_attacher_image_brouillon`, `_creer_event_depuis_brouillon` |
| `BaseBillet/validators.py` | `WizardEventSerializer` (unifié) |
| `BaseBillet/urls.py` | route `event-wizard-*` (remplace `event-propose`/`event-admin-wizard`) |
| `.../event/list.html` | bouton unique vers le wizard |
| `.../event/wizard/step2_event.html` (+ `_events_inner.html`) | template unifié + tags datalist + JS flux #4 |
| `tests/pytest/test_event_wizard_unifie.py` | 6 tests (image, rôle, tag auto, tags public, garde accès) |

### Migration
- **Migration nécessaire / Migration required :** Oui (`BaseBillet/migrations/0216_*`)

### Nettoyage effectué / Cleanup done
Code mort de l'ancien flux **supprimé** : classes `EventWizardAdmin` + `EventWizardPublic`
(`views.py`, 599 lignes), helpers `_creer_event_admin_depuis_brouillon` /
`_creer_event_public_depuis_brouillon`, serializers `WizardEventAdminSerializer` /
`WizardEventPublicSerializer` / `EventProposalEmailSerializer`, et templates
`admin_step*.html`, `public_step0_*.html`, `public_step2_event.html`. Tests obsolètes
(`test_event_wizard_admin.py`, `test_event_wizard_public.py`) supprimés (flux remplacé,
couvert par `test_event_wizard_unifie.py`). Audit conformité djc : OK.

## Cache SEO — fragments par tenant + agrégats par recombinaison / Per-tenant SEO cache fragments

**Date :** 2026-06-01
**Migration :** Oui (`seo 0004`, `alter cache_type`, no-op DB) · **Régénération cache :** au prochain beat ou `refresh_seo_cache()`

**Quoi / What :** refonte de `seo/tasks.py` pour la scalabilité (≈ 500 tenants). Le cache SEO
est désormais produit par **fragments par tenant** puis **recombiné** en agrégats :
- `refresh_tenant_seo_cache(tenant_id)` — recalcule les fragments d'**un** tenant
  (`TENANT_SUMMARY`, `TENANT_EVENTS`, nouveau `TENANT_POINTS`). 1 schema.
- `rebuild_seo_aggregates()` — recompose `AGGREGATE_EVENTS/LIEUX/POINTS` + `SITEMAP_INDEX`
  par lecture des fragments + concat (**zéro cross-schema**).
- `refresh_seo_cache()` — orchestrateur du beat 4 h (tous fragments + rebuild +
  `FEDERATION_INCOMING` cross-schema + nettoyage stale).

**Pourquoi / Why :** l'ancien recalcul intégral faisait un `UNION ALL` sur tous les schemas à
chaque exécution — ingérable à 500 tenants, et impossible à déclencher sur chaque modif.

**Comment / How :** le signal `post_save`/`post_delete` Event/PostalAddress déclenche
**uniquement** `refresh_tenant_seo_cache` du tenant courant (1 schema, débounce **par tenant**
60 s) + `rebuild_seo_aggregates` (débounce **global** 180 s qui **borne la charge**
indépendamment du volume de modifs). Jamais de recalcul des schemas des autres tenants. Les
vues consommatrices sont **inchangées** (mêmes `AGGREGATE_*`). Équivalence vérifiée : agrégats
identiques à l'ancienne version (20 events / 5 lieux / 4 points, 0 collision `pa_id`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | + `cache_type` `TENANT_POINTS` (migration `0004`) |
| `seo/services.py` | + `get_counts_for_tenant(schema_name)` (counts 1-tenant) |
| `seo/tasks.py` | refonte : `refresh_tenant_seo_cache`, `rebuild_seo_aggregates`, `refresh_seo_cache` orchestrateur |
| `BaseBillet/signals.py` | signal → refresh **ciblé tenant** + rebuild débouncés (remplace le refresh complet) |
| `tests/pytest/test_seo_cache_fragments.py` | 4 tests (fragments, recombinaison, unicité pa_id, incoming au beat) |
| `tests/pytest/test_seo_aggregate_points.py` | maj test `is_main_address` (pa_id préfixé) |

### Migration
- **Migration nécessaire / Migration required :** Oui (`seo/migrations/0004_alter_seocache_cache_type.py`, no-op DB)
- `manage.py migrate_schemas --executor=multiprocessing`

## Carto (explorer) — 3 correctifs + rafraîchissement auto du cache / Map explorer fixes + auto cache refresh

**Date :** 2026-06-01
**Migration :** Non · **Régénération du cache requise :** Oui (`refresh_seo_cache`)

**Quoi / What :**
- **Bug adresse décalée** : `pa_id` (clé des markers côté JS) valait `PostalAddress.pk`,
  non unique entre tenants (PK par schema) → collision, mauvaise adresse au clic. Désormais
  préfixé par le tenant (`{tenant_uuid}:{pk}`) en sortie de `build_aggregate_points`.
- **Carte non rafraîchie au clic d'un event** : les cartes event n'avaient pas de
  `data-pa-id` et `bindListDelegation` ne réagissait qu'aux cartes lieu. Ajout de
  `data-pa-id` + nouvelle fonction `focusOnPA(paId, tenantId)`.
- **Images absentes** : les events affichaient toujours une emoji ; le cache ne portait
  pas l'`image_url` des events ni l'image des lieux. Ajout de `image_url` (events) et
  `image_url`/`tenant_image_url` (lieux, via la social card) dans le cache, et affichage
  côté JS (cartes lieu/event, accordéon) avec fallback logo → image → emoji.
- **Rafraîchissement auto** : signal `post_save`/`post_delete` sur `Event` et
  `PostalAddress` → `refresh_seo_cache` (Celery, **débouncé** : 1 refresh / 70 s, différé
  60 s pour grouper les modifs).
- **Audit (bonus)** : `highlightPin`/`highlightPinClass` ciblaient `data-lieu-id` au lieu de
  `data-tenant-id` (surbrillance des pins inopérante) — corrigé (+ multi-adresses) ;
  `scrollToCard` ne gérait que le mode « lieu » — fallback carte event ajouté ; popup
  alignée sur le fallback logo→image.

**Pourquoi / Why :** corriger l'UX de la carto (explorer ROOT + /federation/) et garder le
cache à jour sans attendre le beat 4 h.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `pa_id` unique cross-tenant ; `image_url` events ; `tenant_image_url` lieux (points) |
| `seo/tasks.py` | `image_url` des lieux dans `AGGREGATE_LIEUX` |
| `seo/static/seo/explorer.js` | `focusOnPA` + clic event ; affichage images (cartes lieu/event, accordéon) |
| `BaseBillet/signals.py` | Signal débouncé Event/PostalAddress → `refresh_seo_cache` |

### Migration
- **Migration nécessaire / Migration required :** Non
- **Action requise :** régénérer le cache : `manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"`

## Fédération — options d'affichage par tenant / Federation display options per tenant

**Date :** 2026-06-01
**Migration :** Oui (`BaseBillet 0215`, auto, tous schemas tenant)

**Quoi / What :** nouveau singleton **`FederationConfiguration`** (par tenant) pilotant
l'affichage de la page Réseau local (`/federation/`) : filtre « event à venir seulement »,
toggle des lieux entrants (qui me fédèrent), texte d'introduction WYSIWYG, et tri des lieux
(alphabétique / par prochain événement). Visible dans l'admin section **Fédération**,
au-dessus de « Espaces » et « Assets ».
/ New per-tenant `FederationConfiguration` singleton driving the Local network page display.

**Pourquoi / Why :** rendre configurables des comportements jusque-là figés dans le code
(bidirectionnalité forcée, lieux sans event toujours affichés), au niveau de chaque lieu.

**Comment / How :** tout s'applique à la **consommation** (`FederationViewset.list`), via la
fonction pure `seo.services.appliquer_options_federation`. **Aucune** modification du cache SEO
(`refresh_seo_cache`), du `/explorer/` public ROOT, **ni du JS**. L'option « lieux sans adresse »
est gérée côté serveur (injection d'un point sans coordonnées, listé mais sans marqueur — le JS
ignore déjà les marqueurs sans coords). Tout est testable en pytch.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Modèle `FederationConfiguration(SingletonModel)` (5 champs) |
| `seo/services.py` | Fonction pure `appliquer_options_federation()` (filtre, tri, points sans coords) |
| `Administration/admin_tenant.py` | `FederationConfigurationAdmin` (WYSIWYG + sanitize + permissions) |
| `Administration/admin/dashboard.py` | Item sidebar « Options » en tête de la section Fédération |
| `BaseBillet/views.py` | `FederationViewset.list` : lecture config + filtre/tri/entrants/sans-adresse/intro |
| `BaseBillet/templates/reunion/views/federation/explorer.html` | Affichage du `texte_introduction` |
| `Administration/management/commands/demo_data_v2.py` | Fixtures : 3 scénarios fédération additifs (reseed `--flush` requis) |
| `tests/pytest/test_federation_config.py` | 7 tests DB-only (fonction pure) |
| `tests/pytest/test_federation_view_integration.py` | 4 tests d'intégration de la vue |

### Migration
- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/migrations/0215_federationconfiguration.py`
- `manage.py migrate_schemas --executor=multiprocessing`

## Sentry — tracing désactivé (budget spans saturé) / Sentry tracing disabled

**Date :** 2026-05-25
**Migration :** Non · **Déploiement requis :** Oui (redémarrage prod)

**Quoi / What :** `sentry_sdk.init` (settings) : `traces_sample_rate` et
`profiles_sample_rate` passés de **0.3 → 0.0**. Le tracing/performance monitoring
(spans) est coupé ; les **events d'erreur (issues) restent captés normalement**.
/ Tracing/profiling sampling 0.3 → 0.0. Spans off, error events unaffected.

**Pourquoi / Why :** le volume festival (4000 users + tâches Celery) avec 30 % de
transactions tracées a **saturé le budget de spans** Sentry (100 % consommé → spans
droppés). On coupe le tracing pour ne plus exploser le budget. Remonter prudemment
(0.01–0.05) plus tard si besoin de perf.

**Note :** ne restaure pas l'ingestion de la **période en cours** (déjà consommée) —
ça nécessite un ajustement budget côté Sentry ou le reset de période. Prend effet
**au déploiement** (l'init ne tourne qu'en prod : `not DEBUG and SENTRY_DNS`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `sentry_sdk.init` : `traces_sample_rate=0.0`, `profiles_sample_rate=0.0` |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v1 — validation réservation loggée en `warning` (anti-bruit Sentry) / Reservation validation logged at warning

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :** `ApiReservationViewset.create` (v1) loggeait les **échecs de validation
(400 client)** en `logger.error` → events Sentry. Passé en **`logger.warning`** : la
`LoggingIntegration` Sentry (défaut `event_level=ERROR`, aucune surcharge dans
`settings.py`) ne crée **plus d'event** pour ces 400 (juste un breadcrumb). Le 400 + le
corps d'erreur informent déjà l'appelant.
/ v1 reservation `create` logged client 400 validation failures at `error` (Sentry events).
Now `warning` → no Sentry event (default `event_level=ERROR`).

**Pourquoi / Why :** une validation 400 côté client (payload incomplet) n'est pas une
erreur applicative ; elle ne doit pas solliciter Sentry.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `ApiReservationViewset.create` : `logger.error` → `logger.warning` sur `validator.errors` |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v1 (ApiBillet) — en-têtes de dépréciation vers /api/v2/ / API v1 deprecation headers

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- Les réponses des endpoints **consommateur** de l'API v1 (`ApiBillet`) portent
  désormais des en-têtes HTTP **non bloquants** orientant vers v2 :
  `Deprecation: true`, `Link: </api/v2/>; rel="successor-version"`,
  `Warning: 299 - "TiBillet API v1 is deprecated, migrate to /api/v2/"`.
- Mécanisme : mixin **`DeprecatedV1Mixin`** (override `finalize_response`) placé en
  **première base** des viewsets/APIViews consommateur. Marche pour `ViewSet` **et**
  `APIView` (les deux héritent `finalize_response` de DRF — vérifié).
- 12 classes concernées : `ApiReservationViewset`, `EventsViewSet`, `EventsSlugViewSet`,
  `ProductViewSet`, `TarifBilletViewSet`, `TicketViewset`, `Wallet`, `OptionTicket`,
  `HereViewSet`, `Gauge`, `TicketPdf`, `CancelSubscription`.
- **Exclus** (plomberie, pas de successeur v2) : `Webhook_stripe`, `Onboard_laboutik`,
  `Onboard_stripe_return`, `Get_user_pub_pem`.
- **Pas de `Sunset`** (aucune date de retrait décidée — à ajouter dans
  `API_V1_DEPRECATION_HEADERS` le jour venu).

**Pourquoi / Why :** orienter les intégrateurs (ex. client « codex-api » repéré sur le
tenant `raffinerie`) vers l'API v2 sémantique, sans casser les clients v1 existants.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | + `API_V1_DEPRECATION_HEADERS` + `DeprecatedV1Mixin` ; mixin ajouté en 1ʳᵉ base de 12 classes consommateur |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v2 — Fix `retrieve` Product (lookup_field manquant) / Fix Product retrieve (missing lookup_field)

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- `GET /api/v2/products/{uuid}/` levait `TypeError: retrieve() got an unexpected
  keyword argument 'pk'` (**HTTP 500**), même avec un uuid valide. `ProductViewSet`
  n'avait pas `lookup_field = "uuid"` : le routeur DRF passait `pk`, alors que
  `retrieve(self, request, uuid=None)` attend `uuid`. L'endpoint détail Product
  n'avait donc jamais fonctionné.
- Ajout de `lookup_field = "uuid"` sur `ProductViewSet` (cohérent avec
  Event/Reservation/Membership/Initiative ; aligne le code sur l'OpenAPI qui
  documente déjà `/products/{uuid}/`).

**Pourquoi / Why :** Issue Sentry 7368726717 (crawler appelant l'endpoint détail
Product avec un uuid valide).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `ProductViewSet` : + `lookup_field = "uuid"` |
| `tests/pytest/test_product_retrieve.py` | Nouveau test DB-only : retrieve par uuid → 200, uuid inconnu → 404 |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v2 — `GET /events/{id}/` accepte uuid OU slug front (+ 404 propre) / Event retrieve by uuid OR front slug

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- **Résolution par slug.** `GET /api/v2/events/{id}/` accepte désormais, en plus
  de l'uuid, le **slug** utilisé par le contrôleur front (ex :
  `mon-evenement-260620-0900-7d51dee7`). Logique miroir d'`EventMVT.retrieve` :
  les 8 derniers caractères hex du slug = début de l'uuid → `uuid__startswith`,
  puis fallback `slug__startswith`. Nouvelle fonction
  `get_event_par_identifiant_ou_404(identifiant)`.
- **Plus de filtre `published`** sur la résolution `retrieve` (uuid **et** slug),
  pour coller au comportement du front (`EventMVT.retrieve` ne filtre pas
  `published`). ⚠️ Conséquence : un évènement non publié devient récupérable par
  l'API v2 via son uuid/slug.
- **404 propre sur identifiant inconnu/malformé.** Avant, un slug envoyé sur
  `retrieve`/`destroy`/`link-address` faisait lever `ValidationError` à Django
  (conversion `UUIDField`) → **HTTP 500**. `destroy` et `link-address` utilisent
  un helper `get_objet_par_uuid_ou_404` (uuid-only → 404 si malformé) ; `retrieve`
  résout uuid+slug et renvoie 404 si rien ne correspond.

**Pourquoi / Why :** Issue Sentry 7504311969 — un client/crawler (clé API valide)
appelait l'API avec le **slug** du front au lieu de l'uuid → 500. On rend l'API
robuste (404, jamais 500) **et** on accepte le slug front pour que la même URL
fonctionne des deux côtés. Même classe de bug que le piège 9.76 (`detail_vente`).

**Périmètre / Scope :** Event uniquement. Les autres endpoints détail par uuid
(Product, Reservation, Membership, Initiative) gardent le même défaut latent
(500 sur slug) ; le helper `get_objet_par_uuid_ou_404` est prêt à y être appliqué.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | + `import re` ; + helpers `get_objet_par_uuid_ou_404` et `get_event_par_identifiant_ou_404` ; `retrieve` résout uuid+slug ; `destroy`/`link_address` migrés sur le helper uuid-only |
| `tests/pytest/test_event_retrieve_invalid_uuid.py` | Test DB-only : retrieve par uuid → 200, par slug → 200, slug inconnu → 404, uuid inconnu → 404 |

### Migration
- **Migration nécessaire / Migration required :** Non

### Note appelant / Caller note
Le « spider » Sentry possède une clé API valide et appelle avec un slug : il
existe probablement une intégration qui construit des URLs `/api/v2/events/<slug>/`.
Ce correctif rend l'API robuste et compatible, mais l'appelant peut être revu.

## Admin — Recherche par adhésion + renommage « Adhésion / Abonnement / Pass »

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0213_alter_membership_options` — options only, no-op DB)

**Quoi / What :**
- **Recherche users élargie** : la barre de recherche du changelist
  `HumanUserAdmin` cherche désormais aussi dans les **nom/prénom saisis sur les
  adhésions** (`memberships__first_name`, `memberships__last_name`), en plus du
  nom/prénom/email de l'user. Permet de retrouver un compte par le nom de
  l'adhérent·e (parfois différent du compte). Django ajoute `distinct()` au besoin.
- **Renommage** du modèle `Membership` : `verbose_name` / `verbose_name_plural`
  → **« Adhésion / Abonnement / Pass »** (titre de la page d'administration).
- **Sidebar** : l'item de menu vers les adhésions → **« Adhésion / Pass »**.

**Pourquoi / Why :** Accueil festival/forum/salon : retrouver vite un compte par
le nom de l'adhésion ; libellés reflétant les trois usages (adhésion ponctuelle,
abonnement récurrent, pass).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `HumanUserAdmin.search_fields` : + `memberships__first_name`, `memberships__last_name` |
| `BaseBillet/models.py` | `Membership.Meta` : `verbose_name`/`verbose_name_plural` = « Adhésion / Abonnement / Pass » |
| `BaseBillet/migrations/0213_alter_membership_options.py` | Migration d'options (no-op DB) |
| `Administration/admin/dashboard.py` | Item sidebar adhésions → « Adhésion / Pass » |

### Migration
- **Migration nécessaire / Migration required :** Oui (options only)
- `BaseBillet/0213_alter_membership_options` · `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Nouvelles chaînes (source FR) : `Adhésion / Abonnement / Pass`, `Adhésion / Pass`
(remplacent les anciens `Subscription`/`Subscriptions`). makemessages/compilemessages
par le mainteneur.

## Admin — Évènements et adhésions sur la fiche user / Admin — bookings & memberships on user profile

**Date :** 2026-05-21
**Migration :** Non

**Quoi / What :** La fiche utilisateur·ice de l'admin affiche deux encarts
riches, alimentés **en local** (ORM, tenant courant — aucun appel Fedow),
pensés pour l'accueil d'un festival / forum / salon :
- **Évènements** : toutes les réservations de l'user, séparées « À venir » /
  « Passés ». Colonnes : évènement (lien cliquable vers la réservation), date,
  nombre de billets, montant payé, moyen(s) de paiement, statut (badge couleur).
- **Adhésions** : séparées « En cours » / « Passées ». Colonnes : adhésion
  (lien cliquable), montant (contribution), moyen de paiement, échéance, statut.
- Montants alignés en chiffres tabulaires ; badges de statut en styles inline
  (couleur **+** texte, lisibles en thème clair comme sombre).
- **Performance** : `prefetch_related('tickets', 'lignearticles', 'paiements__lignearticles')`
  + helper `_lignes_payees_prefetch` (montant + moyens calculés en mémoire) →
  **nombre de requêtes SQL constant** quel que soit le nombre de réservations,
  pas de N+1. Mesuré : 6 réservations + 13 adhésions = **5 requêtes**.
- **Robustesse** : la collecte évènements/adhésions est isolée dans son propre
  `try/except` (logge + dégrade) — un cas de données limite ne peut **jamais
  faire planter (500)** la fiche utilisateur. Tri réservations en `NULLS LAST`
  (les réservations sans évènement ne remontent plus en tête).
- **Vérifié visuellement** (Chrome) : encarts remplis, liens cliquables, badges
  de statut colorés (vert/bleu/ambre/rouge), montants alignés, toggles de droits
  fonctionnels, bouton Tirelire OK, aucune erreur console.

**Correctif au passage / Fix :** `HumanUserAdmin` contenait **deux**
`changeform_view` (doublon préexistant) ; la 2ᵉ écrasait la 1ʳᵉ. Les deux sont
fusionnées en une seule méthode (états des droits + évènements + adhésions),
ce qui rend les encarts réellement alimentés.

**Pourquoi / Why :** Donner à l'accueil une vue complète et scannable de
l'activité de la personne, sans dépendre de Fedow.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | Helpers badges + `_admin_url_basebillet` (niveau module) ; fusion des deux `changeform_view` de `HumanUserAdmin` (droits + évènements + adhésions enrichis) ; import `NoReverseMatch` |
| `Administration/templates/admin/human_user/right_and_wallet_info.html` | Encarts « Évènements » et « Adhésions » : tableaux enrichis (badges, montants tabulaires, liens cliquables) |

### Migration
- **Migration nécessaire / Migration required :** Non

### i18n
Nouvelles chaînes, **texte source en français** : `Évènements`, `À venir`,
`Passés`, `Évènement`, `Date`, `Billets`, `Payé`, `Paiement`, `Statut`,
`Aucun évènement à venir`, `Aucun évènement passé`, `Adhésions`, `Adhésion`,
`En cours`, `Passées`, `Montant`, `Échéance`, `Aucune adhésion en cours`,
`Aucune adhésion passée`. Le mainteneur lance makemessages/compilemessages.

## Admin — Dernières transactions Fedow (72 h) dans la fiche user / Admin — last 72h Fedow transactions in user profile

**Date :** 2026-05-21
**Migration :** Non

**Quoi / What :** Le bloc « Tirelire » de la fiche utilisateur·ice de l'admin
affiche désormais, en plus des cartes et du solde, les **transactions des
72 dernières heures** récupérées depuis Fedow.
- Vue `admin_my_cards` enrichie : appel `FedowAPI.transaction.paginated_list_by_wallet_signature(user)`
  filtré sur 72 h. Encadré `try/except` : si Fedow est indisponible, le bloc
  cartes/tokens reste affiché (les transactions sont simplement omises).
- Nouveau bloc « Last transactions (72h) » dans `wallet_info.html` (style Unfold,
  réutilise les filtres `dround` / `get_choice_string` / `naturaltime`).
- L'historique inclut les transactions d'un éventuel **wallet éphémère fusionné**
  (actions `FUS`), car la signature de l'user retrouve tout l'historique du wallet.
- Les transactions d'**adhésion** (asset de catégorie `SUB` / SUBSCRIPTION) sont
  **exclues** du bloc, par cohérence avec l'exclusion des adhésions du solde de tokens.

**Pourquoi / Why :** Donner à l'admin une vue rapide de l'activité récente de la
tirelire d'un membre (support, surveillance des abus).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `admin_my_cards` : transactions 72 h ajoutées au contexte (try/except Fedow) |
| `Administration/templates/admin/membership/wallet_info.html` | Bloc « Last transactions (72h) » |

### Migration
- **Migration nécessaire / Migration required :** Non

### i18n
Nouvelles chaînes, **texte source en français** : `Dernières transactions (72h)`,
`Aucune transaction sur les 72 dernières heures`, `Valeur`, `Sens`.
(`Action`, `Date` identiques FR/EN.) Le mainteneur lance makemessages/compilemessages
(traduction EN générée depuis le FR).

## API v2 — Recharge de tokens non fiduciaires / API v2 — non-fiat wallet refill

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0211_externalapikey_gift_asset`,
`BaseBillet/0212_alter_externalapikey_gift_asset`)

**Quoi / What :** Nouvelle route `POST /api/v2/wallet-refills/` qui crédite des
tokens **non adossés à l'euro** sur la tirelire d'un user à partir de son email,
sans paiement — réplique en API du trigger `Price.fedow_reward_*`.
- Catégories rechargeables (`AssetFedowPublic.REFILLABLE_CATEGORIES`) : `TNF`
  (cadeau), `TIM` (monnaie temps), `FID` (fidélité), `BDG` (badgeuse). Exclues :
  fiduciaires (`TLF`, `FED`) et adhésion (`SUB`).
- Authentification par clé API (`SemanticApiKeyPermission`).
- Nouveau champ `ExternalApiKey.gift_asset` (FK → `fedow_public.AssetFedowPublic`,
  `limit_choices_to={'category__in':['TNF','TIM','FID','BDG']}`). Sa présence
  active le droit `walletrefill` **et** restreint la clé à ce seul asset.
- Payload : `email` + `asset` (uuid TNF) + `amount` (entier, unité brute).
- Plafond hardcodé par recharge : `GIFT_REFILL_MAX_AMOUNT = 10000`.
- Header optionnel `Idempotency-Key` : anti double-crédit (cache best-effort,
  TTL ~48 h ; renvoie la transaction stockée avec un `208 Already Reported`).
- Réponse schema.org `MoneyTransfer`.

**Pourquoi / Why :** Permettre à un service externe d'offrir des tokens cadeau
de façon contrôlée (un asset par clé, catégorie cadeau uniquement, plafond).
La route v1 `/api/wallet/get_stripe_checkout_with_email/` (recharge **payante**
Stripe) reste inchangée.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_public/models.py` | Constante `AssetFedowPublic.REFILLABLE_CATEGORIES` (TNF/TIM/FID/BDG) |
| `BaseBillet/models.py` | Champ `gift_asset` sur `ExternalApiKey` + entrée `api_permissions()` |
| `BaseBillet/migrations/0211_externalapikey_gift_asset.py` | Ajout du champ |
| `BaseBillet/migrations/0212_alter_externalapikey_gift_asset.py` | Élargissement `limit_choices_to` + libellés |
| `api_v2/serializers.py` | `WalletRefillCreateSerializer` |
| `api_v2/views.py` | `WalletRefillViewSet` + `GIFT_REFILL_MAX_AMOUNT` + import `gettext` |
| `api_v2/urls.py` | Route `wallet-refills` (basename `walletrefill`) |
| `Administration/admin_tenant.py` | `gift_asset` dans `ExternalApiKeyAdmin.fields` |
| `api_v2/openapi-schema.yaml` | Path + schéma `MoneyTransfer` |
| `api_v2/README.md`, `api_v2/GUIDELINES.md` | Documentation de la route |
| `tests/pytest/test_api_v2_wallet_refill.py` | 11 tests (FedowAPI mockée) |

### Migration
- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/0211_externalapikey_gift_asset` + `BaseBillet/0212_alter_externalapikey_gift_asset`
- `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Nouvelles chaînes `_()` côté serveur (messages d'erreur de la vue + `verbose_name`/
`help_text` du champ `gift_asset`). Le mainteneur lance makemessages/compilemessages.

## Module « Agenda participatif » / "Participatory agenda" module

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0210_configuration_module_agenda_participatif`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What :** Le wizard public de proposition d'évènement est désormais
piloté par un module Groupware dédié, désactivé par défaut.
- Nouveau champ `Configuration.module_agenda_participatif` (`BooleanField`,
  `default=False`).
- Nouvelle carte « Agenda participatif » sur le dashboard admin (toggle HTMX),
  avec le texte d'aide : « un formulaire pour que vos users puissent proposer
  des évènements sur la page agenda ; évènements à valider dans l'admin ».
- Sur la page agenda, le bouton « Proposer un évènement » ne s'affiche que si
  le module est actif (`{% if config.module_agenda_participatif %}`).
- `WizardEventPublicSerializer.validate()` refuse la création de proposition si
  le module est désactivé (garde côté serveur, même en atteignant l'URL
  directement).

**Pourquoi / Why :** Permettre à chaque tenant d'activer ou non l'agenda
participatif. Le parcours admin de création d'évènement reste inchangé.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Champ `module_agenda_participatif` sur `Configuration` |
| `BaseBillet/migrations/0210_configuration_module_agenda_participatif.py` | Migration du champ |
| `Administration/admin/dashboard.py` | Entrée `MODULE_FIELDS` (carte + texte d'aide) |
| `BaseBillet/templates/reunion/views/event/list.html` | Bouton public conditionné au module |
| `BaseBillet/validators.py` | Garde module dans `WizardEventPublicSerializer.validate()` |

### Migration
- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/0210_configuration_module_agenda_participatif`
- `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Carte dashboard : texte source **en français** (« Agenda participatif » + texte
d'aide), affichée directement sans attendre de traduction. Le mainteneur lance
makemessages/compilemessages pour générer la traduction EN. Autres chaînes `_()` :
`Participatory agenda module` (verbose_name modèle, EN),
`La proposition d'évènement n'est pas activée.` (erreur serializer, FR).

## Triggers Fedow dans les inlines de tarif (adhésion + billet) / Fedow triggers in price inlines (membership + ticket)

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Depuis que les tarifs (`Price`) sont des inlines dans les proxys
produit, l'onglet « Triggers » de l'ancienne vue `PriceAdmin` n'était plus
atteignable (lien désactivé, absent de la sidebar). Les deux déclencheurs Fedow
sont désormais exposés **directement dans l'inline du bon proxy** :
- **Adhésion** (`MembershipPriceInline`) : `fedow_reward_enabled` → recharge le
  wallet du membre à l'achat de l'adhésion.
- **Billet** (`TicketPriceInline`) : `reward_on_ticket_scanned` → récompense le
  wallet de l'acheteur au scan du billet.

Dans les deux cas, `fedow_reward_asset` + `fedow_reward_amount` ne s'affichent que
si le toggle est coché, via le mécanisme JS `inline_conditional_fields` existant.

**Pourquoi / Why :** Redonner l'accès à un réglage rare (très peu de tenants) sans
polluer l'inline du cas courant. Comme chaque proxy n'a qu'un seul toggle, la
limite « une source par règle » du JS conditionnel n'est jamais atteinte (pas de
`OU` à gérer). Le câblage conditionnel est remonté dans la base `ProductAdmin`
pour que `TicketProductAdmin` en bénéficie aussi (avant : uniquement adhésion).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `BasePriceInline.formfield_for_foreignkey` (filtre `fedow_reward_asset` sur `AssetFedowPublic` local du tenant) ; `BasePriceInlineForm.__init__` désactive les boutons +/✎/🗑/👁 du dropdown asset (aucune création/édition/consultation d'asset depuis l'inline) ; champs trigger + règles conditionnelles ajoutés à `MembershipPriceInline` et `TicketPriceInline` (+ `Media.js`) ; `change_form_after_template` + `changeform_view` remontés dans `ProductAdmin` (base), retirés de `MembershipProductAdmin` (devenus redondants) ; **nettoyage** : correction i18n (`_(f"…")` → placeholders `%`) dans `duplicate_product`/`archive`/`desarchive`, suppression d'un `logger.error(self.actions_row)` de debug |
| `Administration/admin_tenant.py` | **nettoyage** : suppression du code mort `PriceInlineChangeForm` + `PriceInline` (ancien inline orphelin, remplacé par le package `Administration/admin/`) |
| `A TESTER et DOCUMENTER/triggers-fedow-inline-tarif.md` | NOUVEAU — scénarios de test manuel |

> **i18n :** les correctifs `_(f"…")` → `_("…%(x)s…") % {…}` **changent les msgid** de
> `duplicate_product`/`archive`/`desarchive`. Lancer le workflow traductions
> (`makemessages` + `.po` + `compilemessages`) — non lancé ici (le mainteneur s'en charge).

### Décisions clés / Key decisions

- **Un toggle par proxy** : adhésion = `fedow_reward_enabled` (recharge à l'achat),
  billet = `reward_on_ticket_scanned` (récompense au scan). Sémantique confirmée
  dans le code consommateur (`tasks.py:refill_..._from_price_solded` vs
  `signals.py:check_reward` → `tasks.py:refill_..._from_ticket_scanned`).
- **JS inchangé** : la séparation par proxy évite le besoin d'un `OU` dans
  `inline_conditional_fields.js`.
- **`PriceAdmin` standalone conservé** (onglet Triggers intact) — sert toujours
  d'autocomplete et de cible de redirection, mais n'est plus le chemin nominal.

### Migration

- **Migration nécessaire / Migration required:** Non (aucun changement de modèle ;
  les 4 champs `Price` existent déjà depuis les migrations 0163 / 0180).

## Wizard évènement V2 : connexion classique, lieu en 2 pages, multi-évènements / Event wizard V2: classic login, 2-page place, multi-events

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Évolution du wizard évènement (cf. entrée du 2026-05-19). Le
wizard public n'utilise plus l'OTP mais la **connexion classique** (l'OTP est
conservé en code, parqué pour un futur offcanvas de connexion). Le choix de lieu
passe en **2 pages** comme l'onboarding (page 1 : adresse existante filtrable OU
nom d'un nouveau lieu ; page 2 : carte pré-remplie avec recherche auto). On peut
désormais **proposer / créer plusieurs évènements** d'un coup (liste HTMX
add/remove, lieu partagé). Le routage des 2 wizards passe sur un **router DRF**
(plus de `path()` manuels). La liste d'adresses **plafonne l'affichage à 50** (la
recherche couvre la totalité) pour rester navigable avec 300+ adresses, et le
toggle de mode passe en **vertical sur mobile**.

**Pourquoi / Why :** `authentication_classes = []` faisait afficher « Connexion »
à un visiteur déjà connecté et imposait un OTP redondant. Le multi-évènements
reproduit le formulaire onboarding (annoncer plusieurs dates d'un lieu). Le
plafond d'adresses et le toggle mobile préparent les tenants « agenda régional ».

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Auth session + garde `_require_login_or_redirect`, split lieu (2 helpers), multi-events (3 helpers + 2 fabriques `_creer_event_*`), `@action` + `url_name` |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` + `WizardPlaceMapSerializer` (remplacent `WizardPlaceSerializer`) |
| `BaseBillet/urls.py` | `SimpleRouter` `wizard_router` (avant le routeur principal), suppression des `as_view`/`path` manuels du wizard |
| `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html` | Toggle full-width + liste filtrable + plafond 50 + media query mobile |
| `BaseBillet/templates/reunion/views/event/wizard/_form_carte.html` + `{admin,public}_step_map.html` | NOUVEAU — page carte (étape 2 du lieu) |
| `BaseBillet/templates/reunion/views/event/wizard/_events_inner.html` | NOUVEAU — liste brouillons + sous-form HTMX add |
| `BaseBillet/templates/reunion/views/event/wizard/{admin,public}_step2_event.html` | Réécrits en étape multi-évènements |
| `Administration/admin/dashboard.py` | Fix badge sidebar « None » (`event_proposals_badge_callback(request) or ""`) |
| `BaseBillet/templates/reunion/partials/navbar.html` | Ouverture auto de l'offcanvas connexion via `?login=1` |
| `static/widgets/widget_carte_adresse.js` | Repli reverse-geocode quand la recherche par nom renvoie une adresse incomplète |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/CHANTIER-02-*.md` | NOUVEAU — recap du chantier |
| `TECH_DOC/SESSIONS/WIDGET_GEO/03-fix-reverse-geocode-fallback.md` | NOUVEAU — note de correctif |
| `A TESTER et DOCUMENTER/event-wizards.md` | Mis à jour (nouveau flux login + multi-events) |

### Décisions clés / Key decisions

- **OTP parqué** (code conservé) → réintégration future dans l'offcanvas de connexion.
- **Lieu partagé** : tous les évènements d'une proposition au même lieu choisi à l'étape 1.
- **Image de brouillon** : `event.img.name = chemin` au finalize (une seule sauvegarde → signaux 1×).
- **HTMX add** : renvoi **200** sur erreur de validation (pas de config swap-on-422 dans le skin reunion).
- **Routage** : `SimpleRouter` inclus avant `EventMVT` pour que `event/propose/...` résolve avant `event/{pk}/`.

### Migration

- **Migration nécessaire / Migration required:** Non (aucun changement de modèle ; `Event.is_proposal` existe déjà depuis la migration 0209).

### À surveiller / Watch out

- Tests `tests/pytest/test_event_wizard_public.py` à adapter (testaient le flow OTP/anonyme) — différé.
- i18n : `makemessages` / `compilemessages` à lancer (nouvelles chaînes).
- Images de brouillons abandonnés (wizard quitté sans finaliser) : restent dans `event_wizard_drafts/` (pas de purge auto).


## Carte explorer ROOT : pills exclusives, tag chips, URL partageable / Exclusive pills, tag chips, shareable URL

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte UX de la carte explorer ROOT (`/explorer/`). La pill
"Tous" est supprimée — il reste "Lieux" et "Événements" exclusives. En mode
Événements, la liste affiche 1 card par event futur (au lieu de cards lieu).
Une nouvelle barre de tag chips (top 10 par fréquence parmi les events visibles)
permet de filtrer par tag, avec bouton "+ N tags" pour le reste. Les filtres
(`v`, `q`, `tag`) sont synchronisés dans l'URL via `history.replaceState`,
ce qui rend la carte partageable. L'accordéon "Prochains événements" sur les
cards lieu est réparé (régression CHANTIER-05 résolue). Un bug 1-ligne sur
le JSON-LD federation des explorers tenant est corrigé en parallèle.

**Pourquoi / Why :** Suite à CHANTIER-05, le filtre "Événements" ne changeait
plus visuellement la vue, et la liste d'événements avait disparu. En parallèle,
l'arrivée de tenants type "réseau régional" ou "agenda culturel régional"
(200+ PostalAddress) demandait une UX de filtrage par thématique pour rester
navigable. Les tags `Event.tag` existaient en DB depuis longtemps mais
n'étaient pas exposés côté SEO.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | +`get_event_tags_for_tenants` (helper SQL cross-schema), propagation `tags` dans `events_pour_popup`, `get_events_for_tenants` retourne aussi `uuid` |
| `seo/tasks.py` | Enrichissement events avec tags dans `refresh_seo_cache` (1 requête SQL supplémentaire) |
| `BaseBillet/views.py` | Fix bug 1-ligne : `lieux` → `tenants` dans le JSON-LD federation des explorers tenant |
| `seo/templates/seo/partials/explorer_widget.html` | Suppression pill "Tous", ajout `#explorer-tags`, data-i18n |
| `seo/static/seo/explorer.js` | Refonte `applyFilters`, chips top 10, URL sync, accordéon réparé |
| `seo/static/seo/explorer.css` | +Styles `.explorer-tag-chip*`, `.explorer-empty-state`, `.explorer-card-tags` |
| `tests/pytest/test_seo_event_tags.py` | NOUVEAU — tests unitaires (3) du nouveau helper |
| `tests/pytest/test_seo_aggregate_points.py` | +2 tests propagation tags |
| `tests/e2e/test_explorer_ux_pills_tags.py` | NOUVEAU — 8 tests Playwright (pills, chips, URL, empty state) |
| `tests/e2e/conftest.py` | NOUVEAU sur la branche — fixtures Playwright (page, browser) |
| `pytest.ini` | +marker `e2e` |
| `CHANGELOG.md` | Cette entrée |
| `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md` | NOUVEAU — scénarios test manuel |

### Activation

Aucune migration DB. Le nouveau format de cache (events avec `tags`) est rétro-
compatible : le JS lit avec `.tags || []`. Activation au prochain cycle Celery
Beat de `refresh_seo_cache` (4h max), ou refresh manuel :

```bash
docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
```

## Wizards de création et proposition d'évènement / Event creation & proposal wizards

**Date :** 2026-05-19
**Migration :** Oui (`BaseBillet/migrations/0209_event_is_proposal.py`, additive, default=False)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte de la création d'évènement en wizard 2 étapes (admin)
avec carte interactive Leaflet pour les nouvelles adresses. Ajout d'un wizard
public anonyme protégé par OTP email permettant à tout visiteur de proposer un
évènement soumis à modération admin (badge sidebar Unfold + filtre + action bulk).

**Pourquoi / Why :** Améliorer l'UX admin (offcanvas → wizard plus FALC) et
ouvrir la plateforme aux contributions publiques avec modération. Mettre en
place un service OTP DRY (`AuthBillet/otp_service.py`) réutilisable pour de
futurs flows (login OTP, SSO).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service OTP stateless DRY |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `AuthBillet/templates/auth/emails/otp_code.{html,txt}` | NOUVEAU — templates email génériques |
| `BaseBillet/models.py` | +`Event.is_proposal` (BooleanField default=False) |
| `BaseBillet/migrations/0209_event_is_proposal.py` | NOUVEAU — migration additive |
| `BaseBillet/views.py` | +`EventWizardAdmin`, +`EventWizardPublic` ViewSets. Suppression `EventMVT.simple_*` |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/urls.py` | +8 routes (admin + public) |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `BaseBillet/templates/reunion/views/event/list.html` | Suppression offcanvas, ajout 2 boutons (admin + public) |
| `BaseBillet/templates/faire_festival/views/event/list.html` | Adaptation skin Faire Festival |
| `BaseBillet/templates/reunion/views/event/partial/simple_add_event.html` | supprimé |
| `BaseBillet/templates/reunion/views/event/partial/address_simple_add.html` | supprimé |
| `Administration/admin/dashboard.py` | +`event_proposals_badge_callback` + badge sur item Events |
| `Administration/admin_tenant.py` | +`IsProposalFilter` + action `approuver_propositions` sur `EventAdmin` |
| `tests/pytest/test_otp_service.py` | NOUVEAU — 16 tests |
| `tests/pytest/test_otp_session.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_is_proposal_field.py` | NOUVEAU — 2 tests |
| `tests/pytest/test_event_wizard_admin.py` | NOUVEAU — 9 tests |
| `tests/pytest/test_event_wizard_public.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_proposal_admin.py` | NOUVEAU — 5 tests |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/` | NOUVEAU hub : INDEX + SPEC + PLAN |
| `TECH_DOC/SESSIONS/OTP/` | NOUVEAU hub : INDEX + SPEC |
| `A TESTER et DOCUMENTER/event-wizards.md` | NOUVEAU — scénarios de test manuel |

### Décisions clés / Key decisions

- **Service OTP DRY** : `OtpService` stateless + `OtpSession` HTTP helper, réutilisable (login OTP, SSO, migration onboard future).
- **Anti-spam** : Throttle DRF (3 demandes/heure/IP) + honeypot champ `website` + garde de session entre les étapes.
- **Modération** : `Event.is_proposal=True, published=False` → badge sidebar Unfold + filtre `Proposals pending` + action bulk `Approve and publish`.
- **Compatibilité** : onboard inchangé (logique OTP custom conservée), events existants restent `is_proposal=False` (défaut migration).

### Migration

- **Migration nécessaire / Migration required:** Oui
- `BaseBillet/migrations/0209_event_is_proposal.py` (additive, default=False, aucune data migration)


## SEO Chantier 05 : carte explorer ROOT — 1 marker par PostalAddress / SEO Chantier 05: 1 marker per PostalAddress on ROOT explorer map

**Date :** 2026-05-17
**Migration :** Non (juste une nouvelle valeur dans CharField choices)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte de la carte `/explorer/` du tenant ROOT. Avant :
1 marker par tenant (positionne sur Configuration.postal_address). Apres :
1 marker par PostalAddress active, avec popup riche listant le nom du lieu,
l'adresse, le tenant + un lien, et les 5 prochains events futurs.

**Pourquoi / Why :** Suite a l'import de 327 PostalAddress geolocalisees
(via outil nominatim-review), les tenants comme l'Universite Populaire de
Villeurbanne (24 lieux d'evenements differents) etaient invisibles. La carte
ROOT devient une vraie cartographie des lieux du reseau, pas juste des sieges.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | +constante `SEOCache.AGGREGATE_POINTS` |
| `seo/services.py` | +`get_postal_addresses_for_tenants`, +`build_aggregate_points`, refacto `build_explorer_data_for_tenants` (retourne `{points, tenants}`) |
| `seo/tasks.py` | +Etape 6 dans `refresh_seo_cache` (ecriture `AGGREGATE_POINTS`) |
| `seo/views.py` | `explorer()` itere sur `explorer_data["tenants"]` pour federation JSON-LD |
| `seo/templates/seo/partials/explorer_widget.html` | Commentaires mis a jour |
| `seo/static/seo/explorer.js` | Boucle sur `state.data.points` (1 marker par PA), popup riche avec `events_futurs`, `state.markers` indexes par `pa_id` |
| `seo/static/seo/explorer.css` | +styles popup riche (.explorer-popup-address, -tenant, -logo, -events-list, -events-more) |
| `tests/pytest/test_seo_aggregate_points.py` | +6 tests unitaires (mocks, sans DB) |
| `tests/playwright/tests/35-explorer-markers-per-pa.spec.ts` | +2 tests E2E (structure JSON + markers visibles) |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md` | Spec |
| `TECH_DOC/SESSIONS/SEO/PLAN-05-explorer-markers-per-pa.md` | Plan d'implementation |

### Decisions cles / Key decisions
- **1 marker par PA** : popup riche listant tout (vs. markers superposes)
- **Filtre "tenant vivant"** : PA incluse si tenant a >=1 event futur OU >=1 produit publie
- **Cache dedie** `AGGREGATE_POINTS` : zero impact sur `AGGREGATE_LIEUX` (utilise par les autres vues `/lieu/<slug>/`, `/lieux/`, recherche)
- **Top 5 events** par popup + `events_futurs_count_total` pour afficher "+ N autres"

### Compatibilite / Compatibility
- `AGGREGATE_LIEUX` reste maintenu en parallele -> vues `/lieu/<slug>/`, `/lieux/`, recherche ROOT, JSON-LD federation continuent de fonctionner comme avant.
- **Activation** : prochain cycle Celery Beat de `refresh_seo_cache` (4h max), ou manuel :
  ```bash
  docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
  ```


## Liste des évènements : filtre par date en SQL + filtres conservés à la pagination / Event list: date filter in SQL + filters kept on pagination

**Quoi / What :** Correction d'un bug de la page liste des évènements (`EventMVT`)
visible sur les gros agendas (festival > 300 évènements). Le filtre par date
était appliqué en Python **après** la pagination (100 évènements/page) : filtrer
un jour situé au-delà de la page 1 (ex : samedi d'un festival jeu/ven/sam) ne
renvoyait rien. Désormais le filtre par date est appliqué en base (SQL) et,
quand un jour est sélectionné, **tous** les évènements de ce jour s'affichent
sans pagination. De plus, le bouton « CHARGER PLUS » conserve maintenant tous
les filtres actifs (recherche, thématique, tags multiples), au lieu du seul
premier tag — la recherche ne « perdait » plus son filtre après un chargement
supplémentaire.

Les pages filtrées par **date seule** sont désormais mises en cache (1 h), comme
la page principale — c'est l'action la plus fréquente sur un festival. Le cache
de la liste utilise un **jeton de version par tenant** réécrit dans `Event.save()` :
modifier un évènement invalide d'un coup la page principale ET toutes les pages
par date (pas de `cache.incr`, qui est piégeux avec memcached).

**Pourquoi / Why :** Sur un festival, la pagination s'arrêtait au milieu et le
filtre par jour affichait « aucun résultat » pour les jours non encore chargés.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `federated_events_filter` : param `date_filter`, filtre SQL `datetime__date`, pagination désactivée si date filtrée. Cache versionné (page principale + page par date seule). Helpers `_parse_date_filter` + `_querystring_filtres`. `list()` : filtre date en SQL (suppression du filtrage Python post-pagination). `partial_list()` : lecture/propagation du filtre date. Querystring des filtres actifs exposée au contexte. |
| `BaseBillet/models.py` | `Event.save()` : invalidation du cache liste par réécriture d'un jeton de version (`event_list_version_{tenant.uuid}`) au lieu de la suppression d'une clé unique. |
| `BaseBillet/templates/faire_festival/views/event/list.html` | Bouton CHARGER PLUS : `{{ querystring_filtres }}` au lieu de `&tag={{ tags.0 }}`. |
| `BaseBillet/templates/faire_festival/views/event/partial/list_append.html` | Idem bouton CHARGER PLUS. |

### Migration
- **Migration nécessaire / Migration required :** Non

## Home publique : section « Ils contribuent » + mention France 2030 dans le footer / Public home: "They contribute" section + France 2030 footer mention

**Quoi / What :** Ajout d'une section « Ils contribuent » sur la landing
page du tenant public (app `seo`), à la suite des bandeaux lieux et
événements de la fédération : panneau gris doux, grille de tuiles
blanches (logo + nom dessous), logos cliquables, pilotée par une liste
explicite dans la vue. Un logo blanc sur transparent (CoopCircuit) a été
inversé pour rester visible sur tuile blanche. Ajout aussi de la mention
obligatoire de financement France 2030 dans le footer de la home publique
(séparateur + texte à gauche / logo aligné à droite), qui en était
dépourvue alors que les footers des tenants l'affichent déjà.

**Pourquoi / Why :** Valoriser les contributeurs du commun sur la page
d'accueil du réseau, et homogénéiser la mention légale France 2030
(« Solutions de billetteries innovantes », Caisse des Dépôts) présente
sur les footers tenants mais absente du footer ROOT.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/views.py` | Constante `CONTRIBUTEURS` (nom + logo + url) + ajout au contexte de `landing` |
| `seo/templates/seo/landing.html` | Section `contributeurs-section` (grille de logos cliquables, masquée si liste vide) |
| `seo/static/seo/seo.css` | Styles `.contributeurs-*` (grille auto-fit centrée, logos couleur, relief au survol) |
| `seo/templates/seo/base.html` | Mention France 2030 + logo `reunion/img/france_2030.png` dans le footer |

### Migration
- **Migration nécessaire / Migration required :** Non
- **i18n :** Nouvelles chaînes (`Ils contribuent`, sous-titre, mention France 2030…) — lancer `makemessages` + `compilemessages` (à la charge du mainteneur).

## SEO Chantier 01 : desindexer les instances DEV / DEMO / TEST / SEO Chantier 01: deindex DEV / DEMO / TEST instances

**Date :** 2026-05-17
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Les instances de dev / demo / test (filaos.re, devtib.fr)
etaient publiquement indexees sur Google et Bing alors qu'elles ne
devraient pas l'etre. Mise en place d'une regle metier simple :
`noindex, nofollow` (via `robots.txt` ET `<meta name="robots">`) quand
au moins un flag d'environnement est a `1` :
- `DEBUG=1` ou `TEST=1` ou `DEMO=1` ou `STRIPE_TEST=1`.

**Pourquoi / Why :** Aligne le projet sur le **Google AI Optimization
Guide** publie le 15 mai 2026 (cf. `TECH_DOC/SESSIONS/SEO/SPEC.md` et
Atomic atom `491b2fe3-049c-4b2d-86bf-ae2fc41b6b31`). Les instances dev
qui apparaissent dans la SERP volent la place du tenant principal sur
les requetes "TiBillet" et brouillent la marque. Une regle
supplementaire sur le host (DOMAIN / ADDITIONAL_DOMAINS) a ete
envisagee puis ecartee : redondante en pratique avec les 4 flags +
Django bloque deja les hosts inconnus via `ALLOWED_HOSTS`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/seo_indexing.py` | NOUVEAU. Helper `should_noindex(request) -> bool` (regle metier complete, FALC bilingue) + context processor `noindex_context` |
| `TiBillet/settings.py` | +1 ligne dans `TEMPLATES.OPTIONS.context_processors` (`'TiBillet.seo_indexing.noindex_context'`) |
| `seo/views_common.py::robots_txt` | Branche sur `should_noindex(request)` : si True, sert `Disallow: /`. Sinon : `Allow: /` + sitemap |
| `BaseBillet/views_robots.py::robots_txt` | Meme logique cote tenant. Supprime imports inutiles (`connection`, `get_current_site`) |
| `seo/templates/seo/base.html` | Block `meta_robots` etend la logique : `noindex_seo` -> `noindex, nofollow`, sinon `index, follow` |
| `BaseBillet/templates/reunion/base.html` | Idem |
| `BaseBillet/templates/faire_festival/base.html` | Idem |
| `BaseBillet/templates/htmx/base.html` | NOUVEAU bloc `meta_robots` (n'en avait pas) + commentaire FALC bilingue |
| `tests/pytest/test_seo_indexing.py` | NOUVEAU. 5 tests unitaires : 4 flags d'env + 1 cas indexable |
| `TECH_DOC/SESSIONS/SEO/INDEX.md` | NOUVEAU. Hub du chantier SEO sur plusieurs sessions |
| `TECH_DOC/SESSIONS/SEO/SPEC.md` | NOUVEAU. Vision globale, principes Google 2026, etat actuel, anti-patterns |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md` | NOUVEAU. Spec actionable de ce chantier |
| `A TESTER et DOCUMENTER/seo-noindex-dev.md` | NOUVEAU. Scenarios de test manuel |

### Migrations

- **Migration necessaire / Migration required :** Non

### Tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_indexing.py --api-key dummy -v
# 5 passed in 0.27s
```

### Note importante

Pour faire desindexer effectivement filaos.re et devtib.fr (deja
presents dans la SERP), il faut **en plus** soumettre une demande
de suppression via Google Search Console + Bing Webmaster apres le
deploiement. Sinon Google peut mettre plusieurs semaines a les
oublier tout seul.

---

## Session marathon onboard + landing : hotfix prod + UX + i18n / Onboard marathon: prod hotfix + UX + i18n

**Date :** 2026-05-17
**Migration :** Oui (2 migrations)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Session multi-axes regroupant un hotfix prod critique
(PostalAddress lat/lng overflow sur les longitudes hors [-99, +99]),
plusieurs bugs UX du wizard onboarding (perte de session après login,
mailer en anglais non traduit, prénom/nom non répercutés sur l'user, long
description / logo non transférés au tenant, polling infini après erreur),
le polish de la landing root (4 nouvelles fonctionnalités + section
roadmap accordéon, JSON-LD WebSite + searchbox SERP, og:locale) et la
réécriture des deux templates email (OTP + ready) avec le wording riche
du flow legacy `/tenant/new/` adapté au contexte wizard.

**Pourquoi / Why :** Avant push prod. Sentry a remonté l'overflow lat/long
(création tenant cassée pour Asie / Pacifique / Amériques). Les autres
bugs étaient bloquants ou dégradants UX. La landing root manquait des
fonctionnalités différenciantes (open-data, AGPLv3, fédération) et n'avait
pas de roadmap visible pour engager la communauté.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `PostalAddress.latitude/longitude` 18/16 → 9/6 (overflow longitude hors [-99, +99]) |
| `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` | NOUVEAU |
| `MetaBillet/models.py` | + champ `language` sur `WaitingConfiguration` (CharField max 10) |
| `MetaBillet/migrations/0016_add_wc_language.py` | NOUVEAU |
| `onboard/views.py::_finalize_otp_success` | + `_set_session_wc()` après login (perte session avec SESSION_SAVE_EVERY_REQUEST=True) ; + report `wc.first_name/last_name` sur user (si user n'a pas déjà ces champs) |
| `onboard/views.py` POST identity | + capture `get_language()` dans `wc.language` |
| `onboard/tasks.py::onboard_otp_mailer` | + `translation.override(wc.language)` autour du sujet + render templates |
| `onboard/tasks.py::onboard_ready_mailer` | idem + nouveau context var `instance_url` |
| `onboard/tasks.py::create_tenant_from_draft` | NOUVEAU bloc "3ter" transfert `wc.long_description` + `wc.logo` vers `Configuration.long_description` + `Configuration.img` (try/except sans re-raise pour préserver l'idempotence Celery, cf. piège #23) |
| `onboard/templates/onboard/steps/06_launch.html` | Fix polling infini : retrait `hx-trigger="load, every 2s"` du parent `#status` (le swap innerHTML ne touche pas les attributs du parent, donc le polling continuait après status_error) |
| `onboard/templates/onboard/emails/ready.html` | Réécrit avec wording riche du legacy `welcome_email.html` adapté au contexte post-création (bouton "ACCÉDER À MON ESPACE", liste "Informations importantes", section "Voici ce que vous pouvez faire", signature équipe coopérative) |
| `onboard/templates/onboard/emails/ready.txt` | Version texte cohérente |
| `onboard/templates/onboard/emails/otp_code.html` | Réécrit dans le style général (table imbriquée, palette `#009058`, Arial) ; capsule vert clair encadrée avec code PIN en `Courier New 36px` letter-spacing 12px |
| `onboard/templates/onboard/emails/otp_code.txt` | Réécrit |
| `seo/templates/seo/landing.html` | Philo réécrite (Code Commun + Ostrom) ; + 4 nouvelles cartes Fonctionnalités (Données ouvertes, Logiciel libre AGPLv3, Agenda participatif, Référencement et SEO) ; + nouvelle section roadmap `<details>` natif "Futur de TiBillet" (Newsletter, Réseaux sociaux, Fédiverse, Cascade) ; + `<h2 visually-hidden>` pour hiérarchie SEO |
| `seo/templates/seo/base.html` | + `<meta property="og:locale">` mappé `fr_FR` / `en_US` |
| `seo/views.py::landing` | Split JSON-LD en 2 blocs : Organization (`json_ld_org`) + WebSite/SearchAction (`json_ld`) pour éligibilité sitelinks searchbox SERP Google |
| `seo/static/seo/seo.css` | + section "ROADMAP / FUTURE" (~85 lignes) — accordéon stylé, chevron rotate, palette orange pour "futur" vs vert pour "actuel", `prefers-reduced-motion` respecté |

### Migrations

- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` — 2 AlterField sur PostalAddress (latitude, longitude) de DecimalField(18,16) à DecimalField(9,6). Compatible avec les données existantes (précision tronquée si > 6 décimales, aucune perte de range).
- `MetaBillet/migrations/0016_add_wc_language.py` — AddField `language` CharField(max_length=10, blank=True, default="") sur WaitingConfiguration.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

### Pièges documentés / Pitfalls documented

Voir `tests/PIEGES.md` section "Onboarding wizard (session 2026-05-17)" :
- DecimalField lat/lng : max_digits - decimal_places ≥ 3 obligatoire
- Polling HTMX : ne JAMAIS doubler `hx-trigger="every Xs"` sur parent + child
- `login()` peut perdre les clés de session avec `SESSION_SAVE_EVERY_REQUEST=True`
- `cron_morning` create_waiting_tenant fragile : `raise` global peut laisser le pool dans un état hybride
- gettext dans tasks Celery sans LocaleMiddleware → fallback `LANGUAGE_CODE`
- `wc.create_tenant()` ne transfère PAS automatiquement long_description, logo, ni first_name/last_name

---

## Widget de saisie d'adresse géolocalisée / Geolocated address input widget

**Date :** 2026-05-15
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What:** nouveau widget Django+Leaflet+leaflet-geosearch réutilisable
pour saisir une adresse (search live, marqueur draggable, géocodage inverse).
Refonte de la step 03_place du wizard onboard pour l'utiliser.
**Architecture full client** : recherche live ET reverse geocode appellent
Nominatim direct depuis le navigateur (pas de proxy serveur).

**Pourquoi / Why:** UX précédente (saisie en 4 champs séparés + géocodage HTMX
au change) trop friction. Pattern GPS standard (suggestions live + drag) plus
intuitif et réutilisable dans d'autres formulaires (Event admin, etc.).

**Décision architecturale 2026-05-15** : la spec initiale proposait une approche
"Hybride" (search client + reverse via endpoint serveur `/widgets/geocode-reverse/`
avec cache Redis). Bascule en **full client** après découverte d'un problème
multi-tenant routing : la route `BaseBillet/urls.py` n'est inclus que dans
`urls_tenants.py`, pas dans `urls_public.py` → 404 sur ROOT (où tourne le
wizard onboard). Plutôt que dupliquer l'URL dans 2 fichiers, on a supprimé
l'endpoint serveur et on appelle Nominatim direct (CORS open, déjà fait par
leaflet-geosearch pour le forward). Trade-off : pas de cache mutualisé, mais
acceptable pour notre volume.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `templates/widgets/widget_carte_adresse.html` | NOUVEAU — widget réutilisable |
| `static/widgets/widget_carte_adresse.js` | NOUVEAU — init IIFE multi-widget, fetch Nominatim direct |
| `static/widgets/widget_carte_adresse.css` | NOUVEAU — surcharges palette TiBillet |
| `BaseBillet/form_fields.py` | NOUVEAU — `AdresseGeolocaliseeField` helper (validation serveur) |
| `TiBillet/settings.py` | + `BASE_DIR / "templates"` dans TEMPLATES dirs, + `BASE_DIR / "static"` dans STATICFILES_DIRS |
| `onboard/templates/onboard/steps/03_place.html` | utilise le widget |
| `onboard/serializers.py` | `OnboardPlaceSerializer` : nouveaux champs `place_*` |
| `onboard/views.py` | mapping persistance + suppression action `geocode` |
| `onboard/urls.py` | suppression route geocode |
| `onboard/templates/onboard/partials/map_widget.html` | SUPPRIMÉ |
| `onboard/templates/onboard/partials/geocode_result.html` | SUPPRIMÉ |
| `tests/pytest/test_widget_form_field_geo.py` | NOUVEAU (6 tests `AdresseGeolocaliseeField`) |
| `onboard/tests/test_step_place.py` | adapté + suppression test endpoint geocode |

### Migration
- **Migration nécessaire / Migration required:** Non
- Pas de modification de schéma DB.

### Breaking changes
- Endpoint `POST /onboard/geocode/` supprimé. Aucun consommateur externe (uniquement utilisé en interne par l'ex-step 03_place).

## Chantier landing #04 — Filtre "lieu vivant" + UX "Voir tous" → explorer

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Le cache SEO listait tous les tenants ayant un domaine, sans
verifier s'il y avait quelque chose a voir/acheter chez eux. En prod
avec 375 tenants, le marquee, `/lieux/`, la carte explorer et le
sitemap pointaient vers des dizaines de pages quasi-vides — bruit UX
et crawl budget gaspille pour Google + bots LLM.

1. **Filtre "lieu vivant"** sur `AGGREGATE_LIEUX` et `SITEMAP_INDEX` :
   un tenant n'apparait que s'il a un domaine ET (au moins 1 event
   futur publie OU au moins 1 produit BILLET/FREERES/ADHESION publie).
   Implementation : `seo/services.py::get_active_tenants_with_counts()`
   ramene `event_count` + `product_count` par tenant en 1 seule requete
   SQL (UNION ALL avec sous-selects scalaires). `seo/tasks.py` applique
   le filtre `lieu_est_vivant` avant de remplir `lieux` et
   `sitemap_tenants`. `TENANT_SUMMARY` / `TENANT_EVENTS` (caches
   per-tenant) restent inchanges.
2. **Chiffres cles supprimes** : "X lieux", "Y events" sur la landing
   — vanity metrics SaaS qui jurent avec le ton commun cooperatif. Bloc
   `stats-row` retire du template. `GLOBAL_COUNTS` n'est plus genere
   (suppression de `get_global_event_count()` dans `seo/services.py` et
   du bloc de generation dans `tasks.py`). Constante
   `SEOCache.GLOBAL_COUNTS` laissee dans `choices` pour eviter une
   migration de schema sur du code mort.
3. **UX "Voir tous"** : les 2 boutons sous les marquees pointent
   maintenant vers `/explorer/` (carte + filtres, vue interactive)
   plutot que `/lieux/` et `/evenements/`. Ces deux pages restent
   indexables pour le SEO/ranking mais ne sont plus mises en avant
   dans la navigation humaine.

**EN :** SEO cache listed every tenant with a domain, no check if there
was anything to see/buy there. In prod with 375 tenants, the marquee,
`/lieux/`, the explorer map and the sitemap pointed to dozens of
near-empty pages — UX noise and wasted crawl budget for Google + LLM
bots. Added an "alive venue" filter, removed vanity counters on the
landing, redirected "See all" buttons to `/explorer/` for humans.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `get_active_tenants_with_event_count()` → `get_active_tenants_with_counts()` (+ `product_count`). `get_global_event_count()` supprime. Constante `CATEGORIES_PRODUIT_LIEU_VIVANT = ("B","F","A")`. |
| `seo/tasks.py` | Filtre `lieu_est_vivant` sur `aggregate_lieux` + `sitemap_tenants`. Suppression du bloc `GLOBAL_COUNTS`. Log final reflete `lieux_vivants` au lieu de `lieux totaux`. |
| `seo/views.py` | `landing()` : suppression de `lieux_count`, `events_count`, lecture `GLOBAL_COUNTS`. |
| `seo/templates/seo/landing.html` | Bloc `stats-row` retire. 2 boutons "Voir tous" → `/explorer/`. |

### Migration / Migration
- **Migration necessaire / Migration required :** Non.
- Anciennes entrees `SEOCache(cache_type='global_counts')` deviennent du
  data mort, ignorees a la lecture. Nettoyage automatique au prochain
  refresh ? Non — la step 6 ne supprime que les entrees rattachees a un
  tenant disparu, pas les entrees globales obsoletes. Pas grave : 1 ligne.

## Chantier landing #03 — Marquee scalable + textes V2 + icone cashless + flush cache

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What :** Quatre fixes sur la landing root `/` qui se voyaient
en prod avec 375 tenants ou apres un `flush`.

1. **Marquee "Nos lieux vivants" scalable** : la duree d'animation etait
   figee a 30s dans le CSS. Avec 6 lieux, vitesse ~41 px/sec (lisible).
   Avec 375 lieux, vitesse ~2580 px/sec (illisible, eclair). Fix :
   - `seo/views.py::landing()` calcule `marquee_lieux_duration_sec` pour
     viser ~40 px/sec constants.
   - Liste melangee aleatoirement (`random.shuffle`) a chaque chargement
     pour valoriser tous les lieux du reseau equitablement.
   - Plafonnee a 30 lieux pour ne pas alourdir le DOM (doublee par le
     `{% for copy in "ab" %}`).
   - `seo/static/seo/seo.css` consomme la duree via la CSS variable
     `--marquee-duration` (fallback 30s pour les autres pages).

2. **Textes V2 portes sur la landing** : hero title "Adhesion,
   billetterie, caisse enregistreuse et outils libres et federes"
   (etait "Lieux culturels, billetterie, outils libres et federes").
   Philosophie etoffee (encaisser au bar, boite a outils complete avec
   cashless/caisse/monnaie locale/budget contributif, "une seule carte
   pour plusieurs lieux"). Subheading features "Une solution complete"
   (au lieu de "Une boite a outils"). Source : prototype V2
   `../lespass-main/seo/templates/seo/landing.html`.

3. **Icone cashless invisible** : `bi-contactless` n'existe pas dans
   Bootstrap Icons 1.11.3. La feature card etait sans icone visible
   (width 0, `content: none`). Remplace par `bi-credit-card-2-front`
   (carte bancaire avec puce).

4. **Cache SEO ne se recharge pas apres `flush.sh` / `flush_dev.sh`** :
   la landing root affichait "0 lieux 0 events" tant que Celery beat
   n'avait pas tourne (toutes les 4h). Ajout de
   `python manage.py refresh_seo_cache` en fin de chaque script de flush.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/views.py` | `landing()` : `random.shuffle`, cap 30 lieux, calcul `marquee_lieux_duration_sec` |
| `seo/templates/seo/landing.html` | Hero V2, philosophie V2, subheading V2, `bi-contactless` → `bi-credit-card-2-front`, `style="--marquee-duration: ...s"` sur la track |
| `seo/static/seo/seo.css` | `.marquee-content` lit `var(--marquee-duration, 30s)` |
| `flush.sh` | Ajout `manage.py refresh_seo_cache` apres collectstatic |
| `flush_dev.sh` | Ajout etape 6/6 `manage.py refresh_seo_cache` |

### Migration / Migration
- **Migration necessaire / Migration required :** Non
- Pas de nouvelle chaine `_()` ajoutee — les `{% translate %}` du hero
  V2 ("Adhesion", "billetterie,", "caisse enregistreuse") n'avaient pas
  d'entree dans les `.po`. **makemessages + compilemessages reportes**
  (le francais s'affiche correctement comme fallback).

## Chantier SEO #02 — Review critique + 10 fixes prod / Critical review + 10 prod fixes

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Review critique de la session SEO/FEDERATION par un agent + navigation
Chrome MCP. Score initial 79/100, 10 fixes appliques pour atteindre la qualite
prod :

1. **Critical XSS JSON-LD** : helper `json_for_html()` qui translate `<>&` en
   sequences unicode `< > &`. Empeche qu'un admin tenant qui met
   `</script>` dans son nom de configuration casse le HTML des pages de ses
   voisins (qui consomment le SEOCache).
2. **`<h1>` ajoutes** sur `/federation/` tenant et `/explorer/` public (etaient
   absents, 21+ H3 seulement). Visually-hidden, n'affecte pas l'UI.
3. **Open Graph + Twitter tags** : override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` sur le wrapper `/federation/`
   (etaient au fallback "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** dans settings.py : canonical URLs et JSON-LD
   contiennent maintenant `https://` (etaient en `http://` car Traefik forwarde
   en HTTP au container Django).
5. **N+1 cache landing** : `event_count` lu directement de `AGGREGATE_LIEUX`
   au lieu de 20 appels `get_seo_cache(TENANT_SUMMARY, ...)`.
6. **`_('Local network')`** : navbar label maintenant traduisible (etait
   hardcode).
7. **XML escape sitemap_index** : `xml.sax.saxutils.escape` sur les URLs et
   timestamps (defense en profondeur).
8. **BreadcrumbList shape** : `"item": {"@id": ..., "name": ...}` (forme
   recommandee Google Rich Results, au lieu du string brut qui passe les tests
   mais genere des warnings).
9. **`config.organisation or tenant.name`** : fallback si organisation vide.
10. **`CSS.escape()`** : remplace l'echappement regex maison dans explorer.js,
    avec fallback pour vieux navigateurs.

**EN :** Critical review of the SEO/FEDERATION session by an agent + Chrome MCP
navigation. Initial score 79/100, 10 fixes applied to reach prod quality:

1. **Critical XSS JSON-LD**: `json_for_html()` helper translating `<>&` to
   `< > &` unicode sequences. Prevents a tenant admin who puts
   `</script>` in their configuration name from breaking the HTML of neighbor
   pages (which consume SEOCache).
2. **`<h1>` added** on tenant `/federation/` and public `/explorer/` (were
   missing, 21+ H3 only). Visually-hidden, doesn't affect UI.
3. **Open Graph + Twitter tags**: override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` on the `/federation/` wrapper
   (defaulted to "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** in settings.py: canonical URLs and JSON-LD
   now contain `https://` (were `http://` because Traefik forwards HTTP to
   the Django container).
5. **N+1 cache landing**: `event_count` read directly from `AGGREGATE_LIEUX`
   instead of 20 `get_seo_cache(TENANT_SUMMARY, ...)` calls.
6. **`_('Local network')`**: navbar label now translatable (was hardcoded).
7. **XML escape sitemap_index**: `xml.sax.saxutils.escape` on URLs and
   timestamps (defense in depth).
8. **BreadcrumbList shape**: `"item": {"@id": ..., "name": ...}` (Google Rich
   Results recommended shape, instead of raw string that passes tests but
   generates warnings).
9. **`config.organisation or tenant.name`**: fallback when organisation empty.
10. **`CSS.escape()`**: replaces homemade regex escaping in explorer.js, with
    fallback for legacy browsers.

**Validation** : tous les fixes verifies via curl + Chrome MCP. Helper
`json_for_html()` teste avec input malicieux (`Foo</script><script>alert(1)`)
→ tous les caracteres dangereux echappes.

---

## Chantier SEO #01 — Decouverte LLM/Google du reseau federe / LLM and Google discovery of the federated network

**Date :** 2026-05-13
**Migration :** Oui (`seo/0002_alter_seocache_cache_type.py`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Trois axes pour rendre le reseau TiBillet visible aux LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) et a Google.

1. **Voisins bidirectionnels** : la carte d'un tenant affiche les voisins
   declarations dans les 2 sens. Si X federate avec moi mais que je n'ai pas
   declare X dans mes `FederatedPlace`, X apparait quand meme. Pre-calcul
   cross-schema dans le Celery task `refresh_seo_cache`, stockage en
   `SEOCache.FEDERATION_INCOMING`. La navbar "Reseau local" est desormais
   pilotee uniquement par `config.module_federation`.

2. **JSON-LD federation** : nouvelle helper
   `seo.views_common.build_json_ld_federation()` qui produit un schema.org/
   Organization + `subOrganization` + `memberOf`. Injecte sur `/federation/`
   tenant (racine = tenant, subOrg = voisins federes, memberOf = reseau
   TiBillet) et sur `/explorer/` public (racine = TiBillet, subOrg = tous les
   tenants). Les crawlers no-JS recoivent immediatement la structure du
   reseau sans avoir besoin d'executer Leaflet. Fix collateral : `meta_robots`
   devient un `{% block %}` dans `seo/base.html`.

3. **Quick wins SEO** :
   - `/humans.txt` sur le ROOT public (manquait avant)
   - `/federation/` ajoute au `StaticViewSitemap` tenant
   - Helper `build_json_ld_breadcrumb()` + BreadcrumbList sur `/federation/`

**EN :** Three axes to make the TiBillet network visible to LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) and Google.

1. **Bidirectional neighbors**: a tenant's map shows neighbors declared in
   both directions. If X federates with me but I haven't declared X in my
   `FederatedPlace`, X still appears. Cross-schema pre-computation in the
   `refresh_seo_cache` Celery task, stored in `SEOCache.FEDERATION_INCOMING`.
   The "Local network" navbar is now driven solely by `config.module_federation`.

2. **Federation JSON-LD**: new helper
   `seo.views_common.build_json_ld_federation()` produces a schema.org/
   Organization + `subOrganization` + `memberOf`. Injected on `/federation/`
   tenant (root = tenant, subOrg = federated neighbors, memberOf = TiBillet
   network) and on `/explorer/` public (root = TiBillet, subOrg = all
   tenants). No-JS crawlers immediately receive the network structure without
   executing Leaflet. Collateral fix: `meta_robots` becomes a `{% block %}`
   in `seo/base.html`.

3. **SEO quick wins**:
   - `/humans.txt` on public ROOT (was missing)
   - `/federation/` added to tenant `StaticViewSitemap`
   - `build_json_ld_breadcrumb()` helper + BreadcrumbList on `/federation/`

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod / In-tenant explorer + production-grade JS refactor

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** `/federation/` (Réseau local) sur chaque tenant rend maintenant l'explorer
(carte Leaflet + filtres) avec uniquement le tenant courant + ses FederatedPlace.
Le code de la carte est consolidé en source unique dans `seo/` (JS + CSS + widget
HTML + data builder), partagé avec le public `/explorer/`. Le JS a été refactoré
pour la prod : IIFE encapsulé (zéro pollution `window`), event delegation (zéro
`onclick=` inline), i18n via `data-i18n-*`, garde-fous défensifs (try/catch JSON,
DOM presence), Leaflet vendoré (plus de CDN externe unpkg.com), event Leaflet
`animationend` au lieu de `setTimeout(...,400)`. Marker visuel "Vous êtes ici"
pour le tenant courant.

**EN :** `/federation/` (Local network) on each tenant now renders the explorer
(Leaflet map + filters) limited to the current tenant + its FederatedPlace.
Map code is consolidated as a single source under `seo/` (JS + CSS + widget HTML +
data builder), shared with the public `/explorer/`. The JS has been refactored
for production: encapsulated IIFE (zero `window` pollution), event delegation
(zero inline `onclick=`), i18n via `data-i18n-*`, defensive guards (try/catch
JSON, DOM presence), vendored Leaflet (no external unpkg.com CDN), Leaflet
`animationend` event instead of `setTimeout(...,400)`. Visual "You are here"
marker for the current tenant.

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier M-To-V2 #02 — Port app `seo/` allegee (landing ROOT lieux + events) / Port lightweight `seo/` app

**Date :** 2026-05-13
**Migration :** Oui (`seo/0001_initial.py` sur le schema public)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Portage de l'app `seo` de V2 (lespass-main) vers V1 en version allegee.
On agrege uniquement les **lieux + evenements** du reseau (pas d'adhesions, pas
d'initiatives crowdfunding, pas de monnaies fedow_core). La landing ROOT remplace
l'ancienne redirection MetaBillet vers tibillet.org. Cache 2 niveaux (Memcached
L1 + DB L2) rafraichi toutes les 4h par Celery Beat. 7 routes : `/`, `/lieux/`,
`/evenements/`, `/recherche/`, `/explorer/`, `/robots.txt`, `/sitemap.xml`.

**EN :** Port of the V2 `seo` app to V1 in a lightweight version. Aggregates only
**venues + events** (no memberships, no crowdfunding initiatives, no fedow_core
currencies). The ROOT landing replaces the previous MetaBillet redirect to
tibillet.org. 2-tier cache (Memcached L1 + DB L2) refreshed every 4h by Celery
Beat. 7 routes: `/`, `/lieux/`, `/evenements/`, `/recherche/`, `/explorer/`,
`/robots.txt`, `/sitemap.xml`.

**Fichiers crees :** voir `TECH DOC/SESSIONS/M-To-V2/02-app-seo.md`
**Fichiers modifies :** `TiBillet/settings.py`, `TiBillet/urls_public.py`, `TiBillet/celery.py`

---

## v1.8 — Modules Groupware + refacto admin + proxies Product / Groupware modules + admin refactor + Product proxies

**Date :** 2026-05-13
**Migration :** Oui (`0204_configuration_module_adhesion_and_more`, `0205_futproduct_membershipproduct_posproduct_and_more`)
**Contributeurs / Contributors :** NothRen (Antoine), JonasFW13 (Jonas)

---

### Vue d'ensemble / Overview

**FR :**
Premiere etape d'integration de la V2 (mono-repo TiBillet/Lespass + LaBoutik + Fedow)
dans la V1 actuelle. On introduit la notion de **Groupware** (activation modulaire par
tenant) et on prepare l'admin pour accueillir les nouveaux types de produits (POS, fut)
sans casser la compatibilite. Refacto majeur de `admin_tenant.py` (~1000 lignes
deplacees) en modules separes. Ajout de proxy models pour separer les vues admin par
type de produit. Fix bug timezone sur les filtres datetime de l'admin (#384).

**EN :**
First step of integrating the V2 mono-repo (TiBillet/Lespass + LaBoutik + Fedow)
into the current V1. Introduces the **Groupware** concept (per-tenant modular activation)
and prepares admin for upcoming product types (POS, keg) without breaking compatibility.
Major refactor of `admin_tenant.py` (~1000 lines moved) into separate modules. Adds proxy
models to split admin views by product type. Fixes timezone bug on admin datetime filters (#384).

---

### 1. Modules Groupware : activation par tenant / Groupware modules: per-tenant activation

**FR :**
Ajout de **9 booleens** `module_*` sur `Configuration` pour activer/desactiver des
sections fonctionnelles par tenant. Les modules deja en production sont actives par
defaut (`module_billetterie`, `module_adhesion`, `module_crowdfunding`,
`module_federation`). Les modules V2 a venir sont desactives par defaut
(`module_monnaie_locale`, `module_caisse`, `module_inventaire`, `module_tireuse`,
`module_booking`).

**Dashboard admin** : nouvelles cartes avec switches HTMX et modal de confirmation.
Apres bascule, `HX-Refresh` recharge la page pour mettre a jour la sidebar.
**Sidebar dynamique** : `get_sidebar_navigation(request)` (callable string) construit
la navigation selon les modules actifs.
**NavBar publique** : les liens `/memberships/`, `/event/`, `/federation/`, `/contrib/`
n'apparaissent dans la barre publique que si le module correspondant est actif (cf.
`BaseBillet/views.py:get_context()`).

**Dependance** : `module_caisse` necessite `module_monnaie_locale`. Validation cote
serveur dans `module_toggle()` qui renvoie un message d'erreur via `django.messages` si
on tente de violer cette regle.

**EN :**
Adds **9 module_* booleans** on `Configuration` to enable/disable functional sections
per tenant. Currently-live modules default to True; upcoming V2 modules default to False.
Admin dashboard gets module cards with HTMX switches and a confirmation modal.
Sidebar is now dynamic (`get_sidebar_navigation` callable). Public navbar links only
show if the matching module is active. `module_caisse` requires `module_monnaie_locale`.

---

### 2. Refacto `admin_tenant.py` : split en modules / `admin_tenant.py` refactor: split into modules

**FR :**
`Administration/admin_tenant.py` faisait ~3000 lignes. On extrait :

- `Administration/admin/site.py` — `StaffAdminSite` + `sanitize_textfields` (utilitaire XSS).
- `Administration/admin/dashboard.py` — `get_sidebar_navigation`, `dashboard_callback`,
  `MODULE_FIELDS`, `_build_modules_context`, `adhesion_badge_callback`, `environment_callback`.
- `Administration/admin/products.py` — `ProductAdmin`, `TicketProductAdmin`,
  `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`,
  `ProductFormFieldInline`, palettes/icones POS (commente, pour V2), validation.
- `Administration/admin/prices.py` — `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm`.

`admin_tenant.py` re-exporte les noms publics (`get_sidebar_navigation`, etc.) via
`from Administration.admin.dashboard import ...` pour ne rien casser cote `settings.py`
qui pointe encore sur `Administration.admin_tenant.get_sidebar_navigation`.

**EN :**
Splits the ~3000-line `admin_tenant.py` into 4 modules under `Administration/admin/`.
Public names re-exported from the original module to keep `settings.py` references valid.

---

### 3. Proxy models Product : 4 vues admin filtrees / Product proxy models: 4 filtered admin views

**FR :**
Sans toucher a la table `BaseBillet_product`, on cree **4 proxy models** :
- `TicketProduct` — filtre `categorie_article IN ('B', 'F')` (Billet, FreeRes).
- `MembershipProduct` — filtre `categorie_article = 'A'` (Adhesion).
- `POSProduct` — filtre `methode_caisse IS NOT NULL` (V2, admin commente).
- `FutProduct` — filtre `categorie_article = 'U'` (V2, admin commente).

Chaque proxy a son propre `ModelAdmin` avec un formulaire restreint et un `get_queryset`
filtre. La sidebar affiche separement "Ticket products" (section Billetterie) et
"Membership products" (section Adhesions). Le `ProductAdmin` original reste enregistre
pour preserver les autocomplete `EventAdmin` et les URLs existantes.

`MembershipProductAdmin` recupere `ProductFormFieldInline` (formulaires dynamiques pour
adhesions). `TicketProductAdmin` ne l'a pas (champs dynamiques inutiles pour la billetterie).

**EN :**
Adds 4 proxy models filtered by product type. Each has its own admin with a restricted
form and filtered queryset. Original `ProductAdmin` is kept to preserve existing URLs
and autocomplete behavior in `EventAdmin`.

---

### 4. Champs conditionnels dans les inlines / Conditional fields in inlines

**FR :**
Unfold supporte `conditional_fields` au niveau ModelAdmin mais **pas** au niveau inline.
Pour le besoin "afficher `iteration` seulement si `recurring_payment` coche" sur l'inline
`MembershipPriceInline`, on ajoute un systeme generique :

- Chaque `Inline` declare un dict `inline_conditional_fields = {"champ": "expression"}`.
- `MembershipProductAdmin.changeform_view()` collecte ces dicts et les injecte en JSON
  via `extra_context["inline_conditional_rules"]`.
- Template `admin/product/inline_conditional_fields.html` rend le JSON dans
  `<script id="inline-conditional-rules" type="application/json">`.
- JS `Administration/static/admin/js/inline_conditional_fields.js` lit le JSON, ecoute
  les `change`/`input` sur les sources, applique cascade (source cachee = condition fausse),
  anime apparition/disparition, observe les nouvelles lignes inline (MutationObserver).

Expressions supportees : `champ == true`, `champ == false`, `champ > N`.

**EN :**
Generic conditional-field system for Django admin inlines (Unfold doesn't support
`conditional_fields` on inlines). Each inline declares `inline_conditional_fields`,
the changeform view collects them and injects JSON, JS reads the JSON, listens on
sources, handles cascade, animates show/hide, observes new inline rows.

---

### 5. Fix bug timezone sur les filtres datetime admin (#384) / Fix timezone bug on admin datetime filters (#384)

**FR :**
`RangeDateTimeFilter` (Unfold) parsait les bornes saisies dans le filtre admin sans
tenir compte de la timezone du tenant, ce qui entrainait des decalages d'une heure sur
les filtrages d'historique. Nouveau filtre `RangeDateTimeFilterWithTimeZone` qui :

1. Recupere la timezone du tenant via `Configuration.get_solo().get_tzinfo()`.
2. Localise les `datetime` parses avec `new_timezone.localize(...)` avant le filtrage.
3. Retourne `None` proprement en cas d'erreur de parsing.

Applique sur `LigneArticleAdmin` et `LigneArticlePosAdmin`.

**EN :**
Fixes one-hour offset in admin datetime range filters by localizing parsed datetimes
with the tenant's timezone (`Configuration.get_solo().get_tzinfo()`).

---

### 6. Fix divers / Miscellaneous fixes

**FR :**
- **Subscription duration** (commit 32e035e2, NothRen) : interdit la creation d'un
  `Price` avec `recurring_payment=True` mais `subscription_type=NA`. Validation cote
  serveur dans `MembershipPriceInlineForm.clean_subscription_type()`.
- **`SyntaxWarning: "is" with a literal`** (commit 5ddeb7ca, JonasFW13) : remplace
  `field_name is "module_caisse"` par `field_name == "module_caisse"` dans
  `module_toggle()`. Le `is` ne doit pas etre utilise pour comparer des strings.
- **`poids` → "Display order"** (commit 0cce7f1b, NothRen) : renomme le `verbose_name`
  pour clarifier le sens metier ("ordre d'affichage", plus petit = en premier). La colonne
  DB reste `poids`.
- **Doc technique V1-to-V2 + Stripe Checkout fix** (commit 1a3f2c0f, JonasFW13) :
  ajout de `TECH DOC/SESSIONS/M-To-V2/INDEX.md` et
  `Administration/Unfold_docs/stripe-checkout-account-business-name.md`.

**EN :**
- Subscription duration validation: `recurring_payment=True` requires `subscription_type != NA`.
- Replaces `is` with `==` for string comparison (PEP 8).
- Renames `poids` verbose_name to "Display order" for clarity.
- Adds technical migration docs.

---

### 7. NavBar publique conditionnelle / Conditional public navbar

**FR :**
Dans `BaseBillet/views.py:get_context()`, les liens publics `/memberships/`, `/event/`,
`/federation/` et `/contrib/` n'apparaissent dans `main_nav` que si le module correspondant
est actif. Avant : ces liens etaient toujours visibles, meme si la fonctionnalite etait
desactivee (404 a la cle).

**EN :**
Public navbar links are now conditional on the matching module flag.

---

### 8. `DATETIME_INPUT_FORMATS` ajoute aux settings / `DATETIME_INPUT_FORMATS` added to settings

**FR :**
Ajout de plusieurs formats de saisie datetime (FR `dd/mm/yyyy hh:mm`, ISO
`yyyy-mm-dd hh:mm:ss`, etc.) pour que les formulaires admin acceptent les variantes
courantes lors du parsing manuel des dates.

**EN :**
Adds several datetime input formats (FR and ISO variants) for admin form parsing.

---

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | +9 champs `module_*` sur `Configuration`, +4 proxy models (`TicketProduct`, `MembershipProduct`, `POSProduct`, `FutProduct`), +`RECHARGE_CASHLESS_FED` et `FUT` dans `CATEGORIE_ARTICLE_CHOICES`, renommage `poids` verbose_name |
| `BaseBillet/migrations/0204_configuration_module_adhesion_and_more.py` | Migration des 9 booleens `module_*` |
| `BaseBillet/migrations/0205_futproduct_membershipproduct_posproduct_and_more.py` | Migration des 4 proxy models |
| `BaseBillet/views.py` | NavBar publique conditionnelle aux modules dans `get_context()` |
| `Administration/admin_tenant.py` | Refacto majeur (~1000 lignes deplacees), re-export des symboles publics, ajout `module_toggle_modal` / `module_toggle`, dependance `module_caisse` ↔ `module_monnaie_locale`, nouveau `RangeDateTimeFilterWithTimeZone` |
| `Administration/admin/__init__.py` | Nouveau (package) |
| `Administration/admin/site.py` | Nouveau : `StaffAdminSite`, `sanitize_textfields` |
| `Administration/admin/dashboard.py` | Nouveau : `get_sidebar_navigation` (sidebar dynamique), `dashboard_callback`, `MODULE_FIELDS`, `_build_modules_context` |
| `Administration/admin/products.py` | Nouveau : `ProductAdmin` + proxy admins `TicketProductAdmin` / `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`, `ProductFormFieldInline`, code POS commente pour V2 |
| `Administration/admin/prices.py` | Nouveau : `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm` |
| `Administration/templates/admin/index.html` | `+include "admin/dashboard.html"` (cartes modules) |
| `Administration/templates/admin/dashboard.html` | Nouveau : grille de cartes modules avec switches HTMX |
| `Administration/templates/admin/dashboard_module_modal.html` | Nouveau : modal de confirmation pour bascule module |
| `Administration/templates/admin/product/inline_conditional_fields.html` | Nouveau : injection JSON des regles conditionnelles |
| `Administration/static/admin/js/inline_conditional_fields.js` | Nouveau : 400 lignes JS, gestion cascade + animation + MutationObserver |
| `Administration/static/admin/css/price_inline.css` | Nouveau : style des titres `StackedInline` (scope `#prices-group`) |
| `TiBillet/settings.py` | `SIDEBAR.navigation` → callable string, ancien dump renomme `SIDEBAR-TEMP-OLD` (a supprimer plus tard), `+DATETIME_INPUT_FORMATS` |
| `PaiementStripe/views.py` | Branche `elif 'account or business name'` (fix v1.7.18, deja documente) |
| `VERSION` | `VERSION=1.8`, `MIGRATE=1` |
| `locale/fr/LC_MESSAGES/django.{po,mo}` | +1500 lignes (modules, proxies, validations) |
| `locale/en/LC_MESSAGES/django.{po,mo}` | +1500 lignes |
| `TECH DOC/SESSIONS/M-To-V2/INDEX.md` | Nouveau : doc technique V1-to-V2 |
| `Administration/Unfold_docs/stripe-checkout-account-business-name.md` | Nouveau : explication + fix Stripe Checkout |

### Migration
- **Migration necessaire / Migration required:** Oui — `MIGRATE=1` dans `VERSION`.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- Les nouveaux booleens ont des `default` : aucun risque sur les tenants existants. Les
  modules deja en production (`billetterie`, `adhesion`, `crowdfunding`, `federation`)
  sont actives par defaut.

### Compatibilite / Compatibility
- **Coexistence V1/V2** : carte "Caisse V2" du dashboard est grisee si `server_cashless`
  est configure (= ancien tenant en V1). Les modules V2 (`monnaie_locale`, `caisse`,
  `inventaire`, `tireuse`, `booking`) restent desactives.
- **`SIDEBAR-TEMP-OLD`** dans `settings.py` : ancien dump conserve commente pour reference,
  a supprimer apres une periode de stabilisation.
- **Code POS/Fut/Categorie** dans `Administration/admin/products.py` : commente bloc par
  bloc (`FROM V2 : TODO`), reactive quand on integre l'app `laboutik` et `inventaire`.

### i18n
- ~1500 lignes ajoutees/modifiees dans `locale/{fr,en}/LC_MESSAGES/django.po`.
- `compilemessages` deja execute (les `.mo` sont a jour dans le commit).

---

## v1.7.18 — Fix 500 sur compte Stripe Connect sans nom commercial / Fix 500 on Stripe Connect account missing business name

**Date :** 2026-05-12
**Migration :** Non

---

### Gestion gracieuse de `account or business name` (Stripe Checkout) / Graceful handling of `account or business name` (Stripe Checkout)

**FR :**
Quand un tenant tente de creer une session Stripe Checkout (adhesion, reservation) alors
que son compte Stripe Connect n'a pas de nom commercial configure, Stripe leve
`InvalidRequestError: In order to use Checkout, you must set an account or business name`.

Avant : l'erreur tombait dans le fallback `else` de `_checkout_session()` qui retentait
betement avec `force=True` sur les line_items (corrige rien) → l'exception bubblait jusqu'a
la vue → **500** pour l'utilisateur final.

Apres : le cas est detecte explicitement, on logge le `schema_name` du tenant concerne pour
que l'admin sache ou intervenir, et on leve `serializers.ValidationError` avec un message
generique. Le `MembershipMVT.create()` (et autres ViewSets qui consomment `is_valid()` sans
`raise_exception=True`) recoit l'erreur dans `.errors`, l'affiche via `django.messages`, et
redirige proprement vers le `Referer`.

**EN :**
When a tenant tries to create a Stripe Checkout session while its Connect account is
missing a business name, Stripe raises `InvalidRequestError`. The error used to fall into
the `else` fallback that retried with `force=True` on line_items — useless, since the
issue is on the account side. Now caught explicitly: we log the tenant schema_name and
raise a user-friendly `ValidationError`. No more 500, the user sees a clear message.

### Decision : pas de patch preventif cote Lespass / Decision: no preventive patch on Lespass side

**FR :**
On a envisage de pre-remplir `business_profile.name` dans
`Configuration.get_stripe_connect_account()` (BaseBillet/models.py) pour que les nouveaux
tenants n'aient jamais l'erreur. **Decision finale : non.** Le bug racine est gere
**cote Stripe** (le gerant doit completer son `business_profile.name` lors du onboarding,
le dashboard Stripe le demande explicitement). Cote Lespass, on se contente donc de :

1. Faire remonter l'erreur a l'utilisateur final via `serializers.ValidationError`
   (message generique).
2. Logger en `ERROR` avec le `schema_name` du tenant pour que Sentry remonte l'incident
   et que l'admin sache ou intervenir.

`Configuration.get_stripe_connect_account()` reste donc inchange : il cree le compte avec
seulement `type="standard"` et `country="FR"`. C'est volontaire.

**Tenants existants deja sans nom commercial :** ils doivent fixer manuellement via
dashboard Stripe ou `stripe accounts update <acct_id> -d "business_profile[name]=..."`.

**EN :**
We considered pre-filling `business_profile.name` in
`Configuration.get_stripe_connect_account()` so that new tenants would never hit the error.
**Final decision: no.** The root cause is handled on the Stripe side (tenant admins now
explicitly fill `business_profile.name` during Connect onboarding). On Lespass we just
surface the error to the user and log it in Sentry.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `PaiementStripe/views.py` | Nouveau branch `elif 'account or business name'` dans `CreationPaiementStripe._checkout_session()` (avant le fallback retry). Loggue l'erreur avec le `schema_name` du tenant (visible dans Sentry), leve `ValidationError` avec un message generique. |

### Migration
- **Migration necessaire / Migration required:** Non

### i18n
Une nouvelle chaine traduisible ajoutee :
- `"Online payment is temporarily unavailable. Please contact the site administrator."`

A executer : `makemessages -l fr -l en` puis `compilemessages`.

---

## v1.7.17 — Améliorations SEO home Faire Festival + humans.txt / SEO improvements on Faire Festival home + humans.txt

**Date :** 2026-05-05
**Migration :** Non

---

### Améliorations SEO sur la home du skin Faire Festival / SEO improvements on Faire Festival skin home

**FR :**
Suite à l'audit RoastMyUrl sur `fairefestival.fr` (score 69/100), correction des points SEO
sur la home du skin Faire Festival :

- **Title trop court (24 char)** : enrichi en `Festival du Faire — Toulouse, 28-30 mai 2026 | <organisation>` (61 char). Inclut désormais les mots-clés métier (`Festival`, `Faire`), géo (`Toulouse`) et la date.
- **Meta description courte (113 char)** : étendue à 158 char avec `fablabs`, `22 thématiques`, et la date.
- **og:title / twitter:title** : alignés sur le nouveau title.
- **og:description / twitter:description** : alignées sur la meta description longue.
- **Bug HTML** : 3 balises `<h3>` étaient fermées par `</h4>` (typo lors du merge `template-faire-festival`). Corrigées en `</h3>`.
- **Hiérarchie H2** : la baseline `Le grand rendez-vous toulousain...` était dans un `<p>`. Passée en `<h2>` (classes Bootstrap conservées, rendu visuel identique). On passe de 1 H2 à 2 H2.
- **Alts d'images génériques** (`Billets`, `Programmation`, `Faire Festival`) : enrichis pour le SEO et l'accessibilité (`Prendre vos billets pour le Faire Festival`, `Programmation du Faire Festival : 22 thématiques`, `Infos pratiques du Faire Festival, 28-30 mai`).

**EN :**
Following the RoastMyUrl audit on `fairefestival.fr` (score 69/100), SEO fixes on the Faire
Festival skin home:

- Title extended from 24 to 61 char with geo + date keywords.
- Meta description extended to 158 char with metier keywords.
- og/twitter title and description aligned.
- Fixed 3 `<h3>` tags closed with `</h4>` (typo from the merge).
- Tagline `<p>` upgraded to `<h2>` for proper heading hierarchy.
- Generic image alts replaced with descriptive ones.

### Ajout de humans.txt dynamique / Dynamic humans.txt added

**FR :**
Ajout d'un endpoint `/humans.txt` dynamique au standard [humanstxt.org](https://humanstxt.org/Standard.html).
Crédite la Coopérative Code Commun comme équipe de développement. Le contenu est identique
pour tous les tenants (même réponse quel que soit le `Host`). La version et la date du
dernier bump sont lues depuis le fichier `VERSION` à la racine.

**EN :**
Added a dynamic `/humans.txt` endpoint following the [humanstxt.org standard](https://humanstxt.org/Standard.html).
Credits Coopérative Code Commun as the dev team. Same content for all tenants. Version
and last update date read from the root `VERSION` file.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/faire_festival/views/home.html` | Title / og / twitter enrichis ; meta description étendue ; fix `<h3>...</h4>` ×3 ; baseline `<p>` → `<h2>` ; alts d'images enrichis |
| `BaseBillet/views_humans.py` | **Nouveau** — vue `humans_txt`, parse le fichier `VERSION` (version + mtime) au chargement du module |
| `BaseBillet/urls.py` | Import `humans_txt` + route `path('humans.txt', humans_txt, name='humans_txt')` |

### Migration
- **Migration necessaire / Migration required:** Non

### À faire en config admin / Admin config TODO (no code)
Pour activer pleinement le SEO en prod sur `fairefestival.fr` :
- Uploader la social card sur `Configuration > img` (1200×630 → génère `og:image`)
- Renseigner `Configuration > facebook` / `instagram` / `twitter` (alimente `JSON-LD sameAs`)
- Compléter `Configuration > postal_address` (alimente `JSON-LD address`)

### À faire i18n / i18n TODO
Les nouvelles chaînes (`Festival du Faire — Toulouse, 28-30 mai 2026`, meta description longue,
3 alts enrichis) sont en `{% translate %}` mais pas encore dans les `.po`. À traiter dans
une session de traduction dédiée (`makemessages` + `compilemessages`).

---

## Unreleased — Fix message trompeur sur reservation gratuite anonyme / Misleading message on anonymous free booking

**Date :** 2026-04-21
**Migration :** Non

---

### Correction de la page de confirmation de reservation gratuite / Free booking confirmation page fix

**FR :**
Lorsqu'un visiteur non connecte reservait une activite gratuite avec l'email d'un compte
deja existant et actif, la page de confirmation affichait « Veuillez valider votre e-mail »
alors que les billets etaient deja envoyes (resa en `FREERES_USERACTIV`) et que la
reservation etait confirmee en back-office.

Cause : la vue `EventViewset.reservation` passait `request.user` au template. Quand le
visiteur n'est pas connecte, `request.user` vaut `AnonymousUser` dont `is_active` est
toujours `False`. Le template basculait alors sur la branche « validez votre email »
en ignorant l'etat reel de l'user retrouve en base par email.

Fix : passer `validator.reservation.user_commande` au template. Cet user est celui
resolu par `get_or_create_user(email)` dans le validator, donc coherent avec la
decision prise par `TicketCreator.method_F` pour envoyer (ou non) les billets
immediatement.

**EN :**
When an unauthenticated visitor booked a free activity using the email of an
already-existing active account, the confirmation page showed "Please validate your
e-mail" even though the tickets were already sent and the booking was confirmed.

Root cause: the view passed `request.user` (an `AnonymousUser` with `is_active=False`)
to the template. Fix: pass `validator.reservation.user_commande` instead — the user
resolved by the validator from the submitted email.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventViewset.reservation` : passe `validator.reservation.user_commande` au template au lieu de `request.user` |

### Migration
- **Migration necessaire / Migration required:** Non

---

## v1.7.7 — Unification actions admin Membership dans MembershipMVT

**Date :** Mars 2026
**Migration :** Non

---

### Unification des actions admin sur les adhésions / Membership admin actions unified

**FR :**
Les actions admin sur les adhésions sont désormais centralisées dans `MembershipMVT` (viewset DRF),
exposées via HTMX dans un panneau inline affiché avant le formulaire admin.

- **Supprimé** : `actions_detail` / `actions_row` Unfold dans `MembershipAdmin` (5 méthodes `@action`)
- **Supprimé** : `has_custom_actions_row_permission`, `has_custom_actions_detail_permission`
- **Supprimé** : templates orphelins `cancel_confirm.html` et `ajouter_paiement.html`
- **Ajouté** : `change_form_before_template = "admin/membership/actions_panel.html"` sur `MembershipAdmin`
- **Ajouté** : 3 nouvelles actions dans `MembershipMVT` : `send_invoice`, `ajouter_paiement`, `cancel`
- **Ajouté** : `PaiementHorsLigneSerializer` dans `BaseBillet/validators.py`
- **Ajouté** : 4 nouveaux partials HTMX dans `admin/membership/partials/`

**EN :**
Admin actions on memberships are now centralised in `MembershipMVT` (DRF viewset),
exposed via HTMX in an inline panel displayed before the admin change form.

**Fichiers modifiés :**
- `BaseBillet/validators.py` : + `PaiementHorsLigneSerializer`
- `BaseBillet/views.py` : + imports `get_or_create_price_sold`, `dec_to_int`, `reverse`, `PaiementHorsLigneSerializer` + 3 actions + update `get_permissions`
- `Administration/admin_tenant.py` : - 5 `@action` Unfold + enrichissement `changeform_view` + `change_form_before_template`
- `Administration/templates/admin/membership/actions_panel.html` : Nouveau — panneau HTMX
- `Administration/templates/admin/membership/partials/send_invoice_success.html` : Nouveau
- `Administration/templates/admin/membership/partials/cancel_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_success.html` : Nouveau

---

## v1.7.6 — Skin Faire Festival + Corrections UX et Sentry

**Date :** Mars 2026
**Migration :** Non

---

### 1. Skin Faire Festival — ameliorations CSS et templates / Faire Festival skin — CSS and template improvements

**FR :**
Ameliorations du skin "Faire Festival" suite aux retours terrain :
- Bordures arrondies (`border-radius`) sur les cartes et le bouton burger mobile
- Titres des evenements en police mono, taille reduite, avec `hyphens: auto`
- Bordure image evenement epaissie (1px → 3px)
- Badge de date repositionne (`margin-left: 0` au lieu de -100px)
- Padding horizontal des cartes ajuste

**EN:**
Improvements to the "Faire Festival" skin based on field feedback:
- Rounded borders (`border-radius`) on cards and mobile burger button
- Event titles in mono font, smaller size, with `hyphens: auto`
- Event image border thickened (1px → 3px)
- Date badge repositioned (`margin-left: 0` instead of -100px)
- Card horizontal padding adjusted

**Fichiers / Files:**
- `BaseBillet/static/faire_festival/css/faire_festival.css`

---

### 2. Lazy-load video sur la page d'accueil / Video lazy-load on homepage

**FR :**
La video motion-table de la page d'accueil bloquait le chargement sur Firefox mobile.
Remplacement de `autoplay` + `src` par un mecanisme `IntersectionObserver` :
la video n'est telechargee et lue que lorsqu'elle entre dans le viewport.
`preload="none"` empeche tout telechargement au chargement initial de la page.

**EN:**
The motion-table video on the homepage was blocking page load on Firefox mobile.
Replaced `autoplay` + `src` with an `IntersectionObserver` mechanism:
the video is only downloaded and played when it enters the viewport.
`preload="none"` prevents any download on initial page load.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/home.html`

---

### 3. Description adhesion en accordeon intelligent / Smart collapsible membership description

**FR :**
La description longue de la page d'adhesion est desormais tronquee automatiquement
si elle depasse ~10-12 lignes (250px). Un bouton "Lire la suite" / "Reduire" apparait.
Si la description est courte, elle s'affiche en entier sans bouton.

**EN:**
The long description on the membership page is now automatically truncated
if it exceeds ~10-12 lines (250px). A "Read more" / "Show less" button appears.
If the description is short, it displays fully without a button.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/membership/list.html`

---

### 4. Filtre par date sur la page evenements / Date filter on events page

**FR :**
Le dropdown "Trier par date" etait present dans le template mais non branche cote back.
Le parametre `?date=` est maintenant lu par la vue `list()`, et le dict `dated_events`
est filtre pour n'afficher que les evenements de la date selectionnee.
Le dropdown conserve toutes les dates disponibles meme quand un filtre est actif.
Le bouton affiche la date selectionnee en format lisible ("lundi 15 mars").

**EN:**
The "Sort by date" dropdown was present in the template but not wired to the backend.
The `?date=` parameter is now read by the `list()` view, and the `dated_events` dict
is filtered to display only events for the selected date.
The dropdown keeps all available dates even when a filter is active.
The button shows the selected date in readable format ("Monday March 15").

**Fichiers / Files:**
- `BaseBillet/views.py` — `EventMVT.list()` : lecture param `date`, filtrage du dict
- `BaseBillet/templates/faire_festival/views/event/list.html` — affichage date active, format ISO dans les liens

---

### 5. Correction erreur Sentry : confirmation email reservation expiree / Fix Sentry error: expired reservation email confirmation

**FR :**
Quand un utilisateur confirmait son email plus de 15 minutes apres une reservation gratuite
et que l'evenement etait presque complet, le signal levait un `ValueError` qui remontait
en `Http404` generique. L'utilisateur voyait une page 404 sans explication.
Desormais le `ValueError` est intercepte dans `emailconfirmation()` et le message
est affiche a l'utilisateur via `django.messages` sur la page d'accueil.
Les messages d'erreur sont maintenant traduits via `_()`.

**EN:**
When a user confirmed their email more than 15 minutes after a free reservation
and the event was nearly full, the signal raised a `ValueError` that surfaced
as a generic `Http404`. The user saw a 404 page with no explanation.
Now the `ValueError` is caught in `emailconfirmation()` and the message
is displayed to the user via `django.messages` on the homepage.
Error messages are now translated via `_()`.

**Fichiers / Files:**
- `BaseBillet/views.py` — `emailconfirmation()` : catch `ValueError` separement
- `BaseBillet/signals.py` — `activator_free_reservation()` : messages avec `_()`

---

### 6. Section produits retiree de la page evenement / Products section removed from event detail page

**FR :**
La section "Tickets and prices" a ete retiree de la page detail evenement du skin Faire Festival.
Le label "Intervenant-e-s" en dur a egalement ete supprime.

**EN:**
The "Tickets and prices" section was removed from the event detail page of the Faire Festival skin.
The hardcoded "Intervenant-e-s" label was also removed.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/event/retrieve.html`

---

### 7. Correction calcul paiement adhesion sans contribution / Fix membership payment calculation without contribution

**FR :**
Correction d'un crash quand `contribution_value` etait absente lors du calcul
du montant de paiement d'une adhesion. La valeur manquante est maintenant traitee gracieusement.

**EN:**
Fixed a crash when `contribution_value` was missing during membership payment amount calculation.
The missing value is now handled gracefully.

**Fichiers / Files:**
- Commit `50132e35`

---

### Autres ameliorations / Other improvements

- **Admin breadcrumb** : affiche le nom du produit au lieu du nom du tarif dans le fil d'Ariane
- **Admin product archive filter** : filtre pour afficher/masquer les produits archives
- **Redirect tarif → produit** : retour automatique vers le produit parent apres sauvegarde d'un tarif
- **Widget adhesions obligatoires** : passage en `MultipleHiddenInput`
- **Integration Fedow** : gestion d'erreur non-bloquante lors de la creation d'assets et validation d'adhesion
- **Newsletter** : ajout de l'URL newsletter dans le skin
- **Traductions** : nouvelles chaines FR/EN pour les filtres, messages d'erreur, et boutons

**Migration necessaire / Migration required:** Non

---

## v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

**Date :** Mars 2026
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 0. Protection doublon paiement adhesion (SEPA) / Duplicate membership payment protection (SEPA)

**FR :**
Quand un utilisateur cliquait plusieurs fois sur le lien de paiement d'adhesion
(recu par email apres validation admin), un nouveau checkout Stripe etait cree a chaque clic.
Cela pouvait entrainer des **doubles prelevements SEPA** (signaie en production).

La vue `get_checkout_for_membership` verifie maintenant si un paiement Stripe existe deja :
- **Session Stripe encore ouverte** : reutilise l'URL existante (pas de doublon).
- **Session "complete" (SEPA en cours)** : affiche une page d'information expliquant
  que le prelevement est en cours de traitement (jusqu'a 14 jours).
- **Session expiree** : cree un nouveau checkout normalement.

**EN:**
When a user clicked multiple times on the membership payment link
(received by email after admin validation), a new Stripe checkout was created each time.
This could cause **duplicate SEPA debits** (reported in production).

The `get_checkout_for_membership` view now checks for an existing Stripe payment:
- **Stripe session still open**: reuses the existing URL (no duplicate).
- **Session "complete" (SEPA pending)**: displays an info page explaining
  the debit is being processed (up to 14 days).
- **Session expired**: creates a new checkout normally.

**Fichiers / Files:**
- `BaseBillet/views.py` — protection doublon dans `get_checkout_for_membership`
- `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` — nouveau template

**Migration necessaire / Migration required:** Non

---

### 1. Avoir comptable (credit note) sur les ventes / Credit note on sales

**FR :**
Les admins peuvent emettre un **avoir** sur une ligne de vente depuis l'admin (bouton "Avoir" dans la liste des ventes).
Un avoir cree une ligne miroir avec quantite negative pour annuler comptablement la vente,
sans supprimer l'ecriture originale (conformite fiscale francaise).
Gardes : uniquement sur lignes confirmees ou payees, et un seul avoir par ligne.
L'avoir est envoye a LaBoutik si un serveur cashless est configure.
L'export CSV inclut une colonne "Ref. avoir" pour la tracabilite.

**EN:**
Admins can issue a **credit note** on a sale line from the admin (row action button in the sales list).
A credit note creates a mirror line with negative quantity to cancel the sale for accounting purposes,
without deleting the original entry (French fiscal compliance).
Guards: only on confirmed or paid lines, and only one credit note per line.
The credit note is sent to LaBoutik if a cashless server is configured.
CSV export includes a "Credit note ref." column for traceability.

**Fichiers / Files:**
- `BaseBillet/models.py` — status `CREDIT_NOTE`, FK `credit_note_for`
- `BaseBillet/signals.py` — transition CREATED → CREDIT_NOTE
- `Administration/admin_tenant.py` — `LigneArticleAdmin.emettre_avoir()`
- `Administration/importers/lignearticle_exporter.py` — colonne export
- `BaseBillet/migrations/0199_credit_note_lignearticle.py`

**Annulation adhesion avec avoir :**
L'action "Annuler" sur une adhesion affiche desormais une page de confirmation.
Si l'adhesion a des lignes de vente payees, l'admin peut choisir "Annuler et creer un avoir".
Les avoirs sont crees pour chaque ligne VALID/PAID liee a l'adhesion.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.cancel()` (GET/POST avec confirmation)
- `Administration/templates/admin/membership/cancel_confirm.html` (nouveau)

---

### 2. Correction annulation reservation admin (cheque, especes) / Fix admin reservation cancellation (non-Stripe)

**FR :**
Quand un admin annulait une reservation creee manuellement (payee par cheque, especes, etc.),
aucune ligne de remboursement ou d'avoir n'etait creee. La reservation passait en "annulee"
sans trace comptable, car `cancel_and_refund_resa` ne cherchait les LigneArticle que via
les `Paiement_stripe` (FK), et les reservations admin n'en ont pas.
Desormais, lors de l'annulation, un avoir (CREDIT_NOTE) est automatiquement cree pour chaque
LigneArticle hors-Stripe (sale_origin=ADMIN) liee a la reservation.
Meme correction pour l'annulation de ticket individuel (`cancel_and_refund_ticket`).

**EN:**
When an admin cancelled a manually created reservation (paid by check, cash, etc.),
no refund or credit note line was created. The reservation was marked as cancelled
with no accounting trace, because `cancel_and_refund_resa` only looked for LigneArticle
via `Paiement_stripe` (FK), and admin reservations don't have one.
Now, upon cancellation, a credit note (CREDIT_NOTE) is automatically created for each
non-Stripe LigneArticle (sale_origin=ADMIN) linked to the reservation.
Same fix for single ticket cancellation (`cancel_and_refund_ticket`).

**Fichiers / Files:**
- `BaseBillet/models.py` — `Reservation._lignes_hors_stripe()`, `Reservation._creer_avoir()`,
  `cancel_and_refund_resa()`, `cancel_and_refund_ticket()`

---

### 3. FK reservation sur LigneArticle / Reservation FK on LigneArticle

**FR :**
Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable a sa reservation
sans dependre de `Paiement_stripe` comme intermediaire.
Avant, les reservations admin (cheque, especes) n'avaient aucun lien vers leurs LigneArticle.
La FK est renseignee dans les 4 flows de creation (front, API v1, API v2, admin).
Une data migration backfill les lignes existantes depuis `paiement_stripe.reservation`.
Les methodes `articles_paid()` et `_lignes_hors_stripe()` utilisent la FK directe
avec fallback sur l'ancien chemin pour compatibilite.

**EN:**
Added a direct FK `LigneArticle.reservation` to link an accounting line to its reservation
without relying on `Paiement_stripe` as intermediary.
Previously, admin reservations (check, cash) had no link to their LigneArticle.
The FK is set in all 4 creation flows (front, API v1, API v2, admin).
A data migration backfills existing lines from `paiement_stripe.reservation`.
`articles_paid()` and `_lignes_hors_stripe()` use the direct FK with legacy fallback.

**Fichiers / Files:**
- `BaseBillet/models.py` — FK `reservation` + simplification `articles_paid()`, `_lignes_hors_stripe()`
- `BaseBillet/validators.py` — `reservation=reservation` (front)
- `ApiBillet/serializers.py` — `reservation=reservation` (API v1)
- `api_v2/serializers.py` — `reservation=reservation` (API v2)
- `Administration/admin_tenant.py` — `reservation=reservation` (admin)
- `BaseBillet/migrations/0200_add_reservation_fk_to_lignearticle.py`
- `BaseBillet/migrations/0201_backfill_lignearticle_reservation.py`

---

### 4. Correction niveau de log API Brevo / Fix Brevo API log level

**FR :**
Quand un admin testait sa cle API Brevo depuis la configuration et que la cle etait invalide,
l'erreur 401 remontait en `logger.error` dans Sentry, polluant les alertes.
C'est une erreur de configuration utilisateur, pas un bug applicatif.
Le niveau de log est passe a `logger.warning`.

**EN:**
When an admin tested their Brevo API key from the configuration and the key was invalid,
the 401 error was logged as `logger.error` in Sentry, polluting alerts.
This is a user configuration error, not an application bug.
Log level changed to `logger.warning`.

**Fichiers / Files:** `Administration/admin_tenant.py` — `BrevoConfigAdmin.test_api_brevo()`

---

### 5. Correction deconnexion automatique apres 3 mois / Fix automatic logout after 3 months

**FR :**
Les utilisateurs etaient deconnectes apres exactement 3 mois, meme s'ils utilisaient le site quotidiennement.
Cause : `SESSION_SAVE_EVERY_REQUEST` n'etait pas defini (defaut Django = `False`),
donc le cookie de session n'etait renouvele que lors de modifications de la session, pas a chaque visite.
Ajout de `SESSION_SAVE_EVERY_REQUEST = True` pour que chaque visite renouvelle le cookie.

**EN:**
Users were logged out after exactly 3 months, even when using the site daily.
Cause: `SESSION_SAVE_EVERY_REQUEST` was not set (Django default = `False`),
so the session cookie was only renewed when the session was modified, not on every visit.
Added `SESSION_SAVE_EVERY_REQUEST = True` so every visit renews the cookie.

**Fichiers / Files:** `TiBillet/settings.py`

---

### 6. Bouton "Ajouter un paiement" sur les adhesions en attente / "Add payment" button on pending memberships

**FR :**
Les admins de lieux recoivent des adhesions remplies en ligne mais payees sur place
(especes, cheque, virement). Ces adhesions restaient bloquees en "attente de paiement"
sans moyen de les valider depuis l'admin.
Nouveau bouton "Ajouter un paiement" sur la page detail d'une adhesion en attente (WP ou AW).
Le formulaire demande le montant et le moyen de paiement, puis declenche toute la chaine :
creation de la ligne de vente, calcul de la deadline, envoi de l'email de confirmation,
transaction Fedow, et notification LaBoutik.

**EN:**
Venue admins receive memberships filled out online but paid on-site
(cash, check, bank transfer). These memberships were stuck in "waiting for payment"
with no way to validate them from the admin.
New "Add payment" button on the detail page of a pending membership (WP or AW).
The form asks for the amount and payment method, then triggers the full chain:
sale line creation, deadline calculation, confirmation email,
Fedow transaction, and LaBoutik notification.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.ajouter_paiement()`
- `Administration/templates/admin/membership/ajouter_paiement.html` (nouveau / new)

---

## v1.6.8 — Corrections Sentry + Import/Export Events

**Date :** Fevrier 2026
**Migration :** Non

---

### 1. Correction boucle infinie sur ProductFormField.save() / Fix infinite loop on ProductFormField.save()

**FR :**
Quand le label d'un champ de formulaire dynamique generait un slug de 64 caracteres ou plus,
la generation de nom unique entrait dans une boucle infinie (le suffixe etait tronque puis identique a chaque tour).
Le serveur finissait par un `SystemExit`.
On utilise maintenant un fragment d'UUID pour garantir l'unicite en un seul essai.

**EN:**
When a dynamic form field label produced a slug of 64+ characters,
the unique name generation entered an infinite loop (the suffix was truncated to the same value each iteration).
The server ended up with a `SystemExit`.
We now use a UUID fragment to guarantee uniqueness in a single attempt.

**Fichiers / Files:** `BaseBillet/models.py` — `ProductFormField.save()`

---

### 2. Correction timeout cashless / Fix cashless ReadTimeout

**FR :**
L'appel HTTP vers le serveur cashless avait un timeout de 1 seconde, trop court en production.
Passe a 10 secondes.

**EN:**
The HTTP call to the cashless server had a 1-second timeout, too short for production.
Increased to 10 seconds.

**Fichiers / Files:** `BaseBillet/tasks.py`

---

### 3. Correction creation de tenant en doublon / Fix duplicate tenant creation

**FR :**
Quand un utilisateur cliquait deux fois sur le lien de confirmation email,
la creation du tenant pouvait echouer car le lien `WaitingConfiguration → tenant` n'etait pas assigne assez tot.
On assigne maintenant le tenant des sa creation, et on ajoute un fallback qui repare le lien si le tenant existe deja.

**EN:**
When a user clicked the email confirmation link twice,
tenant creation could fail because the `WaitingConfiguration → tenant` link was not assigned early enough.
We now assign the tenant immediately after creation, and added a fallback that repairs the link if the tenant already exists.

**Fichiers / Files:** `BaseBillet/validators.py`, `BaseBillet/views.py`

---

### 4. Correction carte perdue 404 / Fix lost_my_card 404

**FR :**
Quand un utilisateur cliquait deux fois sur "carte perdue", le deuxieme appel a Fedow renvoyait un 404
car la carte etait deja detachee. On attrape maintenant cette erreur proprement.

**EN:**
When a user double-clicked "lost my card", the second call to Fedow returned a 404
because the card was already detached. We now catch this error gracefully.

**Fichiers / Files:** `BaseBillet/views.py` — `admin_lost_my_card`, `lost_my_card`

---

### 5. Correction formulaire adhesion admin sans wallet / Fix admin membership form without wallet

**FR :**
Dans l'admin, le formulaire d'adhesion plantait si on validait le numero de carte
sans avoir d'abord renseigne un email valide (attribut `user_wallet_serialized` absent).
On verifie maintenant que le wallet existe avant d'y acceder.

**EN:**
In the admin, the membership form crashed when validating the card number
without first providing a valid email (missing `user_wallet_serialized` attribute).
We now check the wallet exists before accessing it.

**Fichiers / Files:** `Administration/admin_tenant.py` — `MembershipForm.clean_card_number()`

---

### 6. Verification SEPA Stripe avant activation / Stripe SEPA capability check before activation

**FR :**
Activer le paiement SEPA dans la configuration alors que le compte Stripe Connect n'a pas la capacite SEPA
provoquait une erreur au moment du paiement. On verifie maintenant la capacite SEPA via l'API Stripe
au moment de la sauvegarde de la configuration. Si le checkout echoue malgre tout, le SEPA est desactive automatiquement.

**EN:**
Enabling SEPA payment in the configuration while the Stripe Connect account lacked SEPA capability
caused an error at checkout time. We now verify SEPA capability via the Stripe API
when saving the configuration. If checkout still fails, SEPA is automatically disabled.

**Fichiers / Files:** `BaseBillet/models.py` — `Configuration.check_stripe_sepa_capability()`, `PaiementStripe/views.py`

---

### 7. Tri des produits par poids / Product weight ordering

**FR :**
Les prix affiches sur la page evenement ignoraient le poids (`poids`) du produit parent.
Les produits sont maintenant tries par `product__poids`, puis `order`, puis `prix`.

**EN:**
Prices displayed on the event page ignored the parent product's weight (`poids`).
Products are now sorted by `product__poids`, then `order`, then `prix`.

**Fichiers / Files:** `BaseBillet/views.py`

---

### 8. Import/Export CSV des evenements (PR #351) / CSV import/export for events (PR #351)

**FR :**
Contribution de @AoiShidaStr : ajout de l'import/export CSV des evenements depuis l'admin Django.
Ameliore ensuite avec : export de l'adresse postale par nom (pas par ID),
lignes identiques ignorees a l'import, et rapport des lignes ignorees.

**EN:**
Contribution by @AoiShidaStr: added CSV import/export for events from the Django admin.
Then improved with: postal address exported by name (not ID),
unchanged rows skipped on import, and skipped rows reported.

**Fichiers / Files:** `Administration/admin_tenant.py` — `EventResource`

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

---

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

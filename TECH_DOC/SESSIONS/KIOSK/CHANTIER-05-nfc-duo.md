# CHANTIER-05 — NFC duo Android/Pi + DEMO simulateur — Plan

**Goal :** activer le lecteur NFC sur les deux cibles depuis un seul front `/kiosk/` :
- **Android/Cordova** (`type_app=cordova`) → plugin NFC natif (mode `NFCMC`).
- **Pi/desktop** (`type_app=pi|desktop`) → serveur **socket.io local** (`localhost:3000`, mode `NFCLO`),
  fourni par `laboutik_client_pi_desktop_v2/nfcServer.js` (lecteur ACR122U / RC522).
Et un **mode DEMO** avec le **simulateur de cartes** (overlay cliquable) comme LaBoutik.

**Cadre :** le `nfc.js` du kiosk (copié de LaBoutik) gère déjà `NFCMC`/`NFCLO`/`simule()`. Il manque :
socket.io non chargé, mode jamais choisi (lu dans un `localStorage 'laboutik'` absent sur l'origine
serveur), simulateur non déclenché en DEMO.

## Global Constraints
- Subagents SANS git. Pas de `runserver`/`makemessages`. `docker exec lespass_django poetry run ...`.
- Tests `--api-key dummy`. FALC, i18n source FR.
- **Ne pas casser** le parcours existant ni le double-paiement fix (`{once:true}`).

## Task 05 — Brancher le duo + DEMO simulateur

**1. `kiosk/templates/kiosk/base.html`**
- Charger `socket.io` **avant** `nfc.js` : `<script src="{% static 'js/socket.io.min.js' %}"></script>`
  (fichier réel : `www/static/js/socket.io.min.js`).
- Exposer le contexte au JS (pour que `nfc.js` choisisse le mode sans `localStorage`) :
  `<script>window.KIOSK = { type_app: "{{ type_app }}", demo: {{ demo|yesno:"true,false" }} };</script>`
  (placer avant `nfc.js`). `window.DEMO` reste posé comme aujourd'hui.

**2. `kiosk/static/kiosk/js/nfc.js`** — `startLecture(options)` :
- Si `window.DEMO !== undefined` **ou** `options?.simulation === true` → `this.simule()` (overlay cartes) et retour.
- Sinon (hardware) : choisir le mode depuis `type_app` au lieu de `localStorage 'laboutik'` :
  `const mode = (window.KIOSK?.type_app === "cordova") ? "NFCMC" : "NFCLO";` puis `this.gestionModeLectureNfc(mode)`
  et mémoriser `this.modeNfc = mode` (pour `stopLecture`).
- Ne plus lire `localStorage.getItem('laboutik').mode_nfc` (origine serveur = absent). Garder `simuData`
  alimenté par `window.DEMO` (déjà le cas dans le constructeur).
- `NFCLO` inchangé : `io('http://localhost:' + this.socketPort)` (3000), events `nfcStartListening`/`envoieTagId`.

**3. `kiosk/templates/kiosk/sweet_scan_button.html`** : `didOpen` appelle déjà `rfid.startLecture()` ;
avec le point 2, le DEMO déclenche automatiquement l'overlay. **Aucun changement requis** (vérifier).
Optionnel : garder le fallback backdrop→`demoTagIdClient1` ou le retirer (le simulateur le remplace).

**Tests** (`tests/pytest/test_kiosk_flow.py`, compléter) :
- En `DEMO=True`, le rendu de `select_amount`/`base` contient `window.DEMO`, charge `nfc.js` et `socket.io`.
- Le contexte expose `type_app` et les 4 tags DEMO.
- (Le clic simulateur = test manuel navigateur / E2E — documenter.)

## Doc
- Mettre à jour `kiosk/README.md` §5.4 (NFC Pi) : le duo est branché, réutiliser `laboutik_client_pi_desktop_v2`
  (`type_app=pi`, `RFID_TYPE`), plus de « à finaliser ».
- `A TESTER et DOCUMENTER/kiosk-tpe-borne.md` : ajouter le scénario DEMO simulateur (clic carte).

## Fin de chantier : review + correction Fable 5.

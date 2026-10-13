# Caisse : page « Téléchargez l'application » au lieu du refus JSON / POS: "Download the app" page instead of the JSON refusal

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** quand `GET /laboutik/caisse/` est refusé, la caisse affiche une page HTML (statut 403) avec un QR code vers l'application Android, un lien cliquable vers le téléchargement et le lien vers la documentation, au lieu de `{"detail": "Missing LaBoutik API key or admin session."}`.
/ A denied `GET /laboutik/caisse/` now shows an HTML page (403) with a QR code to the Android app, a clickable download link and the documentation link, instead of the DRF JSON.

**Pourquoi / Why :** un humain qui ouvre la caisse dans un navigateur sans droit (non connecté, pas admin du lieu, superuser hors `client_admin`, terminal d'un autre lieu) tombait sur un JSON incompréhensible. La caisse s'ouvre depuis l'application : on lui donne le moyen de l'installer.
/ A human opening the POS in a browser without rights got an unreadable JSON; the POS is meant to run in the app, so we point to it.

Seule la page d'accueil (`CaisseViewSet.list`) est concernée. Les autres routes de la caisse gardent le refus DRF habituel.
/ Only the home page is affected; other POS routes keep the DRF refusal.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Constantes `URL_DE_TELECHARGEMENT_APPLICATION_ANDROID` / `URL_DOCUMENTATION_APPLICATION_ANDROID`, surcharge `CaisseViewSet.handle_exception()` (QR code SVG généré par `segno`) |
| `laboutik/templates/laboutik/views/telecharger_application.html` | Nouveau gabarit autonome, sans JavaScript |
| `tests/pytest/test_caisse_page_telecharger_application.py` | 5 tests (anonyme, connecté non admin, contenu de la page, admin inchangé, autres routes inchangées) |

i18n : 5 nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — visiteur sans droit
1. Navigation privée → `https://lespass.tibillet.localhost/laboutik/caisse/` (lieu V2, module caisse actif).
2. Attendu : la page « Téléchargez l'application pour Android. », un QR code, un bouton « Télécharger l'application », le lien de documentation.
3. Scanner le QR code avec un téléphone → ouvre `https://nuage.codecommun.coop/s/SdcdkDcWYRPETpf`.
4. Cliquer le bouton → même lien. Cliquer le lien de documentation → notes.liiib.re.

### Test 2 — affichage mobile
1. Ouvrir la même URL sur un téléphone (ou DevTools en mode mobile, 390 px).
2. Attendu : le QR code tient dans l'écran, le bouton est cliquable, le lien de documentation passe à la ligne sans déborder.

### Test 3 — admin du lieu (non-régression)
1. Se connecter avec `admin@admin.com` → dashboard admin → carte « Caisse & Restaurant » → « Open POS ».
2. Attendu : l'écran d'attente de la carte primaire, comme avant.

### Test 4 — superuser hors `client_admin`
1. Se connecter avec un superuser qui n'est pas admin du lieu → « Open POS ».
2. Attendu : la page de téléchargement (et non plus le JSON).

### Verifs automatiques
- `make test ARGS="tests/pytest/test_caisse_page_telecharger_application.py"`

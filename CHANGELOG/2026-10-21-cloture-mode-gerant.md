# Clôture des caisses réservée au mode gérant, écran du Z épuré / Register closure restricted to manager mode, bare Z screen

**Date :** 2026-10-21
**Migration :** Non

## Resume / Summary
**Quoi / What :** À la caisse, seule une carte primaire en mode gérant (`CartePrimaire.edit_mode`) peut clôturer toutes les caisses, depuis n'importe quel point de vente, même s'il ne lui est pas lié. Une carte sans mode gérant voit un bouton désactivé « Clôture réservée au mode gérant » ; si elle envoie quand même la demande, le refus s'affiche dans une popup (plus d'erreur 403 silencieuse). Dans l'admin, « Mode édition » s'appelle désormais « Mode gérant » (traduction FR), avec une aide qui liste ses pouvoirs.
/ Only a manager-mode primary card can close all registers, from any point of sale. A non-manager card sees a disabled button; a forced request gets a visible refusal popup (no more silent 403). Admin label renamed "Mode gérant" (FR translation).

**Écran du Z / Z screen :** après la clôture, l'écran n'a plus que deux gestes : « Imprimer un duplicata » (nouvelle route `imprimer_duplicata_z`) et « Fermer la caisse ». Plus de bouton retour dans le header, plus de lien vers l'admin. Les routes de la caisse `rapport_pdf`, `rapport_csv` et `envoyer_rapport` sont supprimées : le téléchargement et l'envoi du rapport sont réservés à l'admin (fiche de la clôture).
/ After closing, the Z screen offers only "Print a duplicate" and "Close the register"; no back button, no admin link. The register's PDF/CSV/e-mail routes are removed (admin only).

**Pourquoi / Why :** La J couvre tout le lieu : exiger le lien au point de vente n'avait pas de sens, et le refus (403) n'était pas affiché par htmx. Clôturer est un geste de gérant.
/ The J covers the whole venue; the point-of-sale check made no sense and its 403 was silently dropped by htmx. Closing is a manager's action.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `CaisseViewSet.cloturer` : contrôle du mode gérant (lu en base) à la place du contrôle d'accès au PV ; refus 400 rendu dans `#messages` (`HX-Retarget`) |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` | Bouton « Clôturer toutes les caisses » et sa popup seulement en mode gérant (ou session admin sans carte) ; sinon bouton désactivé |
| `locale/fr/LC_MESSAGES/django.po` | « Edit mode » → « Mode gérant », aide réécrite |
| `laboutik/views.py` (suite) | Routes `rapport_pdf`, `rapport_csv`, `envoyer_rapport` supprimées ; nouvelle route `imprimer_duplicata_z` ; `_ticket_z_avec_sa_trace` (ticket Z + métadonnées CLOT, partagé avec `cloturer`) ; plus d'adresse admin dans le contexte du Z |
| `laboutik/templates/laboutik/partial/hx_cloture_rapport.html` | Seuls « Imprimer un duplicata » et « Fermer la caisse » ; header remplacé en hx-swap-oob, sans retour |
| `laboutik/templates/laboutik/partial/_hdr_retour_zone.html` | Paramètre `hdr_sans_retour` |
| `tests/pytest/test_cloture_caisse.py` | Mode gérant (4 tests) ; écran du Z (2 tests) ; routes de téléchargement absentes ; duplicata : impression tracée CLOT, sans imprimante, broker en panne, uuid inconnu. Tests des routes supprimées retirés |

Nouvelles chaînes traduisibles : « Seule une carte en mode gérant peut clôturer les caisses. », « Clôture réservée au mode gérant », « Imprimer un duplicata », « Clôture », « Duplicata envoyé à l'imprimante », « Le duplicata n'a pas pu être envoyé à l'imprimante. Réessayez plus tard. ». Le `.po` FR a été édité à la main : `compilemessages` à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — carte en mode gérant, PV non lié
1. Admin → Cartes primaires : vérifier que la carte `A49E8E2A` a « Mode gérant » coché, et retirer un PV de sa liste (ou utiliser « Comptoir points E2E », non lié).
2. Ouvrir la caisse sur ce PV, aller dans « Ventes » (il faut au moins une vente depuis la dernière clôture).
3. Le bouton rouge « Clôturer toutes les caisses » est présent. Cliquer, puis « Confirmer la clôture ».
4. Attendu : l'écran du Z s'affiche, une J est créée (Admin → Clôtures).

### Test 2 — carte sans mode gérant
1. Décocher « Mode gérant » sur une carte primaire, ouvrir la caisse avec elle, aller dans « Ventes ».
2. Attendu : bouton gris désactivé « Clôture réservée au mode gérant », pas de popup.

### Test 3 — refus visible
1. Ouvrir l'écran Ventes avec une carte en mode gérant, puis décocher son mode gérant dans l'admin.
2. Cliquer « Clôturer toutes les caisses » → « Confirmer la clôture ».
3. Attendu : popup « Seule une carte en mode gérant peut clôturer les caisses. », l'écran Ventes reste derrière, aucune J créée.

### Test 4 — écran du Z
1. Clôturer (Test 1).
2. Attendu : header « Clôture » sans bouton retour ; seuls « Imprimer un duplicata » et « Fermer la caisse » ; aucun lien PDF / CSV / e-mail / admin.
3. Terminal avec imprimante : « Imprimer un duplicata » → message « Duplicata envoyé à l'imprimante », le ticket sort marqué DUPLICATA.
4. Terminal sans imprimante : message « Aucune imprimante configurée pour ce terminal ».

### Test 5 — libellé admin
1. Après `compilemessages`, Admin → Cartes primaires → une fiche.
2. Attendu : la case s'appelle « Mode gérant », l'aide liste produits/prix, offrir, clôturer.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_cloture_caisse.py"` (33 tests).
- Pas de test E2E : la logique est côté serveur, le gabarit est vérifié par pytest.

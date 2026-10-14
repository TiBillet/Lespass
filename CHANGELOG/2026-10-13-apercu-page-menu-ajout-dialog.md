# Menus « + Ajouter un bloc » dans une dialog centrée de l'admin / "+ Add a block" menus in a centered admin dialog

**Date :** 2026-10-13
**Migration :** Non

## Resume / Summary
**Quoi / What :** sur la fiche Page de l'admin, les deux boutons « + » (« Ajouter un bloc en premier » dans l'en-tête, et le « + » de la barre de chaque bloc dans l'aperçu) ouvrent maintenant le même menu des modèles, dans une `<dialog>` modale centrée de l'admin.
/ On the admin Page form, both "+" buttons (header "add at top" and each preview bar's "+") now open the same block model menu in a centered modal admin `<dialog>`.

**Pourquoi / Why :** l'iframe d'aperçu prend la hauteur de son contenu. Sur une page courte, le menu ouvert dans l'iframe (jusqu'à 420 px) était coupé : on n'en voyait que la moitié. Un seul fonctionnement pour les deux boutons.
/ The preview iframe is as tall as its content: on a short page the menu was clipped. One behaviour for both buttons.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/admin/pages/apercu/_outils_bloc.html` | Le « + » devient un `<button data-ouvrir-menu-ajout>` |
| `pages/static/pages/admin/apercu_page_outils.js` | Émet `apercu:ouvrir-menu-ajout` vers l'admin ; suppression de la gestion du `<details>` dans l'iframe |
| `pages/templates/admin/pages/page/blocs_de_la_page.html` | Bouton d'en-tête `data-ouvrir-menu-ajout` (inserer_apres=0) ; `<dialog id="dialog-menu-ajout">` centrée, présente aussi sur une page sans bloc ; règle de survol `.menu-modeles__lien` |
| `pages/static/pages/admin/apercu.js` | Ouvre la dialog (clic en-tête ou évènement de l'iframe), charge la liste (htmx.ajax), fermeture, retour du focus ; suppression de la gestion du `<details>` |
| `pages/admin_apercu.py` | `vue_menu_ajout` : liens en `_self`, testid `page-ajouter-en-tete-*` pour inserer_apres=0, docstring à jour |
| `pages/admin.py` | `PageAdmin.changeform_view` ne calcule plus `menu_ajout_en_tete` (chargé à la demande) |
| `pages/templates/admin/pages/apercu/_menu_modeles.html` | **Supprimé** (plus aucun appelant) |
| `pages/templates/admin/pages/apercu/_menu_modeles_liens.html` | Commentaires à jour |
| `tests/pytest/test_pages_admin_apercu.py` | `_top` → `_self`, tests de la dialog (avec et sans bloc), testid de l'en-tête |
| `tests/e2e/test_admin_page_menu_ajout_dialog.py` | Nouveau : dialog entière et centrée, bouton d'en-tête, Échap + focus, clic sur un modèle |

Nouvelles chaînes i18n (msgid FR) : « Ajouter un bloc », « Impossible de charger les modèles. ». Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — page courte (le cas qui coupait)
1. Admin → Site → Pages → ouvrir une page qui n'a qu'**un** bloc.
2. Dans l'aperçu, cliquer sur le « + » de la barre du bloc.
3. Attendu : une fenêtre « Ajouter un bloc » s'ouvre **au centre de l'écran**, fond assombri, liste des modèles **entière**.

### Test 2 — bouton de l'en-tête
1. Sur la même page, cliquer sur « + Ajouter un bloc en premier ».
2. Attendu : la même fenêtre centrée s'ouvre. Choisir un modèle : la fiche d'ajout s'ouvre avec `inserer_apres=0`, le bloc enregistré passe en tête.
3. Refaire sur une page **sans bloc** : le bouton fonctionne aussi.

### Test 3 — choisir un modèle depuis une barre
1. Depuis le « + » du bloc 1, cliquer sur un modèle (ex. « Section carte »).
2. Attendu : la fiche d'ajout de bloc s'ouvre dans la même fenêtre, avec `inserer_apres=1` dans l'URL. Après enregistrement, le bloc est placé après le bloc 1.

### Test 4 — fermeture et clavier
1. Ouvrir la fenêtre, appuyer sur Échap : elle se ferme, le focus revient sur le « + » qui l'a ouverte.
2. Rouvrir, cliquer sur le fond sombre : elle se ferme.
3. Rouvrir, cliquer sur ✕ : elle se ferme.

### Test 5 — non-régression
- ↑ ↓ ✕ et « Modifier » des barres fonctionnent comme avant.

### Verifs automatiques / Automated
- `docker exec lespass_django poetry run pytest tests/pytest/test_pages_admin_apercu.py -q`
- `docker exec lespass_django poetry run pytest tests/e2e/test_admin_page_menu_ajout_dialog.py -v -s` (serveur live requis)

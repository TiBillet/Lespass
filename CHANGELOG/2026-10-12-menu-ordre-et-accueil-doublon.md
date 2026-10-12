# Menu du lieu : ordre fixe et plus de doublon « Accueil » / Venue menu: fixed order, no duplicate "Home"

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le menu du lieu suit toujours le même ordre : pages web (CMS), agenda, adhésions, puis les autres modules (ressources), puis « Autour de nous » en dernier. Dans le skin V2, la page d'accueil CMS n'ajoute plus une deuxième entrée vers `/` à côté de « Accueil ».
/ The venue menu always follows the same order: web pages, agenda, memberships, other modules (resources), network last. In the V2 skin, the CMS home page no longer adds a second `/` entry next to "Home".
**Pourquoi / Why :** En prod (claf, codecommun), le menu affichait « Accueil » et le titre de la page d'accueil (« CLAF »), deux liens vers la même page. Le gabarit V2 ajoute « Accueil » en dur, et la page d'accueil CMS (en « Barre de navigation » par défaut) arrivait aussi par `main_nav`.
/ In production the menu showed "Home" and the home page title, both linking to `/`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `get_context()` : `main_nav` = pages web + principales (agenda, adhésions) + autres modules (ressources) + réseau |
| `pages/templates/pages/V2/tenant_header.html` | Boucles bureau et mobile : l'entrée dont l'url est `/` est sautée |
| `tests/pytest/test_pages.py` | `test_menu_v2_ordre_et_accueil_sans_doublon` |

Le nouvel ordre s'applique à tous les skins (classic et faire_festival compris). Ces deux skins n'ont pas de lien « Accueil » en dur : la page d'accueil CMS y reste visible dans le menu.

---

## Comment tester (a la main) / Manual test
### Test 1 — doublon (skin V2)
1. Lieu en skin V2 avec une Page « page d'accueil » publiée (cas de claf).
2. Ouvrir `/` : le menu montre « Accueil » une seule fois, plus d'entrée au titre de la page d'accueil.
3. Pareil dans le menu mobile (fenêtre < 48rem, bouton « Menu »).

### Test 2 — ordre
1. Activer billetterie, adhésion, pages, réservation et fédération dans la Configuration.
2. Ordre attendu : Accueil, pages CMS, Agenda, Adhésion (ou nom personnalisé), Ressources, Autour de nous.

### Vérif automatique
`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_pages.py -k menu_v2_ordre -q`

### Correctif lié — description longue échappée sur l'accueil par défaut (V2)
**Quoi / What :** `pages/templates/pages/V2/vues/accueil.html` affiche `config.long_description` avec `|safe`, comme classic et faire_festival.
/ The V2 default home renders the long description as HTML, like the other skins.
**Pourquoi / Why :** Sans page d'accueil CMS publiée, l'accueil par défaut montrait les balises en texte brut (`<a href=…>`, `<br>`).

**Test :** dépublier la page d'accueil CMS d'un lieu V2 dont la description longue contient un lien → `/` affiche un vrai lien et des retours à la ligne, sans balises visibles.

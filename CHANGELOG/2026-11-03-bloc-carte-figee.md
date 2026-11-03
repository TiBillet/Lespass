# Bloc « Carte figée » : la carte du réseau nourrie par un fichier JSON / "Frozen map" block: the network map fed by a JSON file

**Date :** 2026-11-03
**Migration :** Oui — `pages/migrations/0004_bloc_carte_figee.py` (ajout de `Bloc.donnees_carte_figee`, nouveau choix `CARTE_FIGEE` sur `type_bloc`).
Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas pages`

## Resume / Summary
**Quoi / What :** Nouveau type de bloc dans l'éditeur de site : « Carte figée ». L'admin du lieu importe un fichier JSON (une liste de lieux, chacun avec ses coordonnées GPS et ses événements). La page affiche le même outil de carte que « Autour de nous » : carte et liste des lieux, événements au clic, vue Événements, filtres par tag. L'aide du champ montre un exemple de fichier dans un accordéon.
/ New page block type, "Frozen map". The venue admin uploads a JSON file (venues with GPS and events). The page shows the same map tool as the "Around us" page. The field help shows an example file in an accordion.

**Pourquoi / Why :** Publier le bilan d'une campagne d'événements passés (ex. Journées Portes Toujours Ouvertes 2026). La carte réseau ne lit que les événements à venir du cache SEO, et seulement des lieux TiBillet.
/ To publish a report on past events (e.g. JPTO 2026). The network map only reads upcoming events of TiBillet venues.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/carte_figee.py` | **Nouveau.** Lecture du fichier (2 Mo, UTF-8, JSON), vérification (`nettoyer_carte_figee`), conversion vers `{points, tenants}` pour explorer.js, aide en accordéon |
| `pages/models.py` | Type `CARTE_FIGEE`, champ `donnees_carte_figee`, `_verifier_la_carte_figee()` appelée par `clean()` : données obligatoires, revérifiées (chemin API), une seule carte figée par page |
| `pages/blocs_catalogue.py` | Entrée `CARTE_FIGEE` (champs `titre`, `donnees_carte_figee`), sans affichage |
| `pages/admin.py` | Champ d'import `fichier_carte_figee` à la place du JSON brut ; aide avec résumé de la carte actuelle |
| `pages/templatetags/pages_tags.py` | Tag `donnees_explorer_carte_figee` |
| `pages/templates/pages/classic/partials/bloc_carte_figee.html` | **Nouveau.** Socle : inclut `seo/partials/explorer_widget.html` |
| `pages/templates/pages/V2/partials/bloc_carte_figee.html` | **Nouveau.** Skin V2 : inclut la coquille V2 de l'explorer |
| `pages/templates/pages/V2/partials/explorer_coquille.html` | **Nouveau.** Coquille V2 de l'explorer, sortie de `V2/vues/reseau.html` (même HTML) |
| `pages/templates/pages/V2/vues/reseau.html` | Inclut la coquille au lieu de la porter en ligne |
| `seo/static/seo/explorer.js` | Liens : une `url` fournie passe avant le lien construit avec le domaine (`lienDuLieu`, `lienDeLEvenement`) ; bouton « Visiter le lieu » masqué sans lien ; événement sans lien rendu en texte (plus de `href="#"`) ; `escapeHtml` échappe aussi `"` et `'` (vaut pour /explorer/ et la page réseau) ; popup limitée à 5 événements avec « + N autre(s) » |
| `seo/templates/seo/partials/explorer_widget.html` | Variable optionnelle `libelle_evenements_popup` |
| `tests/pytest/test_bloc_carte_figee.py` | **Nouveau.** 31 tests (vérification, conversion, modèle, admin, rendu classic + V2) |
| `tests/e2e/test_bloc_carte_figee.py` | **Nouveau.** 5 tests navigateur |
| `tests/pytest/test_pages_api.py` | Le catalogue fermé compte 8 types ; 4 tests de la carte figée par l'API (création, PATCH, URL piégée, bloc d'un autre type) |

Sécurité (relecture Fable) : une URL est acceptée seulement si c'est une adresse http(s) complète, sans guillemet, chevron, espace ni caractère de contrôle (un guillemet refermait l'attribut `href` : XSS reproduit puis corrigé). Fichier très imbriqué : message d'erreur au lieu d'une 500. Dates : seulement `2026-10-02`, `2026-10-02T14:00`, `2026-10-02T14:00:30`. Textes : 200 caractères au plus (nom, adresse, tag). Slugs de tags uniques et non vides (lettres non latines, emoji). Un bloc d'un autre type ne garde aucune donnée de carte.

i18n : environ 35 nouvelles chaînes traduisibles (msgid en français). Le workflow i18n est à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — import nominal
1. Admin du tenant > Pages > ouvrir une page publiée > « + » > modèle « Carte figée ».
2. Ouvrir l'accordéon « Voir un exemple de fichier » sous le champ d'import : l'exemple JSON s'affiche.
3. Renseigner un titre, importer un fichier JSON valide (exemple réel : le bilan JPTO 2026, 72 lieux et 161 événements).
4. Enregistrer : le bloc apparaît dans « Contenu de la page » avec la liste des lieux.
5. Ouvrir la page publique : liste à gauche, carte à droite (skin V2), marqueurs regroupés.
6. Cliquer « N événements » sur un lieu : les événements s'affichent, leurs liens ouvrent l'`url` du fichier.
7. Cliquer un lieu : la popup titre « Événements : (N) », pas « Prochains événements ».
8. Basculer sur « Événements », cliquer un tag : la liste se filtre.

### Test 2 — cas limites
- Fichier avec une latitude à 500, une URL `javascript:` ou une URL contenant un guillemet : l'enregistrement est refusé, toutes les erreurs sont listées avec leur position, rien n'est enregistré. Un seul message par erreur (pas de « Importez un fichier JSON » en plus).
- Fichier fait de 200 000 `[` : message « imbriqué trop profondément », pas d'erreur 500.
- Un événement sans `url` : son nom s'affiche sans lien.
- Rouvrir le bloc : la ligne « Carte actuelle : N lieu(x), M événement(s). » apparaît. Changer le titre sans fichier : la carte est gardée.
- Ajouter une deuxième carte figée sur la même page : refusé (« Cette page a déjà une carte figée »).
- Un lieu sans `url` : pas de bouton « Visiter le lieu ».
- Non-régression : la page « Autour de nous » (`/federation/`) garde sa carte, son bouton « Réseau TiBillet » et ses liens `https://<domaine>/event/<slug>/`.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_bloc_carte_figee.py -q`
- `make e2e ARGS="tests/e2e/test_bloc_carte_figee.py"`
- Non-régression explorer : `make e2e ARGS="tests/e2e/test_explorer_adresse_dupliquee.py tests/e2e/test_explorer_markers_per_pa.py tests/e2e/test_explorer_ux_pills_tags.py"`

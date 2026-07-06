# Migration skins — CHANTIER-01 : resolver `gabarit_skin` + squelettes `pages/<skin>/`

## Ce qui a été fait

Première étape de la migration skins (plan complet : `TECH_DOC/SESSIONS/SKINS/`,
spec : `CHANTIER-01-RESOLVER-SHELL.md`).

- Nouveau resolver `pages.services.gabarit_skin(nom)` : `pages/<skin>/<nom>` si le
  skin fournit le gabarit, sinon fallback automatique `pages/classic/<nom>`.
- Les 4 squelettes (`base.html` / `headless.html` × reunion / faire_festival) sont
  déplacés vers `pages/templates/pages/{classic,faire_festival}/{shell,headless}.html`.
- Les anciens fichiers deviennent des redirections d'héritage (une ligne
  `{% extends %}`) : les templates qui les étendent en dur (404, 500,
  crowds/success, vues faire_festival) fonctionnent sans modification.
- `get_context()` résout `base_template` via `gabarit_skin` (shell.html en page
  complète, headless.html en requête HTMX).

### Modifications
| Fichier | Changement |
|---|---|
| `pages/services.py` | + `gabarit_skin()` |
| `pages/templates/pages/classic/{shell,headless}.html` | NOUVEAUX (ex reunion) |
| `pages/templates/pages/faire_festival/{shell,headless}.html` | NOUVEAUX (ex ff) |
| `BaseBillet/templates/{reunion,faire_festival}/{base,headless}.html` | redirections `{% extends %}` |
| `BaseBillet/views.py` (`get_context`) | branché sur `gabarit_skin` |
| `tests/pytest/test_gabarit_skin.py` | 4 tests |
| `BaseBillet/migrations/0224_merge_20260703_0914.py` | merge technique 0220/0223 (vide, requis pour `migrate_schemas`) |

## Vérifications déjà réalisées (session du 2026-07-03)

- **Iso-rendu au bit près** : snapshots curl normalisés (CSRF + images placeholder
  aléatoires neutralisés) strictement identiques avant/après sur 9 pages :
  `/`, `/event/`, `/memberships/` (+ variantes HX-Request) × tenant lespass (reunion)
  et tenant chantefrein (passé temporairement en faire_festival puis restauré).
- `manage.py check` : 0 issue.
- pytest : `test_gabarit_skin.py` (4) + `test_pages.py` (25) → 29 passed.
- ruff : `pages/services.py` et `test_gabarit_skin.py` propres ; zone modifiée de
  `views.py` sans nouvelle erreur (39 erreurs préexistantes ailleurs, non touchées).
- E2E `test_reservation_validations.py` + `test_membership_validations.py` : lancés
  en fin de session (voir rapport de session pour le résultat).

## Tests à réaliser (mainteneur)

### Test 1 : parcours visuel skin reunion (défaut)
1. Ouvrir `https://lespass.tibillet.localhost/` — home identique à avant.
2. `/event/` : agenda, filtres tags, pagination HTMX (scroll / « voir plus »).
3. `/memberships/` : grille, ouvrir le tunnel `#subscribePanel`, aller jusqu'au
   checkout Stripe (carte `4242…`).
4. Navigation HTMX entre les pages (pas de flash, titre d'onglet mis à jour).

### Test 2 : skin faire_festival
1. Admin → Configuration du site → Thème graphique = Faire Festival (sur un tenant
   de test).
2. Rejouer le parcours du test 1 : rendu brutaliste identique à avant, offcanvas
   contact/login OK.
3. Remettre le thème d'origine.

### Test 3 : pages d'erreur et CMS
1. Une URL inexistante → la 404 s'affiche avec navbar/footer du skin (elle étend
   `reunion/base.html` qui redirige vers le shell).
2. Une page CMS (`/<slug>/`) s'affiche normalement (l'app pages utilise le même
   `base_template`).

## Compatibilité

- `get_skin_template` reste en place pour les 11 templates `views/*` — bascule aux
  CHANTIERS 03+.
- Comportement préservé tel quel (non corrigé ici, connu) : en skin faire_festival,
  les requêtes HTMX renvoient la page complète (les vues ff étendent
  `faire_festival/base.html` en dur, pas `base_template`).
- La migration 0224 est un merge vide : aucun changement de schéma, mais elle doit
  être committée (sans elle, `migrate_schemas` refuse de tourner sur main-pages).

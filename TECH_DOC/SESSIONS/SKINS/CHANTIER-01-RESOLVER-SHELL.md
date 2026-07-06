# CHANTIER-01 — Resolver unifié + squelettes (shell)

**Statut :** en cours (2026-07-03).
**Objectif :** créer le resolver `gabarit_skin()` et déplacer les squelettes
(`base.html` / `headless.html`) des deux skins vers `pages/<skin>/`, **sans aucun
changement de rendu** (iso-rendu prouvé par snapshots curl avant/après).

## Design retenu

### 1. `pages.services.gabarit_skin(nom)` → chemin (str)
- Retourne un **chemin de template** (string), pas un objet Template : les vues font
  `render(request, chemin)` et les templates `{% extends base_template %}` — les deux
  attendent un chemin. Même contrat que `get_skin_template`, mais fallback `classic`.
- Logique : essaie `pages/<skin>/<nom>`, sinon retombe sur `pages/classic/<nom>`.
  `skin` lu via `get_skin_courant()` (import local, comme dans `pages/views.py`,
  pour éviter l'import circulaire BaseBillet ↔ pages).
- FALC : boucle explicite, `try get_template / except TemplateDoesNotExist`.

### 2. Squelettes déplacés — anti-drift par héritage, pas par copie
Le plan disait « porter base.html → shell.html ». Une copie créerait **deux sources
de vérité** qui divergent pendant la migration. À la place :
- `pages/classic/shell.html` = contenu INTÉGRAL de l'ex `reunion/base.html`
  (déplacé, à l'identique — mêmes blocs, mêmes includes `reunion/partials/…`
  pour l'instant : leur déménagement vers `commun/` = CHANTIER-02).
- `BaseBillet/templates/reunion/base.html` devient **une seule ligne** :
  `{% extends "pages/classic/shell.html" %}`.
  → les templates qui font `{% extends "reunion/base.html" %}` en dur
  (`404.html`, `500.html`, `crowds/templates/success.html`) continuent de marcher
  par héritage multi-niveaux, rendu strictement identique.
- Idem pour les 3 autres squelettes :
  - `reunion/headless.html` → `pages/classic/headless.html`
  - `faire_festival/base.html` → `pages/faire_festival/shell.html`
  - `faire_festival/headless.html` → `pages/faire_festival/headless.html`
  (les vues `faire_festival/views/*` étendent `faire_festival/base.html` en dur —
  elles passent par la chaîne d'héritage, on ne les touche pas dans ce chantier).

### 3. Branchement de `base_template` (`get_context`, `BaseBillet/views.py:177-180`)
```python
if request.htmx:
    base_template = gabarit_skin("headless.html")
else:
    base_template = gabarit_skin("shell.html")
```
- skin `reunion` → `pages/reunion/shell.html` absent → fallback
  `pages/classic/shell.html` (= ex reunion/base.html). Iso-rendu.
- skin `faire_festival` → `pages/faire_festival/shell.html`. Iso-rendu.
- NB : les vues faire_festival n'utilisent pas `base_template` (extends en dur) —
  comportement préservé tel quel, y compris « HTMX renvoie la page complète en ff »
  (constaté dans les snapshots de référence, on ne le corrige PAS ici).

## Fichiers touchés
| Fichier | Action |
|---|---|
| `pages/services.py` | + `gabarit_skin()` |
| `pages/templates/pages/classic/shell.html` | NOUVEAU (contenu ex reunion/base.html) |
| `pages/templates/pages/classic/headless.html` | NOUVEAU (ex reunion/headless.html) |
| `pages/templates/pages/faire_festival/shell.html` | NOUVEAU (ex ff/base.html) |
| `pages/templates/pages/faire_festival/headless.html` | NOUVEAU (ex ff/headless.html) |
| `BaseBillet/templates/reunion/base.html` | devient `{% extends shell %}` (1 ligne) |
| `BaseBillet/templates/reunion/headless.html` | idem |
| `BaseBillet/templates/faire_festival/base.html` | idem |
| `BaseBillet/templates/faire_festival/headless.html` | idem |
| `BaseBillet/views.py` (`get_context`) | `get_skin_template` → `gabarit_skin` pour base/headless |
| `tests/pytest/test_gabarit_skin.py` | NOUVEAU (fallback, skin existant, branchement) |

## Invariants (à vérifier avant de terminer)
1. **Iso-rendu** : snapshots curl normalisés (CSRF retiré) identiques avant/après sur
   `/`, `/event/`, `/memberships/` (+ variante HTMX) pour un tenant reunion ET un
   tenant faire_festival.
2. Aucun bloc renommé, aucun id changé, aucun static déplacé.
3. `get_skin_template` reste en place pour les 11 templates `views/*` (CHANTIERS 03+).
4. `manage.py check` : 0 issue. Tests pytest pages + nouveaux tests verts.

## Hors périmètre (ne PAS faire ici)
- Déplacer navbar/footer/toasts/loading/forms vers `commun/` (CHANTIER-02).
- Corriger le « HTMX = page complète » du skin faire_festival.
- Toucher aux vues `views/*`, aux offcanvas, aux statics.

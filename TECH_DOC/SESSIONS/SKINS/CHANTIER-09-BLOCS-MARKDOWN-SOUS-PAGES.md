# CHANTIER-09 — Blocs MARKDOWN + LISTE_SOUS_PAGES (« blog »)

**Statut :** codé le 2026-07-05 (go mainteneur).
**But :** contenu long en Markdown + index de sous-pages en cartes → une Page
parente devient un blog (parent = index, enfants = articles).

## Bloc MARKDOWN
- `type_bloc = "MARKDOWN"`, champs : `titre` (optionnel), `texte` (source MD).
  **Zéro nouveau champ modèle** (réutilise `texte`).
- Rendu : filtre `rendre_markdown` (pages_tags) = `markdown.markdown(...,
  extensions=["extra", "sane_lists"])` puis **`nh3.clean()`** (sanitize XSS
  NON NÉGOCIABLE : un XSS stocké dans une page publique reste un XSS, même si
  seuls les admins écrivent). Les deux libs étaient déjà dans pyproject.
- Gabarit : `pages/classic/partials/bloc_markdown.html` (ff par fallback),
  style `.tb-bloc--markdown` dans tb-blocs.css (titres, listes, code,
  blockquote, tableaux).

## Bloc LISTE_SOUS_PAGES
- `type_bloc = "LISTE_SOUS_PAGES"`, champs : `titre` (optionnel),
  `nombre_max` (réutilisé, défaut 6).
- Rendu : tag `sous_pages_publiees(page, nombre_max)` — requête directe
  (pattern identique à `evenements_a_venir`) : enfants PUBLIÉS de la page
  courante, tri `position, titre`. Cartes `.tb-bloc--carte` dans `.tb-grille`
  (réutilise la grille existante) : image de la page, titre,
  meta_description, lien `/slug/`.

## Intégrations
- `blocs_catalogue.CHAMPS_PAR_TYPE` (source unique API v2) + enum openapi.
- Admin Unfold : `conditional_fields` (titre/texte/nombre_max étendus).
- `grouper_blocs` : rien à faire — types inconnus = groupe « solo ».
- Migration : la choice s'ajoute dans `pages/0001_initial` régénéré
  (non committé, flush en cours) — pas de 0002.

## Tests
`tests/pytest/test_blocs_markdown_sous_pages.py` : rendu MD → HTML, XSS
neutralisé (script/onerror), sous-pages publiées listées / brouillons exclus,
nombre_max respecté.

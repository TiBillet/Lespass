# Blocs MARKDOWN + LISTE_SOUS_PAGES (pages « blog »)

## Ce qui a été fait
Voir CHANGELOG (entrée du 2026-07-05) et la spec
`TECH_DOC/SESSIONS/SKINS/CHANTIER-09-BLOCS-MARKDOWN-SOUS-PAGES.md`.
En bref : bloc MARKDOWN (source MD dans `texte`, rendu sécurisé
markdown+nh3 au gabarit) et bloc LISTE_SOUS_PAGES (cartes des sous-pages
publiées). Parent + enfants = un blog sans nouvelle app.

## Démo déjà en place (lespass, à supprimer après inspection)
- `/demo-journal/` : index avec le bloc LISTE_SOUS_PAGES.
- `/demo-article-1/` : article avec le bloc MARKDOWN (gras, liste, citation,
  tableau). Rendu vérifié par curl + tests ; le certificat Traefik ayant été
  régénéré par le down -v, ré-accepte-le dans Chrome pour le contrôle visuel.
- Suppression : admin pages, ou me demander.

## Tests à réaliser (mainteneur)

### Test 1 : création dans l'admin
1. Admin → Site web → Blocs → Ajouter : choisir « Markdown » → seuls
   `titre` + `texte` apparaissent (conditional_fields).
2. Coller du MD avec titres/listes/liens/code → enregistrer → vérifier le
   rendu public. Vérifier qu'un rechargement de la fiche admin NE modifie PAS
   la source MD (exception clean_html au save).
3. Ajouter un bloc « Liste des sous-pages » sur une page parente →
   `titre` + `nombre_max` seulement.

### Test 2 : sécurité XSS (couvert par pytest, à re-sonder si envie)
Coller dans le texte MD : `<script>alert(1)</script>` et
`<img src=x onerror=alert(1)>` → le rendu public ne doit contenir ni
`<script` ni `onerror` (nh3).

### Test 3 : blog de bout en bout
Créer une page « Blog » publiée + bloc LISTE_SOUS_PAGES ; créer 2 sous-pages
publiées + 1 brouillon avec des blocs MARKDOWN → l'index liste les 2 publiées
(ordre position/titre), pas le brouillon ; navigation HTMX « Lire la suite »
vers l'article.

### Test 4 : API v2
`GET /api/v2/pages/block-types/` liste MARKDOWN et LISTE_SOUS_PAGES (dérivé
de blocs_catalogue) ; création d'un bloc MARKDOWN via l'API.

## Notes
- Skin faire_festival : gabarits par fallback classic (surcharger
  `pages/faire_festival/partials/bloc_markdown.html` si besoin d'un look ff).
- `nombre_max` : libellé généralisé (« Nombre d'éléments ») car partagé
  EVENEMENTS / LISTE_SOUS_PAGES.
- i18n : nouvelles chaînes FR (« Lire la suite », « Aucune page publiée pour
  le moment. », choices) → makemessages/compilemessages à ta charge.

# Admin blocs : filtres avancés Unfold / Blocks admin: Unfold advanced filters

**Date :** 2026-07-05
**Migration :** Non / No

La liste des blocs passe aux filtres avancés Unfold (pattern
« driverwithfilters » de la démo), affichés SUR la page
(`list_filter_sheet = False`) :
- **Par Page** : liste de LIENS cliquables (préférence mainteneur, réitérée
  contre l'autocomplete d'abord proposé) ;
- **Par Page parente** : autocomplete — tous les blocs des sous-pages d'une
  page (ex. tous les blocs des articles du Journal) ;
- **Par Type de bloc** : menu déroulant compact (16 types).
NOTE responsive : l'affichage sur la page n'existe qu'à partir du breakpoint
2xl (fenêtre ≥ 1536 px) — en dessous, Unfold retombe automatiquement sur le
bouton « Filtres » + tiroir latéral (mêmes filtres). Vérifié en captures
authentifiées 1440/1720 px (Playwright + force_login E2E).

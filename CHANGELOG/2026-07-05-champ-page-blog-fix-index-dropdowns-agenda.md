# Champ `Page.est_blog` + fix z-index des dropdowns sur l'agenda / `Page.est_blog` field + agenda dropdowns z-index fix

**Date :** 2026-07-05
**Migration :** Non pour la branche (champ plié dans `pages/0001` régénérée, non committée ; colonne ajoutée à la main sur la base dev) / Folded into the regenerated, uncommitted `pages/0001`

- **`Page.est_blog` (typage EXPLICITE, décision mainteneur)** : le critère
  implicite « le parent porte un bloc LISTE_SOUS_PAGES » posait problème — le
  bloc doit rester de la pure présentation (posable sur l'accueil pour vitrine
  ses rubriques, sans transformer ses sous-pages en articles). Le champ
  booléen (pattern `est_accueil`, case à cocher dans l'admin) pilote désormais
  les trois comportements : sous-pages = ARTICLES (JSON-LD Article + signature
  date/auteur) et PAS de menu déroulant dans la navbar — le clic sur la page
  blog mène directement à l'index en cartes. Seeder : `journal` est_blog=True.
- **Fix z-index (bug signalé)** : les sections sticky de l'agenda classic
  (description + barre de recherche, `sticky-top` = z-index 1020 Bootstrap)
  passaient DEVANT les menus déroulants de la navbar (dropdown = 1000).
  `z-index: 999` posé sur les deux sections — les dropdowns repassent devant,
  la barre reste au-dessus du contenu qui défile.

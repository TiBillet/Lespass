# Blog : images d'illustration dans les articles Markdown / Blog: illustration images in Markdown articles

**Date :** 2026-07-05
**Migration :** Non (réutilise ImageGalerie) / No (reuses ImageGalerie)

Un article Markdown peut désormais être illustré avec de VRAIES images
uploadées (proposition mainteneur : « inline image + balise dans le
markdown ») :
- **L'inline « Images »** (le même que la galerie, avec son tri par
  glisser-déposer) apparaît aussi sur les blocs MARKDOWN
  (`BlocAdmin.get_inlines`).
- **Dans le texte** : syntaxe markdown standard `![légende](galerie:N)` —
  N = position de l'image dans l'inline. Le nouveau filtre
  `rendre_bloc_markdown` résout la référence vers l'URL réelle (variation
  `med`, non croppée) AVANT le rendu markdown+nh3. Alt vide → la légende de
  l'inline ; référence inconnue → marqueur texte visible
  « [image galerie:N introuvable] » (jamais de trou silencieux).
- **Aide dans l'admin** : note contextuelle sur la fiche du bloc MARKDOWN
  (même mécanisme Alpine que l'aide HERO) documentant la syntaxe.
- **Fixture** : l'article « fresque participative » du blog de démo est
  illustré (image dans l'inline + référence dans le texte) — rendu vérifié.
- Les images externes `![alt](https://…)` fonctionnent aussi (nh3 conserve
  `<img src=https>`). Tests : résolution, fallback légende, réf inconnue.

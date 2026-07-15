# Admin : éditeur Markdown EasyMDE pour le bloc MARKDOWN / Admin: EasyMDE Markdown editor for the MARKDOWN block

**Date :** 2026-07-05
**Migration :** Non / No

Le bloc MARKDOWN s'éditait dans le WYSIWYG Trix (qui produit du HTML) —
pénible et destructeur pour de la source Markdown. Après étude des options
(ToastUI trop lourd, Milkdown/MDXEditor exigent un bundler, TinyMDE plus
maintenu), choix : **EasyMDE 2.21.0** (release mai 2026, activement
maintenu), VENDORISÉ (`pages/static/pages/vendor/easymde/`, ~330 Ko,
zéro CDN, zéro dépendance pip).
- **Deux champs de formulaire pour un champ modèle** : `texte` garde Trix
  (types HTML), le nouveau champ de FORMULAIRE `texte_markdown` (affiché
  seulement pour MARKDOWN via conditional_fields) porte EasyMDE ; la valeur
  vit toujours dans `Bloc.texte` (initial au chargement, recopie APRÈS
  sanitize dans save_model — retours à la ligne préservés, aller-retour
  testé en shell).
- Éditeur : coloration markdown live, barre d'outils essentielle (sans
  upload d'image — les images passent par l'encart + `galerie:N`), aperçu,
  côte-à-côte, plein écran ; correcteur anglais désactivé.
- `editeur_markdown.js` : init + PIÈGE géré — CodeMirror mesuré dans le
  conteneur caché par Alpine se dessine à 0px → refresh au changement de
  type et après chargement. `editeur_markdown.css` : accordage clair/sombre
  (classe .dark d'Unfold).
- Vérifié en capture authentifiée (fiche de l'article de démo).
- **Plein écran / côte-à-côte au-dessus de l'admin** : les calques
  position:fixed d'EasyMDE (z-index 8-9) passaient DERRIÈRE les menus
  d'Unfold (z-40) → remontés à z-60 (un plein écran couvre tout l'écran,
  menus compris). Signalé par le mainteneur, vérifié par capture avec clic
  réel sur le bouton côte-à-côte.
- **Aperçu fidèle** : `previewRender` résout `![légende](galerie:N)` vers
  les vraies URLs (table position→URL embarquée par le formulaire en
  data-attribute — même règle que le rendu serveur) au lieu d'une image
  cassée ; typographie de l'aperçu restaurée (le reset Tailwind de l'admin
  aplatissait titres, listes et citations).

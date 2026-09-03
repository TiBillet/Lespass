# LaBoutik : tuiles articles et menu ouvrant au style de la refonte caisse / POS article tiles and burger panel restyled after the sales-screen redesign

**Date :** 2026-09-03
**Migration :** Non

## Resume / Summary

**Quoi / What :** (1) Les tuiles produits de l'écran de vente (`.article-container`)
adoptent le composant `.tile` du prototype de refonte
(`tibillet-laboutik-main/caisse/Laboutik.css`) : composition centrée (visuel +
nom), pastille prix en bas-gauche, badge quantité en bas-droite, dégradé 135° et
relief « touche » — tranche de 4 px dans la teinte de la tuile, assombrie, qui
descend exactement de 4 px à l'appui (descente instantanée, remontée à 170 ms).
Les tuiles billetterie, qui partagent la classe `.article-container`, héritent du
même fond et du même relief tout en gardant leur mise en page paysage.
(2) Le menu ouvrant (`#menu-burger-container`) adopte le panneau `.panel` /
`.panel--left` de la maquette (`#posPanel`) : carte flottante arrondie détachée
sous l'en-tête, avec un titre de section et des lignes `.menu-row` au lieu des
barres pleine largeur, et le point de vente courant y est surligné avec une
coche verte. (3) Le badge de quantité rejoue son rebond à chaque
ajout, et plus seulement à sa première apparition.
/ POS product tiles adopt the `.tile` component from the sales-screen redesign
prototype: centered composition, price chip bottom-left, quantity badge
bottom-right, 135° gradient and the "key" relief. Ticket tiles, which share the
`.article-container` class, inherit the same background and relief while keeping
their landscape layout.

**Pourquoi / Why :** Un premier portage existait dans `articles.css` mais était
inopérant : `--h: 74` était codé en dur (la tranche 3D était orangée pour toutes
les catégories), la classe `is-hit` qui déclenche les animations `flash-*` n'est
jamais posée par le JS de `laboutik/` (elle vient du prototype), la règle de base
`.tile::after` n'avait pas été portée, et `:active` lançait un `flash-lumiere` qui
écrasait le relief pendant 220 ms. Le dégradé et la tranche colorée ne sont
calculables en CSS que si la couleur de la tuile est exposée en variable.
/ A first port existed but was inert: hardcoded hue, `is-hit` never set by the
app's JS, missing `.tile::after` base rule, and an `:active` animation that
overrode the relief. The gradient and colored edge are only computable in CSS if
the tile color is exposed as a variable.

**Isolation des impacts :** aucun changement de structure HTML, de classe, de
`data-*` ni de `data-testid` — seuls des attributs `style` inline changent. Les
contrats JS sont préservés : `.article-touch` reste enfant direct de la tuile
(`articles.js:manageKey()` remonte d'un seul cran), la tuile reste un `<div>`
(`articlesRemove()` sélectionne `#products div[data-uuid]`), aucun `display`
inline n'est posé (le filtre catégorie écrit `style.display`), et le markup de la
pastille stock (swap HTMX OOB) est inchangé. `--article-font-size`
(`laboutik_config.taille_police_articles`) reste prioritaire sur la taille de nom
par défaut. Le CSS est écrit en `rgba()` : seule la tranche colorée a besoin de
`color-mix()`, isolée dans un `@supports` — sur une WebView Android ancienne la
tuile garde son dégradé et son relief, avec une tranche noire translucide au lieu
de sa propre teinte.
/ No HTML structure, class, `data-*` or `data-testid` change — only inline `style`
attributes. All JS contracts are preserved; the CSS is plain `rgba()` except the
colored edge, whose `color-mix()` sits in an `@supports` block so old Android
WebViews degrade to a neutral edge.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/articles.html` | Le `style` inline de la tuile passe de `background-color`/`color` à `--legacy` / `--legacy-ink`, avec gardes `{% if %}` (une custom property vide casserait le `var(--legacy, …)` de repli) ; la source passe de `article.categorie.couleur_backgr` à **`article.couleur_backgr`**, qui applique déjà l'override produit (`couleur_fond_pos`) — la tuile respecte enfin la couleur choisie sur le produit. Suppression des `style="color:…"` sur l'icône de catégorie et l'icône produit, et du `color`/`text-shadow` sur le nom : l'encre vient désormais de `--legacy-ink` |
| `laboutik/static/css/articles.css` | Bloc tuile réécrit : jetons responsive (`--article-height`, `--article-visual-size`, `--article-name-size`, `--article-gap`, `--r-tile`) calés sur les formats « poche » (360 px) et « d3mini » (1280 px) du prototype ; `.article-container` en colonne flex centrée, dégradé + tranche dérivée de `--legacy` (`color-mix` sous `@supports`), relief « touche » sur `:active` ; conteneur de la pastille stock sorti du flux (ses nœuds texte décentraient le groupe visuel + nom) ; `.article-visual-layer` (avec `line-height:0` pour les articles sans visuel), `.article-name-text` centré, `.article-tarif-pill` au style `.tile-price`, `.badge` au style `.tile-qty` + `@keyframes qty-pop`. Suppression du code mort : `--h: 74`, `--tile-light`, `@keyframes flash-lumiere`/`flash-ombre`, règles `.is-hit::after`, bloc `pressing` commenté, `@media (width > 1278px)`, doublons de `--bt-article-width` |
| `laboutik/templates/cotton/billet_tuile.html` | Même bascule du `style` inline vers `--legacy` / `--legacy-ink` |
| `laboutik/static/css/billet_tuile.css` | `:active` passe de `scale(0.97)` à `translateY(4px)` pour suivre le relief hérité ; commentaire de tête mis à jour (le ratio 1:1 `height:0 + padding-bottom` n'existe plus) |
| `laboutik/static/js/articles.js` | Nouvelle fonction `afficherBadgeQuantite()` : retire `badge-visible`, force un reflow, la repose — sinon `qty-pop` ne rejouerait qu'à la première apparition du badge ; appelée dans `addArticle()` |
| `laboutik/static/js/tarif.js` | `addArticleWithPrice()` appelle `afficherBadgeQuantite()` au lieu d'ajouter `badge-visible` directement |
| `laboutik/static/css/palette.css` | Jetons de chrome du prototype ajoutés (`--bg`, `--surface-2/-3`, `--line`, `--line-soft`, `--text`, `--text-dim`, `--text-faint`, `--r-panel`, `--r-ctrl`, `--r-pill`, `--fs-min`) — `V2.css` référençait déjà `--text-dim` et `--text-faint` sans qu'ils existent |
| `laboutik/static/css/header.css` | Menu ouvrant (`#menu-burger-container`) porté sur `.panel` / `.panel--left` du prototype : carte flottante de 300 px détachée de 8 px sous l'en-tête, coins 14 px, filet de 1 px (`--line`), ombre profonde, ouverture en `scale(.94) → 1` (130 ms) ; `.menu-burger-item` porté sur `.menu-row` (46 px mini, coins 10 px, `--fs-min`, icône `--text-faint`, fond `--surface-2` à l'appui, et `[aria-current="true"]` = fond allumé + icône et coche en `--valid`) au lieu de la barre 60 px à filet séparateur ; nouveau `.menu-panel-title` (= `.panel-title`) ; mobile : le panneau reste flottant en `calc(100% - 16px)` |
| `laboutik/templates/cotton/header.html` | Un titre de section par groupe (`.menu-panel-title`, comme la maquette) ; `style="text-decoration:none"` inline retiré des liens points de vente (désormais dans le CSS) ; la variable de boucle des points de vente est renommée `pv` → `pv_item` (elle masquait le `pv` du contexte, le point de vente courant), ce qui permet de poser `aria-current="true"` + une coche sur la ligne courante |

### A faire / To do

Deux nouveaux msgid apparaissent dans `cotton/header.html` — « Points de vente »
(titre de section) et « Point de vente actuel » (`aria-label` de la coche). Les
fichiers de traduction n'ont pas ete touches : a reprendre au prochain
`makemessages` / `compilemessages`. En attendant, ces deux chaines s'affichent
en francais quelle que soit la langue.
/ Two new msgids appear in `cotton/header.html`. Translation files were left
untouched: to be picked up by the next makemessages/compilemessages run. Until
then both strings render in French in every locale.

### Verification / Verification

Aperçu statique généré hors dépôt (toutes les variantes : multi-tarif, prix
libre, prix au poids, méthode `VC`, alerte et rupture de stock, article bloquant,
adhésion, article sans icône ni image, catégorie sans couleur, tuile billet) en
2, 3 et 4 colonnes. À contrôler sur la stack : ajout au panier, filtre par
catégorie, appui long, badge quantité, swap HTMX de la pastille stock.

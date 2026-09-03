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
coche verte. (3) Le panneau addition (colonne de droite) adopte le panneau
`.ticket` de la maquette : colonne `--surface` séparée par un filet, en-tête
« Ticket » + pastille de comptage, lignes à plat séparées d'un simple trait,
bouton « moins » carré arrondi, pastille de comptage alimentée en direct
(« 17 articles »), flash vert à l'ajout / rouge au retrait sur la ligne touchée,
fondu rouge quand une ligne tombe à zéro, et bouton « Vider » à confirmation en
deux temps. (4) Le badge de quantité rejoue son rebond à chaque
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
| `laboutik/templates/cotton/addition.html` | La ligne de légende (`vide / PRODUIT / PRIX`) devient l'en-tête `.tk-head` de la maquette : `.addition-head` avec `.addition-title` (« Ticket ») et la pastille `#addition-count` (à « — » tant que le JS ne l'alimente pas). Libellés singulier/pluriel de la pastille passés en `data-*` (le JS n'a pas accès aux tags de traduction). Bouton VIDER (`.tk-reset` de la maquette) ajouté à droite de l'en-tête, avec ses libellés « Vider » / « Confirmer » en `data-*` et `onclick="additionArmerVider()"` (même convention que le bouton « moins » des lignes). Désactivé au chargement (panier vide) |
| `laboutik/static/js/addition.js` | Trois ajouts : `additionMajEntete()` (somme des quantités lue sur les inputs `repid-*`, alimente `#addition-count` et active/désactive le bouton VIDER ; appelée en fin de `additionInsertArticle()`, `additionRemoveArticle()` et `additionReset()`) ; `additionRejouerAnimation()` + `additionFlashAjout()` / `additionFlashRetrait()` / `additionRetirerLigneAnimee()` (flash vert à l'ajout, rouge au décrément, fondu rouge à zéro — la ligne perd ses `id` dès le début du fondu pour qu'un ré-ajout immédiat ne retombe pas dessus, avec `pointer-events:none` et un `setTimeout` de sécurité ; garde ajoutée en tête de `additionRemoveArticle()` si la ligne est déjà en train de partir) ; `additionArmerVider()` / `additionDesarmerVider()` (confirmation en deux temps du bouton VIDER, désarmement auto à 2,6 s, émission de `resetArticles` — le même événement que le RESET du footer) |
| `laboutik/static/css/addition.css` | Portage de la section TICKET du prototype : `#addition` en colonne `--surface` avec `border-left`, `#addition-list` en `flex:1` (fin du `calc()` sur `--addition-legend-heigh`), `.addition-line-grid` en `.tk-line` (grille `40px 1fr auto`, `gap:10px`, plus de carte grise — un filet `inset` entre lignes), `.addition-remove-btn` en `.tk-minus` (carré 40 px arrondi, `--surface-2`, rouge à l'appui) au lieu du cercle rouge, textes en `--fs-min` / `--text-faint`, montant en colonne de 62 px mini, panier vide en `.tk-empty`, keyframes `addition-line-in` (vert, ajout), `addition-line-out` (rouge, décrément) et `addition-line-vanish` (fondu rouge à zéro), et `.addition-vider` porté sur `.tk-reset` (discret, `--surface-2` à l'appui, rouge `--invalid` une fois armé, effacé quand désactivé) |
| `laboutik/templates/cotton/header.html` | Un titre de section par groupe (`.menu-panel-title`, comme la maquette) ; `style="text-decoration:none"` inline retiré des liens points de vente (désormais dans le CSS) ; la variable de boucle des points de vente est renommée `pv` → `pv_item` (elle masquait le `pv` du contexte, le point de vente courant), ce qui permet de poser `aria-current="true"` + une coche sur la ligne courante |

### A faire / To do

**Reste du panneau addition** — un seul écart avec la maquette : le total et les
boutons « Check carte » / « Valider » y vivent dans le panneau ticket, alors
qu'ici ils sont dans le `<footer>` pleine largeur (`cotton/footer.html`,
`views.css`). Les déplacer dans `#addition` demande de bouger ce markup et de
recâbler `footer.js` + `updateBtValider` — à traiter dans un lot suivant.
/ One gap left: total and action buttons still live in the full-width footer.

**Traductions** — six nouveaux msgid : « Points de vente » (titre de section)
et « Point de vente actuel » (`aria-label` de la coche) dans `cotton/header.html`,
« Vider », « Confirmer », « article » et « articles » dans `cotton/addition.html`. Les
fichiers de traduction n'ont pas ete touches : a reprendre au prochain
`makemessages` / `compilemessages`. En attendant, ces deux chaines s'affichent
en francais quelle que soit la langue.
/ Six new msgids. Translation files were left untouched: to be picked up by the
next makemessages/compilemessages run. Until then those strings render in French
in every locale.

### Verification / Verification

Aperçus statiques générés hors dépôt (tuiles : multi-tarif, prix libre, prix au
poids, méthode `VC`, alerte et rupture de stock, article bloquant, adhésion,
article sans visuel, catégorie sans couleur, tuile billet, en 2/3/4 colonnes ;
menu ouvrant : menu principal, sous-menu PV avec ligne courante, ancrage
gauche/droite ; ticket : rempli, bouton VIDER armé, panier vide).

À contrôler sur la stack : ajout au panier (pastille de comptage, flash vert de
la ligne, rebond du badge sur la tuile), retrait ligne à ligne, bouton VIDER
(premier appui = « Confirmer », désarmement à 2,6 s, deuxième appui = vidage
complet des tuiles et du panier), RESET du footer qui doit remettre la pastille
à « — » et désactiver VIDER, filtre par catégorie, appui long, swap HTMX de la
pastille stock.

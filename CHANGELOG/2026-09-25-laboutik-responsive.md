# LaBoutik : audit et corrections du responsive / LaBoutik: responsive audit and fixes

**Date :** 2026-09-25
**Migration :** Non

## Resume / Summary

**Quoi / What :** relecture de tout le CSS de `laboutik/` aux largeurs 320, 360, 414, 768,
1024 et 1280 px, et en paysage (740 × 360). Corrections des débordements, des hauteurs
d'écran mobile, des cibles tactiles trop petites et des media queries.
/ Review of all laboutik CSS at phone, tablet, desktop and landscape sizes; fixes for
  overflow, mobile viewport height, small touch targets and media queries.

**Pourquoi / Why :** plusieurs écrans cassaient sur petit écran ou en paysage :
- à 320 px, le burger de l'en-tête sortait de l'écran ;
- sur mobile, `100vh` faisait passer le bas de page (Valider, pieds de modale) sous la barre du navigateur ;
- en paysage, il ne restait qu'environ 110 px pour les articles ;
- à 1024 px, le bouton « Vider » du ticket débordait ;
- l'interface restaurant et la carte gérée avaient des tailles fixes qui débordaient.

/ Several screens broke on small or landscape screens (header burger cut off at 320px,
  bottom hidden under the mobile browser bar, 110px left for articles in landscape, cart
  « Empty » button overflowing at 1024px, fixed-size restaurant and managed-card screens).

## Changements principaux / Main changes

1. **Hauteur d'écran mobile.** `100vh` est suivi de `100dvh` (repli `vh` pour les
   WebView anciennes) :
   - dans `body` et `.h100v` (`modele00.css`) ;
   - dans `#contenu` (restaurant) et `#article-panel` ;
   - dans le clavier virtuel (`max-height`).

   `100vw` est remplacé par `100%`, ou par `inset: 0` pour les voiles plein écran.
2. **En-tête à 320 px** : le titre du PV peut rétrécir (`min-width: 0`) et son nom se coupe
   par « … ». Le bandeau **mode école** devient une bande fine posée sous l'en-tête. Il ne
   change donc plus la hauteur de 49 px, dont dépendent la grille et le menu burger.
   Couleur : token `--mode-ecole`.
3. **Panier replié (≤ 1022 px)** : le nombre magique `200px`, présent dans trois fichiers,
   devient `--addition-collapsed-height` (`sizes.css`). En paysage bas (≤ 500 px de haut),
   il passe à 144 px et le panier se compacte.
4. **Media queries** : la syntaxe `(width > 599px)` n'est comprise qu'à partir de
   Chrome/WebView 104. Elle est réécrite en `(min-width: 600px | 1023px | 1200px)`, ce qui
   donne le même comportement et reste compatible avec les SUNMI anciens.
5. **Modale cotton** (`cotton/modal.html`) :
   - largeur `min(…, 100% - 32px)` et `max-height` en `dvh` ;
   - grille en-tête / contenu / pied : le pied n'est plus coupé en paysage ;
   - fermeture à 44 px.
6. **Interface restaurant** : empilement sur une colonne sous 1022 px. Le pavé de
   paiement passe en `auto-fill` (avant : 6 × 80 px fixes, soit 512 px minimum). Les
   catégories du bas défilent au lieu d'être coupées.
7. **Carte gérée** : colonne flex qui défile, pavé et actions empilés sous 600 px. Les
   touches du pavé font entre 56 et 80 px selon l'écran (`--key-*`).
8. **Cibles tactiles ≥ 44 px** : retour d'en-tête, ±  des billets/pièces (30 px avant),
   boutons des ventes, fermeture du clavier de carte, retour récap, bouton hors stock,
   indicateur réseau, bouton Vider.
9. **Débordements de texte** (`overflow-wrap` / `minmax(0,1fr)` / ellipse) :
   - libellés des boutons de popup, des tarifs et des moyens de paiement ;
   - soldes et montants KPI ;
   - grille des articles et lignes du ticket ;
   - titre du ticket.
10. **Dette** :
    - suppression du doublon `.sortie-alerte-btn-*` dans `overlay.css`, dont le résultat dépendait de l'ordre de chargement ;
    - suppression d'un bloc `@media` en double et d'une media query vide ;
    - `:hover` placés dans `@media (hover: hover)` (pas de survol « collé » au doigt) ;
    - couleurs hex des tuiles billet remplacées par des tokens ;
    - `z-index` sans effet supprimé.

11. **Panier responsive (retours du 2026-09-25)** :
    - le chevron du ticket tourne avec `transform: rotate()`. La propriété `rotate` seule
      n'existe qu'à partir de Chrome 104 et les WebView anciennes l'ignoraient ;
    - le titre qui porte le chevron n'est plus coupé par l'ellipse ;
    - VALIDER / CHECK CARTE restent à la même hauteur, panier ouvert ou fermé. Le panier
      replié devient une colonne flex et l'espace en trop passe au-dessus du total. Marge
      basse fixe de 16 px, plus `safe-area-inset-bottom`.
    - le ticket s'ouvre et se ferme au clic sur **toute la bande** `.addition-head-responsive`
      (pastille, espace vide, titre), et non plus seulement sur le titre. La bande a
      `role="button"`, le focus clavier (Entrée / Espace), `aria-controls` et un
      `aria-expanded` mis à jour par `toggleAdditionResponsive()` (addition.js) ;
    - le `data-testid="addition-ouvrir-responsive"` est désormais sur la bande. Il valait
      avant `addition-vider` sur le titre, comme le bouton Vider (aucun test ne l'utilisait).
      Les attributs `type` / `disabled`, sans effet sur un `<span>`, sont retirés du titre.
12. **Menu burger qui ne s'ouvrait pas à chaque clic sur le nom du PV** (`cotton/header.html`).
    `toggleMenuBurger()` lisait `event.target`, c'est-à-dire l'enfant touché (le `<span>` du
    nom ajouté au point 2, l'icône ou le chevron) :
    - la classe `menu-burger-active` se posait sur cet enfant ;
    - l'écouteur global de clic refermait aussitôt le menu ;
    - la classe restait collée sur l'enfant, et le clic suivant prenait la branche « fermer ».

    Correction : `event.currentTarget` dans le toggle, et `closest()` dans l'écouteur global.

13. **Tuiles billet sur petit écran** (`billet_tuile.css`, < 600 px) : elles occupent les
    2 colonnes de la grille (`grid-column: span 2`) au lieu d'une seule. À 360 px, elles
    passent de 136 à 280 px de large. Grand écran inchangé.

14. **Animation d'ouverture du ticket responsive** (`addition.css`, CSS seul, 220 ms) :
    - le panneau se déroule du bas vers le haut (`clip-path`), sans que VALIDER / CHECK
      CARTE bougent ;
    - la liste apparaît en fondu, avec une légère montée ;
    - désactivée avec `prefers-reduced-motion`.

    La fermeture reste instantanée. Le contenu passe en `display: none`, et animer la
    sortie demanderait du JS ou `@starting-style` / `transition-behavior` (Chrome 117+),
    absents des WebView SUNMI.

### Choix qui s'écartent de l'audit / Deliberate deviations
- **Bandeau mode école** : il reste dans `<header>`, en position absolue. Le sortir du
  header aurait ajouté un élément à la grille `#contenu` de l'interface restaurant.
- **Popup tarif** : elle reste sur la grille, le ticket restant visible comme le veut la
  maquette. Elle ne passe en plein écran qu'en paysage bas.
- **Tableau de succès multi-monnaies** : la colonne « Payé » n'est pas masquée en mobile.
  Les colonnes sont resserrées et aucune information n'est perdue.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/css/modele00.css` | `dvh`, `.h100v`/`.l100v`, hover mouse-only, `.bt-basic-text` wrap, plancher des boutons seulement si écran ≥ 600 px de haut, media queries `min-width` |
| `laboutik/static/css/sizes.css` | `--addition-collapsed-height` (+ palier paysage), touches `clamp(56px, …, 80px)` |
| `laboutik/static/css/palette.css` | Token `--mode-ecole` |
| `laboutik/static/css/views.css` | Variable du panier replié, suppression du `@media` dupliqué |
| `laboutik/static/css/header.css` | Titre rétrécissable, `.header-title-nom`, `.bandeau-mode-ecole`, retour à 44 px |
| `laboutik/static/css/categories.css` | Variable du panier replié, media query vide supprimée, seuil 1278 → 1200 |
| `laboutik/static/css/addition.css` | Variable, paysage compact, en-tête du ticket à 1024 px, `minmax(0,1fr)`, Vider 44 px |
| `laboutik/static/css/articles.css` | `minmax(0,1fr)`, panneau article `min(100%, max(360px, 40%))` + `dvh`, seuil 768 → 599, voile `inset:0` |
| `laboutik/static/css/restaurant_interface.css` | `dvh`, colonnes `minmax`, empilement ≤ 1022 px |
| `laboutik/static/css/win_bottom_left.css` / `win_bottom_right.css` | Défilement des catégories, pavé `auto-fill` |
| `laboutik/static/css/hx_managed_card.css` / `numpad.css` | Colonne qui défile, empilement mobile, paysage |
| `laboutik/static/css/ventes.css` | KPI rétrécissables et `clamp`, retour à la ligne 600–1022 px, cibles 44 px |
| `laboutik/static/css/sortie_de_caisse.css` | ± à 44 px, ellipse, `flex-wrap`, focus des alertes |
| `laboutik/static/css/overlay.css` | Doublon supprimé, 44 px, montant total et tableau multi-monnaies en mobile |
| `laboutik/static/css/tarif.css` | Libellés qui passent à la ligne, plein écran en paysage bas |
| `laboutik/static/css/components.css` | Bouton de simulation NFC en bas à gauche, soldes qui passent à la ligne |
| `laboutik/static/css/vk.css`, `ws_indicator.css`, `billet_tuile.css` | Hauteur max + safe-area, 44 px, tokens + hauteur adaptative |
| `laboutik/templates/cotton/header.html` | Bandeau mode école en classe CSS, `<span>` autour du nom du PV |
| `laboutik/templates/cotton/modal.html` | Largeur/hauteur bornées, grille, `inset:0`, fermeture 44 px |
| `laboutik/templates/cotton/tables_definition.html` | Modale « ajouter une table » en hauteur auto |
| `laboutik/templates/laboutik/partial/article_panel_stock.html` | Bouton hors stock à 44 px |
| `laboutik/templates/cotton/addition.html` | Bande responsive cliquable (`role`, `aria-*`, clavier), `data-testid` renommé |
| `laboutik/static/js/addition.js` | `toggleAdditionResponsive()` met à jour `aria-expanded` |

### Migration
- **Migration necessaire / Migration required:** Non

## Tests a realiser / How to test

### Automatiques (passés le 2026-09-25)
```bash
poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_laboutik_*.py \
  tests/pytest/test_paiement_*.py tests/pytest/test_cloture_*.py tests/pytest/test_retour_carte_*.py -q  # 162 passed
poetry run pytest tests/e2e/test_addition_oubli_du_client.py -q                                      # 6 passed
```
Vérification Playwright de la caisse (PV « Bar ») et des ventes, à 320, 360, 414, 768, 1024,
1280 et 740 × 360 : aucun défilement horizontal, burger et bouton Valider visibles.

### Test 1 : caisse sur téléphone (DevTools, 320 × 640 puis 740 × 360)
1. Ouvrir un PV en service direct.
2. Le burger est visible à droite. Un nom de PV long se coupe par « … ».
3. Le bouton VALIDER est entièrement visible en bas.
4. En paysage, une rangée d'articles reste visible au-dessus du panier compact.

### Test 2 : tablette 1024 × 768
1. Ajouter un article. Dans l'en-tête du ticket, titre, compteur et « Vider » tiennent
   dans le panneau. Le titre se coupe si besoin.

### Test 2 bis : ouvrir / fermer le ticket (≤ 1022 px)
1. Toucher n'importe où sur la bande du haut du ticket (pastille, vide, titre) : le ticket
   s'ouvre ou se ferme et le chevron se retourne (aussi sur SUNMI).
2. VALIDER et CHECK CARTE ne bougent pas entre ticket ouvert et fermé.

### Test 2 ter : menu du point de vente
1. Toucher plusieurs fois de suite le nom du PV, puis son icône, puis le chevron : le menu
   s'ouvre puis se ferme à chaque fois, et le chevron se retourne.
2. Même chose avec l'icône burger à droite.

### Test 3 : popups
1. Paiement, tarif multiple, prix libre : à 320 px et en paysage, la popup défile et sa
   croix (44 px) n'est pas recouverte.
2. Mode démo NFC : le bouton de simulation est en bas à gauche.

### Test 4 : mode école
1. Activer le mode école. Une bande orange s'affiche sous l'en-tête.
2. La hauteur de l'en-tête et le menu burger ne bougent pas. Les touchers passent à travers la bande.

### Test 5 : à faire sur appareil réel (non vérifié ici)
- **SUNMI V2s et D3 Mini** : bascule des breakpoints (`min-width`), clavier virtuel.
- **Interface restaurant** (PV avec tables) : aucun PV de ce type dans les données de dev.
- **Écran « carte gérée »** : pavé entier en portrait et en paysage.

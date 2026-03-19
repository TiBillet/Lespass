# UX Phase 4 — Polish header, sidebar et footer

## Prompt

```
On travaille sur l'UX de l'interface POS LaBoutik.
Lis le plan UX : laboutik/doc/UX/PLAN_UX_LABOUTIK.md (section "Session 4").
Cette session ameliore les zones permanentes de l'interface : header, sidebar categories, footer.

Contexte technique :
- Interface POS tactile (caisse de bar/restaurant)
- Stack : Django + HTMX + CSS custom, JS vanilla
- Skill /stack-ccc : commentaires FALC bilingues FR/EN
- Composants cotton : header.html, categories.html
- Variables CSS : palette.css, sizes.css (--header-height, --cat-width, --footer-container-height)

Prerequis : Phase 1 UX (filtre categories + highlight) doit etre faite.

Tache 1 — Header : renforcer la lisibilite :

1. Lis `laboutik/templates/cotton/header.html`.
2. Le titre "Service direct - Bar" utilise clamp(1rem, 3.5vw, 2.5rem).
   Verifier la lisibilite sur une tablette 1278px.
3. Ajouter un accent de couleur sous le header (border-bottom 3px solid var(--vert03)
   ou la couleur du PV si disponible).
4. Verifier que le logo TiBillet est visible (contrast suffisant sur fond --noir03).

Tache 2 — Sidebar categories :

1. Lis `laboutik/templates/cotton/categories.html`.
2. Ajouter un separateur visuel entre "Tous" et les categories specifiques
   (border-bottom 2px solid var(--gris03) apres le premier item).
3. Verifier que "Vins & Spiritueux" ne deborde pas — si oui, reduire
   la font-size du label ou utiliser text-overflow: ellipsis.
4. Verifier que chaque item fait au moins 48x48px de zone tactile
   (minimum Google Material Design pour le tactile).
5. Ajouter text-wrap: balance sur les noms de categories longs.

Tache 3 — Footer : equilibrage et polish :

1. Lis les templates qui rendent le footer (chercher RESET, CHECK CARTE, VALIDER
   dans les templates views/).
2. Verifier que les 3 zones font chacune ~33% de la largeur.
3. Verifier le contraste texte/fond sur chaque bouton :
   - RESET (fond rouge) : texte blanc
   - CHECK CARTE (fond bleu) : texte blanc
   - VALIDER (fond vert) : texte blanc
4. Ajouter `tabular-nums` sur le montant du bouton VALIDER (ex: "11 €").
5. Verifier que la hauteur du footer (--footer-container-height: 90px)
   est suffisante pour le tactile.

Tache 4 — Menu burger : animation et overlay :

1. Lis `laboutik/templates/cotton/header.html` — repere le menu burger.
2. Le menu s'affiche/masque sans animation.
3. Ajouter :
   a. Transition CSS slide-down (transform: translateY(-10px) → 0 + opacity 0→1, 200ms)
   b. Overlay semi-transparent sur le reste de l'interface quand le menu est ouvert
   c. Fermer le menu au clic en dehors (addEventListener 'click' sur document)
4. S'assurer que le menu est au-dessus de tout (z-index suffisant).

Regles :
- Commentaires FALC bilingues FR/EN
- data-testid sur les nouveaux elements
- Ne pas casser les tests existants
- CSS `transition` pour les animations (interruptible)
```

## Verification Chrome

### Test 1 : Header lisible
1. Ouvrir la page POS
   - **Attendu** : le titre "Service direct - Bar" est lisible
   - **Attendu** : un accent de couleur (bordure basse) est visible sous le header
2. Redimensionner la fenetre en 1278px de large (tablette)
   - **Attendu** : le titre reste lisible sans troncature

### Test 2 : Sidebar categories
1. "Tous" doit etre visuellement separe des categories specifiques
   (separateur visible entre "Tous" et "Bar")
2. "Vins & Spiritueux" doit etre entierement lisible ou tronque proprement
3. Cliquer sur chaque categorie → zone tactile reactive (pas besoin de viser au pixel)

### Test 3 : Footer equilibre
1. Les 3 boutons doivent occuper toute la largeur de maniere equilibree
2. Le montant sur VALIDER doit etre en chiffres alignes (tabular-nums)
3. Le texte doit etre lisible sur chaque fond de couleur

### Test 4 : Menu burger
1. Cliquer sur le menu burger (icone ☰ en haut a droite)
   - **Attendu** : le menu s'ouvre avec une animation slide-down douce
   - **Attendu** : un overlay semi-transparent couvre le reste de la page
2. Cliquer en dehors du menu
   - **Attendu** : le menu se ferme
3. Cliquer sur "POINTS DE VENTES" dans le menu
   - **Attendu** : navigation fonctionnelle

### Test responsive
1. Chrome DevTools → Toggle device toolbar → 1278x800 (Sunmi D3mini)
   - **Attendu** : header, sidebar, footer visibles et utilisables
2. Reduire a 599px (mobile) → verifier que rien ne deborde

## Fichiers concernes

- `laboutik/templates/cotton/header.html` — header + menu burger
- `laboutik/templates/cotton/categories.html` — sidebar categories
- `laboutik/templates/laboutik/views/common_user_interface.html` — footer
- `laboutik/static/css/modele00.css` — classes BF, styles globaux
- `laboutik/static/css/sizes.css` — variables dimensions

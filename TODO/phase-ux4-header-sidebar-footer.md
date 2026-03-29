# Phase UX4 — Polish header, sidebar categories et footer

## Ce qui a ete fait

Ameliorations visuelles et d'accessibilite sur les zones permanentes de l'interface POS :
header, sidebar categories, footer et menu burger.
Objectif : un benevole en festival comprend chaque zone en 1 seconde, sur desktop ET mobile.

### Modifications

| Fichier | Changement |
|---|---|
| `laboutik/templates/cotton/header.html` | Bordure accent vert 3px sous le header, `text-wrap: balance` sur titre, `role="button"` + `aria-label` + `data-testid` sur icone burger, `aria-label` + `data-testid` sur nav menu, overlay semi-transparent `#menu-burger-overlay`, animation slide-down 200ms via `visibility` + `opacity` + `transition` (classe `.menu-open`), menu pleine largeur mobile (<600px) |
| `laboutik/templates/cotton/categories.html` | Separateur 2px `--gris01` sous `#category-all`, `text-wrap: balance` + `overflow: hidden` + `max-height: 2.4em` sur `.category-nom` |
| `laboutik/templates/laboutik/views/common_user_interface.html` | `font-variant-numeric: tabular-nums` sur `#bt-valider-total`, `.toFixed(2)` dans `updateBtValider()`, `data-testid` sur les 3 boutons footer |
| `locale/fr/LC_MESSAGES/django.po` | Traductions "Menu", "Menu principal" |
| `locale/en/LC_MESSAGES/django.po` | Traductions "Menu", "Main menu" |

## Tests a realiser

### Test 1 : Header — accent visuel
1. Ouvrir `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/`
2. Verifier qu'une bordure verte 3px est visible sous le header
3. Verifier que le titre est centre et equilibre (`text-wrap: balance`)

### Test 2 : Menu burger — animation et overlay
1. Cliquer sur l'icone burger (en haut a droite)
2. Verifier que le menu apparait avec une animation slide-down (~200ms)
3. Verifier qu'un overlay sombre semi-transparent couvre le reste de l'ecran
4. Cliquer sur l'overlay → le menu doit se fermer
5. Ouvrir et fermer le menu 5 fois rapidement → pas de bug d'etat
6. Ouvrir le menu → cliquer POINTS DE VENTES → le sous-menu doit s'afficher normalement

### Test 3 : Sidebar categories — separateur et noms longs
1. Verifier qu'un trait gris 2px separe "Tous" des categories specifiques
2. Si une categorie a un nom long (ex: "Vins & Spiritueux"), verifier qu'il est equilibre sur 2 lignes max

### Test 4 : Footer — total 2 decimales et tabular-nums
1. Ajouter un article a 6.50 €
2. Verifier que le total du bouton VALIDER affiche "6.50" (pas "6.5")
3. Ajouter un 2e article → le total passe a "13.00" sans decalage visuel (tabular-nums)

### Test 5 : data-testid
Ouvrir Chrome DevTools et verifier la presence de :
- `[data-testid="burger-icon"]` sur l'icone burger
- `[data-testid="menu-burger"]` sur le nav du menu
- `[data-testid="menu-burger-overlay"]` sur l'overlay
- `[data-testid="footer-reset"]` sur le bouton RESET
- `[data-testid="footer-check-carte"]` sur le bouton CHECK CARTE
- `[data-testid="footer-valider"]` sur le bouton VALIDER

### Test 6 : i18n
1. Basculer la locale en EN
2. Verifier que l'aria-label du burger dit "Menu"
3. Verifier que l'aria-label du nav dit "Main menu"

### Test 7 : Responsive
1. Chrome DevTools → 1920px desktop : tout visible et correct
2. Chrome DevTools → 1278x800 (Sunmi D3mini) : tout visible et utilisable
3. Chrome DevTools → 375x667 (mobile) : menu burger pleine largeur, overlay couvre tout

## Compatibilite

- 0 fichier Python modifie → pas de risque de regression backend
- Les sous-menus internes du burger continuent d'utiliser `.hide` (inchange)
- Seul `#menu-burger-container` utilise le nouveau systeme `.menu-open`
- Le listener `document.click` existant gere deja la fermeture au clic overlay (pas de nouveau listener)
- 98 tests pytest verts

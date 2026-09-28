# Popup tarif (#tarif-overlay) : tient dans l'écran et couvre les catégories sur petit écran

## Ce qui a été fait

Sur téléphone, la popup de choix du tarif (multi-tarif, prix libre, poids) sortait de l'écran :
le haut (titre, croix) et le bas (« Ajouter ») étaient coupés. Elle était aussi posée uniquement
sur la grille d'articles, pas sur la colonne des catégories.

Deux causes, corrigées en CSS seul (aucun changement JS) :

1. `.tarif-overlay` est une grille sans pistes définies. Sa ligne `auto` grandissait avec le contenu,
   donc le `max-height: 100%` de la boîte ne limitait rien. Ajout de
   `grid-template-rows / grid-template-columns: minmax(0, 1fr)` (même motif que `.card-modal`).
   La boîte reste dans le voile et défile à l'intérieur. Vaut pour tous les écrans.
2. Sur écran ≤ 1022 px (panier replié en bas), la popup passe en `position: fixed`, de
   `--header-height` jusqu'à `--addition-collapsed-height`, sur toute la largeur. Elle couvre donc
   catégories + articles. Le panier replié reste visible.
   En paysage (hauteur ≤ 500 px), la popup reste en plein écran (`inset: 0`).

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/static/css/tarif.css` | Pistes de grille du voile, media query ≤ 1022 px en `fixed`, `inset: 0` en paysage |
| `tests/e2e/test_tarif_popup.py` | 3 tests : voile au-dessus des catégories (360×640), pavé prix libre qui reste dans le voile, grande grille basse |

## Tests à réaliser

### Test 1 : téléphone portrait (SUNMI V2s / DevTools 360×640)
1. Ouvrir la caisse, toucher un produit à plusieurs tarifs.
2. Vérifier : le voile couvre catégories + articles, sous le header. Le panier replié reste visible en bas.
3. Toucher un tarif fixe : il s'ajoute au panier, la popup reste ouverte.

### Test 2 : prix libre sur téléphone
1. Toucher un produit à prix libre, puis la tuile du prix libre pour ouvrir le pavé.
2. Vérifier : titre et croix visibles en haut ; faire défiler la boîte jusqu'à « Ajouter ». Rien n'est coupé.
3. Taper un montant, « Ajouter » : la ligne arrive dans le panier.

### Test 3 : poids / mesure sur téléphone
Même vérification qu'au test 2 avec un produit au poids.

### Test 4 : fermeture
- Toucher le voile au-dessus de la zone des catégories : la popup se ferme.
- La grille retrouve sa position de défilement.

### Test 5 : autres écrans
- Tablette 768×1024 : même comportement que le téléphone.
- Ordinateur 1280×800 : inchangé (popup sur la grille seule, panier à droite).
- Téléphone paysage 740×360 : popup en plein écran.

### Tests automatiques
```bash
poetry run pytest tests/e2e/test_tarif_popup.py -v
```
Note : `test_echap_ferme_la_popup` et `test_le_premier_tarif_recoit_le_focus_a_l_ouverture`
échouent déjà avant ce changement. Le focus sur le premier tarif est commenté dans
`laboutik/static/js/tarif.js` (« Pas sur de l'utilité de ça »). Sans ce focus, Échap
n'atteint pas la popup.

## Compatibilité
- Aucune migration.
- Les catégories ne sont pas rendues `inert` au clavier (le voile bloque seulement le toucher).

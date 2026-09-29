# Popup tarif (#tarif-overlay) sur petit écran, largeur des catégories, bouton Vider déplacé

## Ce qui a été fait

Sur téléphone, la popup de choix du tarif (multi-tarif, prix libre, poids) sortait de l'écran :
le haut (titre, croix) et le bas (« Ajouter ») étaient coupés. Elle était aussi posée uniquement
sur la grille d'articles, pas sur la colonne des catégories.

Deux causes, corrigées en CSS :

1. `.tarif-overlay` est une grille sans pistes définies. Sa ligne `auto` grandissait avec le contenu,
   donc le `max-height: 100%` de la boîte ne limitait rien. Ajout de
   `grid-template-rows / grid-template-columns: minmax(0, 1fr)` (même motif que `.card-modal`).
   La boîte reste dans le voile et défile à l'intérieur. Vaut pour tous les écrans.
2. Sur écran ≤ 1022 px (panier replié en bas), la popup passe en `position: fixed`, de
   `--header-height` jusqu'à `--addition-collapsed-height`, sur toute la largeur. Elle couvre donc
   catégories + articles. Le panier replié reste visible.
   En paysage (hauteur ≤ 500 px), la popup reste en plein écran (`inset: 0`).

Autres changements du même commit :

3. **Focus sur le premier tarif réactivé** (`tarif.js`). À l'ouverture, le clavier et le lecteur
   d'écran entrent directement dans la popup. Échap la ferme à nouveau.
4. **Crash au toucher du voile corrigé** (`articles.js`). Toucher le voile supprime la popup,
   puis le clic remonte jusqu'à `manageKey()` avec un parent `null`. Une garde arrête la fonction.
5. **Catégories plus larges sur téléphone** (`sizes.css`) : `--cat-width` passe de 64 à 84 px
   sous 600 px de large.
6. **Bouton Vider déplacé** de l'en-tête du panier vers la rangée d'actions, à gauche de
   CHECK CARTE (`addition_footer.html`). C'est une tuile en colonne de largeur fixe (76 px,
   68 px entre 1023 et 1199 px). Quand il est armé, le libellé « Confirmer » ne l'élargit pas :
   VALIDER garde sa place et la rangée ne déborde pas du panneau. Bordure transparente au repos
   (pas de décalage de 2 px au premier article), anneau de focus clavier `--nfc`.

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/static/css/tarif.css` | Pistes de grille du voile, media query ≤ 1022 px en `fixed`, `inset: 0` en paysage |
| `laboutik/static/js/tarif.js` | Focus sur le premier tarif réactivé |
| `laboutik/static/js/articles.js` | Garde `if (!ele) return` dans `manageKey()` |
| `laboutik/static/css/sizes.css` | `--cat-width` 64 → 84 px sous 600 px |
| `laboutik/templates/cotton/addition.html` | Bouton Vider retiré de l'en-tête |
| `laboutik/templates/cotton/addition_footer.html` | Bouton Vider dans la rangée d'actions |
| `laboutik/static/css/addition.css` | Tuile Vider à largeur fixe, bordure transparente, `:focus-visible` sur Vider et les actions, `min-width: 0` sur VALIDER, tuiles à 68 px entre 1023 et 1199 px |
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

### Test 6 : bouton Vider dans la rangée d'actions
1. Écrans à tester : téléphone 320×568 et 360×640 (panier replié), ordinateur 1023×768
   (panneau le plus étroit) et 1280×800.
2. Panier vide : Vider est estompé et désactivé. Ajouter un article : Vider prend un contour
   rouge. CHECK CARTE et VALIDER **ne bougent pas** d'un pixel.
3. Toucher Vider : il devient rouge plein avec « Confirmer ». La rangée reste dans le panneau,
   VALIDER garde son icône et son texte entiers, sans défilement horizontal.
4. Attendre ~3 s sans toucher : Vider se désarme. Ou toucher deux fois : le panier se vide.
5. Au clavier (Tab) : un anneau bleu apparaît sur Vider, CHECK CARTE et VALIDER.
   Au toucher : aucun anneau.

### Tests automatiques
```bash
poetry run pytest tests/e2e/test_tarif_popup.py -v
```
Avec le focus réactivé, `test_echap_ferme_la_popup` et
`test_le_premier_tarif_recoit_le_focus_a_l_ouverture` doivent repasser.

## Compatibilité
- Aucune migration.
- Les catégories ne sont pas rendues `inert` au clavier (le voile bloque seulement le toucher).

# Colonne Stock et filtre « État du stock » dans les listes (option B)

## Ce qui a été fait
Voir `CHANGELOG/2026-09-29-admin-stock-dans-la-fiche-produit.md`.

Listes Produits de caisse et Fûts : colonne « Stock » (badge coloré, clic vers la
section Stock de la fiche) et filtre Épuisé / Stock bas / OK / Non suivi.
Code : `html_badge_stock_avec_lien` et `EtatStockFilter` dans
`Administration/admin/stock_fiche_produit.py`.

## Tests à réaliser

### Test 1 : couleurs du badge
Préparer 4 produits : stock 0, stock 3 avec seuil 5, stock 50, sans stock.
1. Produits de caisse : badge rouge « Épuisé », orange « 3 », vert « 50 », « — ».
2. Un stock en centilitres de 150 s'affiche « 1.5 L ».

### Test 2 : clic sur le badge
1. Cliquer un badge : la fiche produit s'ouvre et défile jusqu'à la section Stock.

### Test 3 : filtre
1. Filtres > État du stock > Stock bas : seul le produit à 3 (seuil 5) reste.
2. Épuisé, OK, Non suivi : un produit chacun.

### Test 4 : tri
1. Cliquer l'en-tête « Stock » : tri par quantité croissante puis décroissante.

### Test 5 : pas de requête par ligne
Avec la Django Debug Toolbar (si active) : le nombre de requêtes de la liste ne
grandit pas avec le nombre de produits.

## Compatibilité
Aucune édition de quantité dans la liste : chaque changement reste un mouvement tracé.

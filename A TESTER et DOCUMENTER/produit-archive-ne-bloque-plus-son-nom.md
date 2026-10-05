# Un produit archivé ne bloque plus son nom

## Ce qui a été fait
La contrainte d'unicité (catégorie, nom) de `Product` ne s'applique plus qu'aux produits
non archivés. Détails : `CHANGELOG/2026-09-30-produit-archive-ne-bloque-plus-son-nom.md`.

## Tests à réaliser

### Test 1 : recréer un produit du même nom
1. Admin > Produits : archiver un produit (ex : « Concert »).
2. Créer un nouveau produit « Concert » dans la même catégorie.
3. Le produit est créé sans erreur.

### Test 2 : deux produits actifs du même nom
1. Créer un second produit actif portant le nom d'un produit actif de la même catégorie.
2. Le formulaire affiche une erreur, rien n'est créé.

### Test 3 : désarchiver
1. Avec les produits du test 1 : afficher les produits archivés, cliquer « Désarchiver »
   sur l'ancien « Concert ».
2. Message d'erreur : un produit de ce nom existe déjà. L'ancien reste archivé.
3. Renommer le nouveau produit, recommencer : l'ancien est désarchivé.

### Test 4 : import d'adhésions
1. Avoir un produit adhésion archivé et un produit adhésion actif du même nom.
2. Importer un fichier d'adhésions avec ce nom de produit.
3. Les adhésions sont rattachées au produit actif.

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_product_nom_unique_si_non_archive.py -v
```

## Compatibilité
- Les rapports de caisse et la comptabilité regroupent les ventes par nom de produit :
  un produit archivé et son remplaçant du même nom apparaissent sur la même ligne.
- Les produits « système » retrouvés par nom (`get_or_create` : vente par lien QR code,
  « Recharge … », « Free booking ») plantent en `MultipleObjectsReturned` si un produit
  archivé et un produit actif portent leur nom dans la même catégorie.

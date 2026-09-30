# Issue #459 : duplication d'un produit « réservation gratuite »

## Ce qui a été fait
Dans `Administration/admin/products.py` (`_duplicate_product`), le tarif gratuit créé
automatiquement à l'enregistrement du nouveau produit est effacé avant la copie des tarifs
du produit source. La copie a maintenant exactement les mêmes tarifs que le source.

Détails : `CHANGELOG/2026-09-30-issue-459-duplication-tarif-gratuit-en-trop.md`.

## Tests à réaliser

### Test 1 : réservation gratuite
1. Admin > Produits > un produit de catégorie « réservation gratuite » avec deux tarifs
   (ex : « participer au chantier »).
2. Cliquer sur « Dupliquer ».
3. Ouvrir la copie « … [DUPLICATA] » : elle a les deux mêmes tarifs, pas de troisième tarif gratuit.

### Test 2 : billet payant
1. Dupliquer un produit billet payant.
2. La copie a les mêmes tarifs que le source.

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_duplication_produit_issue_459.py -v
```

## Compatibilité
Les duplicatas déjà créés avant ce correctif gardent leur tarif gratuit en trop : il faut
le supprimer à la main (il sera archivé).

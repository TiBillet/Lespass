# Archivage des tarifs (« supprimer » un tarif l'archive)

## Ce qui a été fait
`Price.delete()` n'efface plus la ligne : il passe `archived=True` et `publish=False`.
Les ventes passées (`PriceSold`, tickets, adhésions, lignes comptables) gardent leur lien
vers le tarif. Un tarif archivé n'est plus affiché ni accepté nulle part.
La suppression est réactivée dans l'admin et elle archive.

Détails : `CHANGELOG/2026-09-30-archivage-tarif.md`.

Points d'attention :
- `Price.objects.filter(...).delete()` (queryset) ne passe pas par `Price.delete()` :
  Django efface vraiment, ou lève `ProtectedError` si le tarif a été vendu.
- `Price.hard_delete()` efface vraiment un tarif (tests, nettoyages).
- Il n'y a pas d'écran pour désarchiver un tarif. Il faut passer par le shell.
- Migration : `BaseBillet/migrations/0231_price_archived.py`.

## Tests à réaliser

### Test 1 : supprimer un tarif déjà vendu depuis la fiche produit
1. Admin > produit billet qui a déjà des ventes > cocher « Supprimer » sur un tarif > Enregistrer.
2. Le tarif disparaît de la fiche produit, sans message d'erreur « objets protégés ».
3. Page publique de l'événement : le tarif n'est plus proposé.
4. Caisse LaBoutik : le tarif n'est plus proposé.
5. Admin > Réservations / Ventes : les anciennes lignes affichent toujours le nom du tarif.

### Test 2 : supprimer depuis la fiche tarif
1. Ouvrir la fiche d'un tarif > « Supprimer » > confirmer.
2. La page de confirmation indique que le tarif sera archivé.
3. Retour sur la fiche du produit parent, avec le message « tarif archivé ».

### Test 3 : panier en cours
1. Mettre un billet au panier.
2. Archiver son tarif dans l'admin.
3. Valider le panier : refus avec « This rate is not available. », aucune commande créée.

### Test 4 : réservation gratuite
1. Archiver le tarif à 0 € d'un produit « réservation gratuite ».
2. Enregistrer le produit : un nouveau tarif gratuit est créé automatiquement.

### Vérification en base
```bash
docker exec lespass_django poetry run python manage.py tenant_command shell --schema=lespass -c \
  "from BaseBillet.models import Price; print(Price.objects.filter(archived=True).values('name', 'publish', 'product__name'))"
```

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_price_archivage.py -v
```

## Compatibilité
- Les tarifs existants ont `archived=False` : aucun changement pour eux.
- Les sites qui filtraient déjà `publish=True` sont couverts car un tarif archivé est dépublié.

# Relations vers Product : FK proxy, limit_choices_to, autocomplete

## Ce qui a été fait
- `booking.Resource.product` pointe vers le proxy `ResourceProduct` (+ `limit_choices_to`).
- `Event.products` et `Price.adhesions_obligatoires` gardent `Product` mais ont un
  `limit_choices_to` (un proxy sur un M2M renommerait une colonne dans chaque tenant).
- `ProductAdmin.get_search_results` ne filtre plus la catégorie selon le Referer :
  Django applique `limit_choices_to` dans l'autocomplete. Les produits archivés ne
  sont jamais proposés. Stock garde son filtre VENTE.

Détails : `CHANGELOG/2026-09-29-fk-product-proxy-et-limit-choices-to.md`.

## Pré-requis
```bash
docker exec lespass_django poetry run python manage.py migrate_schemas
```
Les deux migrations (`booking 0002`, `BaseBillet 0230`) n'exécutent aucun SQL.

## Tests à réaliser

### Test 1 : produits d'un événement
1. Admin → Événements → un événement → champ « Produits ».
2. Taper quelques lettres. Attendu : uniquement des billets / réservations gratuites,
   aucun produit archivé.
3. Enregistrer l'événement → pas d'erreur.

### Test 2 : adhésions obligatoires (deux endroits)
1. Admin → un produit billetterie → inline des tarifs → « Adhésions obligatoires ».
   Attendu : uniquement des adhésions non archivées. **Avant, tous les produits
   étaient proposés ici** (bug corrigé).
2. Même chose depuis la page d'un tarif seul (`/admin/BaseBillet/price/<id>/change/`).
3. Enregistrer → pas d'erreur.

### Test 3 : ressource (booking)
1. Admin → Ressources → ajouter / modifier → champ « Produit ».
2. Attendu : uniquement des produits ressource non archivés.
3. Enregistrer → pas d'erreur.

### Test 4 : stock (non régression)
1. Admin → Inventaire → Stock → ajouter → champ « Produit ».
2. Attendu : uniquement des articles de vente (VT) non archivés, comme avant.
3. Ouvrir le stock d'un fût existant et l'enregistrer → pas d'erreur
   (pas de `limit_choices_to` sur Stock exprès).

### Test 5 : validation modèle
```bash
docker exec -i lespass_django poetry run python manage.py shell <<'EOF'
from Customers.models import Client
from django_tenants.utils import tenant_context
from django.core.exceptions import ValidationError
from BaseBillet.models import Product
from booking.models import Resource
with tenant_context(Client.objects.get(schema_name="lespass")):
    ressource = Resource.objects.first()
    ressource.product = Product.objects.filter(categorie_article=Product.BILLET).first()
    try:
        ressource.full_clean()
        print("PAS BON : un billet est accepte")
    except ValidationError as erreur:
        print("OK, refuse :", list(erreur.message_dict))
EOF
```
Attendu : `OK, refuse : ['product']`. Rien n'est enregistré (pas de `save()`).

### Test 6 : tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_*.py tests/pytest/test_event_*.py booking/tests/ -q
```

## Compatibilité
- Aucune donnée existante ne viole les nouvelles règles (vérifié sur tous les tenants).
- `resource.product` renvoie maintenant une instance `ResourceProduct` (sous-classe
  de `Product` : `isinstance(x, Product)` reste vrai).
- `Product.resources` (accès inverse) fonctionne toujours.

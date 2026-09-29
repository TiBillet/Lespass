# Proxys de Product : managers filtrants

## Ce qui a été fait
Chaque proxy de `Product` a maintenant un manager qui filtre sa catégorie :
`MembershipProduct.objects.all()` ne renvoie que les adhésions, `POSProduct.objects.all()`
que les produits avec `methode_caisse`, etc. Les filtres en double ont été retirés de
l'admin, des vues et de l'API (commits `ac07d76b` et `003baa24`).

Corrections faites ensuite :
- `/memberships/` plantait (`NameError: products`) → corrigé dans `MembershipMVT.list`.
- `ResourceProductAdmin.get_queryset` filtrait encore la catégorie → retiré.
- `test_pos_product_proxy` mis à jour ; nouveau `test_membership_pages_publiques.py`.

Détails : `CHANGELOG/2026-09-29-managers-proxys-product.md`.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Un manager par proxy (Ticket, Membership, Resource, POS, Fut). |
| `Administration/admin/products.py` | Plus de filtre de catégorie dans les `get_queryset` des admins proxys. |
| `Administration/admin/prices.py` | `adhesions_obligatoires` via `MembershipProduct.objects`. |
| `Administration/admin_tenant.py` | Filtre « adhésion » de la liste des adhésions via `MembershipProduct.objects`. |
| `ApiBillet/serializers.py`, `ApiBillet/views.py` | Adhésions via `MembershipProduct.objects`. |
| `BaseBillet/views.py` | `MembershipMVT` via `MembershipProduct.objects` + correctif `NameError`. |

## Tests à réaliser

### Test 1 : pages publiques des adhésions
1. Ouvrir `https://lespass.tibillet.localhost/memberships/`.
2. Attendu : la page s'affiche (plus d'erreur 500). Seules les adhésions publiées
   apparaissent, avec leur prix minimum en euros.
3. Cliquer sur une adhésion (`/memberships/<uuid>/`) : le formulaire d'adhésion s'ouvre.
4. Ouvrir `/memberships/embed/` (version à intégrer dans un iframe) : même liste d'adhésions.
5. Essayer `/memberships/<uuid d'un billet>/` : réponse 404, pas de formulaire.

### Test 2 : listes de l'admin
Dans `/admin/`, ouvrir chaque liste et vérifier qu'elle ne contient que sa catégorie :

| Liste admin | Doit contenir uniquement |
|---|---|
| Produits billetterie (`/admin/BaseBillet/ticketproduct/`) | Billets et réservations gratuites |
| Produits adhésion (`/admin/BaseBillet/membershipproduct/`) | Adhésions |
| Produits ressources (`/admin/BaseBillet/resourceproduct/`) | Ressources (salle, machine…) |
| Produits de caisse (`/admin/BaseBillet/posproduct/`) | Produits avec une méthode de caisse |
| Produits fût (`/admin/BaseBillet/futproduct/`) | Fûts |

Pour chaque liste : ouvrir une fiche, la modifier, enregistrer → pas d'erreur 404.
Les compteurs « x résultats » doivent être les mêmes qu'avant le refactor.

### Test 3 : tarif avec adhésion obligatoire
1. Admin → un produit billetterie → un tarif → champ « Adhésions obligatoires ».
2. Attendu : la liste ne propose que des adhésions non archivées.
3. Choisir une adhésion, enregistrer → pas d'erreur.

### Test 4 : filtre de la liste des adhésions
1. Admin → Adhésions (liste des `Membership`) → filtre par produit.
2. Attendu : le filtre propose uniquement les produits adhésion non archivés.

### Test 5 : API v1 `here`
```bash
curl -s -H "Authorization: Api-Key <clé>" https://lespass.tibillet.localhost/api/here/ | python -m json.tool
```
Attendu : la clé des adhésions ne contient que des produits adhésion publiés, avec tarif.

### Test 6 : tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_membership_pages_publiques.py tests/pytest/test_pos_models.py tests/pytest/test_signaux_proxys_product.py tests/pytest/test_membership_*.py -q
```
Attendu : tout passe (35 tests au dernier lancement).

## Vérifications en base
Comparer un proxy avec `Product` : les deux nombres doivent être égaux.
```bash
docker exec -i lespass_django poetry run python manage.py shell <<'EOF'
from Customers.models import Client
from django_tenants.utils import tenant_context
from BaseBillet.models import Product, MembershipProduct, POSProduct
with tenant_context(Client.objects.get(schema_name="lespass")):
    print(MembershipProduct.objects.count(), Product.objects.filter(categorie_article=Product.ADHESION).count())
    print(POSProduct.objects.count(), Product.objects.filter(methode_caisse__isnull=False).count())
EOF
```

## Compatibilité
- Pas de migration : les proxys utilisent la même table que `Product`.
- **Changement de comportement :** `XxxProduct.objects.get(pk=...)` lève `DoesNotExist`
  pour un produit hors de sa catégorie. Avant, il le renvoyait. Pour lire n'importe
  quel produit, utiliser `Product.objects`.
- Les relations (`price.product`, etc.) utilisent le manager de base, qui ne filtre
  pas : elles ne changent pas.
- Chaque lancement de `test_membership_pages_publiques.py` laisse 2 produits
  de test en base, dépubliés et archivés. Sous pytest, django-stdimage empêche la
  suppression (`tests/PIEGES.md 10.1`).

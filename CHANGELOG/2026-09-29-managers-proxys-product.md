# Proxys de Product : managers filtrants, et corrections après le refactor / Product proxies: filtering managers, and post-refactor fixes

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :**

1. **Managers sur les proxys** (commits `ac07d76b` et `003baa24`).
   `TicketProduct`, `MembershipProduct`, `ResourceProduct`, `POSProduct` et
   `FutProduct` ont chacun un manager qui filtre déjà la bonne catégorie.
   Exemple : `MembershipProduct.objects.all()` ne renvoie que les adhésions.
   Les filtres en double ont été retirés des `get_queryset` de l'admin et de
   plusieurs `Product.objects.filter(categorie_article=Product.ADHESION)`.
   / Each Product proxy now has a manager that filters its category.
   Duplicate filters were removed from admin and views.

2. **Correctif : la page `/memberships/` plantait (erreur 500).**
   Dans `MembershipMVT.list`, la variable `products` avait été remplacée par
   `template_context['products']`, mais la boucle en dessous lisait toujours
   `products` : `NameError: name 'products' is not defined`. La variable est
   rétablie.
   / `/memberships/` crashed with a NameError after the refactor. Fixed.

3. **Correctif : filtre en double dans `ResourceProductAdmin`.**
   Son `get_queryset` filtrait encore `categorie_article=RESOURCE`, alors que
   `ResourceProductManager` le fait déjà. Retiré, comme pour les autres admins.
   / Leftover duplicate filter removed from ResourceProductAdmin.

4. **Tests.** `test_pos_product_proxy` vérifiait l'ancien comportement (« pas de
   manager, le filtre est dans l'admin ») et échouait. Il vérifie maintenant
   qu'un produit sans `methode_caisse` n'est pas visible via `POSProduct.objects`.
   Nouveau fichier `test_membership_pages_publiques.py` : aucun test n'appelait
   `/memberships/`, d'où le plantage passé inaperçu.
   / Outdated POS proxy test updated; new tests for public membership pages.

**Pourquoi / Why :**
Un proxy qui filtre lui-même évite de répéter le filtre de catégorie partout
(admin, vues, API), et d'en oublier un.
/ A self-filtering proxy avoids repeating (and forgetting) the category filter.

**Attention / Watch out :**
`POSProduct.objects.get(pk=...)` lève maintenant `DoesNotExist` pour un produit
sans `methode_caisse`. Même chose pour les autres proxys hors de leur catégorie.
Pour lire n'importe quel produit, utiliser `Product.objects`.
/ Proxies now raise DoesNotExist outside their category; use Product.objects for any product.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Managers `TicketProductManager`, `MembershipProductManager`, `ResourceProductManager`, `POSProductManager`, `FutProductManager` posés comme `objects` sur chaque proxy. |
| `Administration/admin/products.py` | `get_queryset` des admins Ticket, Membership, Resource, POS et Fut : plus de filtre de catégorie (le manager le fait). POS et Fut gardent leur `select_related`. |
| `Administration/admin/prices.py` | `adhesions_obligatoires` : queryset via `MembershipProduct.objects`. |
| `Administration/admin_tenant.py` | `MembershipPublishedFilter` : `MembershipProduct.objects.filter(archive=False)`. |
| `ApiBillet/serializers.py` | `PriceSerializer.adhesions_obligatoires` : queryset via `MembershipProduct.objects`. |
| `ApiBillet/views.py` | `HereViewSet` : adhésions via `MembershipProduct.objects`. |
| `BaseBillet/views.py` | `MembershipMVT` (`list`, `embed`, `retrieve`, `get_federated_membership_url`) via `MembershipProduct.objects`. Correctif du `NameError` dans `list`. |
| `tests/pytest/test_pos_models.py` | `test_pos_product_proxy` adapté au manager filtrant. |
| `tests/pytest/test_membership_pages_publiques.py` | Nouveau : `/memberships/`, `/memberships/embed/` et `/memberships/<uuid>/` répondent 200 et ne montrent que des adhésions. |

### Migration
- **Migration nécessaire / Migration required :** Non / No (proxys : même table).

### Tests
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_membership_pages_publiques.py tests/pytest/test_pos_models.py tests/pytest/test_signaux_proxys_product.py tests/pytest/test_membership_*.py -q
```

# Relations vers Product : FK vers un proxy, limit_choices_to, fin du filtre par Referer / Relations to Product: proxy FK, limit_choices_to, no more Referer filter

**Date :** 2026-09-29
**Migration :** Oui / Yes (sans SQL / no SQL)

## Résumé / Summary

**Quoi / What :**

1. **`booking.Resource.product` pointe vers le proxy `ResourceProduct`**, avec
   `limit_choices_to={'categorie_article': RESOURCE}`. Même table, même colonne.
   / Resource.product now targets the ResourceProduct proxy.
2. **`Event.products` et `Price.adhesions_obligatoires` restent vers `Product`**,
   mais reçoivent un `limit_choices_to` (BILLET/FREERES, et ADHESION).
   Pourquoi pas un proxy : pour un M2M, la colonne de la table de liaison prend
   le nom du modèle cible. Vérifié avec l'éditeur de schéma :
   `ALTER TABLE "BaseBillet_event_products" RENAME COLUMN "product_id" TO "ticketproduct_id"`
   (idem `membershipproduct_id`), dans chaque schéma tenant. Refusé.
   / The two M2M stay on Product (a proxy target renames the join column) and get a limit_choices_to.
3. **`ProductAdmin.get_search_results` ne filtre plus la catégorie selon le Referer.**
   L'autocomplete de Django applique déjà le `limit_choices_to` du champ
   (`AutocompleteJsonView.get_queryset` → `complex_filter`), et l'autocomplete
   d'un FK vers un proxy passe par l'admin du proxy. Il reste : exclusion des
   produits archivés (pour tous les autocompletes), et le filtre VENTE pour `Stock`.
   / Category filtering by Referer removed; Django applies limit_choices_to itself.

**Pourquoi / Why :**
- Le filtre par Referer était fragile (test de sous-chaîne dans une URL).
- **Bug corrigé au passage :** l'autocomplete « Adhésions obligatoires » dans
  l'inline tarif de la **fiche produit** (`products.py`, `autocomplete_fields =
  ["adhesions_obligatoires"]`) avait un Referer `.../ticketproduct/<id>/change/`.
  Aucune branche ne correspondait : il proposait **tous** les produits. Il ne
  propose plus que des adhésions.
- `limit_choices_to` est aussi contrôlé par `full_clean()`, alors que le manager
  d'un proxy ne l'est pas (`ForeignKey.validate()` passe par `_base_manager`).
  / limit_choices_to is also enforced by full_clean(), unlike a proxy manager.

**Pas de `limit_choices_to` sur `inventaire.Stock.product` / No limit on Stock :**
les fûts (catégorie `U`, sans méthode de caisse) ont aussi un stock (4 en base
dev). Un filtre VENTE les rendrait invalides. Le filtre VENTE reste dans l'autocomplete.

**Non traité / Not done :** `PromotionalCode.product` → `TicketProduct`. Reste dans
`CHANGELOG/a traiter/fk-product-vers-proxys.md`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | `Resource.product` → `ResourceProduct` + `limit_choices_to` RESOURCE. |
| `BaseBillet/models.py` | `limit_choices_to` sur `Event.products` (BILLET, FREERES) et `Price.adhesions_obligatoires` (ADHESION). |
| `Administration/admin/products.py` | `get_search_results` : plus de filtre de catégorie par Referer ; exclusion des archivés pour tout autocomplete ; filtre VENTE gardé pour Stock. |
| `booking/migrations/0002_alter_resource_product.py` | Nouvelle migration (AlterField). |
| `BaseBillet/migrations/0230_alter_event_products_and_more.py` | Nouvelle migration (2 AlterField). |

### Migration
- **Migration nécessaire / Migration required :** Oui / Yes — `migrate_schemas`.
- `sqlmigrate booking 0002` et `sqlmigrate BaseBillet 0230` : **`(no-op)`**, aucun SQL.
  / No SQL is executed; only the migration state changes.

### Vérifications faites / Checks done
- Données de tous les tenants : aucun lien existant ne viole les nouveaux `limit_choices_to`.
- Autocomplete admin réel (lespass) : event → B, adhésions obligatoires (page tarif
  et fiche produit) → A, resource → C, stock → VT ; aucun produit archivé.
- `manage.py check` OK, `makemigrations --check` : rien à générer.
- pytest : `test_admin_*`, `test_event_*`, `test_membership_pages_publiques`,
  `test_pos_models`, `test_signaux_proxys_product` (170) ; `booking/tests/` et
  tests panier/commande/booking (142). Tout passe.

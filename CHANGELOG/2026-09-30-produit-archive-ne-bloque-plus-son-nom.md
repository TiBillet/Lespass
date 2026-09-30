# Un produit archivé ne bloque plus son nom / An archived product no longer reserves its name

**Date :** 2026-09-30
**Migration :** Oui — `BaseBillet/migrations/0232_product_nom_unique_si_non_archive.py` (`migrate_schemas`)

**FR :** Le couple (catégorie, nom) d'un produit était unique pour tous les produits, archivés
compris : impossible de créer un produit portant le nom d'un produit archivé. L'unicité ne
concerne maintenant que les produits NON archivés (contrainte partielle). Plusieurs produits
archivés peuvent porter le même nom. L'action admin « Désarchiver » refuse, avec un message,
de désarchiver un produit si un produit actif porte déjà son nom. L'import d'adhésions
cherche le produit par son nom parmi les produits non archivés seulement.

**EN :** Product (category, name) uniqueness now only applies to NON-archived products
(partial constraint). The admin "Unarchive" action refuses, with a message, when an active
product already has the same name. The membership import looks products up by name among
non-archived products only.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Product.Meta` : `unique_together` remplacé par une `UniqueConstraint` avec `condition=Q(archive=False)` |
| `BaseBillet/migrations/0232_product_nom_unique_si_non_archive.py` | Retire l'ancienne contrainte, ajoute la nouvelle |
| `Administration/admin/products.py` | `desarchive` refuse si le nom est pris ; helper `un_autre_produit_non_archive_porte_ce_nom` |
| `Administration/importers/membership_importers.py` | Produit et tarif cherchés parmi les produits non archivés |
| `tests/pytest/test_product_nom_unique_si_non_archive.py` | Nouveaux tests / New tests |

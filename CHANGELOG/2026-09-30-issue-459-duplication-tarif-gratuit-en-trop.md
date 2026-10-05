# Issue #459 : dupliquer une réservation gratuite ne crée plus de tarif en trop / Duplicating a free booking no longer adds an extra price

**Date :** 2026-09-30
**Migration :** Non

**FR :** Dupliquer un produit « réservation gratuite » donnait une copie avec un tarif gratuit
en trop. L'enregistrement du nouveau produit crée automatiquement un tarif gratuit (signal
`post_save_Product`), puis les tarifs du produit source étaient copiés par-dessus.
Le tarif créé automatiquement est maintenant effacé avant la copie. Les produits billet
payants n'étaient pas touchés par le bug.

**EN :** Duplicating a "free booking" product gave a copy with one extra free price: saving
the new product auto-creates a free price (`post_save_Product` signal), then the source
prices were copied on top. The auto-created price is now removed before the copy.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `_duplicate_product` : efface le tarif gratuit automatique avant de copier les tarifs du source |
| `tests/pytest/test_duplication_produit_issue_459.py` | Nouveaux tests / New tests |

# FK vers Product : reste à traiter (PromotionalCode)

**Relevé du 2026-09-29.** L'inventaire des 13 relations vers `Product` et la
décision proxy / `limit_choices_to` ont été faits le même jour :
voir `CHANGELOG/2026-09-29-fk-product-proxy-et-limit-choices-to.md`
(`Resource.product` → `ResourceProduct` ; `limit_choices_to` sur `Event.products` et
`Price.adhesions_obligatoires` ; fin du filtre par Referer dans l'autocomplete).

Il reste un seul point, volontairement non traité.

## `BaseBillet.PromotionalCode.product` → `TicketProduct`

**Aujourd'hui :** FK vers `Product` (CASCADE). Seul `PromotionalCodeAdmin.formfield_for_foreignkey`
(`Administration/admin/prices.py`) limite le choix à `archive=False, categorie_article=BILLET`.
Rien ne limite la catégorie ailleurs (API, shell, `full_clean()`).

**Données :** aucun code promo lié à autre chose qu'un BILLET (vérifié sur tous les tenants le 2026-09-29).

**Correctif proposé :**
1. `product` → `"BaseBillet.TicketProduct"` + `limit_choices_to={"categorie_article": Product.BILLET}`.
   Le proxy inclut FREERES (résa gratuite) : le `limit_choices_to` reste nécessaire pour l'exclure.
   FK simple : `sqlmigrate` doit donner `(no-op)` (constaté pour `booking.Resource.product`).
2. Dans `PromotionalCodeAdmin.formfield_for_foreignkey`, ne garder que `archive=False`
   (la catégorie vient du `limit_choices_to`).

**Version minimale :** garder `Product` et n'ajouter que le `limit_choices_to` BILLET.
Suffit pour que `full_clean()` refuse un autre type de produit.

**Vérification :** `sqlmigrate` `(no-op)` ; admin code promo → seuls les billets non archivés ;
`pytest tests/pytest/test_admin_*.py -q`.

## Relations laissées sur `Product` exprès (pour mémoire)
- `PointDeVente.products` : produits de caisse **et** adhésions, aucun proxy ne correspond.
- `inventaire.Stock.product` : pas de `limit_choices_to` VENTE, les fûts ont aussi un stock.
- `Price.product`, `ProductSold`, `History`, `FormbricksForms`, `ProductFormField` : toutes catégories.
- `ArticleCommandeSauvegarde.product` → `POSProduct` possible, gain faible (pas de formulaire).

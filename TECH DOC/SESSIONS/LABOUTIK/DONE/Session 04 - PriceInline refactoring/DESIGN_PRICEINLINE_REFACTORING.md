# Design : PriceInline refactoring par proxy product

**Date :** 2026-04-04
**Branche :** integration_laboutik
**Approche retenue :** B — StackedInline collapsible par proxy

## Probleme

Un seul `PriceInline` (TabularInline) est partage entre 4 admins (ProductAdmin, TicketProductAdmin, MembershipProductAdmin, POSProductAdmin). Chacun a des besoins differents sur les champs prix. On empile des conditions dans `get_fields()` et le formulaire. C'est fragile et pas FALC.

De plus, l'UX actuelle impose un flow en 2 pages : le TabularInline ne montre qu'un resume (name, prix, free_price, subscription_type, publish), et l'edition complete passe par un `show_change_link` vers PriceAdmin standalone.

## Solution

Remplacer le PriceInline unique par 4 `StackedInline` avec `collapsible = True` (pattern natif Unfold, cf. demo Formula/Standing). Chaque inline a ses fields en dur, son propre formulaire si necessaire, et zero condition.

**Benefice UX :** edition complete du tarif sans quitter la page produit. Titre replie = resume du tarif. Clic = formulaire complet deplie.

## Architecture

### Classes inline

```
BasePriceInline(StackedInline)
    model = Price
    fk_name = "product"
    collapsible = True
    extra = 0
    show_change_link = True
    form = BasePriceInlineForm
    fields = ("name", "prix", "free_price", "publish", "order")

TicketPriceInline(BasePriceInline)
    fields = ("name", "prix", "free_price", "stock", "max_per_user", "publish", "order")

MembershipPriceInline(BasePriceInline)
    form = MembershipPriceInlineForm
    autocomplete_fields = ["adhesions_obligatoires"]
    fields = ("name", "prix", "free_price",
              "subscription_type", "recurring_payment", "iteration", "commitment",
              "adhesions_obligatoires",
              "publish", "order")

POSPriceInline(BasePriceInline)
    fields = ("name", "prix", "free_price", "contenance", "publish", "order")
```

### Formulaires

**BasePriceInlineForm(ModelForm)** :
- `clean_prix()` : rejette les prix entre 0EUR et 1EUR (existant)

**MembershipPriceInlineForm(BasePriceInlineForm)** :
- `clean_subscription_type()` : adhesion doit avoir une duree (existant dans PriceInlineChangeForm)
- `clean_recurring_payment()` : si recurrent, subscription_type obligatoire (recupere de PriceChangeForm dans prices.py)

### Branchement dans les *Admin

```python
ProductAdmin.inlines = [BasePriceInline, ProductFormFieldInline]
TicketProductAdmin.inlines = [TicketPriceInline]
MembershipProductAdmin.inlines = [MembershipPriceInline, ProductFormFieldInline]
POSProductAdmin.inlines = [POSPriceInline]  # + StockInline en mode add via get_inlines
```

## Ce qui ne change pas

- **PriceAdmin standalone** (prices.py) : inchange, garde son get_fieldsets conditionnel
- **PriceChangeForm** (prices.py) : inchange
- **Modele Price** : zero migration
- **ProductAdmin actions** (duplicate, archive) : inchangees
- **Permissions** (TenantAdminPermissionWithRequest) : heritees de la base
- **ProductFormFieldInline** : inchange

## Suppressions

- `PriceInline` (l'ancien unique TabularInline) : supprime
- `PriceInlineChangeForm` (l'ancien form unique) : supprime, remplace par BasePriceInlineForm
- `get_fields()` conditionnel dans PriceInline : supprime

## Fichiers impactes

| Fichier | Action |
|---------|--------|
| `Administration/admin/products.py` | Supprimer PriceInline + PriceInlineChangeForm. Creer BasePriceInline, TicketPriceInline, MembershipPriceInline, POSPriceInline + formulaires. Brancher dans les 4 *Admin. |
| `Administration/admin/prices.py` | Inchange |
| `BaseBillet/models.py` | Inchange (zero migration) |

## Couverture de tests existante

### Tests qui touchent au refactoring
- `test_admin_proxy_products.py` (6 tests) : verifie l'acces aux pages proxy add/list. Ne teste PAS les change pages ni les inlines.
- `test_product_duplication.py` (1 test) : verifie que les Price sont copiees. Indirect.
- `test_membership_products_create.py` (6 tests) : cree des Price en DB directe, pas via l'admin inline.

### Trou critique
Aucun test ne verifie le rendu ni la soumission du PriceInline en admin. Pas de test POST avec le formset `prices-TOTAL_FORMS`. Le refactoring ne cassera aucun test existant, mais il n'y a pas de filet de securite.

### Tests a ecrire
1. **Smoke test change page** : GET sur chaque proxy admin change page, verifier 200 + presence du formset Price
2. **Test soumission inline** : POST un tarif via l'inline sur MembershipProductAdmin, verifier la creation en DB
3. **Test validation clean_prix** : soumettre un prix entre 0 et 1 via inline, verifier l'erreur
4. **Test validation subscription_type** : soumettre une adhesion sans duree, verifier l'erreur
5. **Test POSPriceInline** : verifier que contenance est present dans le formulaire

## Contraintes

- Retrocompatible : pas de migration
- Le PriceAdmin standalone garde son get_fieldsets conditionnel
- 4-5 tarifs max par produit → pas besoin de per_page/pagination
- Tester que les 4 pages admin fonctionnent apres le changement

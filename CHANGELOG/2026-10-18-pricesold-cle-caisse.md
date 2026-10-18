# Caisse : la photo du prix cherchée avec son prix / Register: price snapshot looked up with its price

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** la caisse cherche la photo du prix (`PriceSold`) avec la clé
(produit vendu, tarif, **prix**), et prend la première qui correspond. Trois endroits de
`laboutik/views.py` : vente simple, paiement NFC en cascade, billets en caisse.
/ The register looks up the price snapshot (`PriceSold`) by (productsold, price, **prix**)
and takes the first match, in the three places of `laboutik/views.py`.

**Pourquoi / Why :** la billetterie en ligne crée une photo par montant (prix libre, code
promo, prix modifié). La caisse cherchait sans le prix : dès qu'un tarif avait plusieurs
photos, le paiement plantait en 500 (`PriceSold.MultipleObjectsReturned`, Sentry
BILLETTERIE-COOP-V6, La Cabine, don à prix libre payé en NFC).
/ Online sales create one snapshot per amount; the register looked up without the price
and crashed as soon as a price had several snapshots.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_creer_lignes_articles`, `_creer_lignes_articles_cascade`, `_creer_billets_depuis_panier` : recherche `filter(productsold, price, prix).first()`, sinon `create` |
| `tests/pytest/test_pricesold_cle_caisse.py` | Nouveau : NFC, CB, et deux ventes qui partagent la même photo |
| `tests/pytest/test_billetterie_pos.py` | Nouveau test : billet dont le tarif a deux photos |

---

## Comment tester (a la main) / Manual test

### Test 1 — le cas Sentry
1. Dans l'admin, un produit vendu en caisse avec un tarif **prix libre** (minimum 1 €).
2. Créer deux `PriceSold` pour ce tarif à 5 € et 10 € (shell ci-dessous), comme le ferait
   la billetterie en ligne.
3. En caisse, vendre ce produit à 5 € en NFC, puis en CB.
4. Attendu : le paiement passe. La ligne vaut 5 €, sa photo de prix vaut 1 €.

```python
# docker exec -it lespass_django poetry run python manage.py tenant_command shell --schema=lespass
from decimal import Decimal
from BaseBillet.models import Price, ProductSold, PriceSold
tarif = Price.objects.get(uuid="<uuid du tarif>")
produit_vendu, _created = ProductSold.objects.get_or_create(product=tarif.product, event=None)
for montant in ["5.00", "10.00"]:
    PriceSold.objects.create(productsold=produit_vendu, price=tarif, prix=Decimal(montant))
```

### Test 2 — vente ordinaire inchangée
1. Vendre une bière deux fois en caisse.
2. Attendu : une seule photo `PriceSold` pour ce tarif, au prix catalogue.

### Verifs DB
- `PriceSold.objects.filter(price=tarif).values_list("prix", flat=True)` : les photos en
  ligne restent intactes, la caisse ajoute au plus une photo au prix catalogue.
- Automatique : `make test ARGS="tests/pytest/test_pricesold_cle_caisse.py tests/pytest/test_billetterie_pos.py"`.

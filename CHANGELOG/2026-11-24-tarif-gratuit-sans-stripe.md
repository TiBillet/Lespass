# Produit gratuit sans Stripe / Free product without Stripe

**Date :** 2026-11-24
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'admin n'exige plus un compte Stripe actif pour un produit dont tous les
tarifs sont gratuits. Stripe reste exigé dès qu'un tarif coûte plus de 0 € ou est à prix libre.
/ The admin no longer requires an active Stripe account for a product whose prices are all
free. Stripe is still required as soon as a price is above 0 € or is a free price.

**Pourquoi / Why :** un lieu sans Stripe ne pouvait pas créer d'adhésion. L'admin demande un
tarif, propose un tarif gratuit, puis le refuse faute de Stripe (issue #501). Même blocage pour
un billet à 0 €.
/ A venue without Stripe could not create a membership: the admin asks for a price, suggests a
free one, then refuses it for lack of Stripe (issue #501). Same for a 0 € ticket.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `ProductAdminCustomForm.clean()` : contrôle Stripe seulement si un tarif envoyé est payant (prix > 0 ou prix libre, tarifs supprimés ignorés) |
| `tests/pytest/test_produit_gratuit_sans_stripe.py` | 3 tests : 0 € accepté, 10 € refusé, prix libre refusé (sans Stripe) |

---

## Comment tester (a la main) / Manual test

Prérequis : un lieu dont le compte Stripe n'est pas actif
(`Configuration.stripe_payouts_enabled = False`).

### Test 1 — adhésion gratuite
1. Admin > Adhésions > Ajouter.
2. Nom « Adhésion libre », un tarif « Gratuit » à `0`, durée « 365 jours », publié.
3. Enregistrer : le produit est créé, sans message Stripe.

### Test 2 — adhésion payante
1. Même chose avec un tarif à `10`.
2. Enregistrer : refus avec « Votre compte Stripe n'est pas activé… ».

### Test 3 — prix libre
1. Tarif à `0`, case « prix libre » cochée.
2. Enregistrer : refus avec le même message Stripe.

### Test 4 — billet à 0 €
1. Admin > Billetterie > Ajouter, type « Billet », un tarif à `0`.
2. Enregistrer : le produit est créé.

### Verifs automatiques
- `make test ARGS="tests/pytest/test_produit_gratuit_sans_stripe.py"`
- Les produits de caisse ne passaient déjà pas par ce contrôle (`POSProductForm.clean()` le
  saute) : un produit de caisse se crée sans Stripe sur `main`.

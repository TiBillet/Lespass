# Total affiché pendant l'attente de carte cashless / Total shown while waiting for the cashless card

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** la popup « Approchez la carte » d'un paiement CASHLESS affiche le total à payer (ou le montant manquant, ou le montant de consigne), avec son unité (€ ou monnaie de points).
/ The CASHLESS "Tap the card" popup shows the amount to pay, with its unit.

**Pourquoi / Why :** le client ne voyait pas le montant au moment de poser sa carte. Les popups espèces / CB l'affichaient déjà.
/ The customer could not see the amount when tapping their card; cash/CC popups already showed it.

Le total voyage dans l'URL de la tuile, comme pour `confirmer()`. Il sert seulement à l'affichage : `payer()` recalcule toujours le montant depuis le panier.
/ Display only: `payer()` always recomputes from the cart.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `lire_nfc()` lit `total` (virgule acceptée) et `devise`, les passe au template |
| `laboutik/templates/laboutik/partial/hx_read_nfc.html` | Bloc `.payment-total` dans le slot `entete` (absent si pas de total) |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | Tuile CASHLESS : `?total=…&devise=…` |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Tuile CASHLESS consigne : `?total=…&devise=…` |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | Tuile CASHLESS 2ᵉ carte : `?total={{ payment.missing }}&devise=…` |
| `tests/pytest/test_popups_paiement_v2.py` | 4 tests (rendu avec/sans total, vue avec virgule + devise, vue sans total) |

---

## Comment tester (a la main) / Manual test

### Test 1 — vente normale
1. Caisse : ajouter des articles pour 12,50 €, VALIDER.
2. Taper CASHLESS.
3. La popup « Approchez la carte » affiche « TOTAL 12,50 € ».
4. Poser la carte : le paiement se fait comme avant.

### Test 2 — panier en points
1. Panier d'articles vendus en points, VALIDER, CASHLESS.
2. Le total s'affiche avec le nom de la monnaie de points (ex : « 300,00 Points fidélité »).

### Test 3 — fonds insuffisants
1. Payer avec une carte dont le solde ne suffit pas.
2. Dans « Compléter avec », taper CASHLESS.
3. La popup affiche le montant MANQUANT, pas le total initial.

### Test 4 — consigne
1. Panier composé uniquement de retours de consigne, VALIDER, CASHLESS.
2. Le montant affiché est positif.

### Verifs automatiques
- `poetry run pytest tests/pytest/test_popups_paiement_v2.py`
- `poetry run pytest tests/e2e/test_caisse_vente_en_points.py`

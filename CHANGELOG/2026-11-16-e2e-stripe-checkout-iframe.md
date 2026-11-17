# E2E : Stripe Checkout lu dans son iframe / E2E: Stripe Checkout read inside its iframe

**Date :** 2026-11-16
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- `tests/e2e/conftest.py` : nouvelle fonction `cadre_du_formulaire_de_paiement_stripe(page)`, qui trouve l'iframe du formulaire de paiement grâce à son bouton « Pay ».
- `fill_stripe_card` est réécrite. Elle remplit l'e-mail s'il est vide, ouvre l'élément « Carte » de l'accordéon quand SEPA est actif, puis remplit la carte. Elle attend aussi le nom du porteur (5 s), obligatoire sur les checkouts de Fedow. Tout se passe dans l'iframe.
- `soumettre_paiement_stripe` clique sur `[data-testid="payment-form-submit-button"]` dans l'iframe. Une erreur de clic pendant le traitement est ignorée : c'est la sortie du checkout qui décide.
- `test_parcours_fedow_reel.py` et `test_carte_liee_par_qrcode_fed_en_caisse.py` : le bloc qui garantissait `input#billingName` est retiré. `fill_stripe_card` s'en charge.
- `tests/PIEGES.md` : nouveau piège 12.19.

/ The Stripe Checkout payment form now lives in a js.stripe.com iframe; the E2E helpers find
that iframe by its "Pay" button and fill/submit inside it.

**Pourquoi / Why :** Stripe a déplacé tout le formulaire de Checkout dans un iframe. Les sélecteurs de la page principale (`input#cardNumber`, `input#billingName`, `hosted-payment-submit-button`) n'existent plus. 18 E2E échouaient sur « Aucun champ de carte bancaire trouve sur la page Stripe ». Ce n'est pas lié à la mise à jour des dépendances : le SDK `stripe` n'est passé que de 12.5.1 à 12.5.2.
/ Stripe moved the whole Checkout form into an iframe; main-page selectors are gone.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/conftest.py` | `cadre_du_formulaire_de_paiement_stripe`, `fill_stripe_card`, `soumettre_paiement_stripe` |
| `tests/e2e/test_parcours_fedow_reel.py` | bloc `billingName` retiré |
| `tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py` | bloc `billingName` retiré |
| `tests/PIEGES.md` | piège 12.19 |

---

## Comment tester / How to test
- `make e2e ARGS="tests/e2e/test_stripe_smoke.py"` (`stripe listen` doit tourner pour Lespass et pour Fedow).
- Voir la page : `make e2e-visible ARGS="tests/e2e/test_stripe_smoke.py"`.

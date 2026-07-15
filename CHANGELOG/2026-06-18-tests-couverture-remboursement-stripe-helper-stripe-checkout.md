# Tests : couverture du remboursement Stripe + helper Stripe Checkout multi-moyens / Tests: Stripe refund coverage + multi-method Checkout helper

**Date :** 2026-06-18
**Migration :** Non / No

**Quoi / What :**
1. **Nouveau `tests/pytest/test_stripe_refund.py`** (3 tests) — couvre le remboursement Stripe, jusqu'ici non testé : (a) `cancel_and_refund_resa()` — `stripe.Refund.create` (montant + `payment_intent`), paiement `REFUNDED`, avoir négatif, réservation + billets annulés ; (b) réservation gratuite → aucun refund ; (c) **remboursement partiel** `cancel_and_refund_ticket()` — 1 billet sur 4 (montant d'**un** billet, pas du panier ; avoir `qty=-1` ; paiement reste `VALID`). Le test (a) documente que `cancel_and_refund_resa` rembourse `amount_total` (le **paiement entier**) — à revoir pour les paniers.
2. **`tests/e2e/conftest.py` — `fill_stripe_card`** : déplie l'accordéon « Carte » de Stripe Checkout (`data-testid="card-accordion-item-button"`, `dispatch_event`) quand plusieurs moyens sont actifs (Carte + SEPA). Attend que le formulaire soit monté (accordéon **ou** champ carte). Reste compatible « carte seule » (no-op). Débloque `test_membership_manual_validation_stripe` après activation de SEPA sur le compte de test.

**Pourquoi / Why :** le chemin de remboursement Stripe n'avait aucune couverture (les tests d'avoir/annulation utilisent des objets gratuits) ; et l'activation de SEPA a changé la page Checkout (sélecteur de moyen de paiement), cassant le helper partagé.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_stripe_refund.py` | Nouveau — 2 tests (refund payé + gratuit sans refund) |
| `tests/e2e/conftest.py` | `fill_stripe_card` : sélection « Carte » sur Checkout multi-moyens |

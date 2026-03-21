# Session 09 — Convertir les tests Playwright TS Stripe

## Decoupage

Cette session a ete decoupee en 3 sous-sessions. La strategie originale (tout en E2E avec
le vrai checkout.stripe.com) a ete remplacee par **mock Stripe cote serveur** + **2 smoke
tests E2E** :

- La majorite des tests verifient la logique Django (formulaire → Paiement_stripe → triggers),
  pas le checkout Stripe lui-meme.
- Mocker Stripe = rapide (~2s/test au lieu de 45s), stable, meme couverture metier.
- 2 smoke tests E2E avec le vrai Stripe garantissent que l'integration bout en bout fonctionne.

| Sous-session | Perimetre | Tests | Statut |
|---|---|---|---|
| [09a](09a_STRIPE_MOCK_ADHESIONS_SIMPLES.md) | Infra mock + 5 adhesions simples | 5 pytest | A FAIRE |
| [09b](09b_STRIPE_MOCK_ADHESIONS_COMPLEXES.md) | Adhesions complexes + crowds | ~10 pytest | A FAIRE |
| [09c](09c_STRIPE_RESERVATIONS_SMOKE.md) | Reservations mock + 2 smoke E2E | 4 pytest + 2 E2E | A FAIRE |

09b et 09c sont independants (mais dependent de 09a pour la fixture mock_stripe).

## Points a mocker

| Appel Stripe | Fichier source | Mock retourne |
|---|---|---|
| `stripe.checkout.Session.create()` | `PaiementStripe/views.py:182` | session mock avec id, url |
| `stripe.checkout.Session.retrieve()` | `BaseBillet/models.py:2771` | session mock avec payment_status="paid" |
| `stripe.PaymentIntent.retrieve()` | `BaseBillet/models.py` | mock avec payment_method_types=["card"] |

## Sources TS couvertes

12 fichiers TS, 25 tests :
- PW 11, 12, 13, 14, 15, 17, 27, 42, 43 (adhesions)
- PW 44 (crowds)
- PW 09, 10 (reservations)

# Session 09a — Mock Stripe : infra + 5 adhesions simples

## Statut : FAIT (2026-03-21)

## Depend de : 08c (31 E2E, 178 pytest)

## Objectif

Creer l'infrastructure mock Stripe (fixture `mock_stripe`) et convertir 5 adhesions simples.

## Strategie

Les tests TS faisaient un aller-retour reel vers checkout.stripe.com (~45s/test).
On mocke Stripe cote serveur : `@patch("stripe.checkout.Session.create")` etc.
Les tests verifient la logique Django (formulaire → Paiement_stripe → triggers) sans toucher le reseau.

## Perimetre

| Fichier pytest | Tests | Source TS | Ce qu'il verifie |
|---|---|---|---|
| `test_stripe_membership_simple.py` | 5 | PW 11,12,13,14+43,15 | Adhesions payantes avec mock Stripe |

**Total : 5 tests + fixture mock_stripe**

### Details des 5 tests

1. `test_anonymous_membership_paid` (PW 11) — adhesion anonyme → Stripe → Membership creee
2. `test_anonymous_membership_dynamic_form` (PW 12) — idem + champs dynamiques form_fields
3. `test_ssa_membership_tokens` (PW 13) — adhesion SSA → tokens Fedow credites
4. `test_membership_manual_validation_stripe` (PW 14+43) — validation manuelle → lien paiement → Stripe
5. `test_membership_free_price` (PW 15) — prix libre → montant custom → Stripe

## Infrastructure a creer

### Fixture `mock_stripe` dans `tests/pytest/conftest.py`

Patche 3 appels :
- `stripe.checkout.Session.create()` → retourne mock session
- `stripe.checkout.Session.retrieve()` → retourne mock session avec `payment_status="paid"`
- `stripe.PaymentIntent.retrieve()` → retourne mock avec `payment_method_types=["card"]`

### Points a mocker (code source)

- `PaiementStripe/views.py:182` — `CreationPaiementStripe._checkout_session()`
- `BaseBillet/models.py:2771` — `Paiement_stripe.update_checkout_status()`

## Ce qui a ete fait

### Fixture `mock_stripe` dans `tests/pytest/conftest.py`

Patche 5 appels Stripe :
- `stripe.checkout.Session.create()` → mock session (id, url, payment_intent)
- `stripe.checkout.Session.retrieve()` → mock session (payment_status="paid")
- `stripe.PaymentIntent.retrieve()` → mock (payment_method_types=["card"])
- `stripe.Subscription.retrieve()` → mock (id="sub_test_mock")
- `stripe.Subscription.modify()` → mock

Retourne un `SimpleNamespace` avec les mocks pour inspection (ex: `mock_stripe.mock_create.called`).

### 5 tests dans `test_stripe_membership_simple.py`

Tous passent en ~7.5s (vs ~4min si vrai Stripe).

### Helpers reutilisables

- `_create_membership_product()` — cree produit adhesion via API v2
- `_submit_membership_form()` — POST le formulaire comme le navigateur
- `_simulate_stripe_return()` — appelle `update_checkout_status()` avec mock retrieve

### Pieges resolus

1. **`newsletter` boolean** : le serializer `MembershipValidator` attend un boolean Python, pas une chaine vide. Envoyer `"false"` (pas `""`).

2. **Header `Referer` manquant** : en cas d'erreur de validation, la vue fait `HttpResponseClientRedirect(request.headers['Referer'])`. Sans ce header, `KeyError`. Ajouter `HTTP_REFERER=...` au POST du test client Django.

3. **`FakeTenant` piege 9.1** : `MembershipValidator.get_checkout_stripe()` accede a `connection.tenant.uuid` pour les metadata Stripe. `schema_context` met un `FakeTenant` → `AttributeError`. Utiliser `tenant_context(tenant)` pour le test manual_validation.

### Resultats

- **183 pytest** (178 + 5 mock Stripe)
- **31 E2E** inchanges
- **5 passed, 0 failed** en ~7.5s

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_simple.py -v -s --tb=long
# 5 passed

docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 183 tests collected
```

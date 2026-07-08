# CHANTIER-04 — Extension Fedow (crédit TPE place Lespass) — Plan

**Repo : `/home/jonas/TiBillet/dev/Fedow` (branche `main`).** Seul chantier côté serveur Fedow.

**Goal :** permettre à une place **Lespass** (sans cashless RSA) de créditer une carte via le TPE
Stripe, en réutilisant la route webhook existante, sans signature (miroir « EXTENSION S6 ») ; et
**durcir l'idempotence** anti-rejeu dont dépend cette décision de sécurité.

**Cadre :** SPEC §8bis. Additif, LaBoutik (place avec `cashless_rsa_pub_key`) strictement inchangé.

## Global Constraints
- Subagents SANS git. Repo Fedow = service distinct ; le mainteneur committera/déploiera.
- Tests Fedow : investiguer l'env (`docker ps | grep fedow`, conteneur `fedow_django`). Lancer via
  le même outil que les tests existants (`fedow_core/test_stripe_refill_regression.py`). Si l'env n'est
  pas lançable, faire au minimum `manage.py check` et le signaler.
- Ne PAS régresser le flux cashless LaBoutik.

## Task 04A — Extension de la vérif de signature (miroir S6)

**Fichier :** `fedow_core/views.py`, `StripeAPI.validate_stripe_reader_wise_pose_and_make_transaction` (~l.1095-1110).

Aujourd'hui :
```python
place = Place.objects.get(uuid=data['fedow_place_uuid'])
signature = stripe_payment.metadata['signature']
if not verify_signature(place.cashless_public_key(), data_to_b64(data), signature):
    raise Exception(...)
```
À remplacer par (⚠️ lire `signature` DANS le `else`, sinon `KeyError` pour un PI Lespass sans signature) :
```python
place = Place.objects.get(uuid=data['fedow_place_uuid'])
# Place Lespass de confiance (mono-serveur, clé Stripe Root exclusive) : pas de
# signature de place — le PaymentIntent sur le compte Root suffit (miroir EXTENSION S6).
# / Trusted Lespass place: no place signature (mirror of the S6 extension).
if place.lespass_domain and not place.cashless_rsa_pub_key:
    pass
else:
    # Place avec cashless RSA (LaBoutik V1) : signature exigée. / LaBoutik: signature required.
    signature = stripe_payment.metadata['signature']
    if not verify_signature(place.cashless_public_key(), data_to_b64(data), signature):
        raise Exception(
            f"validate_stripe_reader_wise_pose_and_make_transaction : Signature verification failed {metadata}")
```
Le reste de la fonction (crédit, CheckoutStripe, transaction REFILL) inchangé.

## Task 04B — Durcir l'idempotence anti-rejeu

**Fichiers :** `fedow_core/models.py` (`CheckoutStripe.checkout_session_id_stripe`, l.38), migration Fedow, `fedow_core/views.py` (webhook, ~l.1395).

- Ajouter `unique=True` sur `checkout_session_id_stripe` (Postgres autorise plusieurs `NULL`, donc les
  checkouts sans id ne collisionnent pas ; seuls les PI renseignés deviennent uniques). **Vérifier
  d'abord l'absence de doublons existants** (`values(...).annotate(Count).filter(count>1)`) ; s'il y en
  a, le signaler et ne pas forcer.
- Migration `makemigrations fedow_core`.
- Dans le webhook (`WebhookStripe`, event `terminal.reader.action_succeeded`), envelopper l'appel à
  `validate_stripe_reader_wise_pose_and_make_transaction` pour capter `IntegrityError` (double livraison
  concurrente du même PI) → renvoyer `208 ALREADY_REPORTED` comme le check `exists()`. Garder le `exists()`
  en pré-filtre rapide ; l'unicité + `IntegrityError` ferment la fenêtre TOCTOU.

## Task 04C — Tests

`fedow_core/` (idiome des tests existants, ex `test_stripe_refill_regression.py`) :
- **Signature Lespass** : une place `lespass_domain` sans `cashless_rsa_pub_key` → `validate_stripe_reader_wise_pose_and_make_transaction` crédite SANS signature (mock `stripe.PaymentIntent.retrieve`).
- **Signature cashless** : une place avec `cashless_rsa_pub_key` → signature toujours exigée (non-régression).
- **Idempotence** : deux passages du même `payment_intent_stripe_id` → une seule transaction/crédit (le 2ᵉ = 208 ou IntegrityError géré).

## Fin de chantier : review + correction Fable 5. Puis passe finale djc + chasse aux bugs.

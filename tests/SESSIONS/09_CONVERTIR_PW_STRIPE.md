# Session 09 — Convertir les tests Playwright TS Stripe → PlaywrightLive Python

## Objectif

Convertir les ~10 tests Playwright TS qui impliquent un paiement Stripe (iframe, redirection checkout, webhook).

## Pre-requis

- Session 08 terminee (PlaywrightLive sans Stripe valide)

## Prompt a envoyer

```
Convertis les tests Playwright TS avec Stripe en PlaywrightLive Python.

Fichiers :
- 11-anonymous-membership.spec.ts
- 12-anonymous-membership-dynamic-form.spec.ts
- 13-ssa-membership-tokens.spec.ts
- 14-membership-manual-validation.spec.ts
- 15-membership-free-price.spec.ts
- 17-membership-free-price-multi.spec.ts
- 27-membership-dynamic-form-full-cycle.spec.ts
- 42-membership-zero-price.spec.ts
- 43-membership-manual-validation-stripe.spec.ts
- 44-crowds-contribution-stripe.spec.ts
- 09-anonymous-events.spec.ts
- 10-anonymous-event-dynamic-form.spec.ts

Creer dans tests/e2e/.
Carte Stripe test : 4242 4242 4242 4242, nom Douglas Adams, date 12/42, code 424.
L'iframe Stripe est un iframe — utiliser page.frame_locator pour y acceder.
```

## Verification

```bash
docker exec lespass_django poetry run pytest tests/e2e/ -v -s --tb=long
```

## Critere de succes

- [ ] ~12 fichiers Python E2E crees
- [ ] Les paiements Stripe passent (iframe remplie, redirect OK)
- [ ] Pas de regression

## Duree estimee

~2h (l'iframe Stripe est toujours penible a automatiser).

## Risques

- **Iframe Stripe** : le selecteur `page.frame_locator('iframe[name*="stripe"]')` peut changer. Toujours utiliser des selecteurs resilients.
- **Timing** : Stripe peut etre lent a repondre en test. Augmenter les timeouts pour ces tests (`self.page.set_default_timeout(30000)`).
- **Webhooks** : si le test attend un webhook Stripe (confirmation de paiement), il faut que le webhook soit configure pour atteindre le LiveServer. Alternative : mocker le webhook dans les tests E2E.

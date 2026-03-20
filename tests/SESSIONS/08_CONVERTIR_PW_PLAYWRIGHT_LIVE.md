# Session 08 — Convertir les tests Playwright TS → PlaywrightLive Python (batch 1)

## Objectif

Convertir les ~20 tests Playwright TS marques "PlaywrightLive" en Python. Ce sont les tests qui necessitent un vrai navigateur (Stripe, HTMX, validation JS, cross-tenant).

## Pre-requis

- Session 04 terminee (PlaywrightTenantLiveTestCase valide)
- Playwright Python installe et Chromium fonctionne dans le conteneur

## Prompt a envoyer

```
Convertis les tests Playwright TS marques "PlaywrightLive" en Python.

Contexte :
- PlaywrightTenantLiveTestCase est valide (session 04)
- Classe de base dans tests/e2e/base.py
- Voir tests/PLAN_TEST.md sections 4.1 a 4.5 — tous les fichiers marques "PlaywrightLive"

Fichiers (par priorite) :

Batch 1 — sans Stripe (~10 fichiers) :
- 20-membership-validations.spec.ts (validation JS)
- 18-reservation-validations.spec.ts (validation JS)
- 23-crowds-participation.spec.ts (popup UI)
- 39-laboutik-pos-paiement.spec.ts (HTMX)
- 44-laboutik-adhesion-identification.spec.ts (NFC + HTMX)
- 45-laboutik-pos-tiles-visual.spec.ts (rendu CSS)
- 01-login.spec.ts (deja fait en session 04 — verifier)
- 31-admin-asset-federation.spec.ts (cross-tenant)

Creer dans tests/e2e/.
Chaque test herite de PlaywrightTenantLiveTestCase.
Utiliser self.page pour les interactions Playwright.
```

## Note

Les tests **avec Stripe** (11, 12, 13, 14, 15, 17, 27, 42, 43, 44-crowds) seront convertis en session 09. Ils necessitent plus de travail (iframe Stripe, redirections, webhooks).

## Verification

```bash
# Chaque fichier E2E passe
docker exec lespass_django poetry run pytest tests/e2e/ -v -s --tb=long

# Tous les tests (pytest + e2e) passent
docker exec lespass_django poetry run pytest tests/ -v --tb=short --reuse-db
```

## Critere de succes

- [ ] ~8 fichiers Python E2E crees
- [ ] Chacun passe avec un navigateur headless
- [ ] Pas de regression sur les tests pytest

## Duree estimee

~1h30 (conversion + debug d'interactions navigateur).

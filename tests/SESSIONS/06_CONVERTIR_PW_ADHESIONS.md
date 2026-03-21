# Session 06 — Convertir les tests Playwright TS adhesions → pytest Python

## Statut : FAIT (2026-03-20) — 20 tests, 162 total

## Objectif

Convertir les ~14 tests Playwright TS adhesions marques "FastTenantTestCase" dans PLAN_TEST.md.

## Resultat

Au lieu de 14 fichiers (1:1), regroupement par theme : **9 fichiers, 20 tests**.

| Fichier pytest | Tests | Source PW TS |
|---|---|---|
| `test_membership_products_create.py` | 5 | 03, 04, 05, 06, 08 |
| `test_membership_manual_validation.py` | 1 | 07 |
| `test_adhesions_obligatoires_m2m.py` | 1 | 37 |
| `test_admin_membership_list_status.py` | 3 | 35 |
| `test_sepa_duplicate_protection.py` | 3 | 36 |
| `test_membership_account_states.py` | 2 | 21, 22 |
| `test_admin_membership_paiement.py` | 2 | 33 |
| `test_admin_membership_cancel.py` | 2 | 34 |
| `test_admin_membership_custom_form.py` | 1 | 26 |

## Pattern utilise

Fixtures pytest + DB dev + `schema_context` (identique sessions 03-05). Pas de FastTenantTestCase.

- ORM dans `schema_context('lespass')` pour creer les donnees
- `admin_client` / `api_client` (fixtures conftest.py) pour les requetes HTTP
- UUID suffixes pour noms uniques (pas de collision entre runs)

## Pieges resolus

- `PriceSold.qty_solded` (pas `qty_sold`)
- `get_checkout_for_membership` attend un UUID dans l'URL (pas le PK int)
- Le template account montre le bouton cancel quand `status='A'` (ONCE), pas AUTO

## Verification

```bash
# Tous les tests passent (162)
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short

# Comptage
docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 162 tests collected
```

## Critere de succes

- [x] 9 fichiers Python crees (regroupes par theme)
- [x] 20 tests passent
- [x] Pas de regression (162/162)
- [x] Fixture `tenant` ajoutee dans conftest.py

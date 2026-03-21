# Session 05 — Convertir tests PW TS admin → pytest Python

## Statut : FAIT (2026-03-20)

## Resultat

- **6 fichiers Python crees** (99-theme_language skippee → session 08)
- **20 nouveaux tests** (9 + 6 + 1 + 2 + 1 + 1)
- **142 tests pytest total** (+ 2 E2E = 144 total)
- **Temps execution** : ~12s pour les 142 tests
- **0 regression**

## Fichiers crees

| Fichier | Tests | Source PW TS |
|---------|-------|-------------|
| `tests/pytest/test_admin_audit_fixes.py` | 9 | 33-admin-audit-fixes.spec.ts |
| `tests/pytest/test_admin_proxy_products.py` | 6 | 29-admin-proxy-products.spec.ts |
| `tests/pytest/test_admin_configuration.py` | 1 | 02-admin-configuration.spec.ts |
| `tests/pytest/test_numeric_overflow_validation.py` | 2 | 28-numeric-overflow-validation.spec.ts |
| `tests/pytest/test_user_account_summary.py` | 1 | 16-user-account-summary.spec.ts |
| `tests/pytest/test_admin_credit_note.py` | 1 | 32-admin-credit-note.spec.ts |

## Fichier modifie

- `tests/pytest/conftest.py` : +2 fixtures session (`admin_user`, `admin_client`)

## Pattern utilise

- **Pas de FastTenantTestCase** — fixtures pytest + DB dev existante + `schema_context`
- Pattern de reference : `test_caisse_navigation.py`
- Fixtures partagees `admin_user`/`admin_client` dans conftest.py (scope=session)

## Pieges rencontres et resolus

1. **Sidebar conditionnelle** : les liens `ticketproduct`/`membershipproduct` n'apparaissent que si `module_billetterie`/`module_adhesion` sont actifs → le test active les modules temporairement
2. **User API `is_active=False`** : les users crees via l'API reservation ont `is_active=False` → le test active le user avant `force_login`
3. **User sans wallet** : `MyAccount.dispatch()` appelle FedowAPI si le wallet est null → le test cree un wallet

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short
# 142 passed in ~12s

docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 142 tests collected
```

## SKIP

- `99-theme_language.spec.ts` : 3 tests DOM/JS/localStorage → session 08 (Playwright Python E2E)

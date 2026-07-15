# Simplification des tests + socle E2E Python (force_login)

**Date :** 2026-06-15
**Migration :** Non

## Ce qui a ete fait

Portage du socle de tests de la V2 (`lespass-main`) vers le main, et
simplification de la suite TypeScript (42 → 30 specs).

### Modifications

| Fichier | Changement |
|---|---|
| `AuthBillet/views_test_only.py` | Nouveau — endpoint `force_login` E2E (triple garde-fou : DEBUG + E2E_TEST_TOKEN + header X-Test-Token) |
| `AuthBillet/urls.py` | Branchement sous `if settings.DEBUG:` |
| `tests/pytest/conftest.py` | Fixtures V2 : `api_client`, `mock_stripe`, `admin_user`, etc. |
| `tests/pytest/test_stripe_*.py` (4 fichiers) | 17 tests Stripe mockés portés de la V2 |
| `tests/e2e/test_*_validations.py` + `test_numeric_overflow_validation.py` | 3 specs TS migrés en Playwright Python |
| `tests/e2e/test_stripe_smoke.py` | 2 checkouts Stripe réels (adhésion + réservation) |
| Templates booking/membership form | Bugfix `min="{{ price.prix|unlocalize }}"` (validation HTML5 cassée en locale FR) |
| 12 specs TS supprimés | Couverts par mock pytest + smoke + tests Python |

## Tests a realiser

### Test 1 : l'endpoint force_login est inoffensif

1. Vérifier qu'en prod (`DEBUG=False`) l'URL n'existe pas :
   `curl -X POST https://<tenant>/api/user/__test_only__/force_login/` → 404.
2. En dev, sans header `X-Test-Token` → 404 silencieux.
3. En dev avec le bon token (`.env`) → 200 + sessionid.

### Test 2 : suites au vert

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q     # ~246 passed, ~50 s
docker exec lespass_django poetry run pytest tests/e2e/ -q        # ~15 passed, ~1 min
cd tests/playwright && yarn test:chromium:console                  # 30 specs, ~7 min
```

### Test 3 : bugfix validation HTML5 prix libre (locale FR)

1. Aller sur un événement avec billet à prix libre (locale FR).
2. Inspecter l'input montant : `min="5.00"` (point, pas virgule).
3. Saisir un montant inférieur au minimum → le navigateur bloque la soumission.
   (Avant le fix, `min="5,00"` était ignoré par le navigateur.)

## Compatibilite

- L'endpoint force_login n'est monté que si `DEBUG=True` — zéro impact prod.
- `pytest-cov` a été installé dans le venv du container via pip (PAS dans
  `pyproject.toml`). Pour le garder après un rebuild d'image, l'ajouter en
  dépendance dev : `poetry add --group dev pytest-cov`.
- Les specs TS supprimés restent dans l'historique git si besoin.

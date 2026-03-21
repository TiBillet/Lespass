# Session 10 — Nettoyage final (Phase E)

## Statut : FAIT (2026-03-21)

## Objectif

Supprimer les tests Playwright TS, nettoyer les fichiers, mettre a jour les metriques.

## Ce qui a ete fait

### 1. Supprime `tests/playwright/` (43 Mo)

Le dossier entier (51 fichiers TS, config Node.js, node_modules).
Tous les tests TS ont un equivalent Python (pytest ou E2E Playwright Python).

### 2. Supprime `os.environ.setdefault('DJANGO_SETTINGS_MODULE', ...)` dans 26 fichiers

Redondant avec `pyproject.toml` :
```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "TiBillet.settings"
```

Fichiers nettoyes : 26 fichiers `test_*.py` dans `tests/pytest/`.

### 3. Pas de conftest.py racine

Les 2 conftest existants sont independants et servent des contextes differents :
- `tests/pytest/conftest.py` : API key, Django test client, fixtures DB, mock_stripe
- `tests/e2e/conftest.py` : Playwright browser, login, django_shell, pos_page, fill_stripe_card

Creer un conftest racine compliquerait le scope sans gain. Decision : garder en l'etat.

### 4. Mis a jour PLAN_TEST.md section 8

Metriques finales mises a jour :

| Metrique | Avant migration | Apres (final) |
|---|---|---|
| Tests TS | 119 x 3 navigateurs | **0** |
| Tests pytest | 0 | **195** (~33s) |
| Tests E2E Python | 0 | **33** (~3 min) |
| Runner | pytest + yarn PW | **pytest seul** |
| Temps total | ~57 min | **~3.5 min** |
| Total tests | ~165 TS | **228 Python** |

## Verification

```bash
# Plus de playwright TS
test ! -d tests/playwright && echo "OK"

# Plus de DJANGO_SETTINGS_MODULE dans les tests
grep -rn "DJANGO_SETTINGS_MODULE" tests/pytest/ tests/e2e/ | wc -l
# 0

# Tous les tests passent
docker exec lespass_django poetry run pytest tests/pytest/ -q
# 195 passed in ~33s

docker exec lespass_django poetry run pytest tests/e2e/ --co -q | tail -1
# 33 tests collected
```

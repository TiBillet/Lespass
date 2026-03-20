# Session 10 — Nettoyage final (Phase E)

## Objectif

Supprimer les tests Playwright TS, consolider conftest.py, nettoyer les fichiers de config Node.js.

## Pre-requis

- Sessions 01-09 terminees
- Tous les tests Python passent
- Les tests PW TS ne sont plus necessaires (chaque test a son equivalent Python)

## Prompt a envoyer

```
Nettoyage final de la migration des tests.

A faire :
1. Verifier que TOUS les tests Python passent : docker exec lespass_django poetry run pytest tests/ -v --reuse-db
2. Compter les tests : on doit avoir ~250 tests Python (pytest + e2e)
3. Supprimer tests/playwright/ (tout le dossier — les tests TS sont remplaces)
4. Consolider conftest.py :
   - Creer tests/conftest.py (racine) avec les fixtures partagees : tenant, admin_user, api_key
   - Simplifier tests/pytest/conftest.py (supprimer le code de generation API key si duplique)
5. Supprimer les os.environ.setdefault('DJANGO_SETTINGS_MODULE', ...) dans les fichiers de test (deja dans pyproject.toml via pytest-django)
6. Mettre a jour tests/PLAN_TEST.md section 8 avec les metriques finales
7. Verifier une derniere fois : docker exec lespass_django poetry run pytest tests/ -v --reuse-db
```

## Verification

```bash
# 1. Tous les tests passent
docker exec lespass_django poetry run pytest tests/ -v --reuse-db --tb=short

# 2. Compter
docker exec lespass_django poetry run pytest tests/ --co -q | tail -1

# 3. Plus de playwright TS
test ! -d tests/playwright && echo "OK: playwright/ supprime"

# 4. --last-failed fonctionne
docker exec lespass_django poetry run pytest tests/ --reuse-db --last-failed -v

# 5. Temps total
time docker exec lespass_django poetry run pytest tests/ --reuse-db -q
```

## Critere de succes

- [ ] ~250 tests Python
- [ ] `tests/playwright/` n'existe plus
- [ ] 1 seul `conftest.py` racine + 1 par sous-dossier si necessaire
- [ ] 0 `os.environ.setdefault('DJANGO_SETTINGS_MODULE')` dans les fichiers de test
- [ ] Temps total < 6 minutes (unitaires ~30s + E2E ~5 min)
- [ ] `--last-failed` fonctionne
- [ ] `--reuse-db` fonctionne (2e run sans CREATE DATABASE)

## Duree estimee

~30 minutes.

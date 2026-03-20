# Session 01 — Installer pytest-django + configurer --reuse-db

## Objectif

Poser les fondations : installer pytest-django, configurer `DJANGO_SETTINGS_MODULE` au bon endroit, activer `--reuse-db` par defaut. Apres cette session, `pytest tests/pytest/` fonctionne toujours, mais via pytest-django au lieu du setup manuel.

## Pre-requis

- Conteneur `lespass_django` tourne (`docker ps`)
- Branche `integration_laboutik`

## Prompt a envoyer

```
Installe pytest-django dans le projet Lespass.

Contexte :
- pytest est deja installe (^8.4.2 dans pyproject.toml)
- pytest-django n'est PAS installe
- Les 28 fichiers pytest existants font `os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')` manuellement dans chaque fichier
- Le conftest.py est dans tests/pytest/conftest.py
- Voir tests/PLAN_TEST.md section 2.1

A faire :
1. `poetry add --group dev pytest-django`
2. Ajouter `DJANGO_SETTINGS_MODULE = TiBillet.settings` dans pyproject.toml ([tool.pytest.ini_options]) ou pytest.ini
3. Ajouter `--reuse-db` comme default dans addopts
4. Migrer les markers de pytest.ini vers pyproject.toml (tout au meme endroit)
5. Verifier que les 28 tests pytest existants passent toujours : `docker exec lespass_django poetry run pytest tests/pytest/ -v`
6. Ne PAS toucher au code des fichiers de test. Juste la config.
```

## Verification

```bash
# 1. pytest-django est installe
docker exec lespass_django poetry show pytest-django

# 2. Config pytest centralisee
grep -A 10 'tool.pytest' pyproject.toml

# 3. Les tests existants passent toujours
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short

# 4. --reuse-db fonctionne (2e run plus rapide — pas de CREATE DATABASE)
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short
# Verifier dans la sortie : pas de "Creating test database"
```

## Critere de succes

- [ ] `poetry show pytest-django` retourne une version
- [ ] `pyproject.toml` contient `[tool.pytest.ini_options]` avec `DJANGO_SETTINGS_MODULE`
- [ ] `pytest.ini` peut etre supprime (tout dans pyproject.toml)
- [ ] Les 28 tests passent (meme nombre qu'avant)
- [ ] Le 2e run est ~12s plus rapide (pas de CREATE DATABASE)

## Duree estimee

~15 minutes.

## Risques

- **Collision avec conftest.py** : si pytest-django detecte Django automatiquement, le `os.environ.setdefault` dans les fichiers de test devient redondant mais pas nocif. Ne pas les supprimer maintenant — ca sera fait en Phase D.
- **Tests API v2 qui font du requests HTTP** : ils continuent a marcher car pytest-django n'interfere pas avec les appels HTTP externes.

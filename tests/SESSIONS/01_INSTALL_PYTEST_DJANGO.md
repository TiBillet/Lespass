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

- [x] `poetry show pytest-django` retourne une version (4.12.0)
- [x] `pyproject.toml` contient `[tool.pytest.ini_options]` avec `DJANGO_SETTINGS_MODULE`
- [x] `pytest.ini` supprime (tout dans pyproject.toml)
- [x] Les 122 tests passent (2 runs successifs OK, ~10s chacun)
- [ ] ~~Le 2e run est ~12s plus rapide (pas de CREATE DATABASE)~~ — N/A, voir ecarts

## Realisation — 2026-03-20

### Fichiers modifies

| Fichier | Action |
|---------|--------|
| `pyproject.toml` | `pytest-django ^4.12.0` ajoute (poetry) + section `[tool.pytest.ini_options]` |
| `pytest.ini` | Supprime (markers + filterwarnings migres dans pyproject.toml) |
| `tests/pytest/conftest.py` | 2 fixtures ajoutees (voir ecarts) |

### Ecarts par rapport au plan

1. **`--reuse-db` retire** : cette option gere les test databases de pytest-django. Nos tests utilisent la base dev existante (django-tenants avec schemas), pas une `test_*` DB. `--reuse-db` n'a pas de sens ici. `addopts = ""` dans pyproject.toml.

2. **`conftest.py` modifie** (le plan disait de ne pas y toucher) : pytest-django bloque l'acces DB par defaut (exige `@pytest.mark.django_db`). Incompatible avec les tests existants qui ont des fixtures `scope="module"` accedant a la DB. Deux fixtures ajoutees :
   - `django_db_setup()` : no-op, empeche pytest-django de creer/gerer une test database
   - `_enable_db_access_for_all(django_db_blocker)` : desactive le bloqueur DB au niveau session

### Lecons apprises

- pytest-django + django-tenants : on ne peut pas utiliser le workflow standard (test DB + --reuse-db). Les tests tournent sur la base dev avec les vrais schemas tenant.
- Le db blocker de pytest-django bloque au niveau connexion, pas au niveau test. Les fixtures `scope="module"` qui accedent a la DB echouent si le blocker n'est pas desactive au niveau session.

## Duree estimee

~15 minutes.

## Risques

- **Collision avec conftest.py** : si pytest-django detecte Django automatiquement, le `os.environ.setdefault` dans les fichiers de test devient redondant mais pas nocif. Ne pas les supprimer maintenant — ca sera fait en Phase D.
- **Tests API v2 qui font du requests HTTP** : ils continuent a marcher car pytest-django n'interfere pas avec les appels HTTP externes.

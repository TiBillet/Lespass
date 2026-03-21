# Session 04 — Prototype Playwright Python (E2E)

**Statut : FAIT (2026-03-20)**

## Objectif

Installer Playwright Python dans le conteneur Docker et convertir le test de login TS en Python. Valider que Playwright Sync + Chromium headless fonctionne dans le conteneur.

## Pre-requis

- Sessions 01-02 terminees (pytest-django + FastTenantTestCase valides)
- Conteneur `lespass_django` tourne
- Serveur Django tourne (via Traefik)

## Decision architecturale : serveur externe (pas LiveServer)

Le PLAN_TEST.md (section 5.2) proposait `PlaywrightTenantLiveTestCase` (TenantTestCase + LiveServerTestCase). On utilise le **serveur externe** (identique aux tests TS) car :
- Le LiveServer ecoute sur `localhost:PORT` → le middleware django-tenants ne resout pas le tenant
- DNS verifie : `lespass.tibillet.localhost` → `172.17.0.1` (Docker gateway → Traefik)
- C'est le fallback explicitement documente dans la fiche session 04 originale

Approche retenue : **fixtures pytest** (pas de classes TestCase), serveur existant via Traefik, Playwright Sync API headless.

## Ce qui a ete fait

1. **Installer Playwright Python** dans le conteneur :
   - `poetry add --group dev playwright` (v1.58.0)
   - `playwright install-deps chromium` (libs systeme, en root)
   - `playwright install chromium` (binaire Chromium)

2. **Marker `e2e`** ajoute dans `pyproject.toml`

3. **`tests/e2e/conftest.py`** avec fixtures :
   - `playwright_instance` (session) — demarre Playwright
   - `browser` (session) — Chromium headless avec `--host-resolver-rules` (fix DNS .localhost)
   - `page` (function) — nouvel onglet par test, `base_url`, `ignore_https_errors=True`
   - `admin_email` (session) — lit `ADMIN_EMAIL` env var
   - `login_as` (session) — fixture factory `(page, email) → void`
   - `login_as_admin` (session) — fixture factory `(page) → void`

4. **`tests/e2e/test_login.py`** — 2 tests (conversion de `01-login.spec.ts`) :
   - `test_authenticate_as_admin` : login complet + verification /my_account + bouton Admin panel
   - `test_validate_email_format` : email invalide → validation HTML5 bloque

## Piege resolu : Chromium et .localhost (RFC 6761)

Chromium resout `*.localhost` → `127.0.0.1` (RFC 6761), ignorant `/etc/hosts`.
Rien n'ecoute sur `127.0.0.1:443` dans le conteneur → `ERR_CONNECTION_REFUSED`.
Fix : `--host-resolver-rules=MAP *.tibillet.localhost 172.17.0.1` force la resolution vers la gateway Docker (Traefik).
Variable d'env `DOCKER_GATEWAY` disponible pour override.

## Verification

```bash
# 1. Playwright Python installe
docker exec lespass_django poetry run python -c "from playwright.sync_api import sync_playwright; print('OK')"

# 2. Les 2 tests E2E passent (~5s)
docker exec lespass_django poetry run pytest tests/e2e/test_login.py -v -s

# 3. Les 122 tests existants ne sont pas casses (~11s)
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short
```

## Critere de succes

- [x] `playwright` Python est dans pyproject.toml (group dev)
- [x] `tests/e2e/conftest.py` contient les fixtures Playwright + login helpers
- [x] `tests/e2e/test_login.py` passe — le navigateur se lance, login fonctionne (2 passed)
- [x] Le test accede a `https://lespass.tibillet.localhost` via Traefik et la page repond
- [x] Les 122 tests pytest existants ne sont pas casses

## Fichiers

| Fichier | Action |
|---------|--------|
| `pyproject.toml` | Modifie (+playwright dep, +marker e2e) |
| `tests/e2e/__init__.py` | Cree (vide) |
| `tests/e2e/conftest.py` | Cree (fixtures Playwright + login helpers + fix DNS .localhost) |
| `tests/e2e/test_login.py` | Cree (2 tests, conversion de 01-login.spec.ts) |

## Duree reelle

~20 minutes (dont ~10 min d'installation Chromium + deps systeme).

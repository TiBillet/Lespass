# Session 04 — Prototype PlaywrightTenantLiveTestCase (Python)

## Objectif

Installer Playwright Python, creer la classe de base `PlaywrightTenantLiveTestCase`, et convertir 1 test TS (`01-login.spec.ts`) en Python. Valider que Playwright Sync + LiveServer + django-tenants cooperent.

## Pre-requis

- Sessions 01-02 terminees (pytest-django + FastTenantTestCase valides)
- Conteneur `lespass_django` tourne

## Prompt a envoyer

```
Installe Playwright Python et cree le prototype PlaywrightTenantLiveTestCase.

Contexte :
- playwright (Python) n'est PAS installe dans le projet
- pytest-django est installe (session 01)
- Voir tests/PLAN_TEST.md section 5.2 pour le pattern cible
- Le test a convertir : tests/playwright/tests/admin/01-login.spec.ts

A faire :
1. Installer playwright Python : `poetry add --group dev playwright` puis `poetry run playwright install chromium`
2. Creer tests/e2e/__init__.py
3. Creer tests/e2e/base.py avec PlaywrightTenantLiveTestCase (voir PLAN_TEST.md section 5.2)
4. Creer tests/e2e/test_login.py — convertir 01-login.spec.ts en Python
5. Verifier : docker exec lespass_django poetry run pytest tests/e2e/test_login.py -v -s

Points d'attention :
- PlaywrightTenantLiveTestCase herite de TenantTestCase + LiveServerTestCase (pas FastTenantTestCase car LiveServer a besoin de la DB reelle)
- Playwright Sync API (pas async) — fonctionne sans probleme en WSGI
- Le LiveServer ecoute sur un port aleatoire. Utiliser self.live_server_url
- Le test de login utilise le pattern "TEST MODE" magic link (voir tests/playwright/tests/utils/auth.ts)
```

## Verification

```bash
# 1. Playwright Python installe
docker exec lespass_django poetry run python -c "from playwright.sync_api import sync_playwright; print('OK')"

# 2. Chromium installe
docker exec lespass_django poetry run playwright install --dry-run chromium

# 3. Le test de login passe
docker exec lespass_django poetry run pytest tests/e2e/test_login.py -v -s

# 4. Les tests existants ne sont pas casses
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short --reuse-db
```

## Critere de succes

- [ ] `playwright` Python est dans pyproject.toml (group dev)
- [ ] `tests/e2e/base.py` contient `PlaywrightTenantLiveTestCase`
- [ ] `tests/e2e/test_login.py` passe — le navigateur se lance, login fonctionne
- [ ] Le test accede a `self.live_server_url` et la page repond
- [ ] Les tests pytest existants ne sont pas casses

## Duree estimee

~45 minutes. C'est la session la plus risquee (3 couches a faire cooperer).

## Risques

- **LiveServer + django-tenants** : le LiveServer Django cree un thread avec un serveur WSGI. Il faut que le tenant soit resolu correctement. Si `self.live_server_url` retourne `http://localhost:PORT`, le tenant middleware peut ne pas matcher. Solution potentielle : configurer le `ALLOWED_HOSTS` et le `SERVER_NAME` dans les tests.
- **Playwright dans Docker** : Chromium a besoin de libs systeme. Si ca crashe au lancement, c'est probablement des libs manquantes (`playwright install-deps chromium`).
- **Si LiveServer ne marche pas avec django-tenants** : fallback sur le serveur Django deja en cours d'execution (comme les tests PW TS actuels). Dans ce cas, PlaywrightTenantLiveTestCase ne lance pas son propre serveur mais utilise l'URL externe. Moins ideal mais fonctionnel.

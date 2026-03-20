# Session 05 — Convertir les tests Playwright TS → FastTenantTestCase (batch 1 : admin)

## Objectif

Convertir les ~10 tests Playwright TS du dossier `admin/` qui ne necessitent pas de navigateur (CRUD admin, validation, logique metier) en tests `FastTenantTestCase` Python.

## Pre-requis

- Sessions 01-02 terminees
- Le pattern de conversion est valide

## Prompt a envoyer

```
Convertis les tests Playwright TS admin en FastTenantTestCase Python.

Contexte :
- Pattern valide en session 02
- Voir tests/PLAN_TEST.md section 4.2 pour la liste des fichiers admin

Fichiers a convertir (ceux marques "FastTenantTestCase" dans PLAN_TEST.md) :
- 02-admin-configuration.spec.ts → test_admin_configuration.py
- 16-user-account-summary.spec.ts → test_user_account_summary.py
- 28-numeric-overflow-validation.spec.ts → test_numeric_overflow_validation.py
- 29-admin-proxy-products.spec.ts → test_admin_proxy_products.py
- 32-admin-credit-note.spec.ts → test_admin_credit_note.py
- 33-admin-audit-fixes.spec.ts → test_admin_audit_fixes.py
- 99-theme_language.spec.ts → test_theme_language.py

Creer les fichiers dans tests/pytest/ (meme endroit que les tests existants).

Pour chaque test :
1. Lire le fichier TS pour comprendre ce qu'il verifie
2. Identifier l'action testee (POST admin, GET page, validation)
3. Ecrire l'equivalent avec self.client.get/post + assertions ORM
4. Verifier que le test passe

Ne pas convertir 01-login.spec.ts et 31-admin-asset-federation.spec.ts — ils necessitent un navigateur (PlaywrightLive).
```

## Verification

```bash
# Chaque fichier converti passe
docker exec lespass_django poetry run pytest tests/pytest/test_admin_configuration.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_admin_proxy_products.py -v
# etc.

# Tous les tests passent (regression)
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short --reuse-db
```

## Critere de succes

- [ ] 7 fichiers Python crees
- [ ] Chaque fichier passe individuellement
- [ ] Tous les tests (anciens + nouveaux) passent ensemble
- [ ] Temps total des 7 fichiers < 15s

## Duree estimee

~1h (7 fichiers, certains sont simples, d'autres ont 6-8 tests).

## Risques

- **Admin Django** : les tests admin doivent utiliser `self.client.force_login(admin_user)` puis `self.client.get('/admin/...')`. Le middleware admin de Django doit reconnaitre le user comme superuser.
- **CSRF** : `self.client` de Django gere le CSRF automatiquement (il envoie le cookie + le token). Pas besoin de le gerer manuellement.

# Vague 2 migration tests TS→Python + fix timeout fedow_api / Wave 2 TS→Python test migration + fedow_api timeout fix

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 8 specs Playwright TS supplémentaires convertis en Playwright Python via un
workflow multi-agents (login, admin-config, account-summary, reservation-limits,
account-states, crowds x2, theme/language — 11 tests Python, tous verts). Suite TS : 30 → 22 specs.
**Bugfix critique** : `timeout=30` sur les appels HTTP de `fedow_connect/fedow_api.py`.

**Pourquoi / Why :** sans timeout, un serveur Fedow muet gelait le runserver mono-thread pour
toujours (incident du 2026-06-11 : serveur bloqué 1h dans `send_membership_product_to_fedow`,
toutes les requêtes en 504, cascade de faux échecs E2E sur les specs 33-39).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | **Bugfix** : `timeout=30` sur `_post` et `_get` |
| `tests/e2e/test_login.py`, `test_admin_configuration.py`, `test_user_account_summary.py`, `test_reservation_limits.py`, `test_membership_account_states.py`, `test_crowds_participation.py`, `test_crowds_summary.py`, `test_theme_language.py` | **Nouveaux** — conversions des specs TS 01, 02, 16, 19, 21, 23, 24, 99 |
| `tests/playwright/tests/` | **Supprimés** : 01, 02, 16, 19, 21, 23, 24, 99 (migrés en Python) |
| `tests/playwright/tests/36-sepa-duplicate-protection.spec.ts` | **Bugfix** : import `Paiement_stripe` depuis `BaseBillet.models` (l'ancien import `PaiementStripe.models` échouait silencieusement → test flaky qui ne testait pas la protection doublon) |
| `tests/playwright/tests/26-admin-membership-custom-form-edit.spec.ts` | Timeout `execSync` 15 s → 60 s (boot `tenant_command shell` sous charge) |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/` | Tableau de migration et CHANTIER-02 à jour |

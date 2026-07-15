# Vague 5 (finale) : la suite TypeScript n'existe plus / Wave 5 (final): TypeScript suite is gone

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** les 3 derniers specs TS (duplication produit complexe, event quick create,
explorer markers) convertis en Playwright Python — 5 tests verts. **`tests/playwright/tests/`
est vide : 42 specs TS → 0 en une journée.** La suite E2E est désormais 100 % Python
(~65 tests, ~6 min) ; suite backend pytest : 246 tests (~50 s).

**Pourquoi / Why :** une seule techno de test (pytest), login E2E instantané (force_login),
Stripe mocké pour la logique + smoke réels pour les parcours d'argent. Reste une décision
mainteneur : supprimer le dossier `tests/playwright/` (outillage Node/yarn mort) et les
`tests/scripts/verify_*.py` devenus inutiles — voir
`TECH_DOC/SESSIONS/TESTS/CHANTIER-05-vague-5-cloture.md`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_product_duplication_complex.py`, `test_event_quick_create_duplicate.py`, `test_explorer_markers_per_pa.py` | **Nouveaux** — conversions des 3 derniers specs TS |
| `tests/playwright/` | **Dossier supprimé entièrement** (specs, utils, configs, node_modules — plus aucune dépendance Node/yarn) |
| `tests/scripts/verify_*.py` (4 fichiers) | **Supprimés** — n'étaient appelés que par les specs TS ; `setup_test_data.py` conservé (fixture e2e) |
| `tests/README.md`, `GUIDELINES.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-05-*.md` | Documentation de clôture |

# Vague 3 migration tests TS→Python — specs admin / Wave 3 TS→Python test migration — admin specs

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 8 specs admin Playwright TS convertis en Playwright Python par un workflow
d'agents Sonnet séquentiels (1 agent par spec, conversion + vérification + corrections) :
custom form edit, credit note, ajouter paiement, cancel membership, list status, adhésions
obligatoires M2M (x2), reservation cancel — 13 tests Python, tous verts. Suite TS : 22 → 14 specs.

**Pourquoi / Why :** poursuite de la migration vers une seule techno de test (pytest), avec un
coût réduit de ~40 % vs la vague 2 (1 agent au lieu de 2 par spec, modèle Sonnet, cheat-sheet
dans le prompt au lieu de relire conftest + PIEGES).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_admin_*.py` (6 fichiers), `test_event_adhesion_obligatoire_check.py` | **Nouveaux** — conversions des specs TS 26, 32, 33, 34, 35, 37, 38, 39 |
| `tests/playwright/tests/` | **Supprimés** : les 8 specs migrés |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-03-*.md` | Documentation à jour, dont un ⚠️ « formulaires imbriqués HTMX dans la fiche admin Membership » à vérifier manuellement |

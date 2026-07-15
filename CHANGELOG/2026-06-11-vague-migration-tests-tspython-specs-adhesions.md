# Vague 4 migration tests TS→Python — specs adhésions / Wave 4 TS→Python test migration — membership specs

**Date :** 2026-06-11
**Migration :** Non / No

**Quoi / What :** 11 specs adhésions Playwright TS convertis en Playwright Python (workflow
d'agents Sonnet séquentiels) : création admin (simple, récurrente, validation, AMAP, solidaire,
manuelle), prix libre multi (Stripe réel ×4), annulation récurrente, cycle complet formulaire
dynamique (7 tests), protection doublon SEPA, validation manuelle + paiement Stripe réel —
22 tests Python, tous verts. **Suite TS : 14 → 3 specs.**

**Pourquoi / Why :** avant-dernière vague de la migration vers pytest unique. Après la vague 5
(3 specs restants : 25, 29, 40), le dossier `tests/playwright/` et l'outillage Node pourront
être supprimés.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_membership*.py`, `test_memberships_admin_create.py`, `test_sepa_duplicate_protection.py` (11 fichiers) | **Nouveaux** — conversions des specs TS 03-07, 14, 17, 22, 27, 36, 43 |
| `tests/playwright/tests/` | **Supprimés** : les 11 specs migrés |
| `BaseBillet/tasks.py` | **Bugfix** : `context_for_membership_email` crashait (`AttributeError`) quand `get_deadline()` ou `last_contribution` est `None` (adhésion en attente de validation) — les lignes de dates du mail ne sont ajoutées que si la date existe |
| `tests/e2e/test_membership_account_states.py` | Résilience : 1 reload si le runserver dev rend une page d'erreur transitoire (`OSError Bad file descriptor` sous charge) |
| `tests/README.md`, `TECH_DOC/SESSIONS/TESTS/CHANTIER-04-*.md` | Documentation à jour (dont constat interop V1 `/api/salefromlespass`) |

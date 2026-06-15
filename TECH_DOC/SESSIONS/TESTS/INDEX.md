# TESTS — Hub de la session

Audit complet des tests du repo Lespass (branche main), comparaison avec
le modèle de tests de la V2 (`../lespass-main`), et plan de simplification.

Date de l'audit : 2026-06-11

## Documents

| Document | Contenu |
|---|---|
| [ETAT_DES_LIEUX.md](ETAT_DES_LIEUX.md) | Inventaire complet, résultats des runs, coverage par app (photo du 2026-06-11 matin, AVANT simplification) |
| [PLAN_SIMPLIFICATION.md](PLAN_SIMPLIFICATION.md) | Suite essentielle vs suite complète, tests à fusionner/retirer, migration vers Playwright Python |
| [TESTS_RESTANTS.md](TESTS_RESTANTS.md) | Ce qui n'est pas testé, classé par priorité + cibles coverage |
| [CHANTIER-01-socle-e2e-python.md](CHANTIER-01-socle-e2e-python.md) | ✅ Socle force_login + vague 1 + politique Stripe V2 + suppressions (fait le 2026-06-11) |
| [CHANTIER-02-vague-2-workflow.md](CHANTIER-02-vague-2-workflow.md) | ✅ Vague 2 : 8 specs migrés par workflow + fix timeout fedow_api (incident serveur gelé) |
| [CHANTIER-03-vague-3-admin-sonnet.md](CHANTIER-03-vague-3-admin-sonnet.md) | ✅ Vague 3 : 8 specs admin migrés (agents Sonnet, -40 % tokens) + ⚠️ formulaires imbriqués HTMX admin à vérifier |
| [CHANTIER-04-vague-4-adhesions.md](CHANTIER-04-vague-4-adhesions.md) | ✅ Vague 4 : 11 specs adhésions migrés (22 tests Python) + bugfix email Celery + constat interop V1 |
| [CHANTIER-05-vague-5-cloture.md](CHANTIER-05-vague-5-cloture.md) | ✅ Vague 5 finale : **0 spec TS restant** — décision mainteneur : supprimer `tests/playwright/` + outillage Node |

## Résumé en 6 lignes

1. Les tests pytest DB-only sont **tous verts** : 229 tests en 49 secondes.
2. Les tests E2E Python sont **tous verts** : 8 tests en 17 secondes.
3. La suite Playwright TypeScript est **toute verte** : 67 tests en 10 min 54 — les 12 specs Stripe coûtent plus de la moitié de ce temps.
4. La suite legacy `tests/django_test/` est **rouge** (2 échecs sur 4) et très lente (2 min 48) — personne ne la lance.
5. La coverage hors migrations est de **32 %** — correcte sur les modèles, faible sur les vues (couvertes par les specs TS, invisibles dans la coverage Python).
6. La V2 (`lespass-main`) montre le chemin : tout en Python (pytest + Playwright Python), markers, fixtures multi-tenant. C'est le modèle à suivre pour remplacer les 42 specs TypeScript.

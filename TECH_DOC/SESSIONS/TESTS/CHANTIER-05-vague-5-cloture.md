# CHANTIER 05 — Vague 5 (finale) : fin du TypeScript

Statut : ✅ TERMINÉ (2026-06-11)

## Résultat : 3/3 verts (5 tests Python) — plus AUCUN spec TS

| Spec TS | Fichier Python | Tests | Verdict |
|---|---|---|---|
| 25-product-duplication-complex | `test_product_duplication_complex.py` | 1 | ✅ |
| 29-event-quick-create-duplicate | `test_event_quick_create_duplicate.py` | 2 | ✅ premier coup |
| 40-explorer-markers-per-pa | `test_explorer_markers_per_pa.py` | 2 | ✅ premier coup |

`tests/playwright/tests/` est vide (reste `utils/` et l'outillage Node).

## Bilan de la migration complète (1 journée, 2026-06-11)

| Vague | Specs | Méthode | Tokens agents |
|---|---|---|---|
| 1 (manuelle) | 18, 20, 28 | copie V2 + conversion à la main | — |
| Stripe | 08-13, 15, 42, 44 | mocks pytest V2 + smoke E2E | — |
| 2 (workflow) | 01, 02, 16, 19, 21, 23, 24, 99 | 16 agents Fable (2/spec) | ~917k |
| 3 (workflow) | 26, 32-35, 37-39 | 8 agents Sonnet (1/spec) | ~560k |
| 4 (workflow) | 03-07, 14, 17, 22, 27, 36, 43 | 11 agents Sonnet | ~592k |
| 5 (workflow) | 25, 29, 40 | 3 agents Sonnet | ~142k |

**42 specs TS → 0.** La suite E2E est désormais 100 % Playwright Python
(~35 fichiers, ~65 tests, ~6 min), plus 19 tests pytest Stripe mockés.

## Décision à prendre par le mainteneur

Le dossier `tests/playwright/` ne contient plus que l'outillage mort :
`utils/`, `global-setup.ts`, `playwright.config.ts`, `package.json`,
`node_modules/`, `yarn.lock`. **Supprimer le dossier entier** retirerait la
dépendance Node/yarn du projet. Les scripts `tests/scripts/verify_*.py`
(appelés par les specs TS) ne sont plus utilisés que par la fixture
`setup_test_data` (qui n'utilise que `setup_test_data.py`) — les `verify_*.py`
peuvent partir aussi.

## Bugs applicatifs corrigés grâce à la migration (récap session)

1. `min="{{ price.prix }}"` localisé (virgule FR) → validation HTML5 morte (2 templates).
2. `fedow_connect/fedow_api.py` sans timeout → runserver gelé 1h (incident 10:56).
3. `context_for_membership_email` → crash Celery sur adhésion sans deadline.
4. Spec TS 36 qui ne testait pas ce qu'il prétendait (import `Paiement_stripe` erroné, avalé).
5. Constat interop V1 `/api/salefromlespass` (500 LaBoutik, vente jamais re-synchronisée).

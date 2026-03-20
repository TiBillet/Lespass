# Session 07 — Convertir les tests Playwright TS → FastTenantTestCase (batch 3 : evenements, crowds, laboutik)

## Objectif

Convertir les derniers tests Playwright TS marques "FastTenantTestCase" dans les dossiers evenements/, crowds/ et laboutik/.

## Pre-requis

- Sessions 05-06 terminees

## Prompt a envoyer

```
Convertis les derniers tests Playwright TS en FastTenantTestCase Python.

Voir tests/PLAN_TEST.md sections 4.3, 4.4, 4.5.

Evenements (4 fichiers) :
- 19-reservation-limits.spec.ts
- 21-event-quick-create-duplicate.spec.ts
- 25-product-duplication-complex.spec.ts
- 35-admin-reservation-cancel.spec.ts
- 38-event-adhesion-obligatoire-check.spec.ts

Crowds (1 fichier) :
- 24-crowds-summary.spec.ts

LaBoutik (3 fichiers) :
- 30-discovery-pin-pairing.spec.ts
- 41-laboutik-cloture-caisse.spec.ts
- 46-laboutik-securite-a11y.spec.ts

9 fichiers total. Creer dans tests/pytest/.
```

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short --reuse-db
docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# Le nombre total doit etre ~130 (existants) + ~30 (sessions 05-07)
```

## Critere de succes

- [ ] 9 fichiers crees, tous passent
- [ ] ~160 tests pytest au total
- [ ] Temps total < 30s

## Duree estimee

~45 minutes.

# Session 06 — Convertir les tests Playwright TS → FastTenantTestCase (batch 2 : adhesions)

## Objectif

Convertir les ~14 tests Playwright TS adhesions marques "FastTenantTestCase" dans PLAN_TEST.md.

## Pre-requis

- Sessions 01-02 + 05 terminees (pattern admin valide)

## Prompt a envoyer

```
Convertis les tests Playwright TS adhesions en FastTenantTestCase Python.

Contexte :
- Pattern valide en sessions 02 et 05
- Voir tests/PLAN_TEST.md section 4.1 pour la liste

Fichiers a convertir (ceux marques "FastTenantTestCase") :
- 03-memberships.spec.ts
- 04-membership-recurring.spec.ts
- 05-membership-validation.spec.ts
- 06-membership-amap.spec.ts
- 07-fix-solidaire.spec.ts
- 08-membership-ssa-with-forms.spec.ts
- 21-membership-account-states.spec.ts
- 22-membership-recurring-cancel.spec.ts
- 26-admin-membership-custom-form-edit.spec.ts
- 33-admin-ajouter-paiement.spec.ts
- 34-admin-cancel-membership.spec.ts
- 35-admin-membership-list-status.spec.ts
- 36-sepa-duplicate-protection.spec.ts
- 37-admin-adhesions-obligatoires-m2m.spec.ts

14 fichiers. Creer dans tests/pytest/.
Ne PAS convertir les fichiers marques "PlaywrightLive" (11, 12, 13, 14, 15, 17, 20, 27, 42, 43).
```

## Verification

```bash
# Tous les tests passent
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short --reuse-db

# Compter le nombre total de tests (doit augmenter)
docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
```

## Critere de succes

- [ ] 14 fichiers Python crees
- [ ] Tous passent
- [ ] Pas de regression sur les tests existants

## Duree estimee

~1h30 (14 fichiers, certains avec de la logique metier complexe).

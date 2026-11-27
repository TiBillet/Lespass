# Test E2E de la récompense d'adhésion : attendre la trace / Membership reward E2E test: wait for the trace

**Date :** 2026-11-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** Refactoring interne des tests, sans impact utilisateur. Le test E2E
`test_adhesion_recompense_puis_qrcode.py` lit maintenant la ligne de vente en boucle
(20 s au plus) jusqu'à ce qu'elle porte `metadata["fedow_reward"]`.
/ Internal test refactoring. The E2E test polls the sale line until it carries the reward trace.

**Pourquoi / Why :** La tâche Celery `refill_from_lespass_to_user_wallet_from_price_solded`
crédite d'abord le Fedow, puis écrit la trace sur la ligne. Le test attendait le crédit,
puis lisait la ligne une seule fois : il échouait de temps en temps en suite complète.
/ The task credits Fedow first and writes the trace after; a single read was flaky.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | Nouvelle fonction `_attendre_la_trace_du_versement_sur_la_ligne`, utilisée par les parcours Stripe (SN) et admin (CA) |

---

## Comment tester (a la main) / Manual test

### Test 1 — le fichier passe
`make e2e ARGS="tests/e2e/test_adhesion_recompense_puis_qrcode.py -q"` → 2 passed.

### Test 2 — vérification par mutation (faite le 2026-11-27)
1. Ajouter temporairement `time.sleep(6)` dans `BaseBillet/tasks.py`, juste avant
   l'écriture de `meta["fedow_reward"]`, puis `docker restart lespass_celery`.
2. Le test corrigé passe (2 passed).
3. Avec `secondes=0` (une seule lecture, l'ancien comportement), les 2 tests échouent :
   « La ligne ne porte aucune trace de versement ».
4. Retirer le `sleep`, relancer `lespass_celery`.

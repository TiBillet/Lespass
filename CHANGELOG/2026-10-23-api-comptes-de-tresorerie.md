# API comptable : les comptes de trésorerie marqués / Accounting API: treasury accounts flagged

**Date :** 2026-10-23
**Migration :** Non

## Resume / Summary
**Quoi / What :** `GET /api/v2/accounts/` rend un champ `treasury` par compte : vrai pour
les comptes où l'argent d'une vente arrive (compte d'un moyen de paiement, compte d'une
monnaie, 419100 des recharges). / `/api/v2/accounts/` returns a `treasury` flag per
account: payment method, currency and top-up accounts.

**Pourquoi / Why :** le module Dolibarr ne crée plus de banque. Il vérifie, dès « Tester
la connexion », que chaque compte de trésorerie du lieu a sa banque, et les liste avec
leur libellé dans son tableau de correspondance. / The Dolibarr module no longer creates
banks: it checks each treasury account has one and lists them.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/plan_comptable.py` | `numeros_des_comptes_de_tresorerie()` : moyens (`MappingMoyenDePaiement`), monnaies (`MappingMonnaie`), 419100 |
| `api_v2/views.py` | `AccountViewSet.list` passe ces numéros au sérialiseur |
| `api_v2/serializers.py` | `CompteComptableSerializer.treasury` |
| `tests/pytest/test_api_v2_comptabilite.py` | `treasury` dans le test du plan ; nouveau test des comptes de trésorerie |

---

## Comment tester (a la main) / Manual test
### Test 1 — le champ `treasury`
1. `curl -H "Authorization: Api-Key <clé comptable>" https://<lieu>/api/v2/accounts/`
2. Attendu : `530000`, `512100`, `517100`, `419100` (et le compte de chaque monnaie) à
   `"treasury": true` ; `706000`, `707000` à `false`.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_api_v2_comptabilite.py -q`

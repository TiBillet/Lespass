# Crowds : financement global débranché / Crowds: global funding disconnected

**Date :** 2026-09-30
**Migration :** Non

## Résumé / Summary
**Quoi / What :** La route `global-funding`, `GlobalFundingViewset` (création, retour Stripe, total financé, répartition), le bouton « Je finance » et son formulaire sont retirés. Le modèle `GlobalFunding` et les champs `CrowdConfig.global_funding_button*` restent en base. /
The `global-funding` route, `GlobalFundingViewset`, the "Je finance" button and its form are removed. The `GlobalFunding` model and the `CrowdConfig.global_funding_button*` fields stay in the database.
**Pourquoi / Why :** Fonction jamais utilisée en production, et injoignable (la route détail d'`InitiativeViewSet` captait `global-funding/`). /
Never used in production, and unreachable (the detail route of `InitiativeViewSet` caught `global-funding/`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `crowds/urls.py` | Route `global-funding` retirée |
| `crowds/views.py` | `GlobalFundingViewset`, cache « total financé par l'utilisateur », aides du formulaire retirés |
| `crowds/serializers.py` | Deux serializers du financement global retirés |
| `crowds/templates/crowds/partial/summary.html` | Bouton, total personnel, scripts et blocs commentés de répartition retirés |
| `crowds/templates/crowds/partial/global_funding_amount.html` | Supprimé |
| `crowds/README.md` | Note « débranché » |
| `tests/pytest/test_crowds_financement_global_debranche.py` | Nouveau |
| `tests/e2e/test_crowds_summary.py` | Ne vérifie plus le bouton (vérifie son absence) |

---

## Comment tester (à la main) / Manual test
1. Ouvrir `/crowd/` : le résumé ne montre ni bouton « Je finance » ni « J'ai financé X », même avec `global_funding_button` actif.
2. `GET /crowd/global-funding/` répond 404/405 (plus de route dédiée).
3. Contribuer à une initiative (page détail) : inchangé.
4. `manage.py makemigrations --check --dry-run` : aucune migration.

Traductions : des chaînes ne sont plus utilisées (aucune ajoutée) ; nettoyage au prochain workflow i18n.

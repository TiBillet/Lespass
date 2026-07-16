# Seed : la démo faire_festival (chantefrein) est branchée au flush / Seed: the faire_festival demo (chantefrein) is now wired into the flush

**Date :** 2026-07-03
**Migration :** Non / No

**Quoi / What :** La commande `charger_demo_faire_festival` (vitrine brutaliste sur
le tenant chantefrein + skin forcé à faire_festival) existait mais n'était appelée
par personne : après un flush, tous les tenants restaient en skin reunion.
`demo_data_v2` l'appelle désormais en fin de seed (`_seed_site_pages_chantefrein()`,
même pattern try/except non bloquant que `_seed_site_pages_lespass()`).
**Pourquoi / Why :** chaque flush produit maintenant les DEUX skins de démo —
indispensable pour comparer les peaux pendant la migration skins.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/demo_data_v2.py` | + `_seed_site_pages_chantefrein()` appelé après le seed lespass |

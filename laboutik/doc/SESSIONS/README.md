# Sessions de travail — Prompts pour agent Claude Code

> Chaque fichier .md est un **prompt autonome** à donner à un agent Claude Code.
> L'agent lit le fichier, code, et vérifie. Pas besoin de lire PLAN_LABOUTIK.md.
>
> **Ordre strict** : chaque session dépend de la précédente.
> Ne pas lancer la session N+1 si la session N n'est pas validée (tests verts).

## Ordre des sessions

| # | Fichier | Phase | Prérequis | Statut |
|---|---------|-------|-----------|--------|
| 01 | `01_refactoring_securite_a11y.md` | ① Refactoring | — | ✅ FAIT |
| 02 | `02_refactoring_extraction_css.md` | ① Refactoring | 01 | ✅ FAIT |
| 03 | `03_refactoring_footer_cotton.md` | ① Refactoring | 02 | ❌ À FAIRE |
| 04 | `04_billetterie_refonte_typage.md` | ② Billetterie | 03 | ✅ FAIT (session 04 + types PV restaurés en session 06) |
| 05 | `05_billetterie_flow_identification_unifie.md` | ② Billetterie | 04 | ✅ FAIT |
| 06 | `06_billetterie_tuiles_et_donnees.md` | ② Billetterie | 05 | ✅ FAIT |
| 07 | `07_billetterie_paiement_et_tests.md` | ② Billetterie | 06 | ✅ FAIT |
| 08 | `08_websocket_infrastructure.md` | ③ WebSocket | 07 | ✅ FAIT |
| 09 | `09_websocket_broadcast_jauge.md` | ③ WebSocket | 08 | ✅ FAIT |
| 10 | `10_impression_modeles_et_interface.md` | ④ Impression | 09 | ✅ FAIT |
| 11 | `11_impression_backends_et_celery.md` | ④ Impression | 10 | ✅ FAIT |
| 12a | `12_bouton_impression_retour_vente.md` | ④ Impression | 11 | ✅ FAIT |
| 12b | `12_rapports_comptables_service.md` | ⑤ Rapports | 12a | ❌ À FAIRE |
| 13 | `13_rapports_comptables_admin_exports.md` | ⑤ Rapports | 12b | ❌ À FAIRE |
| 14 | `14_menu_ventes_ticket_x_liste.md` | ⑥ Menu Ventes | 13 | ❌ À FAIRE |
| 15 | `15_menu_ventes_corrections_fond_sortie.md` | ⑥ Menu Ventes | 14 | ❌ À FAIRE |

> **Note** : les anciens tests Playwright (`tests/playwright/`) ont été migrés vers pytest
> (`tests/pytest/` + `tests/e2e/`). Les commandes de vérification dans les fiches
> utilisent les nouveaux chemins (mise à jour 2026-03-21).

## Comment utiliser

Donner le contenu du fichier .md comme prompt à un agent Claude Code.
L'agent doit :
1. Lire les fichiers source indiqués dans "CONTEXTE"
2. Implémenter les tâches dans l'ordre
3. Lancer les commandes de vérification
4. Ne pas passer à la tâche suivante si un test échoue

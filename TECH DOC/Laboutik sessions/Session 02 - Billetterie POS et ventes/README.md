# Sessions de travail — Prompts pour agent Claude Code

> Chaque fichier .md est un **prompt autonome** a donner a un agent Claude Code.
> L'agent lit le fichier, code, et verifie. Pas besoin de lire PLAN_LABOUTIK.md.
>
> **Ordre strict** : chaque session depend de la precedente (sauf exceptions notees).
> Ne pas lancer la session N+1 si la session N n'est pas validee (tests verts).

## Sessions terminees

| # | Fichier | Phase | Statut |
|---|---------|-------|--------|
| 01 | `01_refactoring_securite_a11y.md` | Refactoring | FAIT |
| 02 | `02_refactoring_extraction_css.md` | Refactoring | FAIT |
| 03 | `03_refactoring_footer_cotton.md` | Refactoring | FAIT |
| 04 | `04_billetterie_refonte_typage.md` | Billetterie | FAIT |
| 05 | `05_billetterie_flow_identification_unifie.md` | Billetterie | FAIT |
| 06 | `06_billetterie_tuiles_et_donnees.md` | Billetterie | FAIT |
| 07 | `07_billetterie_paiement_et_tests.md` | Billetterie | FAIT |
| 08 | `08_websocket_infrastructure.md` | WebSocket | FAIT |
| 09 | `09_websocket_broadcast_jauge.md` | WebSocket | FAIT |
| 10 | `10_impression_modeles_et_interface.md` | Impression | FAIT |
| 11 | `11_impression_backends_et_celery.md` | Impression | FAIT |

## Sessions a faire — Conformite LNE + Rapports + Menu Ventes

> **Design spec** : `specs/2026-03-30-conformite-lne-caisse-design.md`
> **Referentiel LNE v1.7** : `~/Nextcloud/TiBillet/10.Certification LNE/`

| # | Fichier | Exigences LNE | Depend de | Statut |
|---|---------|---------------|-----------|--------|
| 12 | `12_rapports_comptables_service.md` | Ex.3, Ex.8 | — | FAIT |
| 13 | `13_clotures_3_niveaux_total_perpetuel.md` | Ex.6, Ex.7 | 12 | FAIT |
| 14 | `14_mentions_legales_tracabilite_impressions.md` | Ex.3, Ex.9 | 12 | FAIT |
| 15 | `15_mode_ecole_exports_admin.md` | Ex.5 | 13, 14 | FAIT |
| 16 | `16_menu_ventes_ticket_x_liste.md` | — | 12 | FAIT |
| 17 | `17_corrections_fond_sortie_caisse.md` | Ex.4 | 13, 16 | FAIT |
| 18 | `18_archivage_fiscal_acces_administration.md` | Ex.10-12, 15, 19 | 13 | FAIT |
| 19 | `19_envoi_auto_version.md` | Ex.21 | 15, 18 | FAIT |
| 20 | `20_export_comptable_mapping_fec.md` | — | 18 | FAIT |
| 21 | `21_export_comptable_profils_csv.md` | — | 20 | A FAIRE |

## Ordre des sessions (dependances)

```
12 ──→ 13 ──→ 15 ──→ 19
                      ↓
18 ──→ 20 ──→ 21
 │      │      ↑
 │      ├──→ 17 (corrections)
 │      └──→ 18 (archivage fiscal)
 ├──→ 14 ──→ 15
 └──→ 16 ──→ 17
```

La session 12 est le prerequis de tout. Les sessions 13, 14 et 16 peuvent etre
lancees en parallele apres 12. La session 15 necessite 13 et 14. Etc.

## Comment utiliser

Donner le contenu du fichier .md comme prompt a un agent Claude Code.
L'agent doit :
1. Lire les fichiers source indiques dans "CONTEXTE"
2. Lire le design spec (`specs/2026-03-30-conformite-lne-caisse-design.md`)
3. Implementer les taches dans l'ordre
4. Lancer les commandes de verification
5. Ne pas passer a la tache suivante si un test echoue

## Pense-bete futur

`99_pense_bete_futur.md` : idees pour plus tard (multi-tarif modal, supervisor, Traefik wildcard).

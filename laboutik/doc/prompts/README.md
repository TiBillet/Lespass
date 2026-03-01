# Prompts Claude Code — Plan d'integration mono-repo v2

Chaque fichier = 1 prompt a copier-coller en debut de session Claude Code.
Un fichier = une etape = une session (ou demi-session).

## Comment utiliser

1. Ouvrir le fichier de l'etape en cours
2. Copier-coller le contenu comme premier message dans Claude Code
3. Laisser Claude lire le plan et confirmer sa comprehension AVANT de coder
4. Valider chaque etape avant de passer a la suivante

## Modele recommande par phase

| Phase | Modele | Raison |
|-------|--------|--------|
| Phase -1 | **Sonnet** | Django admin/templates, bien cadre |
| Phase 0, etapes 1-2 | **Opus** | Modeles critiques, atomicite, securite |
| Phase 0, etape 3 | **Sonnet** | Admin + tests, pattern repetitif |
| Phase 1 | **Sonnet** | Product unifie + modeles POS, admin |
| Phase 2 | **Sonnet** | Remplacement mocks, vues FALC |
| Phase 3, etapes 1-2 | **Opus** | Paiement atomique, integration fedow_core |
| Phase 3, etape 3 | **Sonnet** | Stress test (code de test) |
| Phase 4 | **Sonnet** | Commandes/tables, vues FALC |
| Phase 5 | **Sonnet** | Cloture/rapports |
| Phase 6 | **Opus** | Migration donnees, zero perte |
| Phase 7 | **Sonnet** | Nettoyage, consolidation |

## Ordre des fichiers

```
Phase -1 — Dashboard Groupware
  phase-1_etape1_modeles_configuration.md
  phase-1_etape2_dashboard_callback.md
  phase-1_etape3_sidebar_conditionnelle.md

Phase 0 — fedow_core : fondations
  phase0_etape1_modeles_fedow_core.md
  phase0_etape2_services_wallet.md
  phase0_etape3_admin_tests_securite.md

Phase 1 — Product unifie + modeles POS (decision 16.9)
  phase1_etape1_modeles_pos.md       ← BaseBillet + laboutik models
  phase1_etape2_admin_fixtures.md    ← Admin Unfold + donnees test

Phase 2 — Remplacement des mocks
  phase2_etape1_caisse_depuis_db.md
  phase2_etape2_paiement_especes_cb.md

Phase 3 — Integration fedow_core
  phase3_etape1_paiement_nfc.md
  phase3_etape2_retour_carte_recharges.md
  phase3_etape3_stress_test.md

Phase 4 — Mode restaurant
  phase4_commandes_tables.md

Phase 5 — Cloture et rapports
  phase5_cloture_rapports.md

Phase 6 — Migration des donnees
  phase6_migration.md

Phase 7 — Consolidation
  phase7_consolidation.md
```

## Regles rappel

- **1 phase = 1-2 sessions max.** Ne jamais enchainer 2 phases.
- **Regle des 3 fichiers** : max 3 fichiers modifies avant check + tests.
- **Valider avec le mainteneur** entre chaque phase.
- **Ne jamais faire de git.** Le mainteneur s'en occupe.
- **Contexte etendu** (1M tokens) : recommande pour Phase 0 et Phase 6.
  Lancer avec `claude --model opus[1m]` (ou `sonnet[1m]` selon la phase).
  En cours de session : `/model opus[1m]`

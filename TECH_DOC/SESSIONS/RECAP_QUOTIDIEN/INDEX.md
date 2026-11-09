# RECAP_QUOTIDIEN — Hub du chantier

> **Objet :** chaque matin, un mail par lieu aux admins : tout ce qui s'est passé la veille
> (adhésions, réservations, ressources, événements, bénévoles, financement participatif,
> remboursements, annulations), avec le ou les tickets Z en pièce jointe. Aucun mail sans contenu.
> Remplace le mail séparé du Z journalier.

**Statut :** spec validée (2026-10-18), relue par Fable. Plan écrit et relu par Fable. **Code : tâches 1 à 8 faites et relues, relecture finale (Fable) faite** (2026-10-18). Essai réel du flush fait (mail reçu), suites pytest et E2E vertes (2026-10-18/19). Reste : le workflow i18n. Fiche : [`CHANGELOG/2026-10-18-recap-quotidien-admins.md`](../../../CHANGELOG/2026-10-18-recap-quotidien-admins.md).

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [SPEC.md](SPEC.md) | Le récap : contenu, fenêtre, heure, destinataires, fusion avec le Z, tests | Validée, relue (Fable) |
| [PLAN.md](PLAN.md) | Le plan d'implémentation : 8 tâches en TDD (la 8 : démo du flush) | Écrit, relu (Fable), corrigé |
| [CHANTIER-02-recap-allege.md](CHANTIER-02-recap-allege.md) | Chantier 02 : récap plus court (tout est né la veille, ruptures de stock, crowds et annulations/remboursements regroupés, 5 lignes, plus de boutons) + compteurs dans les mails Z H/M | Spec relue deux fois (Fable). **§2, §3 et §5 codés** (2026-10-22, non commités, migrations appliquées en dev, 708 tests verts) — fiche [`CHANGELOG/2026-10-22-recap-allege.md`](../../../CHANGELOG/2026-10-22-recap-allege.md) |
| [SUIVI/](SUIVI/) | Journal de l'exécution : registre (`progress.md`), consignes et rapports de chaque agent (`task-N-brief.md`, `task-N-report.md`), constats des relectures, diagnostic de l'incident mémoire (`diag-memoire-cancel-sub.md`), aperçu du mail (`apercu-recap.html` / `.pdf`) | Archive |

## État d'avancement

- [x] Inventaire de l'existant (lecture seule)
- [x] Spec + décisions du mainteneur + relecture Fable
- [x] Plan
- [x] Relecture Fable du plan (5 erreurs factuelles et 8 améliorations intégrées)
- [x] Code tâches 1 à 7 (un agent par tâche, relu avant la suivante)
- [x] Tâche 8 : démo du flush (activité d'hier de 4 personnes + récap envoyé à l'admin)
- [x] Relecture finale de tout le chantier (Fable) et passe de corrections
- [x] Essai réel : `flush.sh`, puis lecture du mail dans la boîte de dev (mail reçu)
- [x] Suites complètes : pytest, booking, E2E (dont Stripe) vertes
- [ ] Workflow i18n — **au mainteneur**

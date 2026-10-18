# RECAP_QUOTIDIEN — Hub du chantier

> **Objet :** chaque matin, un mail par lieu aux admins : tout ce qui s'est passé la veille
> (adhésions, réservations, ressources, événements, bénévoles, financement participatif,
> remboursements, annulations), avec le ou les tickets Z en pièce jointe. Aucun mail sans contenu.
> Remplace le mail séparé du Z journalier.

**Statut :** spec validée (2026-10-18), relue par Fable. Plan écrit et relu par Fable. **Code : tâches 1 à 8 faites et relues, relecture finale (Fable) faite** (2026-10-18). Reste : l'essai réel du flush (accord du mainteneur) et le workflow i18n. Fiche : [`CHANGELOG/2026-10-18-recap-quotidien-admins.md`](../../../CHANGELOG/2026-10-18-recap-quotidien-admins.md).

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [SPEC.md](SPEC.md) | Le récap : contenu, fenêtre, heure, destinataires, fusion avec le Z, tests | Validée, relue (Fable) |
| [PLAN.md](PLAN.md) | Le plan d'implémentation : 8 tâches en TDD (la 8 : démo du flush) | Écrit, relu (Fable), corrigé |

## État d'avancement

- [x] Inventaire de l'existant (lecture seule)
- [x] Spec + décisions du mainteneur + relecture Fable
- [x] Plan
- [x] Relecture Fable du plan (5 erreurs factuelles et 8 améliorations intégrées)
- [x] Code tâches 1 à 7 (un agent par tâche, relu avant la suivante)
- [x] Tâche 8 : démo du flush (activité d'hier de 4 personnes + récap envoyé à l'admin)
- [x] Relecture finale de tout le chantier (Fable) et passe de corrections
- [ ] Essai réel : `flush.sh`, puis lecture du mail dans la boîte de dev — **avec l'accord du mainteneur**
- [ ] Workflow i18n — **au mainteneur**

# EVENT_WIZARD — Hub permanent

**Date d'ouverture :** 2026-05-19

Ce hub regroupe tous les chantiers liés aux **wizards de création / proposition d'évènement** sur la page `event/list` de BaseBillet.

Périmètre fonctionnel :
- Remplacer l'offcanvas admin actuel par un wizard multi-étapes avec carte interactive pour la création d'adresse.
- Ajouter un wizard public (anonyme) protégé par OTP email permettant à tout visiteur de proposer un évènement, soumis à modération admin.
- Mettre en place un service OTP réutilisable (DRY) qui servira aussi au futur login OTP.

## Suivi des chantiers

| # | Chantier | Statut | Spec | Plan |
|---|---|---|---|---|
| 01 | Wizards admin + public + service OTP DRY (MVP) | ✅ Implémenté (2026-05-19) | [SPEC.md](SPEC.md) | [PLAN.md](PLAN.md) |
| 02 | Login classique, choix de lieu en 2 pages, multi-événements, routage DRF, plafond adresses, toggle mobile | ✅ Implémenté (2026-05-21) — tests pytch différés | [CHANTIER-02-login-place-split-multi-events.md](CHANTIER-02-login-place-split-multi-events.md) | — |

> ⚠️ Le chantier 02 fait évoluer le MVP : **l'OTP du wizard public est mis de côté**
> (code conservé) au profit de la connexion classique ; le choix de lieu passe à
> 2 pages ; on peut proposer **plusieurs** événements. Voir CHANTIER-02 pour le détail.

## Comment ajouter un chantier futur

1. Créer `CHANTIER-NN-<slug>.md` à la racine du hub (slug kebab-case, ex: `CHANTIER-02-event-templates-emails.md`).
2. Ajouter une ligne dans le tableau ci-dessus.
3. Si le chantier est non trivial, dérouler un plan d'implémentation via le skill `writing-plans` (fichiers `PLAN-SX-*.md`).

## Hub lié

- [OTP](../OTP/INDEX.md) — service OTP DRY consommé par le chantier 01 (wizard public). La spec OTP détaillée vit dans ce hub dédié pour faciliter ses futurs branchements (login, SSO, migration onboard).

## Liens utiles

- App référence pour le pattern wizard : `onboard/` (6 étapes avec WaitingConfiguration)
- Widget carte adresse réutilisable : `templates/widgets/widget_carte_adresse.html`
- Mécanisme badge sidebar Unfold (référence) : `Administration/admin/dashboard.py:adhesion_badge_callback`
- Conventions de code : `GUIDELINES.md` (FALC) + skill `djc`

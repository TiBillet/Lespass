# OBSERVATOIRE — Hub documentaire

> Hub permanent de l'observatoire des instances : une page de l'admin, réservée
> au superadmin, qui montre l'activité de chaque lieu du réseau mois par mois.
> Le code vit dans l'app `seo/` (`seo/observatoire.py`, `seo/views_observatoire.py`).
>
> Convention : 1 chantier = 1 fichier `.md`. `SPEC.md` est le chantier 01.

## Chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Observatoire des instances : calcul nocturne depuis les clôtures, page admin superadmin | 🟢 Implémenté, non commité (2026-11-12) | [`SPEC.md`](SPEC.md) |
| 02 | Historique des métriques dans le temps | 📋 À faire plus tard | [`CHANTIER-02-historique-des-metriques.md`](CHANTIER-02-historique-des-metriques.md) |
| 03 | Anonymiser les dumps de prod (Lespass, Fedow, LaBoutik V1) : e-mails et clés API | 🟢 Implémenté, non commité (2026-11-12) | [`CHANTIER-03-anonymisation-des-dumps.md`](CHANTIER-03-anonymisation-des-dumps.md) |
| 04 | Mesurer l'usage, pas seulement l'argent : billets gratuits, usages multiples, activité par régularité, rythme sur le volume, ventes Fedow legacy par lieu | 🟢 Implémenté, non commité (2026-11-13) | [`CHANTIER-04-usages-hors-argent.md`](CHANTIER-04-usages-hors-argent.md) |

## Dépendances

- Données de dev : `../COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md`. Sans
  ventes réelles et clôtures M en dev, la page est presque vide.

## Ajouter un chantier

Créer `CHANTIER-NN-<slug>.md` dans ce dossier et ajouter sa ligne au tableau.

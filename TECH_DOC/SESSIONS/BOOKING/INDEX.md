# BOOKING — hub des chantiers de l'app `booking` (réservation de ressources)

Point d'entrée pour tout agent qui travaille sur la réservation de ressources
(salles, matériel, créneaux). Le planning des bénévoles vit aussi dans `booking/`,
mais il a sa propre documentation (voir `booking/doc/` et le code de `booking/benevolat.py`).

Documentation historique, antérieure à ce hub : `booking/doc/` (spec v0.1, plan de
paiement, cas de test, présentation).

## Chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Réservation à validation manuelle (demande → admin → paiement) | Fiche A faite (non commitée), B à faire | [SPEC.md](SPEC.md) |

## Ajouter un chantier

1. Créer `CHANTIER-NN-<slug>.md` dans ce dossier (slug court en kebab-case).
2. Ajouter une ligne au tableau ci-dessus.
3. Le CHANGELOG du chantier va dans `CHANGELOG/AAAA-MM-JJ-<slug>.md`, comme d'habitude.

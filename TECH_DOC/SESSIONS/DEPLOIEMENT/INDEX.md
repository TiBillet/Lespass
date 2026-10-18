# DEPLOIEMENT — mise en production de Lespass

Hub des chantiers sur la façon dont le code arrive en production : image Docker, release,
mise à jour sans coupure, grosse mise à jour planifiée.

Constats d'origine (premier déploiement après la bascule, 2026-10-12) :
`TECH_DOC/SESSIONS/TODO/DEPLOIEMENT-mise-a-jour-sans-coupure.md`.

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | `make update` : image par release, migration dans un conteneur jetable, workers gunicorn remplacés un par un | Spec à valider | [SPEC.md](SPEC.md) |
| 02 | gunicorn 26 et `gunicornc` à la place de la lecture du log | Idée | — |

Ajouter un chantier : une ligne ici, et un fichier `CHANTIER-NN-<slug>.md`.

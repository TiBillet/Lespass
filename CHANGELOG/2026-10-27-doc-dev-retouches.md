# Doc de mise en place : retouches / Dev setup docs: touch-ups

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** suite de la PR #484 (doc de mise en place). Avertissement `DEFAULT_FROM_EMAIL=""` remis dans `env_example`, liens `tibillet.org` -> `tibillet.coop` dans le README anglais, commentaire perime (`--full`) corrige dans `flush.sh`. / Follow-up to PR #484: `DEFAULT_FROM_EMAIL=""` warning restored, `tibillet.org` -> `tibillet.coop` links in the English README, stale `--full` comment fixed in `flush.sh`.
**Pourquoi / Why :** une `DEFAULT_FROM_EMAIL` vide bloque tous les e-mails ; le site est desormais `tibillet.coop` ; l'option `--full` de `demo_data_v2` n'existe plus. / An empty `DEFAULT_FROM_EMAIL` blocks every e-mail; the site is now `tibillet.coop`; `demo_data_v2 --full` no longer exists.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `env_example` | Avertissement : ne jamais laisser `DEFAULT_FROM_EMAIL` vide |
| `README.en.md` | 4 liens `tibillet.org` -> `tibillet.coop` (aligne sur le README FR) |
| `flush.sh` | Commentaire de `demo_data_v2` : 5 lieux par defaut, `--quick` pour le dump |

---

## Comment tester (a la main) / Manual test
Documentation et commentaires uniquement : relire le diff. Aucun comportement ne change.

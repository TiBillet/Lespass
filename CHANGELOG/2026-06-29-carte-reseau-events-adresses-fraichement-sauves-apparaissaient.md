# Carte réseau : events/adresses fraîchement sauvés n'apparaissaient pas / Network map: freshly saved events & addresses didn't show up

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Sur la carte ROOT (`/explorer/`), un nouvel évènement ou une
nouvelle adresse pouvait rester invisible jusqu'au prochain passage du beat
Celery (jusqu'à 4 h), alors que le tenant venait de sauvegarder.

**Pourquoi / Why :** Le rebuild de l'agrégat `AGGREGATE_POINTS` (lu par la carte)
était déclenché en **débounce « front montant »** : la tâche était planifiée à
`T_première_modif + 180 s`. Si une modif arrivait tard dans cette fenêtre, son
fragment `TENANT_POINTS` (countdown plus court) pouvait être recombiné **trop
tôt** — le rebuild figeait un agrégat à partir d'un fragment pas encore à jour —
et **aucun rebuild de rattrapage** n'était garanti. Seul le beat 4 h corrigeait.
Aggravé par une « fenêtre morte » du débounce fragment (countdown 30 s < TTL
verrou 60 s).

**Fix / Fix :** Passage à un **débounce « front descendant » (trailing)**. Chaque
`post_save`/`post_delete` Event/PostalAddress repousse une échéance
(`seo_rebuild_echeance = now + 15 s`) et planifie au plus une tâche rebuild par
fenêtre. À son réveil, `rebuild_seo_aggregates` recombine **seulement si**
l'échéance est atteinte ; sinon il se **replanifie** pile à l'échéance. Garantie :
un rebuild s'exécute **toujours après la dernière modif**, sur des fragments à
jour. Le beat 4 h appelle `rebuild_seo_aggregates(force=True)` (recombine
toujours, filet anti-dérive). Countdown du fragment réduit à 5 s et TTL du verrou
aligné (fin de la fenêtre morte). Latence perçue : ~20 s au lieu de 3 min → 4 h.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/tasks.py` | `planifier_rebuild_agregats()` (débounce trailing) ; garde + `force` dans `rebuild_seo_aggregates` ; beat en `force=True` ; constantes `REBUILD_TRAILING_WINDOW`/`REBUILD_MARGE` |
| `BaseBillet/signals.py` | `declencher_refresh_seo_cache` : fragment countdown 5 s (TTL aligné) ; rebuild via `planifier_rebuild_agregats()` (remplace le front montant 180 s) |
| `tests/pytest/test_seo_cache_fragments.py` | +4 tests : abstention/replanification, recombinaison à l'échéance, `force=True`, débounce du helper |

### Migration
- **Migration nécessaire / Migration required :** Non / No (logique Celery + cache uniquement).

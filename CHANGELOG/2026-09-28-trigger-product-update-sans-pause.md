# Tâche « produit modifié » sans pause fixe / Product-update task without fixed sleep

**Date :** 2026-09-28
**Migration :** Non

## Resume / Summary

**Quoi / What :** `BaseBillet.tasks.trigger_product_update_tasks` (prévenir LaBoutik V1
qu'une adhésion a changé) vérifie d'abord, sans réseau, que LaBoutik V1 est configuré
(adresse + clé) et sort tout de suite sinon. Le produit est ensuite cherché par une boucle
courte (10 essais, 0,1 s entre deux) au lieu d'un `time.sleep(1)` systématique. Viennent
ensuite le test « adhésion ? » puis le ping réseau `check_serveur_cashless()`. /
The task first checks, without network, that LaBoutik V1 is configured and exits
otherwise; the product is then looked up by a short retry loop instead of a fixed 1 s sleep.

**Pourquoi / Why :** la tâche part au `post_save` de **chaque** produit et occupait un
processus Celery 1 seconde, même sans LaBoutik V1 et pour un produit qui n'est pas une
adhésion. Les tests pytest (qui envoient leurs tâches dans la vraie file de dev) en ont
empilé ~28 000 : la file bouchée a retardé les tâches de récompense Fedow et fait échouer
4 E2E. / The task ran for every product save and held a worker 1 s; tests piled up
~28,000 of them, delaying Fedow reward tasks (4 E2E failures).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | `trigger_product_update_tasks` : configuration d'abord, boucle courte, adhésion, puis ping |
| `tests/pytest/test_trigger_product_update.py` | nouveau : 5 tests sans base (config, produit, pause et réseau simulés) |

Avant correctif : 5 tests rouges. Mutations (5, toutes détectées) : pause d'1 s remise,
contrôle de configuration retiré, un seul essai, boucle trop longue, ping avant le test
d'adhésion.

---

## Comment tester (a la main) / Manual test

1. **Redémarrer le worker Celery** (il ne recharge pas le code seul) :
   `docker restart lespass_celery`.
2. Sans LaBoutik V1 configuré : `docker logs -f lespass_celery` pendant un
   `make test ARGS="tests/pytest/test_vente_en_points.py"` → les
   `trigger_product_update_tasks` réussissent en quelques millisecondes (plus 1 s).
3. File Celery : `docker exec lespass_redis redis-cli LLEN celery` se vide vite.

### Suite : le signal n'envoie la tâche que pour une adhésion, à la validation

`BaseBillet/signals.py` `trigger_product_update` : un produit qui n'est pas une adhésion
n'envoie plus de tâche ; pour une adhésion, la tâche part au `transaction.on_commit`
(le produit est en base quand LaBoutik V1 le réclame ; un `save()` annulé — tests, erreur
dans l'admin — n'envoie rien). 2 tests ajoutés à `tests/pytest/test_trigger_product_update.py`
(sans base : receveur appelé sur un produit simulé), vus rouges ; 2 mutations détectées
(envoi pour tous les produits, envoi immédiat). `make test` 2082 passed, file Celery vide
après la suite complète.

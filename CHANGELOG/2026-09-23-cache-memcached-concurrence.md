# Cache memcached : réponses mélangées sous requêtes simultanées (ASGI)

## A. Connexions memcached gardées ouvertes et en pool / Pooled, persistent memcached connections

**Quoi / What :** sous un serveur ASGI (runserver de dev, daphne), des requêtes simultanées pouvaient recevoir la **valeur d'une autre clé de cache**, ou planter.

Erreurs vues dans `runserver.log` :
- `'Configuration' object is not subscriptable` ;
- `KeyError: b'lespass::1:meta_url'` ;
- `OSError: [Errno 9] Bad file descriptor` ;
- `AssertionError` dans pymemcache ;
- `KeyError: ('memcached', 11211)` dans `close`.

Symptôme visible : l'aperçu admin des pages prenait **parfois le mauvais skin**. `get_skin_courant()` avalait l'erreur et retombait sur « reunion », donc sur le style classic. Des erreurs 500 apparaissaient aussi, et le serveur de dev pouvait même se figer.

**Pourquoi / Why :** deux causes s'ajoutent.
1. **Une socket pour tous les threads.** Sans `use_pooling`, pymemcache partage une seule socket entre tous les threads du processus.
2. **Fermeture à chaque requête.** À la fin de chaque requête, Django appelle `close()` sur le cache. `PyMemcacheCache.close()` fait `disconnect_all()`. Sous ASGI, les requêtes simultanées partagent l'instance de cache : une requête qui se termine ferme les sockets que les autres utilisent. Le pool seul ne suffit donc pas.

**Correction :**
- `TiBillet/cache_memcached.py` : `PyMemcacheCacheSansFermeture`, un `PyMemcacheCache` dont `close()` ne fait rien. Les connexions vivent autant que le processus, et pymemcache se reconnecte seul.
- `CACHES["default"]` : ce backend, plus `OPTIONS = {"use_pooling": True}`. Avec ce pool, chaque opération de cache emprunte une connexion libre et la rend ensuite. Le pool n'a pas de taille maximale : il grandit selon le nombre d'opérations simultanées.
- `get_skin_courant()` : l'erreur est désormais **journalisée** (`logger.warning`), sauf sur le schéma public où le repli est normal. Avant, le site changeait de skin sans aucune trace.

**Mesure (serveur de dev neuf, skin V2, 30 requêtes dont 10 simultanées) :**

| | Avant | Après |
|---|---|---|
| Aperçu en direct | 27 V2, 1 **classic**, 2 erreurs 500 | 30 V2 (2 séries) |
| Aperçu de page | 22 V2, 7 erreurs 500, 1 erreur 504 | 30 V2 (2 séries) |
| Erreurs memcached dans le journal | des dizaines | 0 |

**Production :** gunicorn tourne en workers synchrones à un thread (`-w 18`) : les pages HTTP n'étaient pas exposées. daphne (websockets) l'était, puisqu'il exécute le code synchrone dans des threads. Le changement est sans risque pour gunicorn : il y a une connexion persistante par worker au lieu d'une reconnexion à chaque requête.

## B. Délais d'attente et tolérance aux pannes (suite à l'audit) / Timeouts and failure tolerance

**Quoi / What :** les connexions vivent maintenant aussi longtemps que le processus. Sans délai d'attente (pymemcache met `timeout=None` par défaut), deux problèmes pouvaient survenir :
- une connexion coupée à moitié (memcached tué, coupure réseau) bloquait un worker jusqu'au timeout de gunicorn, 30 s ;
- après un redémarrage de memcached, la première opération de chaque worker levait une erreur, soit une 500 ou un mauvais skin.

**Correction :** dans `OPTIONS`, `connect_timeout: 1`, `timeout: 2` et `ignore_exc: True`. Une panne de memcached devient un simple « cache vide » : Django relit la base, la page reste juste un peu plus lente. pymemcache met ensuite le serveur de côté pendant 60 s (`dead_timeout`) s'il reste injoignable. Pendant ce temps, le cache ne sert plus, sans provoquer d'erreur.

**Attention :** avec `ignore_exc`, une panne de memcached ne se voit plus dans les erreurs. Elle se voit dans les temps de réponse. Surveiller memcached à part.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/cache_memcached.py` (nouveau) | `PyMemcacheCacheSansFermeture` |
| `TiBillet/settings.py` | `CACHES` : nouveau backend + `use_pooling` |
| `BaseBillet/views.py` | `get_skin_courant()` journalise l'erreur au lieu de la cacher |

### Tests à réaliser / How to test
1. **Redémarrer** le serveur de dev (le rechargement automatique ne suffit pas s'il est déjà figé).
2. Ouvrir la fiche d'une page qui a plusieurs blocs, et taper vite dans la fiche d'un bloc : l'aperçu garde toujours le bon skin.
3. `grep -E "Bad file descriptor|not subscriptable|get_skin_courant" runserver.log` : aucune nouvelle ligne.

### Migration
- **Migration necessaire / Migration required:** Non

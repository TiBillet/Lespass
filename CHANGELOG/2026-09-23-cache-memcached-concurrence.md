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
- `CACHES["default"]` : ce backend, plus `OPTIONS = {"use_pooling": True}`, soit une connexion par thread en cours.
- `get_skin_courant()` : l'erreur est désormais **journalisée** (`logger.warning`), sauf sur le schéma public où le repli est normal. Avant, le site changeait de skin sans aucune trace.

**Mesure (serveur de dev neuf, skin V2, 30 requêtes dont 10 simultanées) :**

| | Avant | Après |
|---|---|---|
| Aperçu en direct | 27 V2, 1 **classic**, 2 erreurs 500 | 30 V2 (2 séries) |
| Aperçu de page | 22 V2, 7 erreurs 500, 1 erreur 504 | 30 V2 (2 séries) |
| Erreurs memcached dans le journal | des dizaines | 0 |

**Production :** gunicorn tourne en workers synchrones à un thread (`-w 18`) : les pages HTTP n'étaient pas exposées. daphne (websockets) l'était, puisqu'il exécute le code synchrone dans des threads. Le changement est sans risque pour gunicorn : il y a une connexion persistante par worker au lieu d'une reconnexion à chaque requête.

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

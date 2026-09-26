"""
Backend de cache memcached qui garde ses connexions ouvertes.
/ Memcached cache backend that keeps its connections open.

LOCALISATION : TiBillet/cache_memcached.py
Utilise par CACHES["default"] dans TiBillet/settings.py.

LE PROBLEME : a la fin de CHAQUE requete, Django appelle `close()` sur le
cache (signal request_finished). Pour PyMemcacheCache, `close()` fait
`disconnect_all()` : toutes les sockets memcached sont fermees.
Sous ASGI (runserver de dev, daphne), des requetes simultanees partagent la
meme instance de cache. Une requete qui se termine ferme donc les sockets que
les autres sont en train d'utiliser. Resultat : « Bad file descriptor »,
reponses melangees (la valeur d'une autre cle), erreurs 500 — et, dans
l'apercu admin des pages, un skin qui retombait sur « reunion ».

LA SOLUTION : ne pas fermer. Les connexions restent ouvertes pour la vie du
processus (pymemcache se reconnecte seul si memcached redemarre), et
`use_pooling` (dans settings.py) donne une connexion par thread en cours.
C'est aussi plus rapide : plus de reconnexion a chaque requete.
/ Django closes the cache after EVERY request; under ASGI concurrent requests
share the cache instance, so one request closed the sockets others were
using. We never close: connections live for the process, pooled per thread.
"""

from django.core.cache.backends.memcached import PyMemcacheCache


class PyMemcacheCacheSansFermeture(PyMemcacheCache):
    def close(self, **kwargs):
        # Volontairement vide : voir la docstring du module.
        # / Intentionally empty: see the module docstring.
        pass

    def fermer_les_connexions_pour_de_vrai(self):
        """
        Ferme vraiment toutes les sockets memcached de ce processus.
        / Really closes every memcached socket of this process.

        Appelee UNIQUEMENT juste apres un fork (TiBillet/celery.py,
        signal worker_process_init). Celery lance ses processus enfants par
        fork : sans cette fermeture, un enfant heriterait des sockets ouvertes
        par le processus maitre, et plusieurs enfants partageraient la meme
        socket (reponses melangees). Django faisait ce travail via close(),
        que l'on a rendu vide ci-dessus.
        / Called ONLY right after a fork (Celery worker_process_init), so child
        processes never share the parent's sockets.
        """
        super().close()

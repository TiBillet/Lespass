"""
Configuration Gunicorn — prechauffage des workers avant leur premiere requete.
/ Gunicorn configuration — worker warmup before the first request.

LOCALISATION : gunicorn_conf.py (racine du projet, monte dans /DjangoFiles)

Reference par `supervisor/conf.d/gunicorn.conf` via `-c /DjangoFiles/gunicorn_conf.py`.
Les autres reglages (nombre de workers, bind, fichiers de log) restent sur la ligne
de commande : ce fichier ne porte QUE le prechauffage.

POURQUOI CE FICHIER EXISTE
--------------------------
Gunicorn fonctionne en pre-fork : chaque worker est un PROCESS Unix distinct, avec
sa propre memoire. Les caches de code de Django — le resolveur d'URLs et les
gabarits compiles — sont de simples dictionnaires Python : ils ne traversent pas la
frontiere entre deux process. Chaque worker doit donc les construire pour son propre
compte, et il le fait a sa PREMIERE requete, pas a son demarrage.

Mesure en production (2026-07-21), premier rendu dans un process neuf :

    URLconf + imports des vues   224,6 ms   <- l'essentiel
    40 gabarits                   62,8 ms
    premiere connexion memcached   6,3 ms
    catalogues gettext             0,1 ms

Le visiteur qui tombe sur un worker encore froid paie ces ~315 ms. Avec 18 workers
et un site peu frequente, presque chaque visite tombe sur un worker froid : les
pages sortaient entre 500 et 650 ms au lieu de 150 ms.

Ce hook paie ce cout au demarrage du worker, hors requete, une fois pour toutes.

CE QUI EST PRECHAUFFE, ET CE QUI NE L'EST PAS
---------------------------------------------
Uniquement du CODE, jamais des DONNEES. Le resolveur d'URLs est commun a tous les
lieux (django-tenants partage `ROOT_URLCONF` entre tous les schemas), donc ce
prechauffage coute la meme chose avec 3 lieux qu'avec 500. Rien ici n'est propre a
un tenant, et il ne faut RIEN y ajouter qui le soit : ce hook s'execute hors de
tout contexte de tenant, une requete par lieu n'aurait aucun sens et ne passerait
pas a l'echelle.

Les gabarits (62,8 ms) ne sont volontairement PAS prechauffes : ils pesent un
cinquieme du gain pour un code qu'il faudrait tenir a jour a chaque nouveau skin.
A reconsiderer si la mesure montre que le residuel le justifie.

/ Gunicorn is pre-fork: each worker is a separate process with its own memory, and
Django's code caches (URL resolver, compiled templates) are plain Python dicts that
cannot cross a process boundary. Each worker builds them on its FIRST request, so
whoever hits a cold worker pays ~315 ms. This hook pays it at worker startup
instead. It warms CODE only, never per-tenant DATA — the URL resolver is shared by
every tenant, so the cost is the same with 3 venues or 500.
"""

import time


def post_worker_init(worker):
    """
    Construit les caches de code du worker AVANT qu'il n'accepte sa premiere requete.
    / Builds the worker's code caches BEFORE it accepts its first request.

    LOCALISATION : gunicorn_conf.py

    Gunicorn appelle ce hook dans le worker, apres le fork et apres le chargement de
    l'application WSGI, mais avant sa boucle d'acceptation des connexions. Le cout
    est donc paye hors requete, et une connexion ouverte ici appartient a ce worker
    seul — c'est la raison pour laquelle le prechauffage vit ici et non avant le fork
    (avec `--preload`, les 18 workers heriteraient d'une meme socket PostgreSQL ou
    memcached, ce qui produit des corruptions difficiles a diagnostiquer).

    FLUX :
    1. Gunicorn forke le worker et charge l'application WSGI
    2. CETTE FONCTION peuple les deux resolveurs d'URLs
    3. Le worker commence a accepter des connexions

    /!\ CE HOOK PEUT METTRE TOUT LE SERVICE A TERRE — d'ou le rattrapage total
    plus bas. Gunicorn ne marque le worker « demarre » (`self.booted = True`)
    qu'APRES cet appel : une exception qui s'echappe d'ici fait sortir le worker
    en WORKER_BOOT_ERROR, que l'arbitre traduit en HaltServer. Le MASTER s'arrete
    alors, les 18 workers avec lui, et supervisord boucle jusqu'a FATAL — plus une
    seule reponse servie. C'est pour cela que le `except` ci-dessous attrape
    `BaseException` et non `Exception`, et que la journalisation elle-meme est
    protegee : le prechauffage est une optimisation, il ne doit JAMAIS pouvoir
    empecher le service de tourner.

    :param worker: l'objet Worker de gunicorn — sert aussi a journaliser via
        `worker.log`, le logger de gunicorn lui-meme
    """
    try:
        from django.conf import settings
        from django.db import connection
        from django.urls import get_resolver

        debut = time.perf_counter()

        # LES DEUX resolveurs. django-tenants en utilise un pour les lieux
        # (ROOT_URLCONF) et un autre pour le schema public (PUBLIC_SCHEMA_URLCONF) :
        # ce sont deux objets memoises separement. N'en chauffer qu'un laisserait
        # l'autre froid.
        # / BOTH resolvers: django-tenants uses one for tenants and one for the
        # public schema, memoized separately.
        urlconfs_a_chauffer = [
            settings.ROOT_URLCONF,
            getattr(settings, "PUBLIC_SCHEMA_URLCONF", None),
        ]

        nombre_chauffes = 0
        for nom_urlconf in urlconfs_a_chauffer:
            if not nom_urlconf:
                continue
            # `_populate()` importe le module d'URLs — donc toutes les vues et ce
            # qu'elles importent — puis construit le dictionnaire de resolution
            # inverse dont `{% url %}` et `reverse()` ont besoin. C'est CE travail
            # qui coute 225 ms, et Django ne le declenche qu'a la premiere requete.
            # /!\ API privee (underscore) : si une montee de version de Django la
            # supprime, le `except` plus bas journalise et le worker demarre quand
            # meme — on retombe simplement sur l'ancien comportement.
            # / `_populate()` imports the URLconf (hence every view) and builds the
            # reverse-resolution dict. Private API on purpose; failure is logged.
            get_resolver(nom_urlconf)._populate()
            nombre_chauffes += 1

        duree_ms = (time.perf_counter() - debut) * 1000

        # L'import des vues a pu ouvrir une connexion a la base. On la ferme : ce
        # worker n'a pas encore de requete en cours, et une connexion laissee
        # ouverte ici resterait inactive jusqu'a sa premiere visite.
        # / Importing views may have opened a DB connection. Close it: the worker
        # has no request in flight yet.
        connection.close()

        # `worker.log` est le logger de GUNICORN, pas celui de Django : il ecrit
        # dans le meme fichier, mais ne depend ni de `django.setup()` ni du
        # dictionnaire LOGGING du projet. Un logging.getLogger() ordinaire ne
        # remonterait ici que par la grace de `disable_existing_loggers: False` —
        # une condition qu'un reglage de settings.py pourrait retirer sans que
        # personne ne fasse le rapprochement.
        # / `worker.log` is GUNICORN's logger: same file, but independent from
        # django.setup() and from the project's LOGGING dict.
        worker.log.info(
            f"warmup worker {worker.pid} : {nombre_chauffes} URLconf en {duree_ms:.0f} ms"
        )

    except BaseException as erreur_de_prechauffage:
        # `BaseException` et NON `Exception` : voir l'avertissement de la docstring.
        # Tout ce qui s'echappe d'ici arrete le master et donc le service entier.
        # On rattrape donc aussi SystemExit et KeyboardInterrupt, qu'un import de
        # bibliotheque mal configuree peut lever.
        # / BaseException, NOT Exception: anything escaping here halts the master
        # and the whole service (see the docstring warning).
        try:
            worker.log.exception(
                f"warmup worker {getattr(worker, 'pid', '?')} echoue "
                f"({erreur_de_prechauffage}) — le worker demarre sans prechauffage, "
                f"sa premiere requete sera plus lente"
            )
        except BaseException:
            # Meme la journalisation de l'echec ne doit pas pouvoir tuer le service.
            # C'est le seul `pass` silencieux justifie de ce fichier : a ce stade,
            # continuer sans trace vaut mieux que tomber.
            # / Even logging the failure must not be able to kill the service.
            pass

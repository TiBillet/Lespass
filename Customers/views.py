import datetime

from django.db import connection
from django.utils import timezone

from BaseBillet.models import Configuration, logger


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        On a besoin de mettre les dates des évènts au fuseau horaire de l'organisation et non pas du serveur.

        Le fuseau du lieu doit etre pose cote SERVEUR, pas cote navigateur :
        beaucoup de sorties n'ont aucun navigateur (tickets ESC/POS de la
        caisse, exports comptables, emails, PDF), et le fuseau courant sert
        aussi a LIRE les dates saisies dans les formulaires, pas seulement a
        les afficher.
        / The venue timezone must be set SERVER-side: many outputs have no
        browser at all (printed receipts, accounting exports, emails), and the
        current timezone is also used to PARSE submitted dates, not just render.
        """
        # On resout le fuseau AVANT d'entrer dans le bloc `with`, et on ne
        # transmet a override() qu'un vrai objet tzinfo. Toute autre valeur
        # leverait dans override.__enter__, c'est-a-dire HORS de ce try :
        # chaque requete du tenant partirait alors en 500. Le controle de type
        # est donc ce qui garde l'erreur a l'interieur du filet.
        # / Resolve the timezone BEFORE the `with`, and only pass a real tzinfo
        # object to override(). Anything else would raise inside
        # override.__enter__, outside this try, turning every request of the
        # tenant into a 500. The type check keeps failures inside the net.
        fuseau_du_lieu = None
        try:
            tenant = connection.tenant
            if tenant.schema_name != "public":
                fuseau_candidat = Configuration.get_solo().get_tzinfo()
                if isinstance(fuseau_candidat, datetime.tzinfo):
                    fuseau_du_lieu = fuseau_candidat
                else:
                    # On repart sur le fuseau par defaut, mais en le disant :
                    # sans trace, les heures affichees seraient silencieusement
                    # celles du serveur et personne ne saurait pourquoi.
                    # / Fall back to the default timezone, but say so: without a
                    # trace, displayed times would silently be the server's.
                    logger.error(
                        f"Customers views TimezoneMiddleware : fuseau inexploitable "
                        f"pour le tenant {tenant.schema_name} "
                        f"(type {type(fuseau_candidat).__name__}), fuseau par defaut applique."
                    )
        except Exception as e:
            logger.error(f"Customers views TimezoneMiddleware erreur : {e}")

        # Le fuseau courant est un etat THREAD-LOCAL, et les threads sont
        # reutilises d'une requete a l'autre. `override` le pose pour la duree
        # de la requete puis restaure l'etat precedent, meme en cas
        # d'exception : ni la requete suivante ni une tache lancee ensuite
        # n'heritent du fuseau du dernier tenant servi. Un fuseau a None
        # signifie « fuseau par defaut ».
        # / The current timezone is THREAD-LOCAL state and threads are reused
        # across requests. `override` scopes it to the request and restores the
        # previous state, even on exception. None means "default timezone".
        with timezone.override(fuseau_du_lieu):
            return self.get_response(request)
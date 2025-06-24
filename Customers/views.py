import pytz
from django.db import connection
from django.utils import timezone

from BaseBillet.models import Configuration, logger


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        On a besoin de mettre les dates des évènts au fuseau horaire de l'organisation et non pas du serveur.
        """
        try :
            tenant = connection.tenant
            if not tenant.schema_name == "public":
                config = Configuration.get_solo()
                timezone.activate(pytz.timezone(config.fuseau_horaire)) #TODO: A mettre en cache (même si la requete postgres est super rapide : 0,001ms)
        except Exception as e:
            logger.error(f"Customers views TimezoneMiddleware erreur : {e}")
            pass

        return self.get_response(request)
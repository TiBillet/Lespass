import pytz
from django.db import connection
from django.utils import timezone

from BaseBillet.models import Configuration

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = connection.tenant
        if not tenant.schema_name == "public":
            config = Configuration.get_solo()
            timezone.activate(pytz.timezone(config.fuseau_horaire))
        return self.get_response(request)
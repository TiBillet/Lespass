from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, tenant_context
from rest_framework_api_key.models import APIKey

import logging

from BaseBillet.models import ExternalApiKey
from AuthBillet.utils import get_or_create_user

logger = logging.getLogger(__name__)



class Command(BaseCommand):
    """
    docker exec lespass_django poetry run python manage.py test_api_key
    """
    def handle(self, *args, **options):
        if not settings.TEST:
            raise Exception("This command should only be run in test mode.")

        TenantModel = get_tenant_model()
        tenant = TenantModel.objects.get(schema_name='lespass')
        with tenant_context(tenant):
            randuuid = str(uuid4())[:8]

            api_key, key = APIKey.objects.create_key(name=f"test_{randuuid}")
            while key[0].isupper() == False:
                api_key, key = APIKey.objects.create_key(name=f"test_{randuuid}")
                if key[0].isupper() == False:
                    api_key.delete()

            user = get_or_create_user(
                email=f"api-test-{randuuid}@example.org",
                set_active=True,
                send_mail=False,
            )
            if user:
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=["is_staff", "is_superuser"])

            ext_api_key = ExternalApiKey.objects.create(
                name=f"test_{randuuid}",
                user=user,
                event=True,
                product=True,
                reservation=True,
                ticket=True,
                wallet=True,
                sale=True,
                membership=True,
                crowd=True,
                key=api_key,
            )

        print(f"{key}")

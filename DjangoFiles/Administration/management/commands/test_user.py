from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from AuthBillet.models import TibilletUser
from Customers.models import Client
import logging

logger = logging.getLogger(__name__)



class Command(BaseCommand):
    def handle(self, *args, **options):
        User = get_user_model()
        root, created  = User.objects.get_or_create(email="root@root.root")
        logger.info(f"Root created: {created}")
        if created :
            root.set_password('root')
            root.is_staff = True
            root.is_superuser = True
            root.client_source = Client.objects.get(categorie=Client.ROOT)
            root.save()
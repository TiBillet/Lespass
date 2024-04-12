import os

from django.core.management.base import BaseCommand

import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from fedow_connect.models import FedowConfig
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        root_config = RootConfiguration.get_solo()
        if root_config.fedow_create_place_apikey:
            logger.info("fedow key in root configuration. No need to install")
            return True
        else :
            logger.info("Fedow handshake")
            with schema_context('public'):
                fedow_domain = os.environ['FEDOW_DOMAIN']
                root_config.root_fedow_handshake(fedow_domain)



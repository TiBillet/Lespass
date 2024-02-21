from django.core.management.base import BaseCommand

import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from fedow_connect.models import FedowConfig
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        with schema_context('public'):
            root_config = RootConfiguration.get_solo()
            root_config.root_fedow_handshake('fedow.tibillet.localhost')



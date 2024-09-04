import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from faker.utils.text import slugify

from BaseBillet.validators import TenantCreateValidator
from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):

        parser.add_argument('--name',
                            help='Tenant name')
        parser.add_argument('--email',
                            help='Admin email')

    def handle(self, *args, **options):
        with schema_context('meta'):
            waiting_config = WaitingConfiguration.objects.create(
                organisation=options['name'],
                slug=slugify(options['name']),
                email=options['email'],
                dns_choice='tibillet.coop',
            )
            TenantCreateValidator.create_tenant(waiting_config)
        logger.info('Tenant created: %s', waiting_config)
import logging, os

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
        parser.add_argument('--dns',
                        help='DNS')

    def handle(self, *args, **options):
        with schema_context('meta'):
            dns_choice = options['dns'] if options.get('dns') else os.environ.get('DOMAIN')
            waiting_config = WaitingConfiguration.objects.create(
                organisation=options['name'],
                slug=slugify(options['name']),
                email=options['email'],
                dns_choice=dns_choice,
            )
            TenantCreateValidator.create_tenant(waiting_config)
        logger.info('Tenant created: %s', waiting_config)

from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from BaseBillet.models import OptionGenerale, Configuration
from Customers.models import Client

#
# class Command(BaseCommand):
#     help = 'Help for command'
#
#     def add_arguments(self, parser):
#         parser.add_argument('schema_name', type=str)
#         parser.add_argument('server_cashless', type=str)
#         parser.add_argument('key_cashless', type=str)
#
#     def handle(self, *args, **options):
#         tenant = Client.objects.get(schema_name=options['schema_name'])
#         with tenant_context(tenant):
#             configuration = Configuration.get_solo()
#             configuration.server_cashless = options['server_cashless']
#             configuration.key_cashless = options['key_cashless']
#             configuration.save()
#
#             print(f"check_serveur_cashless() : {configuration.check_serveur_cashless()}")

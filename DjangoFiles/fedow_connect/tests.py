import os

from django.conf import settings
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection
from django.contrib.auth import get_user_model
from faker import Faker
from django.test import TestCase
from django_tenants.utils import get_tenant_model, tenant_context, schema_context, get_public_schema_name



class TenantSchemaTestCase(TestCase):
    def setUp(self):
        with schema_context('public'):
            # Création des tenant public et meta
            Customers = get_tenant_model()
            self.assertEqual(Customers.objects.count(), 0)
            call_command('create_public')
            self.assertEqual(get_public_schema_name(), 'public')
            self.assertEqual(Customers.objects.count(), 2)
            tenant_names = [t.schema_name for t in Customers.objects.all()]
            self.assertTrue('public' in tenant_names)
            self.assertTrue('meta' in tenant_names)

    def test_connect_place_to_fedow(self, schema_name=None):
        if schema_name is None:
            schema_name = 'meta'

        with schema_context(f'{schema_name}'):
            from fedow_connect.models import FedowConfig
            from fedow_connect.fedow_api import FedowAPI
            from AuthBillet.models import TibilletUser
            User :TibilletUser = get_user_model()

            settings.DEBUG = True
            fedow_domain = os.environ['FEDOW_DOMAIN']
            fedow_config = FedowConfig.get_solo()

            self.assertFalse(fedow_config.fedow_place_uuid)
            self.assertFalse(fedow_config.fedow_place_wallet_uuid)
            self.assertFalse(fedow_config.fedow_place_admin_apikey)

            root_config = fedow_config.get_conf_root()
            root_config.root_fedow_handshake(fedow_domain)
            root_config.refresh_from_db()

            self.assertEqual(root_config.fedow_domain, fedow_domain)
            self.assertTrue(root_config.fedow_ip)
            self.assertTrue(root_config.fedow_create_place_apikey)
            self.assertTrue(root_config.fedow_primary_pub_pem)

            fedowAPI = FedowAPI(fedow_config)
            # Création de la place
            fake = Faker()
            email = fake.email()
            admin, created = User.objects.get_or_create(
                email=email,
                username=email,
                espece=TibilletUser.TYPE_HUM
            )

            fedowAPI.place.create(admin, fake.company())
            fedow_config.refresh_from_db()
            self.assertTrue(fedow_config.fedow_place_uuid)
            self.assertTrue(fedow_config.fedow_place_wallet_uuid)
            self.assertTrue(fedow_config.fedow_place_admin_apikey)


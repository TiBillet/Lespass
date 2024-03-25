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

    def add_new_user_to_fedow(self):
        from AuthBillet.utils import get_or_create_user
        from fedow_connect.fedow_api import FedowAPI
        from fedow_connect.models import FedowConfig

        fake = Faker()
        email = fake.email()

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            username=email,
            espece='HU'
        )

        fedowAPI = FedowAPI(FedowConfig.get_solo())

        wallet = fedowAPI.wallet.get_or_create(user)
        wallet_uuid = wallet.uuid

        import ipdb; ipdb.set_trace()

        self.assertIsInstance(wallet, Wallet)
        self.assertIsInstance(wallet_uuid, UUID)
        membre.refresh_from_db()
        self.assertEqual(membre.wallet.uuid, wallet_uuid)

        return user

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
            fake = Faker()

            # création de l'admin de la place
            # Lors de la requete vers Fedow, un get_public_key va créer le couple rsa
            email = fake.email()
            admin, created = User.objects.get_or_create(
                email=email,
                username=email,
                espece=TibilletUser.TYPE_HUM
            )

            # Création de la place
            fedowAPI.place.create(admin, fake.company())
            fedow_config.refresh_from_db()
            self.assertTrue(fedow_config.fedow_place_uuid)
            self.assertTrue(fedow_config.fedow_place_wallet_uuid)
            self.assertTrue(fedow_config.fedow_place_admin_apikey)

            # Création d'un nouvel user avec son email seul
            user = self.add_new_user_to_fedow()


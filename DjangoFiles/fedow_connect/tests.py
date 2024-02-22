import os

from django.conf import settings
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection
from django.contrib.auth import get_user_model

from django.test import TestCase
from django_tenants.utils import get_tenant_model, tenant_context, schema_context, get_public_schema_name



class TenantSchemaTestCase(TestCase):

    def test_in_tenant_schema(self):
        with schema_context('public'):
            call_command('create_public')

        with schema_context('meta'):
            from fedow_connect.models import FedowConfig

            settings.DEBUG = True
            fedow_domain = os.environ['FEDOW_DOMAIN']
            fedow_config = FedowConfig.get_solo()

            root_config = fedow_config.get_conf_root()
            root_config.root_fedow_handshake(fedow_domain)
            root_config.refresh_from_db()

            self.assertEqual(root_config.fedow_domain, fedow_domain)
            self.assertTrue(root_config.fedow_ip)
            self.assertTrue(root_config.fedow_create_place_apikey)
            self.assertTrue(root_config.fedow_primary_pub_pem)

            # Création de la place
            from fedow_connect.fedow_api import FedowAPI
            fedowAPI = FedowAPI(fedow_config)

            email = 'jturbeaux@pm.me'
            from AuthBillet.models import TibilletUser
            User :TibilletUser = get_user_model()
            admin, created = User.objects.get_or_create(
                email=email,
                username=email,
                espece=TibilletUser.TYPE_HUM
            )

            fedowAPI.place.create(admin, 'test_place')



"""
class BaseSetup(TenantTestCase):

    def setUp(self):
        super().setUp()
        # Création d'un tenant "test"
        self.c = TenantClient(self.tenant)

    def test_user_profile_view(self):
        with schema_context('test'):
            # response = self.c.get(reverse('user_profile'))
            # self.assertEqual(response.status_code, 200)
            from fedow_connect.fedow_api import FedowAPI
            from AuthBillet.utils import get_or_create_user
            # from root_billet.models import RootConfiguration
            from fedow_connect.models import FedowConfig

            settings.DEBUG = True
            fedow_domain = os.environ['FEDOW_DOMAIN']
            fedow_config = FedowConfig.get_solo()

            root_config = fedow_config.get_conf_root()
            root_config.root_fedow_handshake(fedow_domain)
            root_config.refresh_from_db()

            self.assertEqual(root_config.fedow_domain, fedow_domain)
            self.assertTrue(root_config.fedow_ip)
            self.assertTrue(root_config.fedow_create_place_apikey)
            self.assertTrue(root_config.fedow_primary_pub_pem)

            # Création de la place

            fedowAPI = FedowAPI(fedow_config)
            admin = get_or_create_user('jturbeaux@pm.me', set_active=True)
            fedowAPI.place.create(admin, 'test_place')

            import ipdb; ipdb.set_trace()

"""

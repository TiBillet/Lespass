from django.core.management import call_command
from django.test import TestCase
from django_tenants.utils import schema_context
from django.db import models, connection

from Customers.models import Client
from root_billet.models import RootConfiguration

from BaseBillet.models import Configuration

# from django_tenants.test.cases import TenantTestCase
# from django_tenants.test.client import TenantClient

# Create your tests here.


class APITiBilletTestCase(TestCase):
    def setUp(self):
        call_command('create_public')

    def xtest_Root(self):
        with schema_context('public'):
            root_config = RootConfiguration.get_solo()
            self.assertIsNotNone(root_config)
            self.assertTrue(root_config.stripe_mode_test)
            self.assertIsNotNone(root_config.stripe_test_api_key)

    def test_Meta(self):
        # with schema_context('meta'):
        #     meta_config = Configuration.get_solo()
        #     self.assertIsNotNone(meta_config)

        meta = Client.objects.get(categorie=Client.META)
        self.assertIsNotNone(meta)

        import ipdb; ipdb.set_trace()
        response = self.client.get(f"http://agenda.tibillet.localhost")

        return response




import os
from uuid import UUID

from django.conf import settings
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection
from django.contrib.auth import get_user_model
from faker import Faker
from django.test import TestCase
from django_tenants.utils import get_tenant_model, tenant_context, schema_context, get_public_schema_name

from AuthBillet.models import Wallet
from fedow_connect.validators import WalletValidator


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

        wallet, created = fedowAPI.wallet.get_or_create(user)
        wallet_uuid = wallet.uuid

        self.assertTrue(created)
        self.assertIsInstance(wallet, Wallet)
        self.assertIsInstance(wallet_uuid, UUID)
        user.refresh_from_db()
        self.assertEqual(user.wallet.uuid, wallet_uuid)

        # on lance de nouveau pour retrouver l'user, mais avec un 200 -> created = False
        wallet, created = fedowAPI.wallet.get_or_create(user)
        self.assertFalse(created)
        self.assertIsInstance(wallet, Wallet)
        self.assertIsInstance(wallet_uuid, UUID)
        self.assertEqual(user.wallet.uuid, wallet_uuid)

        return user

    def get_serialized_wallet(self, user):
        from fedow_connect.fedow_api import FedowAPI
        fedowAPI = FedowAPI()
        serialized_wallet = fedowAPI.wallet.retrieve_by_signature(user)
        self.assertIsInstance(serialized_wallet, WalletValidator)
        wallet = serialized_wallet.wallet
        self.assertIsInstance(wallet, Wallet)
        self.assertEqual(wallet.uuid, user.wallet.uuid)
        return serialized_wallet


    def get_checkout(self, user):
        from fedow_connect.fedow_api import FedowAPI
        fedowAPI = FedowAPI()
        stripe_checkout_url = fedowAPI.wallet.get_federated_token_refill_checkout(user)

        self.assertIn('https://checkout.stripe.com/c/pay/cs_test', stripe_checkout_url)
        print('')
        print('Test du paiement. Lancez stripe cli avec :')
        print('stripe listen --forward-to http://127.0.0.1:8442/webhook_stripe/')
        print('')
        print('lancez le paiement avec 42€ et la carte 4242 :')
        print(f"{stripe_checkout_url}")
        print('')
        check_stripe = input("Une fois le paiement validé, 'entrée' pour tester le paiement réussi. NO pour passer :\n")

        if check_stripe != "NO":
            serialized_card = self.get_serialized_wallet(user)
            data = serialized_card.data
            self.assertEqual(data.get('tokens')[0].get('value'), 4200)
            self.assertEqual(data.get('tokens')[0]['asset'].get('is_stripe_primary'), True)

        return stripe_checkout_url

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

            # récupération des informations détaillé du wallet
            serialized_wallet = self.get_serialized_wallet(user)
            wallet = serialized_wallet.wallet

            # Récupération d'un lien de recharge cashless Fedow
            stripe_checkout_url = self.get_checkout(user)


import json
import os
from uuid import UUID, uuid4

from django.test import tag
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection
from django.contrib.auth import get_user_model
from django_tenants.urlresolvers import reverse
from faker import Faker
from django.test import TestCase
from django_tenants.utils import get_tenant_model, tenant_context, schema_context, get_public_schema_name

from AuthBillet.models import Wallet
from fedow_connect.validators import WalletValidator
from rest_framework.test import APIRequestFactory, force_authenticate

class InstallCreationTest(TestCase):
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
        print(f"add_new_user_to_fedow : {connection.tenant.schema_name}")
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
        print(f"get_serialized_wallet : {connection.tenant.schema_name}")
        from fedow_connect.fedow_api import FedowAPI
        fedowAPI = FedowAPI()
        serialized_wallet = fedowAPI.wallet.retrieve_by_signature(user)
        self.assertIsInstance(serialized_wallet, WalletValidator)
        wallet = serialized_wallet.wallet
        self.assertIsInstance(wallet, Wallet)
        self.assertEqual(wallet.uuid, user.wallet.uuid)
        return serialized_wallet

    def get_checkout(self, user):
        print(f"get_checkout : {connection.tenant.schema_name}")
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

    def create_and_pay_membership(self, user):
        print(f"adhesion_and_fedow : {connection.tenant.schema_name}")
        with schema_context('meta'):
            print(f"adhesion_and_fedow : {connection.tenant.schema_name}")
            connection.tenant.uuid = uuid4() # Pour éviter les erreurs coté controleur (on vérifie l'uuid pour stripe)
            from BaseBillet.models import Membership, Product, Price, OptionGenerale


            # Création d'un price/product/options
            # TODO: Le fabriquer avec un formulaire html
            option1 = OptionGenerale.objects.create(name="Option one")
            option2 = OptionGenerale.objects.create(name="Option two")
            option3 = OptionGenerale.objects.create(name="Option three")

            adhesion_asso = Product.objects.create(
                name="Adhesion association",
                categorie_article=Product.ADHESION,
            )
            adhesion_asso.option_generale_radio.add(option1)
            adhesion_asso.option_generale_checkbox.add(option2, option3)

            price = Price.objects.create(
                product=adhesion_asso,
                name='mensuel',
                prix=2,
                vat=Price.VINGT,
                subscription_type= Price.MONTH,
                recurring_payment= True
            )

            fake = Faker()
            email = user.email

            # Fabrication de la requete :
            self.factory = APIRequestFactory()
            post_data = {'acknowledge': 'on',
                         'price': f'{price.uuid}',
                         'email': f'{email}',
                         'first_name': fake.first_name(),
                         'last_name': fake.last_name(),
                         'option_radio': f'{option1.uuid}',
                         'options_checkbox': [f"{option2.uuid}", f"{option3.uuid}"],
                         'newsletter': False,
                         }
            request = self.factory.post('/memberships/', post_data)
            force_authenticate(request, user=user)

            # Récupération de la vue du controleur :
            from BaseBillet.views import MembershipMVT
            view = MembershipMVT.as_view({'post': 'create'})

            # Lancement de la requete, comme si c'etait un front
            response = view(request)
            self.assertEqual(response.status_code, 200)
            self.assertIn('https://checkout.stripe.com/c/pay/cs_test', response.url)

            # Vérification de l'objet membership en DB
            membership = Membership.objects.get(
                user=user,
                price=price
            )
            # Non payée encore :
            self.assertIsNone(membership.last_contribution)
            self.assertFalse(membership.is_valid())

            # TODO: Trouver comment tester une validation de paiement stripe checkout ?
            # Le retour de stripe va sur -> paiment_stripe_validator(request, paiement_stripe)

            from BaseBillet.models import Paiement_stripe
            paiement_stripe = Paiement_stripe.objects.first()
            self.assertEqual(paiement_stripe.status, Paiement_stripe.PENDING)
            self.assertEqual(json.loads(paiement_stripe.metadata_stripe)['tenant'], f"{connection.tenant.uuid}")

            # On valide le paiement, ça va mettre les signas et tasks en branle

            paiement_stripe.status = Paiement_stripe.PAID
            paiement_stripe.last_action = timezone.now()
            paiement_stripe.traitement_en_cours = True

            # CASCADE DE TASK
            paiement_stripe.save()
            # -> génération de PDF ( a tester )
            # -> envoie vers Fedow ( a tester )

            # Vérification de membership et paiement a jour :
            paiement_stripe.refresh_from_db()
            self.assertFalse(paiement_stripe.traitement_en_cours)
            self.assertEqual(paiement_stripe.status, Paiement_stripe.VALID)
            membership.refresh_from_db()
            self.assertTrue(membership.is_valid())
            self.assertIsNotNone(membership.last_contribution)

            self.assertIn(paiement_stripe, membership.stripe_paiement.all())

            print('membership paid!')
            return membership


    def check_membership_sended_to_fedow(self, membership):
        print(f"send_membership_to_fedow : {connection.tenant.schema_name}")

        serialized_wallet = self.get_serialized_wallet(membership.user).data
        tokens = serialized_wallet['tokens']
        tokens_uuid = [(token['asset']['uuid'], token['value']) for token in tokens]
        self.assertIn((str(membership.price.product.uuid), int(membership.contribution_value*100)), tokens_uuid)

        print('membership dans fedow OK !')


        from fedow_connect.fedow_api import FedowAPI
        from fedow_connect.models import FedowConfig
        config_fedow = FedowConfig.get_solo()

        fedow_transaction = membership.fedow_transactions.latest('datetime')

        fedowAPI = FedowAPI()
        serialized_transaction = fedowAPI.transaction.get_from_hash(fedow_transaction.hash)

        self.assertEqual(config_fedow.fedow_place_wallet_uuid, serialized_transaction['sender'])
        self.assertEqual(membership.user.wallet.uuid, serialized_transaction['receiver'])
        self.assertEqual(membership.price.product.uuid, serialized_transaction['asset'])
        self.assertEqual(membership.price.product.fedow_category(), serialized_transaction['action'])
        self.assertEqual('SUB', serialized_transaction['action'])
        self.assertTrue(serialized_transaction['verify_hash'])



    def test_connect_place_to_fedow(self, schema_name=None):
        if schema_name is None:
            schema_name = 'meta'

        with schema_context(f'{schema_name}'):
            from fedow_connect.models import FedowConfig
            from fedow_connect.fedow_api import FedowAPI
            from AuthBillet.models import TibilletUser
            User: TibilletUser = get_user_model()
            print(connection.tenant.schema_name)

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

            # Donner un nom à la config de test
            fake_company = f"{fake.company()} {str(uuid4())[:3]}"
            from BaseBillet.models import Configuration
            config = Configuration.get_solo()
            config.organisation = fake_company
            config.save()

            # Création de la place
            fedowAPI.place.create(admin, fake_company)
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
            # Effectue et test un paiement pour 42€
            # stripe_checkout_url = self.get_checkout(user)

            # Création d'un abonnement
            membership = self.create_and_pay_membership(user)
            # envoi sur Fedow avec wallet déja existant :
            self.check_membership_sended_to_fedow(membership)
            # TODO: test avec user tout neuf, sans wallet
            # TODO: tester avec une place qui n'est pas l'origine du membership
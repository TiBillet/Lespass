import json
import uuid
from io import StringIO
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client, Domain

class ManagementCommandsTest(TestCase):
    def setUp(self):
        # On s'assure d'être dans le contexte public pour créer le tenant
        with schema_context('public'):
            # Nettoyage au cas où (pour les tests)
            Client.objects.filter(schema_name='test-tenant').delete()
            
            self.tenant = Client.objects.create(
                schema_name='test-tenant', 
                name='Test Tenant'
            )
            Domain.objects.create(
                domain='test.tibillet.localhost', 
                tenant=self.tenant, 
                is_primary=True
            )
            
            User = get_user_model()
            with tenant_context(self.tenant):
                # On crée un admin pour metadata
                User.objects.create(
                    email='admin@tibillet.org',
                    username='admin@tibillet.org',
                    is_staff=True,
                    is_active=True,
                    email_valid=True
                )
                self.user = User.objects.create(
                    email='testuser@example.com',
                    username='testuser@example.com',
                    email_valid=True
                )
                from AuthBillet.models import Wallet
                self.wallet = Wallet.objects.create(user=self.user)

    def test_get_login_link(self):
        out = StringIO()
        call_command('get_login_link', 'testuser@example.com', 'test-tenant', stdout=out, no_color=True)
        output = out.getvalue().strip()
        # Le lien doit contenir le domaine et le token
        self.assertIn('https://test.tibillet.localhost/emailconfirmation/', output)

    @patch('Administration.management.commands.launch_payment.FedowAPI')
    @patch('Administration.management.commands.launch_payment.send_sale_to_laboutik')
    @patch('Administration.management.commands.launch_payment.send_payment_success_admin')
    @patch('Administration.management.commands.launch_payment.send_payment_success_user')
    def test_launch_payment_success(self, mock_email_user, mock_email_admin, mock_laboutik, mock_fedow):
        # Config mock Fedow
        mock_api_instance = mock_fedow.return_value
        mock_api_instance.wallet.get_or_create_wallet.return_value = (self.wallet, False)
        mock_api_instance.wallet.get_total_fiducial_and_all_federated_token.return_value = 1000
        
        # Simuler une transaction réussie
        mock_api_instance.transaction.to_place_from_qrcode.return_value = [
            {'asset': str(uuid.uuid4()), 'amount': 100}
        ]
        mock_api_instance.asset.retrieve.return_value = {'category': 'FED'}
        
        out = StringIO()
        err = StringIO()
        # Appel de la commande
        call_command('launch_payment', 'testuser@example.com', 'test-tenant', '100', '--no-input', stdout=out, stderr=err, no_color=True)
        
        output = out.getvalue().strip()
        errors = err.getvalue().strip()
        
        if errors:
            print(f"Command stderr: {errors}")
            
        self.assertIn('Paiement de 100 centimes réussi', output)
        
        # Vérification en DB
        from BaseBillet.models import LigneArticle
        with tenant_context(self.tenant):
            # Status est 'V' (VALID)
            self.assertEqual(LigneArticle.objects.filter(status='V').count(), 1)
            line = LigneArticle.objects.get(amount=100)
            self.assertEqual(line.status, 'V')
            
        # Vérification des appels Celery
        self.assertTrue(mock_laboutik.delay.called)
        self.assertTrue(mock_email_admin.delay.called)
        self.assertTrue(mock_email_user.delay.called)

    @patch('Administration.management.commands.launch_payment.FedowAPI')
    def test_launch_payment_insufficient_balance(self, mock_fedow):
        mock_api_instance = mock_fedow.return_value
        mock_api_instance.wallet.get_or_create_wallet.return_value = (self.wallet, False)
        mock_api_instance.wallet.get_total_fiducial_and_all_federated_token.return_value = 50
        
        out = StringIO()
        err = StringIO()
        call_command('launch_payment', 'testuser@example.com', 'test-tenant', '100', '--no-input', stdout=out, stderr=err, no_color=True)
        
        self.assertIn('Solde insuffisant', err.getvalue())

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django_tenants.utils import get_tenant_model, tenant_context
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from decimal import Decimal
import logging
import argparse
import json
import uuid

from BaseBillet.models import Product, ProductSold, Price, PriceSold, LigneArticle, PaymentMethod, SaleOrigin
from BaseBillet.tasks import send_sale_to_laboutik, send_payment_success_admin, send_payment_success_user
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Lance un paiement pour un utilisateur sur un tenant spécifique."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = """
Lance un paiement pour un utilisateur sur un tenant spécifique.
Reproduit la logique de BaseBillet.views.QrCodeScanPay.valid_payment.

Exemple d'utilisation :
python manage.py launch_payment user@example.com mytenant 1000

Via Docker :
docker exec lespass_django poetry run python manage.py launch_payment user@example.com mytenant 1000
        """
        parser.add_argument('email', type=str, help="L'email de l'utilisateur qui paye")
        parser.add_argument('schema_name', type=str, help="Le schema_name du tenant (lieu de vente)")
        parser.add_argument('amount', type=int, help="Le montant en centimes")
        parser.add_argument('--no-input', action='store_true', help="Ne demande pas de confirmation")
        parser.add_argument('--send-email', action='store_true', help="Envoie un email de confirmation")

    def handle(self, *args, **options):
        email = options['email'].strip()
        schema_name = options['schema_name']
        amount = options['amount']

        TenantModel = get_tenant_model()
        try:
            tenant = TenantModel.objects.get(schema_name=schema_name)
        except TenantModel.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tenant avec le schema_name '{schema_name}' non trouvé."))
            return

        with tenant_context(tenant):
            User = get_user_model()
            try:
                user = User.objects.get(email=email.lower())
            except User.DoesNotExist:
                try:
                    user = User.objects.get(email=email)
                except User.DoesNotExist:
                    self.stderr.write(self.style.ERROR(
                        f"Utilisateur avec l'email '{email}' non trouvé sur le tenant '{schema_name}'."))
                    return

            if not user.email_valid:
                self.stderr.write(self.style.WARNING(f"Attention: L'email de l'utilisateur {email} n'est pas validé."))

            # Initialisation Fedow API
            fedow_api = FedowAPI()
            wallet, created = fedow_api.wallet.get_or_create_wallet(user)
            user_balance = fedow_api.wallet.get_total_fiducial_and_all_federated_token(user)

            if user_balance < amount:
                self.stderr.write(self.style.ERROR(
                    f"Solde insuffisant. Solde: {user_balance}, Montant requis: {amount}"))
                return

            if not options.get('no_input'):
                prompt = (f"solde disponible sur le portefeuille de l'user : {user_balance}, "
                          f"vous allez faire une vente pour le tenant : {tenant.name} "
                          f"de la somme {amount}, êtes vous sur de continuer ? (y/N) ")
                confirm = input(prompt)
                if confirm.lower() not in ['y', 'yes']:
                    self.stdout.write(self.style.WARNING("Opération annulée par l'utilisateur."))
                    return

            # Création d'une LigneArticle temporaire pour simuler le processus QR Code
            product = Product.objects.get_or_create(
                name=_('Sale via management command'), 
                categorie_article=Product.QRCODE_MA
            )[0]
            product_sold = ProductSold.objects.get_or_create(product=product)[0]
            price_val = dround(Decimal(amount) / 100)
            price = Price.objects.get_or_create(
                name=f"{price_val}€", 
                product=product, 
                prix=price_val
            )[0]
            price_sold = PriceSold.objects.get_or_create(
                productsold=product_sold, 
                price=price, 
                prix=price_val
            )[0]

            # On simule un admin (nécessaire pour les métadonnées de valid_payment)
            # On prend le premier admin trouvé ou l'utilisateur lui-même par défaut
            admin_user = User.objects.filter(is_staff=True).first()
            admin_email = admin_user.email if admin_user else "admin@tibillet.org"

            metadata = {"admin": admin_email, "scanner_email": user.email}

            ligne_article = LigneArticle.objects.create(
                pricesold=price_sold,
                qty=1,
                amount=amount,
                payment_method=PaymentMethod.QRCODE_MA,
                status=LigneArticle.CREATED,
                metadata=json.dumps(metadata, cls=DjangoJSONEncoder),
                sale_origin=SaleOrigin.ADMIN,
            )

            ligne_article_uuid_hex = ligne_article.uuid.hex
            metadata["ligne_article_uuid_hex"] = ligne_article_uuid_hex
            ligne_article.metadata = json.dumps(metadata, cls=DjangoJSONEncoder)
            ligne_article.save()

            # Lancement de la transaction via Fedow api (Logique de valid_payment)
            asset_type = "EURO"
            try:
                self.stdout.write(f"Tentative de paiement: {amount} centimes pour {user.email}...")
                transactions = fedow_api.transaction.to_place_from_qrcode(
                    metadata=metadata,
                    amount=amount,
                    asset_type=asset_type,
                    user=user,
                )
                
                if transactions is None or not isinstance(transactions, list):
                    self.stderr.write(self.style.ERROR("Erreur lors de la transaction Fedow: Pas de transactions retournées."))
                    return

                total_amount = amount
                metadata['transactions'] = transactions
                pricesold = ligne_article.pricesold
                ex_ligne_article_uuid = ligne_article.uuid
                ligne_article.delete()

                for transaction in transactions:
                    asset_used = fedow_api.asset.retrieve(str(transaction['asset']))
                    if asset_used['category'] == 'FED':
                        mp = PaymentMethod.STRIPE_FED
                    elif asset_used['category'] == 'TLF':
                        mp = PaymentMethod.LOCAL_EURO
                    else:
                        self.stderr.write(self.style.WARNING(f"Catégorie d'asset inconnue: {asset_used['category']}"))
                        mp = PaymentMethod.LOCAL_EURO

                    new_ligne_article = LigneArticle.objects.create(
                        uuid=ex_ligne_article_uuid if transactions.index(transaction) == 0 else uuid.uuid4(),
                        pricesold=pricesold,
                        qty=dround(Decimal(transaction['amount']) / Decimal(total_amount)) if total_amount > 0 else 1,
                        amount=transaction['amount'],
                        payment_method=mp,
                        status=LigneArticle.VALID,
                        metadata=json.dumps(metadata, cls=DjangoJSONEncoder),
                        asset=transaction['asset'],
                        wallet=wallet,
                        sale_origin=SaleOrigin.ADMIN,
                    )

                    send_sale_to_laboutik.delay(new_ligne_article.uuid)

                # Emails de confirmation
                if options.get('send-email'):
                    payment_time_str = timezone.now().strftime("%d/%m/%Y %H:%M")
                    place = tenant.name

                    send_payment_success_admin.delay(
                        amount,
                        payment_time_str,
                        place,
                        user.email
                    )
                    send_payment_success_user.delay(
                        user.email,
                        amount,
                        payment_time_str,
                        place
                    )

                self.stdout.write(self.style.SUCCESS(f"Paiement de {amount} centimes réussi pour {user.email} sur le tenant {tenant.name}."))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Erreur lors du traitement du paiement: {str(e)}"))
                logger.exception("Erreur launch_payment")

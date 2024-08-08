import json
from django.core.management.base import BaseCommand
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Product, Price, Membership
from fedow_connect.fedow_api import FedowAPI
from decimal import Decimal


class Command(BaseCommand):
    def handle(self, *args, **options):
        fedowAPI = FedowAPI()
        adhesion = Product.objects.get(categorie_article=Product.ADHESION)

        with open('memberships.json', 'r', encoding='utf-8') as readf:
            loaded_data = json.load(readf)

        """
        test :
        for member in loaded_data:
            if member['card_qrcode_uuid']:
                if len(member['card_qrcode_uuid']) > 1:
                    break
        """

        for member in loaded_data:
            # Création de l'user
            email = member['email']
            user = get_or_create_user(email, send_mail=False)
            # Création du wallet Fedow
            wallet, created = fedowAPI.wallet.get_or_create_wallet(user)

            membership = None
            if user.membership.exists():
                # Contribution la plus récente :
                membership = user.membership.all().order_by('-last_contribution').first()

            # Vérification de l'adhésion
            if member.get('last_contribution'):
                # On compare l'adhésion en base de donnée et celle sur le cashless
                # Si elle a une date ultérieure, on la fabrique en db
                last_contribution = datetime.strptime(member['last_contribution'], '%Y-%m-%d').date()
                if membership.last_contribution < last_contribution:
                    price = None
                    cotisation = Decimal(member['cotisation'])
                    if cotisation > 0:
                        try:
                            price = adhesion.prices.get(prix=cotisation)
                        except Price.DoesNotExist:
                            price = None

                    # Création du Membership
                    membership = Membership.objects.create(
                        user=user,
                        price=price,
                        date_added=datetime.fromisoformat(member['date_added']) if member['date_added'] else None,
                        last_contribution=datetime.strptime(member['last_contribution'], '%Y-%m-%d').date(),
                        contribution_value=cotisation,
                        first_name=member['first_name'] if member['first_name'] else None,
                        last_name=member['last_name'] if member['last_name'] else None,
                        postal_code=member['postal_code'] if member['postal_code'] else None,
                    )

            if membership:
                if not membership.fedow_transactions.exists():
                    serialized_transaction = fedowAPI.membership.create(membership=membership)

            # Liaison avec la carte
            if member['card_qrcode_uuid']:
                for qrcode_uuid in member['card_qrcode_uuid']:
                    linked_serialized_card = fedowAPI.NFCcard.linkwallet_cardqrcode(user=user, qrcode_uuid=qrcode_uuid)

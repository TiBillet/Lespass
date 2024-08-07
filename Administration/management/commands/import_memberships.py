import json
from django.core.management.base import BaseCommand
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Product, Price, Membership


class Command(BaseCommand):
    def handle(self, *args, **options):
        adhesion = Product.objects.get(categorie_article=Product.ADHESION)

        with open('memberships.json', 'r', encoding='utf-8') as readf:
            loaded_data = json.load(readf)

        for member in loaded_data:
            # Création de l'user
            email = member['email']
            user = get_or_create_user(email, send_mail=False)

            # Création du wallet
            fedowAPI = FedowAPI()
            wallet, created = fedowAPI.wallet.get_or_create_wallet(user)

            # Création du Membership
            if member['date']:
                Membership.objects.create(
                    user=user,
                    date_added=member['date_added'],
                    last_contribution=member['last_contribution'],
                    first_name=member['first_name'],
                    last_name=member['last_name'],
                    postal_code=member['postal_code'],
                )

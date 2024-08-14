import json
from datetime import datetime

from django.contrib.auth import get_user_model
from rest_framework import serializers

from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Product, Price, Membership
from fedow_connect.fedow_api import FedowAPI
from decimal import Decimal

### Set all email to lower :
# a faire pour chaque tenant
"""
User = get_user_model()
for user in User.objects.all():
    email = user.email
    search = User.objects.filter(email__icontains=email.lower())
    if search.count() > 1:
        userlower = User.objects.get(email=email.lower())
        for result in search :
            if result != userlower:
                print(userlower.email, result.pk, result.email, result.wallet, result.membership.all(), result.paiement_stripe_set.all())
                
                for paiement in result.paiement_stripe_set.all():
                    paiement.user = userlower
                    paiement.save()
                for membership in result.membership.all():
                    membership.user = userlower
                    membership.save()
                try :
                    result.delete()
                except Exception as e :
                    print(f"erreur delete {e}")

for user in User.objects.all():
    user.email=user.email.lower()
    user.username=user.username.lower()
    user.save()
    
re=User.objects.get(email='réseau976974@gmail.com')
re.email='reseau976974@gmail.com'
re.username='reseau976974@gmail.com'
re.save()
"""

## Doit être lancé dans un terminal django

fedowAPI = FedowAPI()
adhesion = Product.objects.get(categorie_article=Product.ADHESION)
serialized_asset, created = fedowAPI.asset.get_or_create_asset(adhesion)
asset_fedow = f"{serialized_asset['uuid']}"


with open('memberships.json', 'r', encoding='utf-8') as readf:
    loaded_data = json.load(readf)

# Checker de mail
class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

#Source depuis LaBoutik : todo, a integrer dans le serializer
"""
'email': membre.email.lower(),
'first_name': membre.prenom,
'last_name': membre.name,
'postal_code': membre.code_postal,
'date_added': membre.date_ajout,
'last_contribution': membre.date_derniere_cotisation,
'cotisation': membre.cotisation,
'card_qrcode_uuid': [f"{carte.uuid_qrcode}" for carte in membre.CarteCashless_Membre.all()]
"""

for member in loaded_data:
    check_mail = EmailSerializer(data=member)
    if not check_mail.is_valid():
        print(member['email'])

check_mail = EmailSerializer(data=loaded_data, many=True)
if not check_mail.is_valid():
    raise Exception('check mail false')

for member in loaded_data:
    # Création de l'user
    email = member['email'].lower()
    print(email)
    user = get_or_create_user(email, send_mail=False)
    if not user :
        # Email non valide
        continue

    # Création du wallet Fedow
    wallet, created = fedowAPI.wallet.get_or_create_wallet(user)

    # Vérification de l'adhésion
    # Contribution déja enregistré sur Lespass.
    membership = None
    if user.membership.exists():
        membership = user.membership.all().order_by('-last_contribution').first()

    if member.get('last_contribution'):
        # date :
        last_contribution = datetime.strptime(member['last_contribution'], '%Y-%m-%d').date()
        # cotisation :
        price = None
        cotisation = Decimal(member['cotisation'])
        if cotisation > 0:
            try:
                price = adhesion.prices.get(prix=cotisation)
            except Price.DoesNotExist:
                price = None


        # Contribution déja enregistré sur Lespass.
        if membership:
            # On compare l'adhésion en base de donnée et celle sur le cashless
            # Si elle a une date ultérieure, on la fabrique en db
            if not membership.last_contribution :
                membership = None
            elif membership.last_contribution < last_contribution:
                membership = None

        if not membership :
            # Création du Membership
            membership = Membership.objects.create(
                user=user,
                price=price,
                asset_fedow=asset_fedow,
                date_added=datetime.fromisoformat(member['date_added']) if member['date_added'] else None,
                last_contribution=last_contribution,
                contribution_value=cotisation,
                first_name=member['first_name'] if member['first_name'] else None,
                last_name=member['last_name'] if member['last_name'] else None,
                postal_code=member['postal_code'] if member['postal_code'] else None,
            )

    # Vérifie que l'adhésion a bien été envoyé a Fedow
    if membership:
        print(email, membership.last_contribution, membership.contribution_value, membership.price)
        if not membership.asset_fedow:
            membership.asset_fedow = asset_fedow
            membership.save()
        if not membership.fedow_transactions.exists() and membership.contribution_value :
            serialized_transaction = fedowAPI.membership.create(membership=membership)
    # Liaison avec la carte
    if member['card_qrcode_uuid']:
        for qrcode_uuid in member['card_qrcode_uuid']:
            linked_serialized_card = fedowAPI.NFCcard.linkwallet_cardqrcode(user=user, qrcode_uuid=qrcode_uuid)

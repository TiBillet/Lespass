import logging

from django.utils.timezone import localtime
from uuid import UUID

from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Membership, FedowTransaction, Product, Price
from BaseBillet.templatetags.tibitags import dround
from fedow_connect.fedow_api import FedowAPI
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# Fedow comme moteur d'intérop avec des systèmes externe.
# Ex si adhésion effectuée ailleurs (LaBoutik), fedow est au courant et prévient Lespass

class Membership_fwh(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [AllowAny, ]

    def retrieve(self, request, pk=None):
        # pk correspond à l'uuid de la transaction
        transaction_uuid = UUID(pk)
        # Récupération des infos de la transaction
        fedowAPI = FedowAPI()
        transaction_serialized = fedowAPI.transaction.retrieve(transaction_uuid)
        transaction = FedowTransaction.objects.get(pk=transaction_serialized['uuid'])

        if Membership.objects.filter(fedow_transactions=transaction).exists():
            # Déja enregistré !
            logger.info("transaction déja enregistrée")
            return Response(status=status.HTTP_208_ALREADY_REPORTED)

        # Recherche de l'user associé : get user or none
        user = TibilletUser.objects.filter(wallet__uuid=transaction_serialized.get('receiver')).first()
        # Recherche d'une carte associée

        # Recherche du prix :
        amount = dround(transaction_serialized.get('amount'))
        asset_uuid = transaction_serialized['asset']
        product = Product.objects.get(pk=asset_uuid)
        price = Price.objects.filter(product=product, prix=amount).first()
        if not price:
            try :
                price = Price.objects.get(free_price=True, product=product)
            except Price.DoesNotExist:
                # Fabrication d'un prix libre, non publié si créé
                price = Price.objects.create(
                    product=product,
                    free_price=True,
                    publish=False,
                    name=_('Open price'),
                    subscription_type=Price.YEAR,
                )

        # Création de l'objet membership associé
        now = localtime()
        new_membership = Membership.objects.create(
            user=user,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            phone=user.phone if user else None,
            postal_code=user.postal_code if user else None,
            birth_date=user.birth_date if user else None,
            price=price,
            card_number=transaction_serialized['card']['number_printed'] if transaction_serialized.get('card') else None,
            asset_fedow=asset_uuid,
            first_contribution=now,
            last_contribution=now,
            contribution_value=amount,
            status=Membership.LABOUTIK, # Provenance de Fedow = Laboutik
        )
        new_membership.fedow_transactions.add(transaction)

        # On rajoute la deadline en fonction du prix choisi :
        new_membership.set_deadline()

        return Response(status=status.HTTP_201_CREATED)


class Ticket_fwh(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [AllowAny, ]

    def retrieve(self, request, pk=None):
        # Un nouveau billet vendu ! On met à jour
        # Pour le futur : moteur d'intérop
        pass

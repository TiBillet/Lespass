import json
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils.timezone import localtime
from uuid import UUID

from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Membership, FedowTransaction, Product, Price, LigneArticle, PaymentMethod, SaleOrigin
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import ajouter_article, ajouter_reglement, encaisser_vente, ouvrir_vente
from BaseBillet.templatetags.tibitags import dround
from fedow_connect.fedow_api import FedowAPI
from laboutik.views import _taux_tva_de_la_ligne_de_caisse
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
        transaction_fedow = FedowTransaction.objects.get(pk=transaction_serialized['uuid'])

        if Membership.objects.filter(fedow_transactions=transaction_fedow).exists():
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
        price = Price.objects.filter(product=product, prix=amount, archived=False).first()
        if not price:
            try :
                price = Price.objects.get(free_price=True, product=product, archived=False)
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
        membership = Membership.objects.create(
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
            status=Membership.LABOUTIK, # Provenance de Fedow = LaBoutik
        )
        membership.fedow_transactions.add(transaction_fedow)

        # On rajoute la deadline en fonction du prix choisi :
        membership.set_deadline()

        # Création de la ligne vente
        metadata = None
        try :
            metadata = json.dumps(transaction_serialized, cls=DjangoJSONEncoder)
        except Exception as e:
            logger.error(f"Erreur de création metadata depuis transaction fedow : {e}")

        # La vente de l'ancienne caisse : l'argent a été reçu là-bas, le moyen n'est pas
        # connu. La ligne (VALID, moyen inconnu, origine LaBoutik) est l'article d'une
        # vente (client = l'adhérent, vide s'il est inconnu de Lespass), avec UN
        # règlement UNKNOWN du montant, puis l'encaissement. Ligne, vente et
        # encaissement sont écrits ensemble ou pas du tout (`atomic`).
        # LIMITE : l'adhésion est créée AVANT ce bloc. Si ce bloc échoue, l'erreur est
        # journalisée, l'adhésion reste sans ligne ni vente, et un rejeu de Fedow répond
        # 208 sans rien écrire : la vente n'est pas réécrite.
        # / The legacy register's sale: one sale, one UNKNOWN payment, settled; all or
        # nothing. LIMIT: the membership is created BEFORE this block; on failure it stays
        # without line nor sale, and a Fedow replay (208) writes nothing.
        try :
            #TODO : Ajouter toute les infos de wallet, card, asset, moyen de paiement quand Laboutik sera intégrée :
            # beaucoup d'info dans le metadata
            with transaction.atomic():
                vente_de_l_ancienne_caisse = ouvrir_vente(
                    origine=SaleOrigin.LABOUTIK,
                    nature=Vente.Nature.VENTE,
                    client=user,
                )
                ligne_de_l_adhesion = ajouter_article(
                    vente_de_l_ancienne_caisse,
                    pricesold=get_or_create_price_sold(price),
                    quantite=1,
                    prix_unitaire=dec_to_int(membership.contribution_value),
                    taux_tva=_taux_tva_de_la_ligne_de_caisse(product, PaymentMethod.UNKNOWN),
                    membership=membership,
                    payment_method=PaymentMethod.UNKNOWN,
                    status=LigneArticle.VALID,
                    sale_origin=SaleOrigin.LABOUTIK,
                    metadata=metadata,
                )
                montant_recu_par_l_ancienne_caisse = ligne_de_l_adhesion.total_catalogue
                if montant_recu_par_l_ancienne_caisse != 0:
                    ajouter_reglement(
                        vente_de_l_ancienne_caisse,
                        moyen=PaymentMethod.UNKNOWN,
                        montant=montant_recu_par_l_ancienne_caisse,
                    )
                encaisser_vente(vente_de_l_ancienne_caisse)
        except Exception as e:
            logger.error(f"Erreur de création ligne article depuis membership from wallet fedow : {e}")

        return Response(status=status.HTTP_201_CREATED)


class Ticket_fwh(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [AllowAny, ]

    def retrieve(self, request, pk=None):
        # Un nouveau billet vendu ! On met à jour
        # Pour le futur : moteur d'intérop
        pass

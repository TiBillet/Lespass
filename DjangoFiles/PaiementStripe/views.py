import json
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
import stripe
# Create your views here.
from django.utils import timezone
from django.views import View

from AuthBillet.models import HumanUser
from BaseBillet.models import Configuration, Article, LigneArticle
from PaiementStripe.models import Paiement_stripe

# from QrcodeCashless.views import postPaimentRecharge

import logging

logger = logging.getLogger(__name__)


class creation_checkout_stripe():

    def __init__(self,
                 email_paiement: str,
                 liste_ligne_article: list,
                 metadata: dict,
                 absolute_domain: str
                 ) -> None:

        self.absolute_domain = absolute_domain
        self.configuration = Configuration.get_solo()
        self.email_paiement = email_paiement
        self.user = self._user_paiement()
        self.detail = self._detail()
        self.total = self._total()
        self.liste_ligne_article = liste_ligne_article
        self.metadata = metadata
        self.metadata_json = json.dumps(self.metadata)
        self.paiement_stripe_db = self._paiement_stripe_db()
        self.stripe_api_key = self._stripe_api_key()
        self.line_items = self._line_items()
        self.checkout_session = self._checkout_session()

    def _user_paiement(self):
        User = get_user_model()
        user_paiement, created = User.objects.get_or_create(
            email=self.email_paiement)

        if created:
            user_paiement: HumanUser
            user_paiement.client_source = connection.tenant
            user_paiement.client_achat.add(connection.tenant)
            user_paiement.is_active = False
        else:
            user_paiement.client_achat.add(connection.tenant)
        user_paiement.save()

        return user_paiement

    def _total(self):
        total = 0
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            total += ligne.qty * ligne.article.prix
        return total

    def _detail(self):
        detail = ""
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            detail += f"{ligne.article}"
        return detail

    def _paiement_stripe_db(self):

        paiementStripeDb = Paiement_stripe.objects.create(
            user=self.user,
            detail=self.detail,
            total=self.total,
            metadata_stripe=self.metadata_json,
        )

        return paiementStripeDb

    def _stripe_api_key(self):
        if self.configuration.stripe_mode_test:
            stripe.api_key = self.configuration.stripe_test_api_key
        else:
            stripe.api_key = self.configuration.stripe_api_key

        return stripe.api_key

    def _line_items(self):
        line_items = []
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            line_items.append(
                {
                    "price": f"{ligne.article.get_id_price_stripe()}",
                    "quantity": ligne.qty,
                }
            )

    def _checkout_session(self):
        checkout_session = stripe.checkout.Session.create(
            customer_email=f'{self.user.email}',
            line_items=self.line_items,
            payment_method_types=['card'],
            mode='payment',
            metadata=self.metadata,
            success_url=f'{self.absolute_domain}/stripe/return/{self.paiement_stripe_db.uuid}',
            cancel_url=f'{self.absolute_domain}/stripe/return/{self.paiement_stripe_db.uuid}',
            client_reference_id=f"{self.user.uuid_user}",
        )

        print(checkout_session.id)
        self.paiement_stripe_db.id_stripe = checkout_session.id
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()

        return checkout_session

    def is_valid(self):
        if self.checkout_session.id and \
            self.checkout_session.url :
            return True

        else:
            return False

    def redirect_to_stripe(self):
        return HttpResponseRedirect(self.checkout_session.url)


class retour_stripe(View):

    def get(self, request, uuid_stripe):
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=uuid_stripe)

        configuration = Configuration.get_solo()
        if configuration.stripe_mode_test:
            stripe.api_key = configuration.stripe_test_api_key
        else:
            stripe.api_key = configuration.stripe_api_key

        if paiement_stripe.status != Paiement_stripe.VALID:

            checkout_session = stripe.checkout.Session.retrieve(paiement_stripe.id_stripe)
            if checkout_session.payment_status == "unpaid":
                paiement_stripe.status = Paiement_stripe.PENDING
                if checkout_session.expires_at > datetime.now().timestamp():
                    paiement_stripe.status = Paiement_stripe.EXPIRE
                paiement_stripe.save()

            elif checkout_session.payment_status == "paid":
                paiement_stripe.status = Paiement_stripe.PAID
                paiement_stripe.save()

                # on vérifie si les infos sont cohérente avec la db : Never Trust Input :)
                metadata_stripe_json = checkout_session.metadata
                metadata_stripe = json.loads(str(metadata_stripe_json))

                metadata_db_json = paiement_stripe.metadata_stripe
                metadata_db = json.loads(metadata_db_json)

                try:
                    assert metadata_stripe == metadata_db
                    assert set(metadata_db.keys()) == set(metadata_stripe.keys())
                    for key in set(metadata_stripe.keys()):
                        assert metadata_db[key] == metadata_stripe[key]
                except:
                    logger.error(f"{timezone.now()} "
                                 f"retour_stripe {uuid_stripe} : "
                                 f"metadata ne correspondent pas : {metadata_stripe} {metadata_db}")
                    raise Http404

                # on check si il y a un rechargement de carte cashless dans la commande
                if metadata_db.get('recharge_carte_uuid'):
                    logger.info(
                        f'{timezone.now()} retour stripe pour rechargement carte : {metadata_db.get("recharge_carte_uuid")}')
                    print(
                        f'{timezone.now()} retour stripe pour rechargement carte : {metadata_db.get("recharge_carte_uuid")}')

                    print('gerer la recharge sur le serveur cashless')
                    # return postPaimentRecharge(paiement_stripe, request)




            else:
                paiement_stripe.status = Paiement_stripe.CANCELED
                paiement_stripe.save()
                return HttpResponse(f'Le paiement annulé.')

        return HttpResponse(f'Paiement validé')


'''

class webhook_stripe(View):
    def get(self, request):
        print(f"webhook_stripe GET")
        return  HttpResponse(f'ok')

    def post(self, request):
        endpoint_secret = 'whsec_1Urn98yUMsgwdXA7vhN5dwDTRQLD2vmD'
        event = None
        payload = request.data
        sig_header = request.headers['STRIPE_SIGNATURE']

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError as e:
            # Invalid payload
            raise e
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            raise e

        # Handle the event
        print('Unhandled event type {}'.format(event['type']))

        print(f"webhook_stripe POST {event}")
        return  HttpResponse(f'ok {event}')
'''

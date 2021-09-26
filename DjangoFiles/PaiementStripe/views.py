import json
from datetime import datetime

from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
import stripe
# Create your views here.
from django.utils import timezone
from django.views import View

from BaseBillet.models import Configuration
from PaiementStripe.models import Paiement_stripe


from QrcodeCashless.views import postPaimentRecharge

import logging
logger = logging.getLogger(__name__)

class retour_stripe(View):

    def get(self, request, uuid_stripe):
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=uuid_stripe)

        configuration = Configuration.get_solo()
        if configuration.stripe_mode_test:
            stripe.api_key = configuration.stripe_test_api_key
        else:
            stripe.api_key = configuration.stripe_api_key

        if paiement_stripe.status != Paiement_stripe.VALID :

            checkout_session = stripe.checkout.Session.retrieve(paiement_stripe.id_stripe)
            if checkout_session.payment_status == "unpaid":
                paiement_stripe.status = Paiement_stripe.PENDING
                if checkout_session.expires_at > datetime.now().timestamp() :
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
                    for key in set(metadata_stripe.keys()) :
                        assert metadata_db[key] == metadata_stripe[key]
                except:
                    logger.error(f"{timezone.now()} "
                                 f"retour_stripe {uuid_stripe} : "
                                 f"metadata ne correspondent pas : {metadata_stripe} {metadata_db}")
                    raise Http404

                # on check si il y a un rechargement de carte cashless dans la commande
                if metadata_db.get('recharge_carte_uuid') :
                    logger.info(f'{timezone.now()} retour stripe pour rechargement carte : {metadata_db.get("recharge_carte_uuid")}')
                    print (f'{timezone.now()} retour stripe pour rechargement carte : {metadata_db.get("recharge_carte_uuid")}')
                    return postPaimentRecharge(paiement_stripe, request)




            else:
                paiement_stripe.status = Paiement_stripe.CANCELED
                paiement_stripe.save()
                return HttpResponse(f'Le paiement a été annulé.')

        return  HttpResponse(f'ok {uuid_stripe}')


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

from datetime import datetime

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
import stripe
# Create your views here.
from django.views import View

from BaseBillet.models import Configuration
from PaiementStripe.models import Paiement_stripe


class retour_stripe(View):

    def get(self, request, uuid):
        configuration = Configuration.get_solo()
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=uuid)

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
            elif checkout_session.payment_status == "paid":
                paiement_stripe.status = Paiement_stripe.PAID
            else:
                paiement_stripe.status = Paiement_stripe.CANCELED

            paiement_stripe.save()
        return  HttpResponse(f'ok {uuid}')


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

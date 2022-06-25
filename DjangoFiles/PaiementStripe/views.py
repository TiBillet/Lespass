import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
import stripe
from django.utils import timezone
from django.views import View
from rest_framework import serializers

from BaseBillet.models import Configuration, LigneArticle, Paiement_stripe, Reservation, Price
from django.utils.translation import gettext, gettext_lazy as _

import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class creation_paiement_stripe():

    def __init__(self,
                 user: User,
                 liste_ligne_article: list,
                 metadata: dict,
                 reservation: (Reservation, None),
                 source: str,
                 absolute_domain: str
                 ) -> None:

        self.user = user
        self.email_paiement = user.email
        self.absolute_domain = absolute_domain
        self.liste_ligne_article = liste_ligne_article
        self.metadata = metadata
        self.reservation = reservation
        self.source = source
        self.configuration = Configuration.get_solo()

        self.total = self._total()
        self.metadata_json = json.dumps(self.metadata)
        self.paiement_stripe_db = self._paiement_stripe_db()
        self.stripe_api_key = self._stripe_api_key()
        self.line_items = self._line_items()
        self.mode = self._mode()
        self.return_url = self._return_url()
        self.checkout_session = self._checkout_session()


    def _total(self):
        total = 0
        for ligne in self.liste_ligne_article:
            total += float(ligne.qty) * float(ligne.pricesold.prix)
        return total

    def _paiement_stripe_db(self):

        paiementStripeDb = Paiement_stripe.objects.create(
            user=self.user,
            total=self.total,
            metadata_stripe=self.metadata_json,
            reservation=self.reservation,
            source=self.source,
        )

        for ligne_article in self.liste_ligne_article:
            ligne_article: LigneArticle
            ligne_article.paiement_stripe = paiementStripeDb
            ligne_article.save()

        return paiementStripeDb

    def _stripe_api_key(self):
        api_key = self.configuration.get_stripe_api()
        if api_key:
            stripe.api_key = api_key
            return stripe.api_key
        else :
            raise serializers.ValidationError(_(f"No Stripe Api Key in configuration"))

    def _line_items(self):
        line_items = []
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            line_items.append(
                {
                    "price": f"{ligne.pricesold.get_id_price_stripe()}",
                    "quantity": int(ligne.qty),
                }
            )
        return line_items

    def _mode(self):
        subscription_types = [Price.MONTH, Price.YEAR]
        mode = 'subscription'
        for ligne in self.liste_ligne_article:
            if ligne.pricesold.price.subscription_type not in subscription_types :
                mode = 'payment'
        return mode

    def _return_url(self):
        '''
        Si la source est le QRCode, alors c'est encore le model MVC de django qui gère ça.
        Sinon, c'est un paiement via la billetterie vue.js
        :return:
        '''

        if self.source == Paiement_stripe.QRCODE :
            return "/api/webhook_stripe/"
        else :
            return "/stripe/return/"

    def _checkout_session(self):

        data_checkout = {
            'success_url' : f'{self.absolute_domain}{self.return_url}{self.paiement_stripe_db.uuid}',
            'cancel_url' : f'{self.absolute_domain}{self.return_url}{self.paiement_stripe_db.uuid}',
            'payment_method_types' : ["card"],
            'customer_email' : f'{self.user.email}',
            'line_items' : self.line_items,
            'mode' : self.mode,
            'metadata' : self.metadata,
            'client_reference_id' : f"{self.user.pk}",
        }
        checkout_session = stripe.checkout.Session.create(**data_checkout)

        logger.info(" ")
        logger.info("-"*40)
        logger.info(f"Création d'un nouveau paiment stripe. Metadata : {self.metadata}")
        logger.info(f"checkout_session.id {checkout_session.id} payment_intent : {checkout_session.payment_intent}")
        logger.info("-"*40)
        logger.info(" ")

        self.paiement_stripe_db.payment_intent_id = checkout_session.payment_intent
        self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()

        return checkout_session

    def is_valid(self):
        if self.checkout_session.id and \
                self.checkout_session.url:
            return True
        else:
            return False

    def redirect_to_stripe(self):
        return HttpResponseRedirect(self.checkout_session.url)

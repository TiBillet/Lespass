import json
import logging
from decimal import Decimal

import stripe
from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from stripe.error import InvalidRequestError

from BaseBillet.models import Configuration, LigneArticle, Paiement_stripe, Reservation, Price, PriceSold, PaymentMethod
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)
User = get_user_model()


class CreationPaiementStripe():

    def __init__(self,
                 user: User,
                 liste_ligne_article: list,
                 metadata: dict,
                 reservation: (Reservation, None),
                 source: str = None,
                 absolute_domain: (str, None) = None,
                 success_url: (str, None) = None,
                 cancel_url: (str, None) = None,
                 invoice=None,
                 ) -> None:

        # On va chercher les informations de configuration
        # et test si tout est ok pour créer un paiement
        self.user = user
        self.email_paiement = user.email
        self.invoice = invoice
        self.liste_ligne_article = liste_ligne_article
        self.reservation = reservation
        self.source = source

        self.metadata = metadata
        self.metadata_json = json.dumps(self.metadata)

        # Construction du retour :
        self.absolute_domain = absolute_domain
        self.success_url = success_url
        self.cancel_url = cancel_url

        # On instancie Stripe et entre en db le paiement en state Pending
        self.stripe_api_key = self._stripe_api_key()
        self.stripe_connect_account = Configuration.get_solo().get_stripe_connect_account()

        self.paiement_stripe_db = self._send_paiement_stripe_in_db()

        # Création des items prices et de l'instancee de paiement Stripe
        self.line_items = self._set_stripe_line_items()
        self.mode = self._mode()

        # S'il existe une facture de paiement récurrent.
        # La classe a été intanciée pour entrer en db le paiement.
        # Pas besoin de créer une nouvelle session
        self.checkout_session = None
        if not self.invoice:
            self.checkout_session = self._checkout_session()

    def _stripe_api_key(self):
        # La clé root comme clé par default pour tout paiement.
        api_key = RootConfiguration.get_solo().get_stripe_api()
        if not api_key:
            raise serializers.ValidationError(_(f"No Stripe Api Key in configuration"))
        stripe.api_key = api_key
        return stripe.api_key

    def _send_paiement_stripe_in_db(self):
        dict_paiement = {
            'user': self.user,
            'metadata_stripe': self.metadata_json,
            'reservation': self.reservation,
            'source': self.source,
            'status': Paiement_stripe.PENDING,
        }

        if self.invoice:
            dict_paiement['invoice_stripe'] = self.invoice.id
            if bool(self.invoice.subscription):
                dict_paiement['subscription'] = self.invoice.subscription

        paiementStripeDb = Paiement_stripe.objects.create(**dict_paiement)

        for ligne_article in self.liste_ligne_article:
            ligne_article: LigneArticle
            ligne_article.paiement_stripe = paiementStripeDb
            ligne_article.save()

        return paiementStripeDb

    def _set_stripe_line_items(self, force=False):
        """
        Retourne une liste de dictionnaire avec l'objet line_item de stripe et la quantitée à payer.

        :param force: Force la création de l'id Stripe
        :return:
        """
        line_items = []
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            line_items.append(
                {
                    "price": f"{ligne.pricesold.get_id_price_stripe(force=force)}",
                    "quantity": int(ligne.qty),
                }
            )

        return line_items

    def _mode(self):
        """
        Mode Stripe payment ou subscription
        :return: string
        """

        subscription_types = [Price.MONTH, Price.YEAR]
        mode = 'payment'
        for ligne in self.liste_ligne_article:
            price = ligne.pricesold.price
            if price.subscription_type in subscription_types and price.recurring_payment:
                mode = 'subscription'
        logger.info(f"Stripe payment method: {mode}")
        return mode

    def dict_checkout_creator(self):
        """
        Retourne un dict pour la création de la session de paiement
        https://stripe.com/docs/api/checkout/sessions/create
        :return: dict
        """
        success_url = f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.success_url}"
        cancel_url = f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.cancel_url}"

        data_checkout = {
            'success_url': f'{success_url}',
            'cancel_url': f'{cancel_url}',
            'payment_method_types': ["card"],
            'customer_email': f'{self.user.email}',
            'line_items': self.line_items,
            'mode': self.mode,
            'metadata': self.metadata,
            'client_reference_id': f"{self.user.pk}",
            'stripe_account': f'{self.stripe_connect_account}',
        }

        config = Configuration.get_solo()
        if self.mode == 'payment' and config.stripe_invoice :
            data_checkout['invoice_creation'] = {"enabled": True,}
        return data_checkout

    def _checkout_session(self):

        data_checkout = self.dict_checkout_creator()
        try:
            checkout_session = stripe.checkout.Session.create(**data_checkout)
        except InvalidRequestError as e:
            # L'id stripe d'un prix est mauvais.
            # Probablement dû à un changement d'état de test/prod.
            # On force là creation de nouvel ID en relançant la boucle self.line_items avec force=True
            logger.warning(f"InvalidRequestError on checkout session creation : {e}")
            self.line_items = self._set_stripe_line_items(force=True)
            data_checkout = self.dict_checkout_creator()
            checkout_session = stripe.checkout.Session.create(**data_checkout)

        logger.info(" ")
        logger.info("-" * 40)
        logger.info(f"Création d'un nouveau paiment stripe. Metadata : {self.metadata}")
        logger.info(f"checkout_session.id {checkout_session.id} payment_intent : {checkout_session.payment_intent}")
        logger.info("-" * 40)
        logger.info(" ")

        self.paiement_stripe_db.payment_intent_id = checkout_session.payment_intent
        self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()

        return checkout_session

    def is_valid(self):
        if self.checkout_session:
            if self.checkout_session.id and \
                    self.checkout_session.url:
                return True

        # Pas besoin de checkout, c'est déja payé.
        if self.invoice:
            return True

        else:
            return False

    def redirect_to_stripe(self):
        if self.checkout_session:
            return HttpResponseRedirect(self.checkout_session.url)
        else:
            return None


def new_entry_from_stripe_invoice(user, id_invoice):
    stripe.api_key = Configuration.get_solo().get_stripe_api()
    invoice = stripe.Invoice.retrieve(id_invoice)

    lines = invoice.lines
    lignes_articles = []
    for line in lines['data']:
        ligne_article = LigneArticle.objects.create(
            pricesold=PriceSold.objects.get(id_price_stripe=line.price.id),
            payment_method=PaymentMethod.STRIPE_RECURENT,
            amount=line.amount,
            qty=line.quantity,
        )
        lignes_articles.append(ligne_article)

    metadata = {
        'tenant': f'{connection.tenant.uuid}',
        'from_stripe_invoice': f"{invoice.id}",
    }

    new_paiement_stripe = CreationPaiementStripe(
        user=user,
        liste_ligne_article=lignes_articles,
        metadata=metadata,
        reservation=None,
        source=Paiement_stripe.INVOICE,
        invoice=invoice,
        absolute_domain=None,
    )

    if new_paiement_stripe.is_valid():
        paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

        return paiement_stripe



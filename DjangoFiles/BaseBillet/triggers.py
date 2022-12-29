import datetime

import requests
from django.db import connection

from BaseBillet.models import LigneArticle, Product, Configuration, Membership, Price
from BaseBillet.tasks import send_membership_to_cashless

import logging

from Customers.models import Client
from QrcodeCashless.models import Asset, Wallet

logger = logging.getLogger(__name__)


def increment_to_cashless_serveur(vente):
    logger.info(f"TRIGGER RECHARGE_CASHLESS")
    configuration = Configuration.get_solo()
    if not configuration.server_cashless or not configuration.key_cashless:
        logger.error(f"triggers/increment_to_cashless_serveur - No cashless config for {connection.tenant}")
        raise Exception(f'triggers/increment_to_cashless_serveur - No cashless config for {connection.tenant}')

    vente.data_for_cashless['card_uuid'] = vente.ligne_article.carte.uuid
    vente.data_for_cashless['qty'] = vente.ligne_article.pricesold.prix

    data = vente.data_for_cashless

    sess = requests.Session()
    r = sess.post(
        f'{configuration.server_cashless}/api/chargecard',
        headers={
            'Authorization': f'Api-Key {configuration.key_cashless}'
        },
        data=data,
    )

    sess.close()

    if r.status_code == 202:
        vente.ligne_article.status = LigneArticle.VALID
        logger.info(f"rechargement cashless ok {r.status_code} {r.text}")
        # set_paiement_and_reservation_valid(None, self.ligne_article)
    else:
        logger.error(f"erreur réponse serveur cashless {r.status_code} {r.text}")
    return r.status_code, r.text


def increment_stripe_token(vente):
    # On incrémente la valeur du wallet Stripe de la carte.
    # Cela déclenche un post save qui lance une requete celery
    # pour alerter tous les cashless fédérés

    user = vente.ligne_article.paiement_stripe.user

    # On va chercher l'asset Stripe primaire.
    root = Client.objects.get(categorie=Client.ROOT)
    asset, created = Asset.objects.get_or_create(
        origin=root,
        name="Stripe",
        is_federated=True,
    )

    # Un seul wallet par user
    wallet, created = Wallet.objects.get_or_create(
        asset=asset,
        user=vente.ligne_article.paiement_stripe.user
    )

    logger.info(f"    WALLET : {wallet.qty} + {vente.ligne_article.total()}")

    wallet.qty += vente.ligne_article.total()

    wallet.save()

    # et pouf, ça lance le /DjangoFiles/BaseBillet/signals.py/wallet_update_to_celery
    # qui va informer tous les serveurs cashless qu'un wallet stripe est disponible


class ActionArticlePaidByCategorie:
    """
    Trigged action by categorie when Article is PAID
    """

    def __init__(self, ligne_article: LigneArticle):
        self.ligne_article = ligne_article
        self.categorie = self.ligne_article.pricesold.productsold.product.categorie_article

        self.data_for_cashless = {}
        if ligne_article.paiement_stripe:
            self.data_for_cashless = {
                'uuid_commande': ligne_article.paiement_stripe.uuid,
                'email' : ligne_article.paiement_stripe.user.email
            }

        try:
            # on met en majuscule et on rajoute _ au début du nom de la catégorie.
            trigger_name = f"_{self.categorie.upper()}"
            logger.info(
                f"category_trigger launched - ligne_article : {self.ligne_article} - trigger_name : {trigger_name}")
            trigger = getattr(self, f"trigger{trigger_name}")
            trigger()
        except AttributeError:
            logger.info(f"Pas de trigger pour la categorie {self.categorie}")
        except Exception as exc:
            logger.error(f"category_trigger ERROR : {exc} - {type(exc)}")

    # Category DON
    def trigger_D(self):
        # On a besoin de valider la ligne article pour que le paiement soit validé
        self.ligne_article.status = LigneArticle.VALID
        logger.info(f"TRIGGER DON")

    # Category BILLET
    def trigger_B(self):
        logger.info(f"TRIGGER BILLET")

    # Category Free Reservation
    def trigger_F(self):
        logger.info(f"TRIGGER FREE RESERVATION")

    # Category RECHARGE_CASHLESS
    def trigger_R(self):
        reponse_cashless_serveur = increment_to_cashless_serveur(self)
        logger.info(f"TRIGGER RECHARGE_CASHLESS : {reponse_cashless_serveur}")

    # Category RECHARGE SUSPENDUE
    def trigger_S(self):
        reponse_cashless_serveur = increment_stripe_token(self)
        logger.info(f"TRIGGER RECHARGE_SUSPENDUE")

    # Categorie ADHESION
    def trigger_A(self):

        logger.info(f"TRIGGER ADHESION")

        paiement_stripe = self.ligne_article.paiement_stripe
        user = paiement_stripe.user
        price: Price = self.ligne_article.pricesold.price
        product: Product = self.ligne_article.pricesold.productsold.product

        membership, created = Membership.objects.get_or_create(
            user=user,
            price=price
        )

        membership.first_contribution = datetime.datetime.now().date()
        membership.last_contribution = datetime.datetime.now().date()
        membership.contribution_value = self.ligne_article.pricesold.prix

        if paiement_stripe.invoice_stripe:
            membership.last_stripe_invoice = paiement_stripe.invoice_stripe

        if paiement_stripe.subscription:
            membership.stripe_id_subscription = paiement_stripe.subscription
            membership.status = Membership.AUTO

        membership.save()

        # C'est le cashless qui gère l'adhésion et l'envoi de mail
        if product.send_to_cashless:
            logger.info(f"    Envoie celery task.send_membership_to_cashless")
            data = {
                "ligne_article_pk": self.ligne_article.pk,
            }
            send_membership_to_cashless.delay(data)

        # TODO: C'est un abonnement autre que l'adhésion cashless, on gère l'envoi du contrat.
        else:
            logger.info(f"    TODO Envoie mail abonnement")
            pass

        self.ligne_article.status = LigneArticle.VALID

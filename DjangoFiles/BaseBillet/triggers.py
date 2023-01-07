import datetime

import requests
from django.db import connection

import QrcodeCashless.models
import TiBillet.settings
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


def get_federated_wallet(cashless_card: QrcodeCashless.models.CarteCashless = None,
                         user: TiBillet.settings.AUTH_USER_MODEL = None,) -> Wallet:
    """
        Récupère le wallet en fonction des informations : email, carte ou les deux.

    Exemples :
        Lors d'un rechargement cashless via le QRCode, nous avons l'email et la carte
        Lors d'un achat de billet en ligne d'un utilisateur anonyme, nous n'avons que l'email,
        aucune carde ne lui encore a été donnée.
        Lors d'une distribution de carte cashless a l'entrée d'un lieu sans adhésion,
        nous n'avons que la carte, et il est possible qu'une recharge se fasse en liquide ou en carte bancaire
        sans connaitre le mail de l'utilisateur.

    :param cashless_card:
    :param user:
    :return:
    """
    wallet = None

    # La monnaie fédérée vient toujours du tenant public.
    tenant_root = Client.objects.get(categorie=Client.ROOT)
    asset, created = Asset.objects.get_or_create(
        origin=tenant_root,
        name="Stripe",
        is_federated=True,
    )

    if cashless_card:
        # Si la carte à un utilisateur
        if cashless_card.user:
            if user :
                if user != cashless_card.user:
                    logger.error(f"get_federated_wallet - carte {cashless_card} et user {user} ne correspondent pas")
                    raise OverflowError(f"get_federated_wallet : user != cashless_card.user")
            else :
                cashless_card.user = user
                cashless_card.save()

        # Si la carte n'a pas d'utilisateur,
        else :
            if user :
                logger.info(f"get_federated_wallet - carte {cashless_card} sans user, on lui affecte {user}")
                cashless_card.user = user
                cashless_card.save()


    try :
        #   Lors d'un rechargement cashless via le QRCode, nous avons l'email et la carte
        if user and cashless_card:
            wallet, created = Wallet.objects.get_or_create(asset=asset, user=user, card=cashless_card)

        #   Lors d'un achat de billet en ligne d'un utilisateur anonyme, nous n'avons que l'email,
        #   aucune carte ne lui encore a été donnée.
        elif user:
            wallet = Wallet.objects.get(asset=asset, user=user)

        #   Lors d'une distribution de carte cashless a l'entrée d'un lieu sans adhésion
        #   nous n'avons que la carte, et il est possible qu'une recharge se fasse en liquide ou en carte bancaire
        #   sans connaitre le mail de l'utilisateur
        elif cashless_card:
            wallet = Wallet.objects.get(asset=asset, card=cashless_card)

    except Wallet.DoesNotExist:
        logger.error(f"get_federated_wallet - Wallet does not exist for")
        import ipdb; ipdb.set_trace()
    except ValueError as e:
        logger.error(f"get_federated_wallet - {e}")
        import ipdb; ipdb.set_trace()




        # if user :
        #     wallet, created = Wallet.objects.get_or_create(asset=asset, user=user)
        #     if cashless_card :
        #         cashless_card.user = user
        #         cashless_card.save()
        #         wallet.card = cashless_card
        #         wallet.save()
        # elif cashless_card :
        #     wallet, created = Wallet.objects.get_or_create(asset=asset, card=cashless_card)
        #     if user :
        #         cashless_card.user = user
        #         cashless_card.save()
        #         wallet.user = user
        #         wallet.save()

    return wallet


def increment_federated_wallet(vente):
    vente: ActionArticlePaidByCategorie
    ligne_article : LigneArticle = vente.ligne_article
    # On incrémente la valeur du wallet Stripe de la carte.
    # Cela déclenche un post save qui lance une requete celery
    # pour alerter tous les cashless fédérés

    user = ligne_article.paiement_stripe.user
    cashless_card = ligne_article.carte
    wallet = get_federated_wallet(cashless_card=cashless_card, user=user)

    logger.debug(f"    triggers.increment_federated_wallet - WALLET : {wallet.qty} + {ligne_article.total()}")

    wallet.qty += ligne_article.total()
    wallet.save()

    # et pouf, ça lance le /DjangoFiles/BaseBillet/signals.py/wallet_update_to_celery
    # qui va informer tous les serveurs cashless qu'un wallet stripe est disponible

    # On valide pour avoir un retour positif coté front :
    vente.ligne_article.status = LigneArticle.VALID
    logger.info(f"rechargement cashless fédéré ok")


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
                'email': ligne_article.paiement_stripe.user.email
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

    # Category RECHARGE_FEDERATED
    def trigger_S(self):
        reponse_cashless_serveur = increment_federated_wallet(self)
        logger.info(f"TRIGGER RECHARGE_FEDERATED")

    # Categorie ADHESION
    def trigger_A(self):

        logger.info(f"TRIGGER ADHESION")

        paiement_stripe = self.ligne_article.paiement_stripe
        user = paiement_stripe.user
        price: Price = self.ligne_article.pricesold.price
        product: Product = self.ligne_article.pricesold.productsold.product

        # On check s'il n'y a pas déjà une fiche membre avec le "price" correspondant
        membership = Membership.objects.filter(
            user=user,
            price=price
        ).first()

        if not membership:
            membership, created = Membership.objects.get_or_create(
                user=user,
            )
            if not membership.first_contribution:
                membership.first_contribution = datetime.datetime.now().date()
            membership.price = price

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

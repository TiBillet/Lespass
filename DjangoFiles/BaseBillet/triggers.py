import requests
# from django.db import connection
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
# from django.utils import timezone

# from ApiBillet.thread_mailer import ThreadMaileur
from BaseBillet.models import Reservation, LigneArticle, Ticket, Product, Configuration, Paiement_stripe
from BaseBillet.tasks import ticket_celery_mailer

# from TiBillet import settings

import logging
logger = logging.getLogger(__name__)


def request_to_cashless_server(data):
    configuration = Configuration.get_solo()
    if not configuration.server_cashless or not configuration.key_cashless :
        raise Exception(f'Pas de configuration cashless')

    sess = requests.Session()
    r = sess.post(
        f'{configuration.server_cashless}/api/billetterie_endpoint',
        headers={
            'Authorization': f'Api-Key {configuration.key_cashless}'
        },
        data=data,
    )

    sess.close()
    logger.info(
        f"        demande au serveur cashless pour {data}. réponse : {r.status_code} ")

    if r.status_code != 200:
        logger.error(
            f"            erreur réponse serveur cashless {r.status_code} {r.text}")

    return r.status_code

class action_article_paid_by_categorie:
    '''
    BILLET, PACK, RECHARGE_CASHLESS, VETEMENT, MERCH, ADHESION = 'B', 'P', 'R', 'T', 'M', 'A'
        CATEGORIE_ARTICLE_CHOICES = [
            (BILLET, _('Billet')),
            (PACK, _("Pack d'objets")),
            (RECHARGE_CASHLESS, _('Recharge cashless')),
            (VETEMENT, _('Vetement')),
            (MERCH, _('Merchandasing')),
            (ADHESION, ('Adhésion')),
        ]

    Trigged action by categorie when Article is PAID
    '''

    def __init__(self, ligne_article:LigneArticle, **kwargs):
        self.ligne_article = ligne_article
        self.categorie = self.ligne_article.pricesold.productsold.product.categorie_article
        self.data_for_cashless = {}

        try:
            # on mets en majuscule et on rajoute _ au début du nom de la catégorie.
            trigger_name = f"_{self.categorie.upper()}"
            logger.info(f"category_trigger launched - ligne_article : {self.ligne_article} - trigger_name : {trigger_name}")
            trigger = getattr(self, f"trigger{trigger_name}")
            trigger()
        except AttributeError:
            logger.info(f"Pas de trigger pour la categorie {self.categorie}")
        except Exception as exc:
            logger.error(f"category_trigger ERROR : {exc} - {type(exc)}")

    # Categorie BILLET
    def trigger_B(self):
        logger.info(f"TRIGGER BILLET")

    # Categorie RECHARGE_CASHLESS
    def trigger_R(self):
        self.data_for_cashless['recharge_qty'] = self.ligne_article.pricesold.prix
        self.data_for_cashless['uuid'] = self.ligne_article.carte.uuid
        logger.info(f"TRIGGER RECHARGE_CASHLESS")

    # Categorie ADHESION
    def trigger_A(self):
        self.data_for_cashless['tarif_adhesion'] = self.ligne_article.pricesold.prix
        logger.info(f"TRIGGER ADHESION")

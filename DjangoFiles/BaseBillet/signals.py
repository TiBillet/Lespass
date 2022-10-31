import requests
from django.db import connection
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
# from django.utils import timezone

# from ApiBillet.thread_mailer import ThreadMaileur
from AuthBillet.models import TibilletUser
from BaseBillet.models import Reservation, LigneArticle, Ticket, Product, Configuration, Paiement_stripe
from BaseBillet.tasks import ticket_celery_mailer, webhook_reservation, wallet_update_celery

# from TiBillet import settings
from BaseBillet.triggers import ActionArticlePaidByCategorie

import logging

from QrcodeCashless.models import Wallet

logger = logging.getLogger(__name__)


########################################################################
######################## SIGNAL PRE & POST SAVE ########################
########################################################################


######################## SIGNAL PAIEMENT STRIPE ########################


def set_ligne_article_paid(old_instance, new_instance):
    # Type :
    old_instance: Paiement_stripe
    new_instance: Paiement_stripe

    logger.info(f"    SIGNAL PAIEMENT STRIPE set_ligne_article_paid {new_instance}.")
    logger.info(f"        On passe toutes les lignes d'article non validées en payées !")

    lignes_article = new_instance.lignearticle_set.exclude(status=LigneArticle.VALID)
    for ligne_article in lignes_article:
        logger.info(f"            {ligne_article.pricesold} {ligne_article.status} to P")
        ligne_article.status = LigneArticle.PAID
        ligne_article.save()

    # s'il y a une réservation, on la met aussi en payée :
    if new_instance.reservation:
        new_instance.reservation.status = Reservation.PAID
        new_instance.reservation.save()
    # except new_instance.reservation.RelatedObjectDoesNotExist:


def expire_paiement_stripe(old_instance, new_instance):
    logger.info(f"    SIGNAL PAIEMENT STRIPE expire_paiement_stripe {old_instance.status} to {new_instance.status}")
    pass


def valide_stripe_paiement(old_instance, new_instance):
    logger.info(f"    SIGNAL PAIEMENT STRIPE valide_stripe_paiement {old_instance.status} to {new_instance.status}")


######################## SIGNAL LIGNE ARTICLE ########################

# post_save ici nécéssaire pour mettre a jour le status du paiement stripe en validé
# si toutes les lignes articles sont save en VALID.
# @receiver(post_save, sender=LigneArticle)

def set_paiement_stripe_valid(old_instance: LigneArticle, new_instance: LigneArticle):
    if new_instance.status == LigneArticle.VALID:
        # Si paiement stripe :
        if new_instance.paiement_stripe:
            logger.info(
                f"    SIGNAL LIGNE ARTICLE set_paiement_and_reservation_valid {new_instance.pricesold}. On test si toute les lignes sont validées")

            # On exclut l'instance en cours, car elle n'est pas encore validée en DB : on est sur du signal pre_save
            # on teste ici : Si toutes les autres lignes sont valides et que celle ci l'est aussi.
            lignes_meme_panier = new_instance.paiement_stripe.lignearticle_set.all().exclude(
                uuid=new_instance.uuid)
            lignes_meme_panier_valide = lignes_meme_panier.filter(status=LigneArticle.VALID).exclude(
                uuid=new_instance.uuid)

            # Si toutes les lignes du même panier sont validés
            if len(lignes_meme_panier) == len(lignes_meme_panier_valide):
                # on passe le status du paiement stripe en VALID
                logger.info(
                    f"         paiement stripe {new_instance.paiement_stripe} {new_instance.paiement_stripe.status} à VALID")
                new_instance.paiement_stripe.status = Paiement_stripe.VALID
                new_instance.paiement_stripe.traitement_en_cours = False
                new_instance.paiement_stripe.save()
            else:
                logger.info(
                    f"         len(lignes_meme_panier) {len(lignes_meme_panier)} != len(lignes_meme_panier_valide) {len(lignes_meme_panier_valide)} ")

'''
def send_to_cashless(instance: LigneArticle):
    logger.info(f"        send_to_cashless {instance.pricesold}")
    data_for_cashless = {'uuid_commande': instance.paiement_stripe.uuid}
    data_for_cashless['uuid'] = instance.carte.uuid

    if instance.pricesold.productsold.product.categorie_article == Product.RECHARGE_CASHLESS:
        data_for_cashless['recharge_qty'] = instance.pricesold.prix

    if instance.pricesold.productsold.product.categorie_article == Product.ADHESION:
        data_for_cashless['tarif_adhesion'] = instance.pricesold.prix

    # s'il y a des données à envoyer au serveur cashless :
    sess = requests.Session()
    configuration = Configuration.get_solo()
    r = sess.post(
        f'{configuration.server_cashless}/api/billetterie_endpoint',
        headers={
            'Authorization': f'Api-Key {configuration.key_cashless}'
        },
        data=data_for_cashless,
    )

    sess.close()
    logger.info(
        f"        demande au serveur cashless pour {instance.pricesold}. réponse : {r.status_code} ")

    if r.status_code != 200:
        logger.error(
            f"erreur réponse serveur cashless {r.status_code} {r.text} pour paiement stripe {instance.pricesold} uuid {instance.uuid}")

    return r.status_code
'''


def check_paid(old_instance: LigneArticle, new_instance: LigneArticle):
    logger.info(
        f"    SIGNAL LIGNE ARTICLE check_paid {old_instance.pricesold} new_instance status : {new_instance.status}")
    ActionArticlePaidByCategorie(new_instance)
    logger.info(
        f"    SIGNAL LIGNE ARTICLE check_paid {old_instance.pricesold} new_instance status : {new_instance.status}")
    set_paiement_stripe_valid(old_instance, new_instance)

    '''
    if new_instance.pricesold.productsold.product.categorie_article in \
            [Product.RECHARGE_CASHLESS, Product.ADHESION]:
        if send_to_cashless(new_instance) == 200:
            new_instance.status = LigneArticle.VALID
    '''


######################## SIGNAL RESERVATION ########################

# @receiver(post_save, sender=Reservation)
# def send_billet_to_mail(sender, instance: Reservation, **kwargs):
def send_billet_to_mail(old_instance: Reservation, new_instance: Reservation):
    # On check les webhooks
    webhook_reservation.delay(new_instance.pk)

    # On active les tickets
    if new_instance.tickets:
        # On prend aussi ceux qui sont déja activé ( avec les Q() )
        # pour pouvoir les envoyer par mail en cas de nouvelle demande
        for ticket in new_instance.tickets.filter(Q(status=Ticket.NOT_ACTIV) | Q(status=Ticket.NOT_SCANNED)):
            logger.info(f'signal_reservation, activation des tickets {ticket} NOT_SCANNED')
            ticket.status = Ticket.NOT_SCANNED
            ticket.save()

    # import ipdb; ipdb.set_trace()

    # On vérifie que le mail n'a pas déja été envoyé
    if not new_instance.mail_send:
        logger.info(f"    SIGNAL RESERVATION send_billet_to_mail {new_instance.status}")

        if new_instance.user_commande.email:
            # import ipdb; ipdb.set_trace()
            base_url = f"https://{connection.tenant.get_primary_domain().domain}"
            task = ticket_celery_mailer.delay(new_instance.pk, base_url)
            # https://github.com/psf/requests/issues/5832
    else:
        logger.info(
            f"    SIGNAL RESERVATION mail déja envoyé {new_instance} : {new_instance.mail_send} - status : {new_instance.status}")
        set_paiement_valid(old_instance, new_instance)


def set_paiement_valid(old_instance: Reservation, new_instance: Reservation):
    # On envoie les mails
    if new_instance.mail_send:
        logger.info(
            f"    SIGNAL RESERVATION set_paiement_valid Mail envoyé {new_instance.mail_send},"
            f" on valide les paiements payés")
        for paiement in new_instance.paiements.filter(status=Paiement_stripe.PAID):
            paiement.status = Paiement_stripe.VALID
            paiement.traitement_en_cours = False
            paiement.save()


def error_in_mail(old_instance: Reservation, new_instance: Reservation):
    logger.info(f"    SIGNAL RESERVATION error_in_mail")
    new_instance.paiements.all().update(traitement_en_cours=False)
    # TODO: Prévenir l'admin q'un billet a été acheté, mais pas envoyé


######################## SIGNAL TIBILLETUSER ########################

def activator_free_reservation(old_instance: TibilletUser, new_instance: TibilletUser):
    logger.info(f"activator_free_reservation : {new_instance}")
    if connection.tenant.schema_name != "public" :
        free_reservation = Reservation.objects.filter(
            user_commande=new_instance,
            to_mail=True,
            status=Reservation.FREERES
        )

        for resa in free_reservation:
            print(f"    {resa}")
            resa.status = Reservation.FREERES_USERACTIV
            resa.save()

######################## MOTEUR SIGNAL ########################

def error_regression(old_instance, new_instance):
    logger.info(f"models_signal erreur_regression {old_instance.status} to {new_instance.status}")
    logger.error(f"######################## error_regression ########################")
    # raise Exception('Regression de status impossible.')
    pass


def test_signal(old_instance, new_instance):
    logger.info(f"Test signal instance : {new_instance} - Status : {new_instance.status}")


# On déclare les transitions possibles entre différents etats des statuts.
# Exemple première ligne : Si status passe de PENDING vers PAID, alors on lance set_ligne_article_paid

PRE_SAVE_TRANSITIONS = {
    'PAIEMENT_STRIPE': {
        Paiement_stripe.PENDING: {
            Paiement_stripe.PAID: set_ligne_article_paid,
            Paiement_stripe.EXPIRE: expire_paiement_stripe,
            Paiement_stripe.CANCELED: expire_paiement_stripe,
        },
        Paiement_stripe.EXPIRE: {
            Paiement_stripe.PAID: set_ligne_article_paid,
        },
        Paiement_stripe.PAID: {
            Paiement_stripe.PAID: set_ligne_article_paid,
            Paiement_stripe.VALID: valide_stripe_paiement,
            '_else_': error_regression,
        },
        Paiement_stripe.VALID: {
            '_all_': error_regression,
        }
    },

    'LIGNEARTICLE': {
        LigneArticle.CREATED: {
            LigneArticle.PAID: check_paid,
        },
        LigneArticle.UNPAID: {
            LigneArticle.PAID: check_paid,
        },
        LigneArticle.PAID: {
            LigneArticle.PAID: check_paid,
            LigneArticle.VALID: set_paiement_stripe_valid,
            '_else_': error_regression,
        },
        LigneArticle.VALID: {
            '_all_': error_regression,
        }
    },

    'RESERVATION': {
        Reservation.CREATED: {
            Reservation.PAID: send_billet_to_mail,
            Reservation.FREERES_USERACTIV : send_billet_to_mail,
        },
        Reservation.FREERES:{
            Reservation.FREERES_USERACTIV : send_billet_to_mail,
        },
        Reservation.FREERES_USERACTIV: {
            Reservation.FREERES_USERACTIV: send_billet_to_mail,
        },
        Reservation.UNPAID: {
            Reservation.PAID: send_billet_to_mail,
        },
        Reservation.PAID: {
            Reservation.PAID_ERROR: error_in_mail,
            Reservation.PAID: send_billet_to_mail,
            Reservation.VALID: set_paiement_valid,
            '_else_': error_regression,
        },
        Reservation.VALID: {
            '_all_': error_regression,
        }
    },

    'TIBILLETUSER': {
        False: {
            True: activator_free_reservation,
        }
    },
}


@receiver(pre_save)
def pre_save_signal_status(sender, instance, **kwargs):
    # logger.info(f"pre_save_signal_status. Sender : {sender} - Instance : {instance}")
    # if not create
    if not instance._state.adding:
        sender_str = sender.__name__.upper()
        dict_transition = PRE_SAVE_TRANSITIONS.get(sender_str)

        if dict_transition:
            old_instance = sender.objects.get(pk=instance.pk)
            new_instance = instance

            # Trick pour les status qui s'appellent différement que status
            CALLABLE_STATUS_MODEL = {'TIBILLETUSER': 'is_active'}
            if CALLABLE_STATUS_MODEL.get(sender_str):
                old_instance.status = getattr(old_instance, CALLABLE_STATUS_MODEL.get(sender_str))
                new_instance.status = getattr(new_instance, CALLABLE_STATUS_MODEL.get(sender_str))

            logger.info(f"dict_transition {sender_str} {new_instance} : {old_instance.status} to {new_instance.status}")
            transitions = dict_transition.get(old_instance.status, None)
            if transitions:
                # Par ordre de préférence :
                trigger_function = transitions.get('_all_', (
                    transitions.get(new_instance.status, (
                        transitions.get('_else_', None)
                    ))))

                if trigger_function:
                    if not callable(trigger_function):
                        raise Exception(f'Fonction {trigger_function} is not callable. Disdonc !?')
                    trigger_function(old_instance, new_instance)



@receiver(pre_save, sender=Wallet)
def wallet_update_to_celery(sender, instance: Wallet, **kwargs):
    if instance.asset.is_federated:
        old_instance = sender.objects.get(pk=instance.pk)
        new_instance = instance

        if old_instance.qty != new_instance.qty:
            logger.info(f"wallet_update_celery : need update cashless serveur")
            # update all cashless serveur
            wallet_update_celery.delay(instance.pk)

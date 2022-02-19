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

from BaseBillet.triggers import action_article_paid_by_categorie

logger = logging.getLogger(__name__)


########################################################################
######################## SIGNAL PRE & POST SAVE ########################
########################################################################


######################## TRIGGER PAIEMENT STRIPE ########################


def set_ligne_article_paid(old_instance, new_instance):
    # Type :
    old_instance: Paiement_stripe
    new_instance: Paiement_stripe

    logger.info(f"    TRIGGER PAIEMENT STRIPE set_ligne_article_paid {new_instance}.")
    logger.info(f"        On passe toutes les lignes d'article non validées en payées !")

    lignes_article = new_instance.lignearticle_set.exclude(status=LigneArticle.VALID)
    for ligne_article in lignes_article:
        logger.info(f"            {ligne_article.pricesold} {ligne_article.status} to P")
        ligne_article.status = LigneArticle.PAID
        ligne_article.save()

    # si ya une reservation, on la met aussi en payée :
    # try :
    if new_instance.reservation:
        new_instance.reservation.status = Reservation.PAID
        new_instance.reservation.save()
    # except new_instance.reservation.RelatedObjectDoesNotExist:


def expire_paiement_stripe(old_instance, new_instance):
    logger.info(f"    TRIGGER PAIEMENT STRIPE expire_paiement_stripe {old_instance.status} to {new_instance.status}")
    pass


def valide_stripe_paiement(old_instance, new_instance):
    logger.info(f"    TRIGGER PAIEMENT STRIPE valide_stripe_paiement {old_instance.status} to {new_instance.status}")


######################## TRIGGER LIGNE ARTICLE ########################

# post_save ici nécéssaire pour mettre a jour le status du paiement stripe en validé
# si toutes les lignes articles sont save en VALID.
# @receiver(post_save, sender=LigneArticle)

def set_paiement_and_reservation_valid(old_instance: LigneArticle, new_instance: LigneArticle):
    if new_instance.status == LigneArticle.VALID:
        logger.info(
            f"    TRIGGER LIGNE ARTICLE set_paiement_and_reservation_valid {new_instance.pricesold}. On test si toute les lignes sont validées")

        # On exclu l'instance en cours car elle n'est pas encore validé en DB comme Valide : on est sur du signal pre_save
        # on test ici : Si toute les autre ligne sont valide et que celle ci l'est aussi.
        lignes_dans_paiement_stripe = new_instance.paiement_stripe.lignearticle_set.all().exclude(
            uuid=new_instance.uuid)
        lignes_valide_dans_paiement_stripe = lignes_dans_paiement_stripe.filter(status=LigneArticle.VALID).exclude(
            uuid=new_instance.uuid)

        if len(lignes_dans_paiement_stripe) == len(lignes_valide_dans_paiement_stripe):
            # on passe le status du paiement stripe en VALID
            logger.info(
                f"         paiement stripe {new_instance.paiement_stripe} {new_instance.paiement_stripe.status} à VALID")
            new_instance.paiement_stripe.status = Paiement_stripe.VALID
            new_instance.paiement_stripe.traitement_en_cours = False
            new_instance.paiement_stripe.save()
        else:
            logger.info(
                f"         len(lignes_dans_paiement_stripe) {len(lignes_dans_paiement_stripe)} != len(lignes_valide_dans_paiement_stripe) {len(lignes_valide_dans_paiement_stripe)} ")


def send_to_cashless(instance: LigneArticle):
    logger.info(f"        send_to_cashless {instance.pricesold}")
    data_for_cashless = {'uuid_commande': instance.paiement_stripe.uuid}
    data_for_cashless['uuid'] = instance.carte.uuid

    if instance.pricesold.productsold.product.categorie_article == Product.RECHARGE_CASHLESS:
        data_for_cashless['recharge_qty'] = instance.pricesold.prix

    if instance.pricesold.productsold.product.categorie_article == Product.ADHESION:
        data_for_cashless['tarif_adhesion'] = instance.pricesold.prix

    # si il y a des données a envoyer au serveur cashless :
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



def check_paid(old_instance: LigneArticle, new_instance: LigneArticle):
    logger.info(f"    TRIGGER LIGNE ARTICLE check_paid {old_instance.pricesold}")
    action_article_paid_by_categorie(new_instance)

    if new_instance.pricesold.productsold.product.categorie_article in \
            [Product.RECHARGE_CASHLESS, Product.ADHESION]:
        if send_to_cashless(new_instance) == 200:
            new_instance.status = LigneArticle.VALID
            set_paiement_and_reservation_valid(old_instance, new_instance)


######################## TRIGGER RESERVATION ########################


# @receiver(post_save, sender=Reservation)
# def send_billet_to_mail(sender, instance: Reservation, **kwargs):
def send_billet_to_mail(old_instance, new_instance):
    # On active les tickets
    if new_instance.tickets:
        # On prend aussi ceux qui sont déja activé ( avec les Q() )
        # pour pouvoir les envoyer par mail en cas de nouvelle demande
        for ticket in new_instance.tickets.filter(Q(status=Ticket.NOT_ACTIV) | Q(status=Ticket.NOT_SCANNED)):
            logger.info(f'trigger_reservation, activation des tickets {ticket} NOT_SCANNED')
            ticket.status = Ticket.NOT_SCANNED
            ticket.save()

    # import ipdb; ipdb.set_trace()
    # On vérifie qu'on a pas déja envoyé le mail
    if not new_instance.mail_send:
        logger.info(f"    TRIGGER RESERVATION send_billet_to_mail {new_instance.status}")
        new_instance: Reservation

        if new_instance.user_commande.email:
            # import ipdb; ipdb.set_trace()
            task = ticket_celery_mailer.delay(new_instance.pk)
            # https://github.com/psf/requests/issues/5832
    else:
        logger.info(
            f"    TRIGGER RESERVATION mail déja envoyé {new_instance} : {new_instance.mail_send} - status : {new_instance.status}")
        set_paiement_valid(old_instance, new_instance)


def set_paiement_valid(old_instance, new_instance):
    new_instance: Reservation
    if new_instance.mail_send:
        logger.info(
            f"    TRIGGER RESERVATION set_paiement_valid Mail envoyé {new_instance.mail_send}, on valide les paiements payés")
        for paiement in new_instance.paiements.filter(status=Paiement_stripe.PAID):
            paiement.status = Paiement_stripe.VALID
            paiement.traitement_en_cours = False
            paiement.save()


def error_in_mail(old_instance, new_instance):
    logger.info(f"    TRIGGER RESERVATION error_in_mail")
    new_instance.paiements.all().update(traitement_en_cours=False)
    # TODO: Prévenir l'admin q'un billet a été acheté, mais pas envoyé


######################## MOTEUR TRIGGER ########################

def error_regression(old_instance, new_instance):
    logger.info(f"models_trigger erreur_regression {old_instance.status} to {new_instance.status}")
    logger.error(f"######################## error_regression ########################")
    # raise Exception('Regression de status impossible.')
    pass


# On déclare les transitions possibles entre différents etats des statuts.
# Exemple première ligne : Si status passe de PENDING vers PAID, alors on lance set_ligne_article_paid

TRANSITIONS = {
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
            LigneArticle.VALID: set_paiement_and_reservation_valid,
            '_else_': error_regression,
        },
        LigneArticle.VALID: {
            '_all_': error_regression,
        }
    },

    'RESERVATION': {
        Reservation.CREATED: {
            Reservation.PAID: send_billet_to_mail,
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
}


@receiver(pre_save)
def pre_save_signal_status(sender, instance, **kwargs):
    # if not create
    if not instance._state.adding:
        sender_str = sender.__name__.upper()
        dict_transition = TRANSITIONS.get(sender_str)
        if dict_transition:
            old_instance = sender.objects.get(pk=instance.pk)
            new_instance = instance

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

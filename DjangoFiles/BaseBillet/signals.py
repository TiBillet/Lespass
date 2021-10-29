import requests
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from BaseBillet.models import Reservation, LigneArticle, Ticket, Product, Configuration
import logging

from PaiementStripe.models import Paiement_stripe

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Reservation)
def trigger_reservation(sender, instance: Reservation, created, **kwargs):
    if instance.status == Reservation.PAID:
        if instance.tickets:
            for ticket in instance.tickets.filter(status=Ticket.NOT_ACTIV):
                logger.info(f'trigger_reservation, activation des tickets {ticket} NOT_SCANNED')
                ticket.status = Ticket.NOT_SCANNED
                ticket.save()


@receiver(pre_save, sender=LigneArticle)
def trigger_LigneArticle(sender, instance: LigneArticle, update_fields=None, **kwargs):
    # if not created
    if not instance._state.adding:
        old_instance = sender.objects.get(pk=instance.pk)
        new_instance = pre_save_signal_status(old_instance, instance)


@receiver(pre_save, sender=Paiement_stripe)
def trigger_paiement_stripe(sender, instance: Paiement_stripe, update_fields=None, **kwargs):
    # if not create
    if not instance._state.adding:
        old_instance = sender.objects.get(pk=instance.pk)
        new_instance = pre_save_signal_status(old_instance, instance)


########################################################################
######################## SIGNAL PRE & POST SAVE ########################
########################################################################


######################## TRIGGER LIGNE ARTICLE ########################

# post_save ici nécéssaire pour mettre a jour le status du paiement stripe en validé
# si toutes les lignes articles sont VALID.
@receiver(post_save, sender=LigneArticle)
def set_paiement_and_reservation_valid(sender, instance: LigneArticle, **kwargs):
    if instance.status == LigneArticle.VALID:
        lignes_dans_paiement_stripe = instance.paiement_stripe.lignearticle_set.all()
        if len(lignes_dans_paiement_stripe) == len(lignes_dans_paiement_stripe.filter(status=LigneArticle.VALID)):
            # on passe le status du paiement stripe en VALID
            logger.info(f"    TRIGGER LIGNE ARTICLE set_paiement_and_reservation_valid {instance.price} "
                        f"paiement stripe {instance.paiement_stripe} {instance.paiement_stripe.status} à VALID")
            instance.paiement_stripe.status = Paiement_stripe.VALID
            instance.paiement_stripe.save()


def check_paid(old_instance, new_instance):
    # Type :
    old_instance: LigneArticle
    new_instance: LigneArticle
    logger.info(f"    TRIGGER LIGNE ARTICLE check_paid {old_instance.price}")

    if new_instance.price.product.categorie_article in \
            [Product.RECHARGE_CASHLESS, Product.ADHESION]:
        send_to_cashless(new_instance)


def send_to_cashless(instance):
    # Type :
    instance: LigneArticle

    logger.info(f"        send_to_cashless {instance.price}")
    data_for_cashless = {'uuid_commande': instance.paiement_stripe.uuid}
    data_for_cashless['uuid'] = instance.carte.uuid

    if instance.price.product.categorie_article == Product.RECHARGE_CASHLESS:
        data_for_cashless['recharge_qty'] = instance.price.prix

    if instance.price.product.categorie_article == Product.ADHESION:
        data_for_cashless['tarif_adhesion'] = instance.price.prix

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
        f"        demande au serveur cashless pour un rechargement. réponse : {r.status_code} ")

    if r.status_code == 200:
        instance.status = LigneArticle.VALID
    else:
        logger.error(
            f"erreur réponse serveur cashless {r.status_code} {r.text} pour paiement stripe {instance.price} uuid {instance.uuid}")


######################## TRIGGER PAIEMENT STRIPE ########################


def set_ligne_article_paid(old_instance, new_instance):
    # Type :
    old_instance: Paiement_stripe
    new_instance: Paiement_stripe

    logger.info(f"    TRIGGER PAIEMENT STRIPE set_ligne_article_paid {old_instance}.")
    logger.info(f"        On passe toutes les lignes d'article non validées en payées !")

    lignes_article = new_instance.lignearticle_set.exclude(status=LigneArticle.VALID)
    for ligne_article in lignes_article:
        logger.info(f"            {ligne_article.price} {ligne_article.status} to P]")
        ligne_article.status = LigneArticle.PAID
        ligne_article.save()

    # si ya une reservation, on la met aussi en payée :
    if new_instance.reservation:
        new_instance.reservation.status = Reservation.PAID
        new_instance.reservation.save()


def expire_paiement_stripe(old_instance, new_instance):
    logger.info(f"    TRIGGER PAIEMENT STRIPE expire_paiement_stripe {old_instance.status} to {new_instance.status}")
    pass


def valide_stripe_paiement(old_instance, new_instance):
    logger.info(f"    TRIGGER PAIEMENT STRIPE valide_stripe_paiement {old_instance.status} to {new_instance.status}")
    pass

######################## TRIGGER RESERVATION ########################


def send_billet_to_mail(old_instance, new_instance):
    logger.info(f"    TRIGGER RESERVATION send_billet_to_mail {old_instance.status} to {new_instance.status}")
    pass


######################## MOTEUR TRIGGER ########################

def error_regression(old_instance, new_instance):
    logger.info(f"models_trigger erreur_regression {old_instance.status} to {new_instance.status}")
    logger.error(f"######################## error_regression ########################")
    # raise Exception('Regression de status impossible.')
    pass


# def pass(old_instance, new_instance):

# On déclare les transitions possibles entre différents etats des statuts.
# Exemple première ligne : Si status passe de PENDING vers PAID, alors on lance set_ligne_article_paid
class Transitions():
    ''''''
    '''
        Reservation choices :
        (CANCELED, _('Annulée')),
        (UNPAID, _('Non payée')),
        (PAID, _('Payée')),
        (VALID, _('Validée')),
    '''
    RESERVATION = {
        Reservation.UNPAID: {
            Reservation.PAID : send_billet_to_mail
        },
        Reservation.PAID: {
            LigneArticle.PAID: send_billet_to_mail,
           '_else_': error_regression,
        },
        Reservation.VALID: {
            '_all_': error_regression,
        }
    }
    '''
        Paiement_stripe choices :
        (NON, 'Lien de paiement non créé'),
        (OPEN, 'Envoyée a Stripe'),
        (PENDING, 'En attente de paiement'),
        (EXPIRE, 'Expiré'),
        (PAID, 'Payée'),
        (VALID, 'Payée et validée'),  # envoyé sur serveur cashless
        (CANCELED, 'Annulée'),
    '''
    PAIEMENT_STRIPE = {
        Paiement_stripe.PENDING: {
            Paiement_stripe.PAID: set_ligne_article_paid,
            Paiement_stripe.EXPIRE: expire_paiement_stripe,
            Paiement_stripe.CANCELED: expire_paiement_stripe,
        },
        Paiement_stripe.PAID: {
            Paiement_stripe.PAID: set_ligne_article_paid,
            Paiement_stripe.VALID: valide_stripe_paiement,
            '_else_': error_regression,
        },
        Paiement_stripe.VALID: {
            '_all_': error_regression,
        }
    }
    '''
        LigneArticle Choices :
        (CANCELED, _('Annulée')),
        (UNPAID, _('Non payée')),
        (PAID, _('Payée')),
        (VALID, _('Validée par serveur cashless')),
    '''
    LIGNEARTICLE = {
        LigneArticle.UNPAID: {
            LigneArticle.PAID: check_paid,
        },
        LigneArticle.PAID: {
            LigneArticle.PAID: check_paid,
            # LigneArticle.VALID: valide_stripe_paiement,
            '_else_': error_regression,
        },
        LigneArticle.VALID: {
            '_all_': error_regression,
        }
    }


def pre_save_signal_status(old_instance, new_instance):
    # import ipdb; ipdb.set_trace()
    sender_str = old_instance.__class__.__name__.upper()
    dict_transition = getattr(Transitions, f"{sender_str}", None)
    if dict_transition:
        logger.info(f"dict_transition {sender_str} {new_instance} : {old_instance.status} to {new_instance.status}")
        transitions = dict_transition.get(old_instance.status, None)
        if transitions:
            # Par ordre de préférence :
            trigger_function = transitions.get('_all_', (
                transitions.get(new_instance.status, (
                    transitions.get('_else_', None)
                ))))

            if trigger_function:
                # import ipdb; ipdb.set_trace()

                if not callable(trigger_function):
                    raise Exception(f'Fonction {trigger_function} is not callable. Disdonc !?')
                trigger_function(old_instance, new_instance)

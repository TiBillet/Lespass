import logging

from django.db import connection
from django.db.models import Q
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from ApiBillet.serializers import get_or_create_price_sold
from AuthBillet.models import TibilletUser
from BaseBillet.models import Reservation, LigneArticle, Ticket, Paiement_stripe, Product, Price, \
    PaymentMethod, Membership, SaleOrigin
from BaseBillet.tasks import ticket_celery_mailer, webhook_reservation
from BaseBillet.triggers import TRIGGER_LigneArticlePaid_ActionByCategorie
from fedow_connect.fedow_api import AssetFedow
from fedow_connect.models import FedowConfig

logger = logging.getLogger(__name__)


########################################################################
######################## SIGNAL PRE & POST SAVE ########################
########################################################################


######################## SIGNAL PAIEMENT STRIPE ########################


def set_ligne_article_paid(old_instance: Paiement_stripe, new_instance: Paiement_stripe):
    # Type :
    logger.info(
        f"    START PAIEMENT_STRIPE set_ligne_article_paid {new_instance} -> {old_instance.status} to {new_instance.status}")

    logger.info(f"        On passe toutes les ligne_article non validées en PAID et save() :")
    lignes_article = new_instance.lignearticles.exclude(status=LigneArticle.VALID)
    for ligne_article in lignes_article:
        # Chaque passage en PAID activera le pre_save triggers.LigneArticlePaid_ActionByCategorie
        # # Si toutes les lignes sont validées, ça met le paiement stripe en valid via set_paiement_stripe_valid
        ligne_article.payment_method = PaymentMethod.STRIPE_NOFED
        logger.info(f"            {ligne_article.pricesold} {ligne_article.status} to {LigneArticle.PAID} : save()")
        ligne_article.status = LigneArticle.PAID
        ligne_article.save()

    # s'il y a une réservation, on la met aussi en payée :
    if new_instance.reservation:
        logger.info(
            f"        PAIEMENT_STRIPE set_ligne_article_paid : Toutes les ligne_article on été passé en {LigneArticle.PAID} et on été save()")
        logger.info(f"        On passe la reservation en PAID et save()")
        new_instance.reservation.status = Reservation.PAID
        new_instance.reservation.save()

    logger.info(f"    END PAIEMENT_STRIPE set_ligne_article_paid\n")


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
    logger.info(
        f"    START SIGNAL LIGNE_ARTICLE set_paiement_stripe_valid {old_instance.status} to {new_instance.status}")
    if new_instance.status == LigneArticle.VALID:
        # Si paiement stripe :
        if new_instance.paiement_stripe:

            # On exclut l'instance en cours, car elle n'est pas encore validée en DB : on est sur du signal pre_save
            # on teste ici : Si toutes les autres lignes sont valides et que celle ci l'est aussi.
            lignes_meme_panier = new_instance.paiement_stripe.lignearticles.all().exclude(
                uuid=new_instance.uuid)
            lignes_meme_panier_valide = lignes_meme_panier.filter(status=LigneArticle.VALID).exclude(
                uuid=new_instance.uuid)

            # Si toutes les lignes du même panier sont validés
            logger.info(
                f"        On test si toute les autres lignes sont validées : {len(lignes_meme_panier) == len(lignes_meme_panier_valide)}")
            if len(lignes_meme_panier) == len(lignes_meme_panier_valide):
                # on passe le status du paiement stripe en VALID
                logger.info(
                    f"         OK ! Toute les lignes sont valides, on passe le paiement_stripe {new_instance.paiement_stripe} de {new_instance.paiement_stripe.status} à {Paiement_stripe.VALID}")
                new_instance.paiement_stripe.status = Paiement_stripe.VALID
                logger.info(f"        paiement_stripe traitement_en_cours = False")
                new_instance.paiement_stripe.traitement_en_cours = False
                new_instance.paiement_stripe.save()
            else:
                logger.info(
                    f"         PAS OK, il doit y avoir d'autres lignes à valider : {len(lignes_meme_panier)} != {len(lignes_meme_panier_valide)}")

    logger.info(
        f"    END SIGNAL LIGNE_ARTICLE set_paiement_stripe_valid {old_instance.status} to {new_instance.status}\n")


def ligne_article_paid(old_instance: LigneArticle, new_instance: LigneArticle):
    # MACHINE A ETAT pour les ventes, activé lorsque LigneArticle passe à PAID
    # Actions qui se lancent en fonction de la catégorie d'article ( adhésion, don, reservation, etc ... )
    logger.info(
        f"    LIGNE ARTICLE ligne_article_paid {new_instance} -> {old_instance.status} to {new_instance.status}")
    TRIGGER_LigneArticlePaid_ActionByCategorie(new_instance)

    # Si toutes les lignes sont validées, ça met le paiement stripe en valid.
    set_paiement_stripe_valid(old_instance, new_instance)


######################## SIGNAL RESERVATION ########################

# @receiver(post_save, sender=Reservation)
# def send_billet_to_mail(sender, instance: Reservation, **kwargs):
def reservation_paid(old_instance: Reservation, new_instance: Reservation):
    # Toutes les ligne_article on été passé, cela déclanche le reservation status PAID et le SAVE
    logger.info(f"    START SIGNAL RESERVATION reservation_paid {old_instance.status} to {new_instance.status}")

    logger.info(f"        Check webhook send")
    webhook_reservation.delay(new_instance.pk)

    logger.info(f"        On active les tickets")
    if new_instance.tickets:
        # On prend aussi ceux qui sont déja activé ( avec les Q() )
        # pour pouvoir les envoyer par mail en cas de nouvelle demandes
        for ticket in new_instance.tickets.filter(Q(status=Ticket.NOT_ACTIV) | Q(status=Ticket.NOT_SCANNED)):
            logger.info(f'         {ticket} : {ticket.status} to {ticket.NOT_SCANNED} && save()')
            ticket.status = Ticket.NOT_SCANNED
            ticket.save()

    # On vérifie que le mail n'a pas déja été envoyé
    if not new_instance.mail_send:
        # Envoie du mail. Le succes du mail envoyé mettra la Reservation.VALID
        if new_instance.user_commande.email:
            logger.info(
                f"         Envoie du mail via celery à {new_instance.user_commande.email}. Celery passera la Reservation à VALID")
            ticket_celery_mailer.delay(new_instance.pk)  # met la Reservation à VALID si mail envoyé

    else:
        # Dans quel cas cela arrive ? TODO: checker ?
        logger.info(f"         mail déja envoyé : {new_instance.mail_send}")
        # Le mail a déja été envoyé
        set_paiement_valid(old_instance, new_instance)

    logger.info(f"    END SIGNAL RESERVATION reservation_paid\n")


def set_paiement_valid(old_instance: Reservation, new_instance: Reservation):
    logger.info(f"    START SIGNAL RESERVATION set_paiement_valid {old_instance.status} to {new_instance.status}")

    if new_instance.mail_send:
        logger.info(f"        Le mail a déja été envoyé, on valide les paiements payés")
        for paiement in new_instance.paiements.filter(status=Paiement_stripe.PAID):
            paiement.status = Paiement_stripe.VALID
            paiement.traitement_en_cours = False
            paiement.save()

    logger.info(f"    END SIGNAL RESERVATION set_paiement_valid\n")


def error_in_mail(old_instance: Reservation, new_instance: Reservation):
    logger.info(f"    SIGNAL RESERVATION error_in_mail")
    new_instance.paiements.all().update(traitement_en_cours=False)
    # TODO: Prévenir l'admin q'un billet a été acheté, mais pas envoyé


######################## SIGNAL TIBILLETUSER ########################

def activator_free_reservation(old_instance: TibilletUser, new_instance: TibilletUser):
    logger.info(f"activator_free_reservation : {new_instance}")
    if connection.tenant.schema_name != "public":
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
            LigneArticle.PAID: ligne_article_paid,
        },
        LigneArticle.UNPAID: {
            LigneArticle.PAID: ligne_article_paid,
        },
        LigneArticle.PAID: {
            LigneArticle.PAID: ligne_article_paid,
            LigneArticle.VALID: set_paiement_stripe_valid,
            '_else_': error_regression,
        },
        LigneArticle.VALID: {
            '_all_': error_regression,
        }
    },

    'RESERVATION': {
        Reservation.CREATED: {
            Reservation.PAID: reservation_paid,
            Reservation.FREERES_USERACTIV: reservation_paid,
        },
        Reservation.FREERES: {
            Reservation.FREERES_USERACTIV: reservation_paid,
        },
        Reservation.FREERES_USERACTIV: {
            Reservation.FREERES_USERACTIV: reservation_paid,
        },
        Reservation.UNPAID: {
            Reservation.PAID: reservation_paid,
        },
        Reservation.PAID: {
            Reservation.PAID_ERROR: error_in_mail,
            Reservation.PAID: reservation_paid,
            Reservation.VALID: set_paiement_valid,  # Celery passe la reservation a Valid si mail sended = True
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


# MACHINE A ETAT
# Pour tout les modèls qui possèdent un système de status choice
@receiver(pre_save)
def pre_save_signal_status(sender, instance, **kwargs):
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

            logger.info(
                f"\nSTART pre_save_signal_status {sender_str} {new_instance} : {old_instance.status} to {new_instance.status}\n")

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


@receiver(pre_save, sender=Product)
def unpublish_if_archived(sender, instance, **kwargs):
    if instance.archive:
        instance.publish = False


@receiver(post_save, sender=Product)
def send_membership_and_badge_product_to_fedow(sender, instance: Product, created, **kwargs):
    logger.info(f"send_membership_product_to_fedow")
    # Est ici pour éviter les double imports
    # vérifie l'existante du produit Adhésion et Badge dans Fedow et le créé si besoin
    if instance.categorie_article in [Product.ADHESION, Product.BADGE]:
        fedow_config = FedowConfig.get_solo()
        fedow_asset = AssetFedow(fedow_config=fedow_config)
        if not instance.archive:
            # Si l'adhésion n'est pas archivé, on vérifie qu'elle existe bien :
            asset, created = fedow_asset.get_or_create_asset(instance)
            logger.info(f"send_membership_product_to_fedow : created : {created} - asset {asset}")

        if instance.archive:
            # L'instance est archivé, on le notifie à Fedow :
            fedow_asset.archive_asset(instance)


@receiver(pre_save, sender=Price)
def price_if_free_set_t_1(sender, instance: Price, **kwargs):
    if instance.free_price:
        if instance.prix : # On met le prix a minimum à 1.
            if instance.prix < 1 :
                instance.prix = 1
        else :
            instance.prix = 1
        instance.max_per_user = 1

@receiver(post_save, sender=Membership)
def create_lignearticle_if_membership_created_on_admin(sender, instance: Membership, created, **kwargs):
    membership: Membership = instance
    # Pour une nouvelle adhésion réalisée sur l'admin et non offerte, une vente est enregitrée.
    if created and membership.status == Membership.ADMIN:
        logger.info(f"create_lignearticle_if_membership_created_on_admin {instance} {created}")

        vente = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(membership.price),
            qty=1,
            membership=membership,
            amount=int(membership.contribution_value * 100),
            payment_method=membership.payment_method,
            status=LigneArticle.CREATED,
        )

        # On lance les post_save et triggers associés au adhésions en passant en PAID
        # Envoie a la boutik, Fedow, webhook, etc ...
        vente.status = LigneArticle.PAID
        vente.save()


@receiver(post_save, sender=Ticket)
def create_lignearticle_if_ticket_created_on_admin(sender, instance: Ticket, created, **kwargs):
    ticket: Ticket = instance
    # Pour une nouvelle adhésion réalisée sur l'admin et non offerte, une vente est enregitrée.
    if created and ticket.sale_origin == SaleOrigin.ADMIN:
        logger.info(f"create_lignearticle_if_ticket_created_on_admin {instance} {created}")

        vente = LigneArticle.objects.create(
            pricesold=ticket.pricesold,
            qty=1,
            amount=int(ticket.pricesold.prix * 100),
            payment_method=ticket.payment_method,
            status=LigneArticle.CREATED,
        )

        # import ipdb; ipdb.set_trace()

        # On lance les post_save et triggers associés au adhésions en passant en PAID
        # Envoie a la boutik, Fedow, webhook, etc ...
        vente.status = LigneArticle.PAID
        vente.save()

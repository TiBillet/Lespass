import logging

from django.db import connection
from django.utils import timezone
from django.utils.text import slugify

from BaseBillet.models import LigneArticle, Product, Membership, Price, Configuration, Paiement_stripe
from BaseBillet.tasks import send_membership_to_cashless, send_to_ghost, send_email_generique, create_invoice_pdf
from django.utils.translation import gettext_lazy as _

from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig

logger = logging.getLogger(__name__)


### MEMBERSHIP TRIGGER : Lors qu'une vente article adhésion est PAID ####

def context_for_membership_email(membership: Membership = None, paiement_stripe=None):
    config = Configuration.get_solo()
    # domain = connection.tenant.get_primary_domain().domain

    context = {
        'username': membership.member_name(),
        'now': timezone.now(),
        'title': f"{config.organisation} : {membership.price.product.name}",
        'objet': _("Email de confirmation"),
        'sub_title': _("Bienvenue à bord !"),
        'main_text': _(
            f"Votre paiement pour {membership.price.product.name} à bien été pris en compte. Vous trouverez la facture en pièce jointe."),
        # 'main_text_2': _("Si vous pensez que cette demande est main_text_2, vous n'avez rien a faire de plus :)"),
        # 'main_text_3': _("Dans le cas contraire, vous pouvez main_text_3. Merci de contacter l'équipe d'administration via : contact@tibillet.re au moindre doute."),
        'table_info': {
            'Reçu pour': f'{membership.member_name()}',
            'Article': f'{membership.price.product.name}',
            'Tarif': f'{membership.price.name} {membership.price.prix} €',
            'Dernière contribution': f'{membership.last_contribution}',
            'Valable jusque': f'{membership.deadline()}',
        },
        'button_color': "#009058",
        # 'button': {
        #     'text': 'RECUPERER UNE FACTURE',
        #     'url': f'https://{domain}/memberships/{paiement_stripe.pk}/invoice/',
        # },
        'next_text_1': "Si vous recevez cet email par erreur, merci de contacter l'équipe de TiBillet",
        # 'next_text_2': "next_text_2",
        'end_text': 'A bientôt, et bon voyage',
        'signature': "Marvin, le robot de TiBillet",
    }
    # Ajout des options str si il y en a :
    if membership.option_generale.count() > 0:
        context['table_info']['Options'] = f"{membership.options()}"
    return context


def get_membership_after_paiement(trigger):
    paiement_stripe : Paiement_stripe = trigger.ligne_article.paiement_stripe
    user = paiement_stripe.user
    price: Price = trigger.ligne_article.pricesold.price
    product: Product = trigger.ligne_article.pricesold.productsold.product

    # On check s'il n'y a pas déjà une fiche membre avec le "price" correspondant
    membership = Membership.objects.filter(
        user=user,
        price=price
    ).first()
    logger.info(f"    membership trouvé : {membership}")

    if not membership:
        membership = Membership.objects.create(
            user=user,
            price=price,
            first_contribution = timezone.now().date(),
        )

    return membership


def update_membership_state_after_paiement(trigger, membership: Membership):
    paiement_stripe = trigger.ligne_article.paiement_stripe

    membership.last_contribution = timezone.now().date()
    membership.contribution_value = trigger.ligne_article.pricesold.prix
    membership.stripe_paiement.add(paiement_stripe)

    if paiement_stripe.invoice_stripe:
        membership.last_stripe_invoice = paiement_stripe.invoice_stripe

    if paiement_stripe.subscription:
        membership.stripe_id_subscription = paiement_stripe.subscription
        membership.status = Membership.AUTO

    membership.save()
    logger.info(f"    update_membership_state_after_paiement : Mise à jour de la fiche membre OK")
    return membership


def send_membership_invoice_email_after_paiement(trigger, membership: Membership):
    paiement_stripe = trigger.ligne_article.paiement_stripe
    user = paiement_stripe.user

    # Mails de confirmation et facture en PJ :
    logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email")
    send_email_generique.delay(
        context=context_for_membership_email(paiement_stripe=paiement_stripe, membership=membership),
        email=f"{user.email}",
        attached_files={
            f'{slugify(membership.member_name())}_{slugify(paiement_stripe.invoice_number())}_tibillet_invoice.pdf' :
                create_invoice_pdf(paiement_stripe)},
    )
    logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email DELAY")
    return True

def send_membership_to_ghost(membership: Membership):
    # Envoyer à ghost :
    if membership.newsletter:
        send_to_ghost.delay(membership.pk)
        logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation à Ghost DELAY")
    return True


### END MEMBERSHIP TRIGGER ####

### SEND TO LABOUTIK for comptabilité ###

def send_sale_to_laboutik(membership: Membership):
    return True

### END SEND TO LABOUTIK

class ActionArticlePaidByCategorie:
    """
    Trigged action by categorie when Article is PAID
    """

    def __init__(self, ligne_article: LigneArticle):
        self.ligne_article = ligne_article
        self.categorie = self.ligne_article.pricesold.productsold.categorie_article

        if self.categorie == Product.NONE:
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
            logger.error(f"category_trigger {self.categorie.upper()} ERROR : {exc} - {type(exc)}")

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
        logger.info(f"TRIGGER RECHARGE_CASHLESS")

    # Category RECHARGE_FEDERATED
    def trigger_S(self):
        logger.info(f"TRIGGER RECHARGE_FEDERATED")

    # Categorie ADHESION
    def trigger_A(self):
        logger.info(f"TRIGGER ADHESION")

        membership : Membership = get_membership_after_paiement(self)
        updated_membership : Membership = update_membership_state_after_paiement(self, membership)

        email_sended = send_membership_invoice_email_after_paiement(self, updated_membership)
        ghost_sended = send_membership_to_ghost(updated_membership)

        # Envoyer à fedow
        logger.info(f"TRIGGER ADHESION -> envoi à Fedow")
        fedow_config = FedowConfig.get_solo()
        fedowAPI = FedowAPI(fedow_config=fedow_config)
        serialized_transaction = fedowAPI.membership.create(membership=membership)

        # TODO: On a débranché le cashless, il ira chercher ses tokens tout seul comme un grand
        # laboutik_sended = send_sale_to_laboutik(updated_membership)

        # Si tout est passé plus haut, on VALID La ligne :
        # Tout ceci se déroule dans un pre_save signal.pre_save_signal_status()
        self.ligne_article.status = LigneArticle.VALID

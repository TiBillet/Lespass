import logging

from django.utils import timezone

from BaseBillet.models import LigneArticle, Product, Membership, Price
from BaseBillet.tasks import send_membership_to_cashless, send_to_ghost

logger = logging.getLogger(__name__)


def update_membership_state(trigger):
    paiement_stripe = trigger.ligne_article.paiement_stripe
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
        membership, created = Membership.objects.get_or_create(
            user=user,
        )
        membership.price = price

    # Si Membership a été créé juste avant ce paiement,
    # la first contribution est vide.
    if not membership.first_contribution:
        membership.first_contribution = timezone.now().date()

    membership.last_contribution = timezone.now().date()
    membership.contribution_value = trigger.ligne_article.pricesold.prix

    if paiement_stripe.invoice_stripe:
        membership.last_stripe_invoice = paiement_stripe.invoice_stripe

    if paiement_stripe.subscription:
        membership.stripe_id_subscription = paiement_stripe.subscription
        membership.status = Membership.AUTO

    membership.save()

    # TODO: On a débranché le cashless.
    import ipdb; ipdb.set_trace()
    # Envoyer à fedow
    # Envoyer les mails de confirmation
    # Envoyer les facture ici
    # Envoyer les contrats à signer ici

    # Envoyer à ghost :
    send_to_ghost.delay(membership.pk)

    trigger.ligne_article.status = LigneArticle.VALID


    return membership


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
        logger.info(f"TRIGGER RECHARGE_CASHLESS")

    # Category RECHARGE_FEDERATED
    def trigger_S(self):
        logger.info(f"TRIGGER RECHARGE_FEDERATED")

    # Categorie ADHESION
    def trigger_A(self):
        logger.info(f"TRIGGER ADHESION")
        membership = update_membership_state(self)


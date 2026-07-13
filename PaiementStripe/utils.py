import stripe
import logging
from stripe import InvalidRequestError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

def partial_refund_payment(paiement, config, ligne_articles, specified_quantity=None):
    """
    Refund a part of a payment.
    Refund all "ligne_articles". They must be linked to the "paiement"

    By default, it refunds the MAX qty from the ligne_articles. To only refund a part of it, you have two option :
    - pass the "specified_quantity" parameter : it will refund the indicated quantity on ALL "ligne_articles" -> The same for all lignes_articles
    - add "to_refund_qty" attribute to "ligne_articles" before calling this method, it will override the qty of the ligne_article-> Independent for all lignes_articles
    """
    from BaseBillet.models import Paiement_stripe, LigneArticle, SaleOrigin

    if specified_quantity == 0:
        raise Exception(_("Vous devez rembourser au moins un article"))

    for ligne_article in ligne_articles:
        if not paiement.lignearticles.filter(pk=ligne_article.pk).exists():
            raise Exception(_("Une LigneArticle n'est pas lié au bon paiement"))

    paiement: Paiement_stripe
    try:
        checkout = paiement.get_checkout_session()
        payment_intent = checkout.payment_intent
    except Exception:
        payment_intent = paiement.payment_intent_id

    try:
        total_refunded_amount = 0
        for ligne_article in ligne_articles:
            # If there is a specified_quantity, only refund the specified_quantity from the LigneBillet
            if specified_quantity:
                total_refunded_amount += ligne_article.amount * specified_quantity
            # If the ligne_article has a to_refund_qty, only refund the to_refund_qty from the LigneBillet
            elif hasattr(ligne_article, "to_refund_qty"):
                total_refunded_amount += ligne_article.amount * ligne_article.to_refund_qty
            else:
                total_refunded_amount += ligne_article.total() # It returns ligne_article.qty * ligne_article.amount

        # Si le montant à rembourser est inférieur à 1€, on passe l'étape du remboursement stripe
        if total_refunded_amount >= 1:
            refund = stripe.Refund.create(
                payment_intent=payment_intent,
                reason='requested_by_customer',
                amount=total_refunded_amount,
                stripe_account=config.get_stripe_connect_account()
            )
            logger.info(f"Refund stripe : {refund.status}")
            paiement.status = Paiement_stripe.PARTIALLY_REFUNDED
            paiement.save()

        for ligne_article in ligne_articles:
            # Update accounting line status to REFUNDED if it was VALID to trigger signals
            if ligne_article.status == LigneArticle.VALID:
                metadata = ligne_article.metadata if ligne_article.metadata else {}
                metadata['original_lignearticle_uuid'] = str(ligne_article.uuid)

                # Met refund_qty à :
                # specified_quantity (si spécifié)
                # sinon à : ligne_article.to_refund_qty (si spécifié)
                # Et sinon juste à ligne_article.qty
                refund_qty = ligne_article.qty
                if specified_quantity:
                    refund_qty = specified_quantity
                elif hasattr(ligne_article, "to_refund_qty"):
                    refund_qty = ligne_article.to_refund_qty

                # Don't create a LigneArticle for ligne that have nothing to refund.
                # For ex : in a command with 2 tickets with different Price on the same Event.
                #          If we cancel one ticket and then cancel the Reservation, it will create a ligne article for the already canceled ticket
                if refund_qty > 0:
                    refunded_line = LigneArticle.objects.create(
                        datetime=timezone.now(),
                        pricesold=ligne_article.pricesold,
                        # specified_quantity = Quantité spécifiée en appellant la méthode
                        # lignearticle.to_refund_qty = "surcharge" de qty en modifiant les lignes articles avant l'appel de la méthode
                        # lignearticle.qty = qty classique au moment de la commande
                        qty=-refund_qty,  # ! Attention negative
                        amount=ligne_article.amount,
                        vat=ligne_article.vat,
                        paiement_stripe=paiement,
                        payment_method=ligne_article.payment_method,
                        asset=ligne_article.asset,
                        wallet=ligne_article.wallet,
                        status=LigneArticle.CREATED,
                        sended_to_laboutik=False,
                        metadata=metadata,
                        sale_origin=SaleOrigin.LESPASS,
                    )
                    refunded_line.status = LigneArticle.REFUNDED  # pour envoyer le trigger qui va informer LaBoutik
                    refunded_line.save()

        # Check if paiment is fully refunded
        if paiement.is_fully_refunded():
            paiement.status = Paiement_stripe.REFUNDED
            paiement.save()

    except InvalidRequestError as e:
        logger.error(f"CheckoutStripe Refund InvalidRequestError {e}")
        raise Exception(f"CheckoutStripe Refund InvalidRequestError {e}")
    except Exception as e:
        logger.error(f"CheckoutStripe Refund Exception : {e}")
        raise e

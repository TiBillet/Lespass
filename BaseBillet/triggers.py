import logging

import stripe
from django.db import connection, transaction
from django.utils import timezone

from AuthBillet.models import TibilletUser
from BaseBillet.models import LigneArticle, Product, Membership, Price, Configuration, Paiement_stripe, PaymentMethod
from BaseBillet.tasks import send_to_ghost, send_membership_invoice_to_email, send_sale_to_laboutik, webhook_membership, \
    send_to_brevo, refill_from_lespass_to_user_wallet_from_price_solded
from BaseBillet.templatetags.tibitags import dround
# NOTE : plus aucun appel Fedow dans ce module depuis le retrait du push d'adhesion.
# / NOTE: no Fedow call left in this module since the membership push was removed.
from booking.models import Booking
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


def update_membership_state_after_stripe_paiement(ligne_article: LigneArticle):

    paiement_stripe: Paiement_stripe = ligne_article.paiement_stripe

    membership = ligne_article.membership
    if not membership:
        membership: Membership = paiement_stripe.membership.first()

    # GARDE : un paiement ne ressuscite jamais une adhesion annulee par un admin.
    #
    # Sans elle, un prelevement Stripe arrivant apres une annulation administrative
    # repasse la fiche en AUTO avec une nouvelle echeance (plus bas dans cette
    # fonction) : l'adhesion annulee — et peut-etre remboursee par avoir —
    # redevient active toute seule.
    #
    # Le cas arrive quand l'abonnement Stripe tourne encore : l'admin a decoche la
    # resiliation, ou notre appel a Stripe a echoue (reseau, cle, compte Connect).
    # Cet echec est volontairement non bloquant cote admin, donc silencieux ici.
    #
    # On garde `last_stripe_invoice` : c'est la SEULE deduplication du webhook
    # (ApiBillet.views, invoice.paid compare la facture a celle-ci). Sans elle, un
    # rejeu Stripe du meme evenement creerait une deuxieme vente.
    #
    # On ne leve pas : TRIGGER_LigneArticlePaid_ActionByCategorie avale les
    # exceptions, la LigneArticle resterait PAID sans passer VALID — comptabilite
    # fausse alors que l'argent EST encaisse. On retourne `membership`, que
    # l'appelant utilise aussitot (set_deadline()).
    #
    # Le reste de trigger_A suit son cours : reçu par mail, vente envoyee a
    # LaBoutik, ligne passee VALID — c'est voulu, le paiement est reel. Une
    # recompense wallet peut aussi etre creditee : c'est le seul effet non
    # souhaitable, assume et signale dans l'alerte ci-dessous plutot que traite
    # par du code supplementaire.
    #
    # / GUARD: a payment never revives an admin-cancelled membership. Keeps
    # last_stripe_invoice (the webhook's only dedup), never raises (the caller
    # swallows exceptions and the accounting line would stay PAID), returns the
    # membership. The rest of trigger_A still runs: the payment is real.
    if membership.status == Membership.ADMIN_CANCELED:
        if paiement_stripe.invoice_stripe:
            membership.last_stripe_invoice = paiement_stripe.invoice_stripe
            membership.save(update_fields=["last_stripe_invoice"])

        logger.error(
            f"Paiement Stripe encaisse sur une adhesion ANNULEE PAR UN ADMIN : "
            f"adhesion {membership.uuid}, facture {paiement_stripe.invoice_stripe}, "
            f"abonnement {membership.stripe_id_subscription}. La fiche n'est PAS "
            f"reactivee. A faire a la main : resilier l'abonnement dans Stripe, "
            f"rembourser, et verifier qu'aucune recompense wallet n'a ete creditee."
        )
        return membership

    price: Price = ligne_article.pricesold.price
    membership.contribution_value = ligne_article.pricesold.prix

    if not membership.first_contribution:
        membership.first_contribution = timezone.now()

    membership.last_contribution = timezone.now()

    membership.stripe_paiement.add(paiement_stripe)

    membership.status = Membership.ONCE

    if paiement_stripe.invoice_stripe:
        membership.last_stripe_invoice = paiement_stripe.invoice_stripe

    if paiement_stripe.subscription:
        membership.stripe_id_subscription = paiement_stripe.subscription
        membership.status = Membership.AUTO

        # Si c'est un paiement récurrent :
        if price.recurring_payment :
            try :
                membership.current_iteration += 1
            except TypeError: # il est a None
                membership.current_iteration = 1
            except Exception as exc:
                raise exc

            # On dit a stripe d'annuler les prochaines itérations
            if membership.max_iteration:
                if membership.current_iteration == membership.max_iteration:
                    # L'appel reseau a Stripe ne doit JAMAIS empecher le membership.save()
                    # plus bas. Sans cette protection, la moindre erreur ici fait perdre
                    # toutes les mises a jour de la fiche (iteration, abonnement, date de
                    # derniere cotisation) alors que la ligne comptable, elle, vient
                    # d'etre creee. On se retrouve avec une vente enregistree et une fiche
                    # adherent restee en arriere.
                    # Cas concret : l'abonnement a deja ete annule cote Stripe, qui refuse
                    # alors toute modification (InvalidRequestError).
                    # / The network call to Stripe must NEVER prevent membership.save()
                    # below. Without this guard, any error here loses every update to the
                    # record while the accounting line has just been created.
                    try:
                        stripe.Subscription.modify(
                            f"{membership.stripe_id_subscription}",
                            stripe_account=Configuration.get_solo().get_stripe_connect_account(),
                            cancel_at_period_end=True
                        )
                    except Exception as erreur_stripe:
                        # Niveau ERROR volontaire : Sentry en fait une alerte, et un
                        # gestionnaire doit aller verifier l'abonnement a la main dans
                        # le tableau de bord Stripe.
                        # / ERROR level on purpose: Sentry raises an alert, and a manager
                        # must check the subscription by hand in the Stripe dashboard.
                        logger.error(
                            f"    Annulation Stripe impossible pour l'abonnement "
                            f"{membership.stripe_id_subscription} "
                            f"(adhesion {membership.uuid}, iteration "
                            f"{membership.current_iteration}/{membership.max_iteration}) "
                            f": {erreur_stripe}. La fiche adhesion est mise a jour malgre "
                            f"tout, mais si cet abonnement est encore actif chez Stripe, "
                            f"il continuera de prelever au-dela du nombre d'iterations "
                            f"prevu. A annuler a la main dans le tableau de bord Stripe."
                        )

    membership.save()
    logger.info(f"    update_membership_state_after_paiement : Mise à jour de la fiche membre OK")

    return membership



### END MEMBERSHIP TRIGGER ####

### SEND TO LABOUTIK for comptabilité ###


# Pour usage en CLI :
# def send_sale_from_membership_to_laboutik(membership: Membership):
#     """
#     for m in Membership.objects.filter(stripe_paiement__isnull=False):
#         send_sale_from_membership_to_laboutik(m)
#     """
#     config = Configuration.get_solo()
#     if config.check_serveur_cashless():
#         if membership.stripe_paiement.exists():
#             stripe_paiement:Paiement_stripe = membership.stripe_paiement.first()
#             if stripe_paiement.lignearticles.exists():
#                 ligne_article : LigneArticle = stripe_paiement.lignearticles.first()
#                 if ligne_article.status in [LigneArticle.PAID, LigneArticle.VALID]:
#                     send_sale_to_laboutik(ligne_article)


### END SEND TO LABOUTIK

# MACHINE A ETAT pour les ventes, activé lorsque LigneArticle passe à PAID
# Actions qui se lancent en fonction de la catégorie d'article ( adhésion, don, reservation, etc ... )
class TRIGGER_LigneArticlePaid_ActionByCategorie:
    """
    Trigged action by categorie when Article is PAID
    """

    def __init__(self, ligne_article: LigneArticle):
        self.ligne_article = ligne_article

        # Si le product sold a été créé sans copier la catégorie originale
        self.categorie = self.ligne_article.pricesold.productsold.categorie_article
        if self.categorie == Product.NONE:
            self.categorie = self.ligne_article.pricesold.productsold.product.categorie_article

        try:
            # on met en majuscule et on rajoute _ au début du nom de la catégorie.
            trigger_name = f"_{self.categorie.upper()}"
            logger.info(f"\nSTART TRIGGER_LigneArticlePaid_ActionByCategorie : {self.ligne_article} - trigger_name : {trigger_name}")
            trigger = getattr(self, f"trigger{trigger_name}")
            trigger()
            logger.info(f"END TRIGGER_LigneArticlePaid_ActionByCategorie\n")

        except AttributeError as exc:
            logger.info(f"Pas de trigger pour la categorie {self.categorie} - ERROR : {exc} - {type(exc)}")
        except Exception as exc:
            logger.error(f"category_trigger {self.categorie.upper()} ERROR : {exc} - {type(exc)}")

    # Category DON
    # def trigger_D(self):
        # On a besoin de valider la ligne article pour que le paiement soit validé
        # self.ligne_article = update_sale_if_free_price(self.ligne_article)
        # self.ligne_article.status = LigneArticle.VALID
        # logger.info(f"TRIGGER DON")

    # Catégorie reservation de ressource
    def trigger_C(self):
        ligne_article: LigneArticle = self.ligne_article
        logger.info(f"    START TRIGGER_C BOOKING PAID ligne_article.uuid : {ligne_article.uuid}")

        # On va chercher l'article vendu et la réservation associée
        booking = ligne_article.booking
        user = booking.user

        if not user.first_name or not user.last_name:
            user.first_name = booking.first_name if not user.first_name else user.first_name
            user.last_name = booking.last_name if not user.last_name else user.last_name
            user.save()


        booking.status = Booking.PAID_BY_USER
        booking.save()


        logger.info(f"        TRIGGER_C BOOKING PAID -> set ligne_article VALID (no save)")
        self.ligne_article.status = LigneArticle.VALID

        logger.info(f"    END TRIGGER_C BOOKING PAID\n")


    # Category BILLET
    def trigger_B(self):
        # Envoi de la vente à LaBoutik, APRÈS la validation en base (on_commit) : le worker
        # Celery relit la ligne avec sa propre connexion (même contrainte que trigger_A).
        # Hors transaction, on_commit lance la tâche tout de suite.
        # / Send the sale to LaBoutik AFTER the commit (same constraint as trigger_A).
        logger.info(f"        TRIGGER_B BILLET PAID -> envoi à LaBoutik?")
        pk_de_la_ligne = self.ligne_article.pk
        transaction.on_commit(lambda: send_sale_to_laboutik.delay(pk_de_la_ligne))

        logger.info(f"        TRIGGER_B BILLET PAID -> set ligne_article VALID (no save)")
        self.ligne_article.status = LigneArticle.VALID

        logger.info(f"    END TRIGGER_A BILLET PAID\n")

    # Category Free Reservation
    # def trigger_F(self):
    #     logger.info(f"TRIGGER FREE RESERVATION")

    # Category RECHARGE_CASHLESS
    # def trigger_R(self):
    #     logger.info(f"TRIGGER RECHARGE_CASHLESS")

    # Category RECHARGE_FEDERATED
    # def trigger_S(self):
    #     logger.info(f"TRIGGER RECHARGE_FEDERATED")

    # Categorie ADHESION
    def trigger_A(self):
        ligne_article: LigneArticle = self.ligne_article
        logger.info(f"    START TRIGGER_A ADHESION PAID ligne_article.uuid : {ligne_article.uuid}")

        # On va chercher l'article vendu et l'adhésion associéé
        membership = ligne_article.membership

        # Refresh en cas de prix libre, le prix est mis à jour par le update membership.
        if ligne_article.paiement_stripe:
            membership: Membership = update_membership_state_after_stripe_paiement(ligne_article)

        # Mise à jour de la deadline
        deadline = membership.set_deadline()
        logger.info(f"        TRIGGER_A membeshipr set_deadline() : {deadline}")

        # On lie le tenant à l'user, pour qu'iel soit visible dans l'admin et que les adéhsion et reservations soient visible dans my_account
        user: TibilletUser = membership.user
        if connection.tenant not in user.client_achat.all():
            user.client_achat.add(connection.tenant)

        # Si l'user n'a pas de nom/prenom, on lui colle celui de l'adhésion
        if not user.first_name or not user.last_name:
            user.first_name = membership.first_name if not user.first_name else user.first_name
            user.last_name = membership.last_name if not user.last_name else user.last_name
            user.save()

        # C'est parti pour l'envoi dans les mails !
        email_sended = send_membership_invoice_to_email.delay(str(membership.uuid))

        # Si la personne accepte la newsletter :
        if membership.newsletter:
            send_to_ghost.delay(membership.pk)
            send_to_brevo.delay(membership.pk)

        # L'adhésion n'est PLUS poussée vers Fedow.
        # Ce push existait pour que LaBoutik V1 lise l'adhésion sous forme de jeton SUB dans
        # le wallet Fedow du porteur. LaBoutik interroge désormais Lespass directement
        # (`/api/v2/memberships/by-wallet/`), qui est la source de vérité : c'est lui qui
        # porte la deadline et donc la VALIDITÉ, que Fedow n'a jamais connue.
        # L'asset d'adhésion, lui, reste déclaré à Fedow
        # (`BaseBillet.signals.send_membership_and_badge_product_to_fedow`) : c'est par lui
        # qu'un comptoir V1 peut encore VENDRE une adhésion.
        # / The membership is NO LONGER pushed to Fedow. That push existed so LaBoutik V1
        #   could read it as a SUB token; LaBoutik now queries Lespass directly, which is
        #   the source of truth (it holds the deadline, hence validity). The membership
        #   ASSET stays declared to Fedow: a V1 counter still needs it to SELL memberships.

        # Récompense monnaie (réglage du tarif) puis envoi de la vente à LaBoutik.
        # Les deux tâches partent APRÈS la validation en base (on_commit) : le worker Celery a
        # sa propre connexion et relit la ligne. Lancée avant (panier matérialisé dans une
        # transaction), la tâche peut ne pas la trouver et échouer sans nouvel essai. Hors
        # transaction, on_commit lance la tâche tout de suite.
        # / Reward then LaBoutik sale, sent AFTER the commit: the Celery worker reads the line
        # with its own connection. Outside a transaction, on_commit runs right away.
        pk_de_la_ligne = ligne_article.pk
        transaction.on_commit(
            lambda: refill_from_lespass_to_user_wallet_from_price_solded.delay(pk_de_la_ligne)
        )

        logger.info(f"    TRIGGER_A ADHESION PAID -> envoi à LaBoutik?")
        transaction.on_commit(lambda: send_sale_to_laboutik.delay(pk_de_la_ligne))

        # Si tout est passé plus haut, on VALID La ligne :
        # Tout ceci se déroule dans un pre_save signal.pre_save_signal_status()
        logger.info(f"    TRIGGER_A ADHESION PAID -> set ligne_article VALID")
        self.ligne_article.status = LigneArticle.VALID

        # Envoi des webhooks lors du save membership
        # webhook_membership.delay(membership.pk)

        logger.info(f"END    TRIGGER_A ADHESION PAID\n")

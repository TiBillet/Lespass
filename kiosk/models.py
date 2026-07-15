# Pilotage des paiements TPE de la borne libre-service.
# / Self-service kiosk card-payment driver.
#
# NOTE : les modeles Terminal et StripeLocation vivent dans laboutik/models.py.
# Un TPE n'est pas reserve aux bornes : une caisse LaBoutik peut en avoir un.
# / Terminal and StripeLocation live in laboutik/models.py: a card terminal is not
# kiosk-only, a LaBoutik cash register may have one too.

import json
import logging
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class PaymentsIntent(models.Model):
    """
    Pilotage d'un paiement TPE + affichage. Copié de LaBoutik APIcashless.PaymentsIntent.
    / Card-terminal payment driver + display state. Copied from LaBoutik.

    Objet TECHNIQUE local : ce n'est PAS le crédit (le crédit = Fedow via webhook).
    Le champ `pos` de LaBoutik est supprimé (inutile au flux Fedow, cf. SPEC).
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    amount = models.PositiveIntegerField()  # centimes / cents
    payment_intent_stripe_id = models.CharField(max_length=30, blank=True, null=True,
                                                verbose_name=_("Paiement intent stripe id"))

    # LA BORNE, PAS LE LECTEUR.
    #
    # Un paiement appartient a l'appareil qui l'a lance. C'est cette cle qui repond a
    # « cette borne a-t-elle le droit de consulter, ou d'annuler, ce paiement ? »
    # (kiosk/views.py, wsocket/consumers.py).
    #
    # Elle ne pointe surtout PAS le lecteur : un lecteur se DEPLACE d'un appareil a
    # l'autre. Si le paiement pointait le lecteur, debrancher celui-ci en pleine
    # transaction ferait perdre a la borne la propriete de son propre paiement — elle
    # prendrait un 404 sur son ecran, carte peut-etre deja debitee.
    # / The KIOSK, not the reader. Readers move between devices; a payment must not change
    # owner because someone unplugged a cable.
    terminal = models.ForeignKey(
        "laboutik.Terminal", on_delete=models.PROTECT, verbose_name=_("Borne"),
    )

    # Le lecteur sur lequel ce paiement est REELLEMENT parti, fige au moment de l'envoi.
    # Sert a annuler sur le bon lecteur, meme s'il a ete debranche depuis. Voir
    # send_to_terminal() et annuler_sur_le_terminal().
    # / The reader this payment was actually sent to, frozen at send time.
    reader_stripe_id = models.CharField(
        max_length=21, blank=True, null=True,
        verbose_name=_("Lecteur utilisé (Stripe)"),
    )

    datetime = models.DateTimeField(auto_now_add=True)
    card = models.ForeignKey("QrcodeCashless.CarteCashless", on_delete=models.PROTECT,
                             verbose_name=_("Carte cashless"), related_name="payments_intents",
                             blank=True, null=True)

    REQUIRES_PAYMENT_METHOD = "R"
    IN_PROGRESS = "P"
    REQUIRES_CAPTURE = "A"
    SUCCEEDED = "S"
    CANCELED = "C"
    STATUS_CHOICES = [
        (REQUIRES_PAYMENT_METHOD, _("requires_payment_method")),
        (IN_PROGRESS, _("in_progress")),
        (REQUIRES_CAPTURE, _("Paiement autorisé, mais pas encore capturé")),
        (SUCCEEDED, _("Succes")),
        (CANCELED, _("Canceled")),
    ]
    status = models.CharField(max_length=2, choices=STATUS_CHOICES,
                              default=REQUIRES_PAYMENT_METHOD, verbose_name=_("Status"))

    def get_from_stripe(self):
        """Rafraîchit le statut depuis Stripe.
        / Refresh status from Stripe."""
        if self.status in [PaymentsIntent.CANCELED, PaymentsIntent.SUCCEEDED]:
            return self.status

        import stripe
        from root_billet.models import RootConfiguration
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        stripe_payment = stripe.PaymentIntent.retrieve(self.payment_intent_stripe_id)
        if stripe_payment.status == "requires_payment_method":
            self.status = PaymentsIntent.REQUIRES_PAYMENT_METHOD
        elif stripe_payment.status == "processing":
            self.status = PaymentsIntent.IN_PROGRESS
        elif stripe_payment.status == "requires_capture":
            self.status = PaymentsIntent.REQUIRES_CAPTURE
        elif stripe_payment.status == "canceled":
            self.status = PaymentsIntent.CANCELED
        elif stripe_payment.status == "succeeded":
            self.status = PaymentsIntent.SUCCEEDED
        self.save()
        return self.status

    def send_to_terminal(self, terminal):
        """Crée le PaymentIntent Stripe (card_present) et l'envoie au lecteur de carte.
        Metadata {fedow_place_uuid, tag_id} NON signées (place Lespass de confiance, SPEC §8bis).
        / Create the Stripe PaymentIntent (card_present) and push it to the card reader.

        LOCALISATION : kiosk/models.py

        :param terminal: le laboutik.Terminal (la borne). Son lecteur est resolu ICI.
        :raises ValueError: si aucun lecteur actif n'est branche sur cette borne
        """
        import stripe
        from root_billet.models import RootConfiguration
        from fedow_connect.models import FedowConfig
        from BaseBillet.models import Configuration

        # LE LECTEUR EST RESOLU AU MOMENT DE L'ENVOI, pas stocke sur le paiement.
        # Le paiement appartient a la BORNE (self.terminal), pas au lecteur : un lecteur se
        # deplace d'un appareil a l'autre, et un paiement en cours ne doit pas changer de
        # proprietaire parce qu'on a debranche un cable. C'est ce qui protege le controle
        # d'acces (kiosk/views.py : la borne ne voit que SES paiements).
        # / The reader is resolved AT SEND TIME. The payment belongs to the KIOSK, not to
        # the reader: readers move between devices, payments must not change owner.
        lecteur = getattr(terminal, "tpe", None)
        if lecteur is None or not lecteur.active:
            raise ValueError(
                f"Aucun lecteur de carte actif n'est branché sur « {terminal.name} »."
            )
        if not lecteur.stripe_id:
            raise ValueError(
                f"Le lecteur « {lecteur.name} » n'est pas encore enregistré chez Stripe."
            )

        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        fedow_config = FedowConfig.get_solo()
        currency = Configuration.get_solo().currency_code.lower()

        # Vérification de la disponibilité du lecteur / Check reader availability
        try:
            stripe.terminal.Reader.retrieve(lecteur.stripe_id)
        except stripe._error.InvalidRequestError as e:
            raise e

        # Metadata lues par Fedow au webhook. PAS de signature (cf. SPEC §8bis).
        # / Metadata read by Fedow at the webhook. NO signature (see SPEC §8bis).
        data = {
            "fedow_place_uuid": f"{fedow_config.fedow_place_uuid}",
            "tag_id": f"{self.card.tag_id}" if self.card else None,
        }

        payment_intent_stripe = stripe.PaymentIntent.create(
            amount=self.amount,
            currency=currency,
            payment_method_types=["card_present"],
            capture_method="automatic",
            metadata={"data": json.dumps(data)},
        )
        self.payment_intent_stripe_id = payment_intent_stripe.id

        # ON RETIENT SUR QUEL LECTEUR CE PAIEMENT EST PARTI.
        #
        # Sans cette trace, annuler le paiement plus tard (timeout, annulation manuelle)
        # relirait le lecteur actuellement branche sur la borne. Or un lecteur se deplace :
        # si on l'a debranche entre-temps pour le mettre ailleurs, on enverrait l'ordre
        # d'annulation au MAUVAIS lecteur — et on couperait le paiement d'un autre client,
        # en train de payer sur une autre caisse.
        # / We remember WHICH reader this payment was sent to. Readers move; cancelling later
        # by re-reading the terminal's current reader could kill another customer's payment.
        self.reader_stripe_id = lecteur.stripe_id
        self.save()

        stripe.terminal.Reader.process_payment_intent(
            lecteur.stripe_id,
            payment_intent=payment_intent_stripe.id,
        )
        self.status = self.IN_PROGRESS
        self.save()
        return self

    def annuler_sur_le_terminal(self):
        """Annule l'action en cours sur le lecteur ET le PaymentIntent Stripe.
        / Cancel the ongoing reader action AND the Stripe PaymentIntent.

        Best-effort : chaque appel Stripe est isole. Si l'action a deja ete
        capturee (carte tapee juste avant), Stripe refuse l'annulation ; on
        rafraichit alors le statut reel plutot que d'ecraser aveuglement.
        Appele quand on doit lacher le lecteur : annulation manuelle (vue cancel),
        broker injoignable, ou timeout de suivi.
        / Best-effort; each Stripe call is isolated. If already captured, Stripe
        refuses the cancel and we refresh the real status instead of overwriting.
        Called whenever we must release the reader: manual cancel, broker down,
        or tracking timeout.

        Retourne le statut final (apres tentative). / Returns the final status.
        """
        import stripe
        from root_billet.models import RootConfiguration
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()

        # 1. Arreter l'invite de carte sur le lecteur physique.
        #
        # On utilise le lecteur SUR LEQUEL LE PAIEMENT EST PARTI (reader_stripe_id), pas
        # celui actuellement branche sur la borne. Un lecteur se deplace : si on l'a
        # debranche depuis, relire la borne nous ferait couper le paiement d'un AUTRE
        # client, en train de payer ailleurs sur ce meme lecteur.
        # / Use the reader the payment was SENT TO, not the one currently plugged into the
        # kiosk: readers move, and we would otherwise cancel another customer's payment.
        if self.reader_stripe_id:
            try:
                stripe.terminal.Reader.cancel_action(self.reader_stripe_id)
            except Exception as erreur_reader:
                logger.error(f"annuler_sur_le_terminal : cancel_action a echoue : {erreur_reader}")

        # 2. Annuler le PaymentIntent. Peut echouer s'il est deja capture/annule.
        # / Cancel the PaymentIntent. May fail if already captured/canceled.
        if self.payment_intent_stripe_id:
            try:
                stripe.PaymentIntent.cancel(self.payment_intent_stripe_id)
            except Exception as erreur_pi:
                logger.error(f"annuler_sur_le_terminal : PaymentIntent.cancel a echoue : {erreur_pi}")

        # 3. Refleter le statut reel de Stripe en base (annule, ou capture entre-temps).
        # / Reflect the real Stripe status in DB (canceled, or captured in the meantime).
        try:
            return self.get_from_stripe()
        except Exception as erreur_refresh:
            logger.error(f"annuler_sur_le_terminal : get_from_stripe a echoue : {erreur_refresh}")
            return self.status

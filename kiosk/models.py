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

    Suit le paiement Stripe. Quand il reussit, la carte est creditee dans la base
    locale (fedow_core), comme a la caisse V2 : voir kiosk/credit.py.
    Le champ `pos` de LaBoutik est supprimé.
    / Tracks the Stripe payment. On success the card is credited locally
    (fedow_core), like the V2 POS: see kiosk/credit.py.
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    amount = models.PositiveIntegerField(verbose_name=_("Montant"))  # centimes / cents
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

    datetime = models.DateTimeField(auto_now_add=True, verbose_name=_("Date et heure"))
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

    # Solde de la carte AVANT la recharge, lu au moment du paiement.
    # Il sert seulement a l'affichage : l'ecran de succes est rendu hors requete
    # (websocket), il ne peut pas relire la carte.
    # / Card balance BEFORE the refill, read at payment time. Display only: the
    # success screen is rendered outside a request (websocket).
    solde_avant_centimes = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_("Solde avant recharge (centimes)"),
    )

    # Date du credit de la carte. Vide = pas encore credite.
    # Pose dans la MEME transaction que le credit (kiosk/credit.py) : c'est ce
    # qui empeche de crediter deux fois le meme paiement.
    # / Card credit date. Empty = not credited yet. Set in the SAME transaction
    # as the credit: this prevents a double credit.
    carte_creditee_le = models.DateTimeField(
        blank=True, null=True,
        verbose_name=_("Carte créditée le"),
    )

    def contexte_ecran_final(self):
        """
        Les montants affiches sur l'ecran de succes, en centimes.
        / Amounts shown on the success screen, in cents.

        LOCALISATION : kiosk/models.py

        Utilise par kiosk/tasks.py (evenement websocket), wsocket/consumers.py
        (rejeu a la reconnexion) et kiosk/views.py (payment_status). Les valeurs
        sont des entiers : elles traversent le channel layer Redis, qui ne sait
        pas serialiser un Decimal. Le filtre `euros` (kiosk_tags) les formate.
        / Integers only: they go through the Redis channel layer. The `euros`
        template filter formats them.

        Le nouveau solde = solde avant + montant. La carte est creditee dans la
        base locale au moment ou le paiement passe a « reussi » (kiosk/credit.py).
        / New balance = balance before + amount. The card is credited locally
        when the payment turns "succeeded".
        """
        nouveau_solde_centimes = None
        if self.solde_avant_centimes is not None:
            nouveau_solde_centimes = self.solde_avant_centimes + self.amount
        # Le bouton « Reessayer » de l'ecran de refus relance le meme paiement :
        # il lui faut la carte et le montant (avec un point decimal).
        # / The refusal screen's "Retry" button replays the same payment.
        tag_id_de_la_carte = self.card.tag_id if self.card_id else ""
        montant_pour_formulaire = f"{self.amount // 100}.{self.amount % 100:02d}"

        # « L'argent n'est pas parti » ne s'ecrit que si Stripe a CONFIRME
        # l'annulation. Sinon (erreur de suivi, delai depasse sans reponse),
        # l'ecran reste prudent et ne propose pas de reessayer.
        # / "No money was taken" only when Stripe CONFIRMED the cancellation.
        statut_certain = self.status in (PaymentsIntent.SUCCEEDED, PaymentsIntent.CANCELED)

        return {
            "statut_certain": statut_certain,
            "montant_ajoute_centimes": self.amount,
            "nouveau_solde_centimes": nouveau_solde_centimes,
            "tag_id": tag_id_de_la_carte,
            "montant_pour_formulaire": montant_pour_formulaire,
        }

    def get_from_stripe(self):
        """Rafraîchit le statut depuis Stripe, et credite la carte des que le
        paiement a reussi (kiosk/credit.py, une seule fois).
        / Refresh status from Stripe, and credit the card once the payment
        succeeded (kiosk/credit.py, once only)."""
        if self.status == PaymentsIntent.SUCCEEDED:
            # Deja reussi : on rattrape un credit qui aurait echoue avant.
            # / Already succeeded: catch up a credit that failed before.
            self.crediter_la_carte_si_besoin()
            return self.status
        if self.status == PaymentsIntent.CANCELED:
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
        # update_fields : SEULEMENT le statut. Une copie en memoire perimee (celle
        # de la tache Celery, chargee avant le credit) ne doit jamais remettre
        # carte_creditee_le a vide : ce serait un double credit.
        # / Status ONLY: a stale in-memory copy must never reset carte_creditee_le.
        self.save(update_fields=["status"])

        if self.status == PaymentsIntent.SUCCEEDED:
            self.crediter_la_carte_si_besoin()
        return self.status

    def crediter_la_carte_si_besoin(self):
        """
        Credite la carte si ce n'est pas deja fait (voir kiosk/credit.py).
        / Credits the card unless already done.

        LOCALISATION : kiosk/models.py
        """
        if self.carte_creditee_le is not None:
            return
        from kiosk.credit import crediter_la_carte_du_paiement

        crediter_la_carte_du_paiement(self.pk)
        # Relit la date posee par le credit. / Re-read the date set by the credit.
        self.refresh_from_db(fields=["carte_creditee_le"])

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


class ReglagesBorne(models.Model):
    """
    Les services proposes au public par UNE borne.
    / The services one kiosk offers to the public.

    LOCALISATION : kiosk/models.py

    Une ligne par borne (laboutik.Terminal). L'equipe du lieu les change depuis
    l'ecran de configuration de la borne, debloque par une carte primaire
    (kiosk/views.py : acces_admin, configuration, basculer_module).

    Seule la recharge existe aujourd'hui. Adhesion, reservation et caisse sont
    affichees « bientot » : elles auront leur champ quand elles existeront.
    / Only the refill exists today. Membership, booking and cash register are
    shown as "coming soon": they will get a field when they exist.
    """
    terminal = models.OneToOneField(
        "laboutik.Terminal", on_delete=models.CASCADE,
        related_name="reglages_borne", verbose_name=_("Borne"),
    )
    recharge_active = models.BooleanField(
        default=True, verbose_name=_("Recharge de carte active"),
    )

    class Meta:
        verbose_name = _("Réglages de la borne")
        verbose_name_plural = _("Réglages des bornes")

    def __str__(self):
        return f"{self.terminal}"


def obtenir_reglages_de_la_borne(terminal):
    """
    Renvoie les reglages de la borne, et les cree la premiere fois.
    / Returns the kiosk settings, creating them the first time.

    :param terminal: laboutik.Terminal, ou None (admin en DEMO sans borne appairee)
    :return: ReglagesBorne, ou None si aucune borne
    """
    if terminal is None:
        return None
    reglages, _created = ReglagesBorne.objects.get_or_create(terminal=terminal)
    return reglages


# --- Borne : un terminal vu depuis le module Kiosk ---
# / Kiosk: a terminal seen from the Kiosk module

# Import ici, et pas en tete : ce modele est le seul a avoir besoin de la classe
# Terminal elle-meme (les autres la designent par une chaine "laboutik.Terminal").
# / Imported here: only this proxy needs the Terminal class itself.
from laboutik.models import Terminal  # noqa: E402


class BorneManager(models.Manager):
    """
    Ne renvoie que les terminaux de role « Kiosk ».
    / Returns only kiosk-role terminals.
    """

    def get_queryset(self):
        from AuthBillet.models import TibilletUser

        return super().get_queryset().filter(
            terminal_role=TibilletUser.ROLE_KIOSQUE,
        )


class Borne(Terminal):
    """
    Une borne libre-service. C'est un laboutik.Terminal de role « Kiosk ».
    / A self-service kiosk: a laboutik.Terminal with the "Kiosk" role.

    LOCALISATION : kiosk/models.py

    POURQUOI UN PROXY :
    Avant, on creait une borne dans « Terminaux matériels », en choisissant le
    type « Kiosk ». Le module Kiosk ne montrait que ses paiements et ses reglages.
    Pour trouver ses bornes, il fallait aller dans un autre module.
    Ce proxy donne au module Kiosk sa propre liste de bornes, avec sa propre URL
    (/admin/kiosk/borne/). Meme table que Terminal : aucune donnee n'est copiee.

    Admin : kiosk/admin.py, BorneAdmin.
    / Same table as Terminal, no data copied. Gives the Kiosk module its own list.
    """

    objects = BorneManager()

    class Meta:
        proxy = True
        verbose_name = _("Borne")
        verbose_name_plural = _("Bornes")

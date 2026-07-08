# Modèles TPE Stripe du kiosk (chantier CHANTIER-01).
# / Kiosk Stripe terminal models (CHANTIER-01).

import json
import uuid
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StripeLocation(models.Model):
    """
    Location Stripe Terminal, requise pour créer un reader (TPE).
    / Stripe Terminal location, required to create a reader (card terminal).

    Copié de LaBoutik APIcashless.Location, rebranché sur RootConfiguration.
    Ce n'est PAS un singleton : is_primary_location distingue la location
    primaire fédérée. get_primary_location() la crée chez Stripe à la volée.
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Nom"))
    stripe_id = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe ID"))
    is_primary_location = models.BooleanField(default=False, verbose_name=_("Primary Asset Location"))

    def __str__(self):
        return self.name or "StripeLocation"

    @classmethod
    def get_primary_location(cls):
        """La location pour les recharges de monnaie fédérée. La crée chez Stripe si absente.
        / The location for federated money refills. Creates it at Stripe if missing."""
        if not cls.objects.filter(is_primary_location=True).exists():
            import stripe
            from root_billet.models import RootConfiguration

            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            location = stripe.terminal.Location.create(
                display_name="Primary Asset Location",
                address={
                    "line1": "Primary Asset Location",
                    "country": "FR",
                    "city": "Villeurbanne",
                    "postal_code": "69100",
                },
            )
            return cls.objects.create(
                stripe_id=location.id,
                name="Primary Asset Location",
                is_primary_location=True,
            )
        return cls.objects.get(is_primary_location=True)


class Terminal(models.Model):
    """
    TPE Stripe (BBPOS WisePOS E). Copié de LaBoutik APIcashless.Terminal.
    / Stripe card terminal. Copied from LaBoutik APIcashless.Terminal.

    Lien borne : term_user OneToOne → TermUser (1 borne = 1 TPE). Remplace le
    Appareil.terminals de LaBoutik (pas de modèle Appareil côté Lespass).
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Nom"))

    # 1 borne = 1 TPE. FK vers TibilletUser CONCRET, pas le proxy TermUser :
    # le manager de TermUser filtre par tenant et casserait l'accès hors contexte
    # tenant (public/shell/Celery). Le form d'admin restreint le choix aux TermUser.
    # Pattern = BaseBillet.LaBoutikAPIKey.user.
    # / 1 borne = 1 terminal. FK to the CONCRETE TibilletUser (not the TermUser
    # proxy, whose manager filters by tenant). Admin form restricts choices to TermUser.
    term_user = models.OneToOneField(
        "AuthBillet.TibilletUser",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="terminal",
        verbose_name=_("Borne (terminal appairé)"),
    )

    # Pour les TPE Stripe / For Stripe terminals
    registration_code = models.CharField(max_length=200, blank=True, null=True,
                                         verbose_name=_("Code d'enregistrement du lecteur"))
    stripe_id = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe ID"))

    STRIPE_WISEPOS = "W"
    TYPE_CHOICES = [
        (STRIPE_WISEPOS, _("bbpos_wisepos_e")),
    ]
    type = models.CharField(max_length=2, choices=TYPE_CHOICES, default=STRIPE_WISEPOS,
                            verbose_name=_("Type"))
    archived = models.BooleanField(default=False)

    def status(self):
        """Statut du lecteur côté Stripe. / Reader status from Stripe."""
        if self.stripe_id:
            import stripe
            from root_billet.models import RootConfiguration
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            reader = stripe.terminal.Reader.retrieve(self.stripe_id)
            return reader.status
        return "Unknown"

    def get_stripe_id(self):
        """Appairage : crée le reader Stripe depuis le registration_code + la location primaire.
        / Pairing: create the Stripe reader from registration_code + primary location."""
        if not self.stripe_id:
            if self.type == Terminal.STRIPE_WISEPOS and self.registration_code:
                try:
                    import stripe
                    from root_billet.models import RootConfiguration
                    stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
                    location = StripeLocation.get_primary_location()
                    reader = stripe.terminal.Reader.create(
                        registration_code=self.registration_code,
                        label=self.name,
                        location=location.stripe_id,
                    )
                    self.stripe_id = reader.id
                except Exception as e:
                    raise Exception(f"Error while creating stripe reader : {e}")
            else:
                raise Exception("The registration code is not set.")
        return self.stripe_id

    def __str__(self):
        return f"{self.get_type_display()} {self.name}"


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
    terminal = models.ForeignKey(Terminal, on_delete=models.PROTECT, verbose_name=_("TPE"))
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
        """Rafraîchit le statut depuis Stripe. En DEMO, tire un statut au sort.
        / Refresh status from Stripe. In DEMO, draw a random status."""
        if settings.DEMO:
            import random
            random_value = random.random()
            if random_value < 0.8:
                self.status = PaymentsIntent.REQUIRES_PAYMENT_METHOD
            elif random_value < 0.9:
                self.status = PaymentsIntent.CANCELED
            else:
                self.status = PaymentsIntent.SUCCEEDED
            self.save()
            return self.status

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

    def send_to_terminal(self, terminal: "Terminal"):
        """Crée le PaymentIntent Stripe (card_present) et l'envoie au reader.
        Metadata {fedow_place_uuid, tag_id} NON signées (place Lespass de confiance, SPEC §8bis).
        / Create the Stripe PaymentIntent (card_present) and push it to the reader.
        Unsigned {fedow_place_uuid, tag_id} metadata (trusted Lespass place, SPEC §8bis)."""
        if settings.DEMO:
            # Simulation d'un TPE Stripe / Fake a Stripe terminal
            self.payment_intent_stripe_id = uuid.uuid4().hex[:30]
            self.status = self.IN_PROGRESS
            self.save()
            return self

        import stripe
        from root_billet.models import RootConfiguration
        from fedow_connect.models import FedowConfig
        from BaseBillet.models import Configuration

        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        fedow_config = FedowConfig.get_solo()
        currency = Configuration.get_solo().currency_code.lower()

        # Vérification de la disponibilité du terminal / Check terminal availability
        try:
            stripe.terminal.Reader.retrieve(terminal.stripe_id)
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
        self.save()

        stripe.terminal.Reader.process_payment_intent(
            terminal.stripe_id,
            payment_intent=payment_intent_stripe.id,
        )
        self.status = self.IN_PROGRESS
        self.save()
        return self

from uuid import uuid4

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
# Create your models here.
from stdimage import StdImageField, JPEGField
from stdimage.validators import MaxSizeValidator, MinSizeValidator

from Customers.models import Client


class EventDirectory(models.Model):
    datetime = models.DateTimeField()
    event_uuid = models.UUIDField()
    place = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="place")
    artist = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="artist")



# On stocke ici tous les ID Product de Stripe.
# Utile par exemple :
# Savoir depuis quel tenant vient la mise à jour auto depuis le webhook Stripe
#    ApiBillet.Webhook_stripe(APIView) - > payload.get('type') == "customer.subscription.updated"
class ProductDirectory(models.Model):
    product_sold_stripe_id = models.CharField(max_length=30, null=True, blank=True)
    place = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="product_place")




class WaitingConfiguration(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=False)
    email = models.EmailField()
    organisation = models.CharField(db_index=True, max_length=50, verbose_name=_("Collective name"))

    # LEGACY 2026-05-16 — champ orphelin du flow `/tenant/new/` supprime.
    # Etait rempli par `Tenant.onboard_stripe()` (BaseBillet/views.py) avec
    # le `id` du compte Stripe Connect cree apres confirmation email.
    # Aujourd'hui Stripe Connect se configure depuis l'admin Unfold du
    # tenant existant (cf. PaiementStripe/views.py::StripeConnectOnboardingViewSet)
    # et l'id_acc_connect vit sur `Configuration.stripe_connect_account*`,
    # pas sur WaitingConfiguration. A SUPPRIMER lors d'une migration data
    # de cleanup (cf. TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md section 9.6).
    # / LEGACY — orphan field from removed `/tenant/new/` flow. To remove
    # via a future data migration.
    id_acc_connect = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe connect ID"))

    # LEGACY 2026-05-16 — flags orphelins du formulaire `/tenant/new/`.
    # Etaient remplis par le serializer `TenantCreateValidator` (supprime).
    # Le wizard onboard ne demande pas ces choix — l'activation des modules
    # se fait dans le dashboard Unfold post-creation (cf. Configuration.module_*).
    # / LEGACY — orphan flags from the removed `/tenant/new/` form.
    laboutik_wanted = models.BooleanField(default=False)
    payment_wanted = models.BooleanField(default=False)
    email_confirmed = models.BooleanField(default=False)

    dns_choice = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Domain name choice"))

    ### Ex method :
    slug = models.SlugField(max_length=50, default="")

    short_description = models.CharField(max_length=250, verbose_name=_("Short description"), blank=True, null=True)
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"))

    adress = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Address"))
    postal_code = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Zip code"))
    city = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("City"))

    phone = models.CharField(max_length=20, verbose_name=_("Phone number"))

    # LEGACY 2026-05-16 — champs orphelins du formulaire `/tenant/new/`.
    # `site_web` etait pre-rempli depuis Stripe (`info_stripe.business_profile.url`)
    # par `TenantCreateValidator.create_tenant`. `legal_documents`, `twitter`,
    # `facebook`, `instagram` n'etaient remplis nulle part en pratique
    # (jamais expose dans le formulaire legacy non plus). Le wizard onboard
    # ne demande aucun de ces champs — l'admin les saisira plus tard dans
    # son admin Unfold (`Configuration.site_web` etc.).
    # / LEGACY — orphan URL fields from `/tenant/new/`. Onboard wizard doesn't
    # collect these; admin fills them later in Unfold Configuration.
    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name='By-laws')

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    # adhesion_obligatoire = models.BooleanField(default=False, verbose_name="Proposer l'adhésion lors d'un scan de QRCode de carte NFC")
    # button_adhesion = models.BooleanField(default=False)

    # LEGACY 2026-05-16 — champs images orphelins du formulaire `/tenant/new/`.
    # `map_img`, `carte_restaurant`, `img` n'etaient en pratique JAMAIS
    # uploades par le legacy (pas de champ image dans `new_tenant.html`).
    # Le wizard onboard utilise un seul champ `logo` (StdImageField, declare
    # plus bas dans ce modele). Les 3 champs ci-dessous sont dead-code en
    # base, conserves pour ne pas casser une migration data eventuelle —
    # a SUPPRIMER via une migration de cleanup.
    # / LEGACY — orphan image fields. Never uploaded by legacy in practice.
    # Onboard uses a single `logo` StdImageField. To remove via a future
    # cleanup data migration.
    map_img = JPEGField(upload_to='images/',
                            null=True, blank=True,
                            validators=[MaxSizeValidator(1920, 1920)],
                            variations={
                                'fhd': (1920, 1920),
                                'hdr': (720, 720),
                                'med': (480, 480),
                                'thumbnail': (150, 90),
                            },
                            delete_orphans=True,
                            verbose_name=_('Geographical map')
                            )

    carte_restaurant = JPEGField(upload_to='images/',
                                     null=True, blank=True,
                                     validators=[MaxSizeValidator(1920, 1920)],
                                     variations={
                                         'fhd': (1920, 1920),
                                         'hdr': (720, 720),
                                         'med': (480, 480),
                                         'thumbnail': (150, 90),
                                     },
                                     delete_orphans=True,
                                     verbose_name=_('Restaurant menu')
                                     )

    img = JPEGField(upload_to='images/',
                        validators=[MinSizeValidator(720, 135)],
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                        },
                        delete_orphans=True,
                        verbose_name=_('Background'),
                        )

    # stripe_connect_account = models.CharField(max_length=21, blank=True, null=True)

    TZ_REUNION, TZ_PARIS = "Indian/Reunion", "Europe/Paris"
    TZ_CHOICES = [
        (TZ_REUNION, _('Indian/Reunion')),
        (TZ_PARIS, _('Europe/Paris')),
    ]

    # LEGACY 2026-05-16 — champ orphelin. Le wizard onboard ne demande
    # pas la timezone (deduite de la locale browser et/ou settings projet).
    # Etait remplit par TenantCreateValidator legacy. A SUPPRIMER via
    # migration data future.
    # / LEGACY — orphan timezone field, never set by onboard.
    fuseau_horaire = models.CharField(default=TZ_REUNION,
                                      max_length=50,
                                      choices=TZ_CHOICES,
                                      )

    # noinspection PyUnresolvedReferences
    def img_variations(self):
        if self.img:
            return {
                'fhd': self.img.fhd.url,
                'hdr': self.img.hdr.url,
                'med': self.img.med.url,
                'thumbnail': self.img.thumbnail.url,
                'crop_hdr': self.img.crop_hdr.url,
                'crop': self.img.crop.url,
            }
        else:
            return {}

    logo = StdImageField(upload_to='images/',
                         validators=[MaxSizeValidator(1920, 1920)],
                         blank=True, null=True,
                         variations={
                             'fhd': (1920, 1920),
                             'hdr': (720, 720),
                             'med': (480, 480),
                             'thumbnail': (300, 120),
                         },
                         delete_orphans=True,
                         verbose_name='Logo'
                         )

    # noinspection PyUnresolvedReferences
    def logo_variations(self):
        if self.logo:
            return {
                'fhd': self.img.fhd.url,
                'hdr': self.img.hdr.url,
                'med': self.img.med.url,
                'thumbnail': self.img.thumbnail.url,
            }
        else:
            return []

    ARTISTE, SALLE_SPECTACLE, FESTIVAL, TOURNEUR, PRODUCTEUR, META, ROOT = 'A', 'S', 'F', 'T', 'P', 'M', 'R'
    CATEGORIE_CHOICES = [
        (ARTISTE, _('Artist')),
        (SALLE_SPECTACLE, _("Scene")),
        (FESTIVAL, _('Festival')),
        (TOURNEUR, _('Tour operator')),
        (PRODUCTEUR, _('Producer')),
        (META, _('Event aggregator')),
        (ROOT, _('Root public tenant')),
    ]

    categorie = models.CharField(max_length=3, choices=CATEGORIE_CHOICES, default=SALLE_SPECTACLE,
                                         verbose_name=_("Category"))

    datetime = models.DateTimeField(auto_now_add=True)
    # LEGACY 2026-05-16 — flag orphelin du flow `/tenant/new/`. Etait
    # passe a True par `Tenant.onboard_stripe_return` apres validation
    # Stripe Connect. Aujourd'hui Stripe se configure post-creation (cf.
    # PaiementStripe/views.py), donc le flag n'est plus jamais mis a jour
    # pendant l'onboard. A SUPPRIMER via migration data future.
    # / LEGACY — orphan flag from `/tenant/new/`. Stripe is now configured
    # post-creation, this flag is never set anymore.
    onboard_stripe_finished = models.BooleanField(default=False)
    created = models.BooleanField(default=False)
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name=_('Tenant'), related_name='waiting_config', blank=True, null=True)

    # === Wizard d'onboarding (extension) ===
    # LOCALISATION: MetaBillet/models.py — extension WaitingConfiguration pour le wizard onboard.
    # Champs ajoutes pour porter tout le brouillon du wizard pas-a-pas.
    # Tous nullable / blank pour ne pas casser les anciens WC crees par /tenant/new/.
    # / Onboarding wizard fields. All nullable/blank so old WCs keep working.
    # Note : long_description, postal_code et logo existent deja plus haut dans la classe ;
    # on les reutilise tels quels (postal_code reste IntegerField, logo reste sur images/).
    # / Note: long_description, postal_code and logo are reused from the existing fields above.

    first_name = models.CharField(
        max_length=60, blank=True, default="",
        verbose_name=_("First name"),
    )
    last_name = models.CharField(
        max_length=60, blank=True, default="",
        verbose_name=_("Last name"),
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name=_("Latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name=_("Longitude"),
    )
    street_address = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name=_("Street address"),
    )
    # Coexiste avec le champ legacy `city` (rempli par /tenant/new/). Le wizard
    # onboard utilise `address_locality` (vocabulaire schema.org). `city` reste
    # pour compat avec les anciens WaitingConfiguration.
    # / Coexists with the legacy `city` field (set by /tenant/new/). The onboard
    # wizard uses `address_locality` (schema.org vocab). `city` stays for
    # backward compat with old WaitingConfiguration records.
    address_locality = models.CharField(
        max_length=120, blank=True, default="",
        verbose_name=_("City"),
    )
    address_country = models.CharField(
        max_length=80, blank=True, default="",
        verbose_name=_("Country"),
    )
    events_draft = models.JSONField(
        default=list, blank=True,
        verbose_name=_("Events draft"),
    )
    otp_hash = models.CharField(
        max_length=128, blank=True, default="",
        verbose_name=_("OTP hash"),
        help_text=_("PBKDF2 hash of the one-time password. Never stored in plain text."),
    )
    otp_expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("OTP expires at"),
        help_text=_("Expiration of the OTP, usually 10 minutes after issuance."),
    )
    otp_attempts = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("OTP wrong attempts"),
    )
    otp_resend_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("OTP resend count"),
    )
    # Cooldown anti-spam : timestamp du dernier envoi OTP (auto ou via
    # resend). Sert a bloquer un spam de re-envois (60s entre 2 envois).
    # / Anti-spam cooldown: timestamp of the last OTP send (auto or
    # resend). Used to block a resend spam (60s between two sends).
    otp_sent_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("OTP last sent at"),
        help_text=_("Timestamp of the last OTP send (used for cooldown)."),
    )
    # Langue preferee de l'utilisateur, captee depuis la session au POST
    # identity (`get_language()`). Sert aux tasks Celery `onboard_otp_mailer`
    # et `onboard_ready_mailer` qui n'ont pas de `request` pour deduire la
    # langue : sans ce champ, les sujets de mail sont rendus dans la langue
    # par defaut du worker (souvent 'en' via LANGUAGE_CODE settings) meme si
    # l'utilisateur a navigue tout le wizard en francais.
    # / Preferred user language captured from session at identity POST
    # (`get_language()`). Used by Celery tasks `onboard_otp_mailer` and
    # `onboard_ready_mailer` which have no `request` to infer the language:
    # without this field, email subjects fall back to the worker's default
    # locale (often 'en') even if the user filled the wizard in French.
    language = models.CharField(
        max_length=10, blank=True, default="",
        verbose_name=_("Preferred language"),
        help_text=_("BCP47 language code captured during the onboarding wizard."),
    )
    # Warnings non-bloquants accumules pendant la creation du tenant.
    # Cas typique : un draft d'event mal forme (datetime invalide, image
    # corrompue, etc.) qui est skip silencieusement par la task pour ne
    # pas tuer la creation entiere. Le user voit ces warnings sur la page
    # `/onboard/launch/` (status_done.html) pour pouvoir corriger
    # manuellement dans son admin.
    # / Non-blocking warnings accumulated during tenant creation. Typical
    # case: a malformed event draft (invalid datetime, broken image, etc.)
    # silently skipped by the task to avoid killing the whole creation.
    # The user sees these warnings on `/onboard/launch/` (status_done.html)
    # to fix them manually in their admin.
    events_creation_warnings = models.TextField(
        blank=True, default="",
        verbose_name=_("Events creation warnings"),
        help_text=_("Non-blocking warnings from event draft processing during tenant creation."),
    )

    # Etapes du wizard. / Wizard steps.
    STEP_IDENTITY = "identity"
    STEP_VERIFY = "verify"
    # STEP_VENUE : nouvelle étape « Votre lieu » (recherche Tiers-Lieux + nom +
    # domaine), insérée après la vérification email.
    # / STEP_VENUE: new "Your venue" step (Tiers-Lieux search + name + domain),
    # inserted right after email verification.
    STEP_VENUE = "venue"
    STEP_PLACE = "place"
    STEP_DESCRIPTIONS = "descriptions"
    STEP_EVENTS = "events"
    STEP_LAUNCH = "launch"
    STEP_CHOICES = (
        (STEP_IDENTITY, _("Identity")),
        (STEP_VERIFY, _("Verify email")),
        (STEP_VENUE, _("Your venue")),
        (STEP_PLACE, _("Address")),
        (STEP_DESCRIPTIONS, _("Descriptions")),
        (STEP_EVENTS, _("Events")),
        (STEP_LAUNCH, _("Launch")),
    )
    current_step = models.CharField(
        max_length=20, choices=STEP_CHOICES, default=STEP_IDENTITY,
        verbose_name=_("Current wizard step"),
        help_text=_("Current step the user is on in the wizard."),
    )

    # FK vers l'invitation utilisee pour creer ce brouillon (optionnel).
    # / FK to the invitation used to seed this draft (optional).
    invitation = models.ForeignKey(
        "onboard.OnboardInvitation", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="used_by_drafts",
        verbose_name=_("Invitation used"),
    )

    error_message = models.TextField(
        blank=True, default="",
        verbose_name=_("Async task error"),
        help_text=_("Error message captured by the async tenant-creation task, if any."),
    )

    def save(self, *args, **kwargs):
        '''
        Transforme le nom en slug si vide, pour en faire une url lisible
        '''
        if not self.slug:
            self.slug = slugify(f"{self.organisation}")
        super().save(*args, **kwargs)

    def create_tenant(self):
        from BaseBillet.validators import TenantCreateValidator
        tenant = TenantCreateValidator.create_tenant(self)
        return tenant


    def __str__(self):
        return f"{self.organisation} - {self.email} -> {self.slug}"

    class Meta:
        verbose_name = _('Settings')
        verbose_name_plural = _('Settings')

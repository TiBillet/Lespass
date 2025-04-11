# import os
import json
import logging
import uuid
from datetime import timedelta, datetime
from decimal import Decimal
from uuid import uuid4

import pytz
import requests
import stripe
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db import models
from django.db.models import JSONField, SET_NULL, Sum
# Create your models here.
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.postgresql_backend.base import FakeTenant
from django_tenants.utils import tenant_context
from rest_framework_api_key.models import APIKey

from solo.models import SingletonModel

from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator, MinSizeValidator
from stripe import InvalidRequestError

import AuthBillet.models
from AuthBillet.models import HumanUser, RsaKey
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from TiBillet import settings
from fedow_connect.utils import dround, sign_message, verify_signature, data_to_b64, sign_utf8_string
from root_billet.models import RootConfiguration
from root_billet.utils import fernet_decrypt, fernet_encrypt

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


# TODO, plus utile, a retirer et utiler un choice
class Weekday(models.Model):
    WEEK = [
        (0, _('Monday')),
        (1, _('Tuesday')),
        (2, _('Wednesday')),
        (3, _('Thursday')),
        (4, _('Friday')),
        (5, _('Saturday')),
        (6, _('Sunday')),
    ]
    day = models.IntegerField(choices=WEEK, unique=True)

    def __str__(self):
        return self.get_day_display()


class SaleOrigin(models.TextChoices):
    LESPASS = "LP", _("Online platform")
    LABOUTIK = "LB", _("Cash register")
    ADMIN = "AD", _("Administration")
    EXTERNAL = "EX", _("External")


class PaymentMethod(models.TextChoices):
    FREE = "NA", _("Offered")
    CC = "CC", _("Credit card: POS terminal")
    CASH = "CA", _("Cash")
    CHEQUE = "CH", _("Check")
    TRANSFER = "TR", _("Bank transfer")
    STRIPE_FED = "SF", _("Online: federated Stripe")
    STRIPE_NOFED = "SN", _("Online: Stripe account")
    STRIPE_RECURENT = "SR", _("Recurring: Stripe account")

    @classmethod
    def online(cls):
        """Renvoie uniquement les choix de type 'en ligne'"""
        return [
            (choice, label) for choice, label in cls.choices if
            choice in [cls.STRIPE_FED, cls.STRIPE_NOFED, cls.STRIPE_RECURENT]
        ]

    @classmethod
    def not_online(cls):
        """Renvoie uniquement les choix de type 'en ligne'"""
        return [
            (choice, label) for choice, label in cls.choices if
            choice not in [cls.STRIPE_FED, cls.STRIPE_NOFED, cls.STRIPE_RECURENT]
        ]


class Tag(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=50, verbose_name=_("Tag name"))
    slug = models.CharField(max_length=50, verbose_name=_("Tag slug"), db_index=True)
    color = models.CharField(max_length=7, verbose_name=_("Tag color"), default="#000000")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = slugify(f"{self.name}")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")


class OptionGenerale(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=250, blank=True, null=True)
    poids = models.PositiveIntegerField(default=0, verbose_name=_("Weight"), db_index=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Option')
        verbose_name_plural = _('Options')


class PostalAddress(models.Model):
    """
    Modèle Django conforme à Schema.org pour une adresse postale avec coordonnées GPS.
    """
    name = models.CharField(max_length=400,
                            blank=True, null=True,
                            verbose_name=_("Address name"),
                            help_text=_("It will help with finding it quickly later.")
                            )

    street_address = models.TextField(
        verbose_name=_("Street address"),
        help_text=_("Street number, name, etc.")
    )
    address_locality = models.CharField(
        max_length=255,
        verbose_name=_("Locality"),
        help_text=_("Town or city name.")
    )
    address_region = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Region"),
        help_text=_("State, province or region.")
    )
    postal_code = models.CharField(
        max_length=20,
        verbose_name=_("Zip code"),
        help_text=_("Postcode or zip code.")
    )
    address_country = models.CharField(
        max_length=255,
        verbose_name=_("Country"),
        help_text=_("Full name or ISO code.")
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name=_("Latitude"),
        help_text=_("GPS coordinate: latitude.")
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name=_("Longitude"),
        help_text=_("GPS coordinate: longitude.")
    )
    comment = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Comment"),
        help_text=_("Comment about the address.")
    )
    is_main = models.BooleanField(
        default=False,
        verbose_name=_("Main address"),
    )

    def __str__(self):
        return f"{self.street_address}, {self.address_locality}, {self.address_country}"

    class Meta:
        verbose_name = _("Postal address")
        verbose_name_plural = _("Postal addresses")


# class ExternalLink(models.Model):
#     uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
#     name = models.CharField(max_length=50, verbose_name=_("Nom du lien"))
#     url = models.URLField(verbose_name=_("URL"))


@receiver(post_save, sender=OptionGenerale)
def poids_option_generale(sender, instance: OptionGenerale, created, **kwargs):
    if created:
        # poids d'apparition
        if instance.poids == 0:
            instance.poids = len(OptionGenerale.objects.all()) + 1

        instance.save()


class Carrousel(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("Slide name"))
    img = StdImageField(upload_to='images/',
                        validators=[MinSizeValidator(720, 135)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                        },
                        delete_orphans=True,
                        verbose_name=_('Image file'),
                        )

    # publish = models.BooleanField(default=True, verbose_name=_("Publier"))
    on_event_list_page = models.BooleanField(default=True, verbose_name=_("Add to event list carousel"))
    link = models.URLField(blank=True, null=True, verbose_name=_("Link URL"))
    order = models.PositiveSmallIntegerField(verbose_name=_("Weight"), default=1000, )

    def __str__(self):
        return self.name


class Configuration(SingletonModel):
    def uuid(self):
        return connection.tenant.pk


    organisation = models.CharField(db_index=True, max_length=50, verbose_name=_("Collective name"))

    slug = models.SlugField(max_length=50, default="")

    short_description = models.CharField(max_length=250, verbose_name=_("Short description"), blank=True, null=True)
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"))

    postal_address = models.ForeignKey(PostalAddress, on_delete=SET_NULL, blank=True, null=True)

    adress = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Address"))
    postal_code = models.IntegerField(blank=True, null=True, verbose_name=_("Zip code"))
    city = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("City"))
    tva_number = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("VAT number"))
    siren = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("SIREN number"))

    phone = models.CharField(max_length=20, verbose_name=_("Phone number"))
    email = models.EmailField()

    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name=_('Terms and conditions document'))

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    map_img = StdImageField(upload_to='images/',
                            null=True, blank=True,
                            validators=[MaxSizeValidator(1920, 1920)],
                            variations={
                                'fhd': (1920, 1920),
                                'hdr': (720, 720),
                                'med': (480, 480),
                                'thumbnail': (150, 90),
                            },
                            delete_orphans=True,
                            verbose_name=_('Geographical map image')
                            )

    carte_restaurant = StdImageField(upload_to='images/',
                                     null=True, blank=True,
                                     validators=[MaxSizeValidator(1920, 1920)],
                                     variations={
                                         'fhd': (1920, 1920),
                                         'hdr': (720, 720),
                                         'med': (480, 480),
                                         'thumbnail': (150, 90),
                                     },
                                     delete_orphans=True,
                                     verbose_name=_('Restaurant menu image')
                                     )

    img = StdImageField(upload_to='images/',
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
                        verbose_name=_('Background image'),
                        )

    # TZ_REUNION, TZ_PARIS = "Indian/Reunion", "Europe/Paris"
    # TZ_CHOICES = [
    #     (TZ_REUNION, _('Indian/Reunion')),
    #     (TZ_PARIS, _('Europe/Paris')),
    # ]
    TZ_CHOICES = zip(pytz.all_timezones, pytz.all_timezones)
    fuseau_horaire = models.CharField(default="Europe/Paris",
                                      max_length=50,
                                      choices=TZ_CHOICES,
                                      verbose_name=_("Timezone"),
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

    """
    ######### OPTION GENERALES #########
    """

    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Default maximum capacity"))

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="radiobutton")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="checkbox")

    need_name = models.BooleanField(default=True,
                                    verbose_name=_("Users have to give a first and last name at registration."))
    allow_concurrent_bookings = models.BooleanField(default=True, verbose_name=_("Allow concurrent bookings"),
                                                    help_text=_("Events need start and end dates to be comparable."))

    currency_code = models.CharField(max_length=3, default="EUR")

    additional_text_in_membership_mail = models.TextField(blank=True, null=True, verbose_name=_("Additional text in membership mail"), help_text=_("You can add additional information that will be e-mailed to you when you sign up."))

    """
    PERSONALISATION
    """

    membership_menu_name = models.CharField(max_length=200, default=_("Subscriptions"),
                                            verbose_name=_("Subscription page name"))
    event_menu_name = models.CharField(max_length=200, default=_("Calendar"), verbose_name=_("Calendar page name"))
    first_input_label_membership = models.CharField(max_length=200, default=_("First name"),
                                                    verbose_name=_("Title of the first input on the membership form"))
    second_input_label_membership = models.CharField(max_length=200, default=_("Last name or organization"),
                                                     verbose_name=_("Title of the second input on the membership form"))

    description_membership_page = models.TextField(blank=True, verbose_name=_("Description on the membership page"), help_text=_("Displayed above membership products."))

    """
    ######### CASHLESS #########
    """

    server_cashless = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name=_("Cashless server URL")
    )

    key_cashless = models.CharField(
        max_length=41,
        blank=True,
        null=True,
        verbose_name=_("Cashless server API key")
    )

    laboutik_public_pem = models.CharField(max_length=512, editable=False, null=True, blank=True)

    def check_serveur_cashless(self):
        logger.info(f"Checking cashless server... URL: {self.server_cashless}")
        if self.server_cashless and self.key_cashless:
            sess = requests.Session()
            try:
                r = sess.get(
                    f'{self.server_cashless}/api/check_apikey',
                    headers={
                        'Authorization': f'Api-Key {self.key_cashless}',
                        'Origin': self.domain(),
                    },
                    timeout=1,
                    verify=bool(not settings.DEBUG),
                )
                sess.close()
                logger.info(f"    check_serveur_cashless : {r.status_code} {r.text}")
                if r.status_code == 200:
                    # TODO: Check cashless signature avec laboutik_public_pem
                    return True
                else :
                    raise Exception(f"{r.status_code} {r.content}")
            except Exception as e:
                # import ipdb; ipdb.set_trace()
                logger.error(f"    ERROR check_serveur_cashless : {e}")
                raise e
        return False

    """
    ######### FEDOW #########
    """

    federated_cashless = models.BooleanField(default=False)

    server_fedow = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name=_("Fedow server URL")
    )

    key_fedow = models.CharField(
        max_length=41,
        blank=True,
        null=True,
        verbose_name=_("Fedow server API")
    )

    """
    ######### STRIPE #########
    """
    stripe_mode_test = models.BooleanField(default=False)

    stripe_connect_account = models.CharField(max_length=21, blank=True, null=True)
    stripe_connect_account_test = models.CharField(max_length=21, blank=True, null=True)
    stripe_payouts_enabled = models.BooleanField(default=False)

    # A degager, on utilise uniquement le stripe account connect
    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)

    def get_stripe_api(self):
        # Test ou pas test ?
        # return self.stripe_test_api_key if self.stripe_mode_test else self.stripe_api_key
        return RootConfiguration.get_solo().get_stripe_api()

    def get_stripe_connect_account(self):
        # Si la procédure a déja été démmaré, le numero stripe connect a déja été créé.
        # Sinon, on en cherche un nouveau
        id_acc_connect = self.stripe_connect_account_test if self.stripe_mode_test else self.stripe_connect_account
        if not id_acc_connect:
            logger.info('création du id_acc_connect')
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            acc_connect = stripe.Account.create(
                type="standard",
                country="FR",
            )
            id_acc_connect = acc_connect.get('id')
            if self.stripe_mode_test:
                self.stripe_connect_account_test = id_acc_connect
            else:
                self.stripe_connect_account = id_acc_connect
            self.save()
        return id_acc_connect

    # Vérifie que le compte stripe connect soit valide et accepte les paiements.
    def check_stripe_payouts(self):
        logger.info("check_stripe_payouts")
        id_acc_connect = self.get_stripe_connect_account()
        if id_acc_connect:
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            if info_stripe and info_stripe.get('payouts_enabled'):
                self.stripe_payouts_enabled = info_stripe.get('payouts_enabled')
                self.save()
        return self.stripe_payouts_enabled

    def link_for_onboard_stripe(self):
        # Doublon avec basebillet.views.create_account_link_for_onboard ?
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        url_onboard_stripe = stripe.AccountLink.create(
            account=self.get_stripe_connect_account(),
            refresh_url=f"https://{tenant_url}/tenant/{self.stripe_connect_account}/onboard_stripe_return/",
            return_url=f"https://{tenant_url}/tenant/{self.stripe_connect_account}/onboard_stripe_return/",
            type="account_onboarding",
        )

        # Clean des objets stripes
        Configuration.get_solo().clean_product_stripe_id()

        return url_onboard_stripe.url

    def onboard_stripe(self):
        try:
            # on vérifie que le compte soit toujours lié et qu'il peut recevoir des paiements :
            if not self.stripe_payouts_enabled:
                if not self.check_stripe_payouts():
                    logger.info("onboard_stripe")
                    # if self.check_stripe_payouts():
                    #     return "Stripe connected"
                    url_onboard_stripe = self.link_for_onboard_stripe()
                    msg = _('Link your stripe account to accept payment')
                    return format_html(f"<a href='{url_onboard_stripe}'>{msg}</a>")
            return _("Stripe connected")
        except Exception as e:
            logger.error(_("Stripe error, check admin"))
            return format_html("<p>" + _("Stripe error, check admin") + "</p>")

    def clean_product_stripe_id(self):
        ProductSold.objects.all().update(id_product_stripe=None)
        PriceSold.objects.all().update(id_price_stripe=None)
        return True

    """
    ### FEDERATION
    """

    federated_with = models.ManyToManyField(Client,
                                            blank=True,
                                            verbose_name=_("Federated with"),
                                            related_name="federated_with",
                                            help_text=_(
                                                "Displays events and subscription of the federated collectives."))

    """
    ### TVA ###
    """

    vat_taxe = models.DecimalField(max_digits=4, decimal_places=2, default=0, help_text=_("Default VAT"))

    ######### GHOST #########
    # ghost_url = models.URLField(blank=True, null=True)
    # ghost_key = models.CharField(max_length=200, blank=True, null=True)
    # ghost_last_log = models.TextField(blank=True, null=True)

    """
    ### Tenant fields ###
    """

    def domain(self):
        return connection.tenant.get_primary_domain().domain

    def categorie(self):
        return connection.tenant.categorie

    def save(self, *args, **kwargs):
        '''
        Transforme le nom en slug si vide, pour en faire une url lisible
        '''
        if not self.slug:
            self.slug = slugify(f"{self.organisation}")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('Settings')
        verbose_name_plural = _('Settings')

    def __str__(self):
        if self.organisation:
            return _("Settings for ") + self.organisation
        return _('Settings')


class Product(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=500, verbose_name=_("Name"))

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Short description"))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"))

    publish = models.BooleanField(default=True, verbose_name=_("Publish"))
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Weight"),
                                             help_text=_("Products are ordered lightest first."))

    tag = models.ManyToManyField(Tag, blank=True, related_name="produit_tags")

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="produits_radio",
                                                   verbose_name=_("Single choice options"),
                                                   help_text=_(
                                                       "Only one choice can be selected at order time."))

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="produits_checkbox",
                                                      verbose_name=_("Multiple choice options"),
                                                      help_text=_(
                                                          "Any number of choices can be selected at order time."))

    # TODO: doublon ?
    terms_and_conditions_document = models.URLField(blank=True, null=True)
    legal_link = models.URLField(blank=True, null=True, verbose_name=_("Terms and conditions link"),
                                 help_text=_(
                                     "Not required. If completed, displays a checkbox to validate the membership product."))

    img = StdImageField(upload_to='images/',
                        null=True, blank=True,
                        validators=[MaxSizeValidator(1920, 1920)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                        },
                        delete_orphans=True,
                        verbose_name=_('Product image'),
                        )

    NONE, BILLET, PACK, RECHARGE_CASHLESS = 'N', 'B', 'P', 'R'
    RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION, BADGE = 'S', 'T', 'M', 'A', 'G'
    DON, FREERES, NEED_VALIDATION = 'D', 'F', 'V'

    CATEGORIE_ARTICLE_CHOICES = [
        (NONE, _('Select a category')),
        (BILLET, _('Ticket booking')),
        (FREERES, _('Free booking')),
        # (PACK, _("Pack d'objets")),
        # (RECHARGE_CASHLESS, _('Recharge cashless')),
        # (RECHARGE_FEDERATED, _('Recharge suspendue')),
        # (VETEMENT, _('Vetement')),
        # (MERCH, _('Merchandasing')),
        (ADHESION, _('Subscription or membership')),
        (BADGE, _('Punchclock')),
        # (DON, _('Don')),
        # (NEED_VALIDATION, _('Nécessite une validation manuelle'))
    ]

    categorie_article = models.CharField(max_length=3, choices=CATEGORIE_ARTICLE_CHOICES, default=NONE,
                                         verbose_name=_("Product type"))

    nominative = models.BooleanField(default=False,
                                     verbose_name=_("Named booking"),
                                     help_text=_("Intended recipient's first and last names required for each ticket."),
                                     )

    archive = models.BooleanField(default=False, verbose_name=_("Archive"))

    # TODO: A retirer, plus utilisé ?
    # send_to_cashless = models.BooleanField(default=False,
    #                                        verbose_name="Envoyer au cashless",
    #                                        help_text="Produit checké par le serveur cashless.",
    #                                        )

    def fedow_category(self):
        self_category_map = {
            self.ADHESION: 'SUB',
            self.RECHARGE_CASHLESS: 'FED',
            self.BADGE: 'BDG',
        }
        return self_category_map.get(self.categorie_article, None)

    def origin(self):
        return connection.tenant

    def __str__(self):
        return f"{self.name}"

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        unique_together = ('categorie_article', 'name')


@receiver(post_save, sender=Product)
def post_save_Product(sender, instance: Product, created, **kwargs):
    if created:
        # poids d'apparition
        if instance.poids == 0:
            instance.poids = len(Product.objects.all()) + 1
        instance.save()


"""
Un autre post save existe dans .signals.py : send_membership_and_badge_product_to_fedow
Dans fichier signals pour éviter les doubles imports
Il vérifie l'existante du produit Adhésion et Badge dans Fedow et le créé si besoin
"""


class Price(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="prices", verbose_name=_("Product"))

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    name = models.CharField(max_length=50, verbose_name=_("Rate name"))
    prix = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_("Price"),
                               help_text=_("If the free price is activated, the amount is the minimum accepted rate."))
    order = models.SmallIntegerField(default=100, verbose_name=_("Display order"))

    free_price = models.BooleanField(default=False, verbose_name=_("Open price"),
                                     help_text=_("The amount will be asked on the Stripe checkout page."))

    publish = models.BooleanField(default=True, verbose_name=_("Publish"))

    TNA, DIX, VINGT, HUITCINQ, DEUXDEUX = 'NA', 'DX', 'VG', 'HC', 'DD'
    TVA_CHOICES = [
        (TNA, _('Non applicable')),
        (DIX, _("10 %")),
        (VINGT, _('20 %')),
        (HUITCINQ, _('8.5 %')),
        (DEUXDEUX, _('2.2 %')),
    ]

    vat = models.CharField(max_length=2,
                           choices=TVA_CHOICES,
                           default=TNA,
                           verbose_name=_("VAT rate"),
                           )

    stock = models.SmallIntegerField(blank=True, null=True)
    max_per_user = models.PositiveSmallIntegerField(
        default=10,
        verbose_name=_("Maximum orders per user"),
        help_text=_("The same email can be used for multiple orders.")
    )

    adhesion_obligatoire = models.ForeignKey(Product, on_delete=models.PROTECT,
                                             related_name="adhesion_obligatoire",
                                             verbose_name=_("Subscription required"),
                                             help_text=_(
                                                 "Rate available to suscribers only: "),
                                             blank=True, null=True)

    NA, YEAR, MONTH, DAY, HOUR, CIVIL, SCHOLAR = 'N', 'Y', 'M', 'D', 'H', 'C', 'S'
    SUB_CHOICES = [
        (NA, _('Non applicable')),
        (HOUR, _('1 hour')),
        (DAY, _('1 day')),
        (MONTH, _('30 days')),
        (YEAR, _("365 days")),
        (CIVIL, _('Calendar year : 1st of January')),
        (SCHOLAR, _('School year: 1st of September')),
    ]

    subscription_type = models.CharField(max_length=1,
                                         choices=SUB_CHOICES,
                                         default=NA,
                                         verbose_name=_("Subscription duration"),
                                         )

    recurring_payment = models.BooleanField(default=False,
                                            verbose_name="Monthly fee",
                                            help_text="Monthly payment through Stripe, "
                                                      "limited to one product at checkout.",
                                            )

    # def range_max(self):
    #     return range(self.max_per_user + 1)

    def __str__(self):
        return f"{self.product.name} {self.name}"

    # def has_stock(self):
    #     if self.stock > 0 :
    #         ticket_count = Ticket.objects.filter(pricesold__price=self).count()
    #     return True


    class Meta:
        unique_together = ('name', 'product')
        ordering = ('order',)
        verbose_name = _('Rate')
        verbose_name_plural = _('Rates')


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=200, verbose_name=_("Event name"))
    slug = models.SlugField(unique=True, db_index=True, blank=True, null=True, max_length=250)

    datetime = models.DateTimeField(verbose_name=_("Event start"))
    end_datetime = models.DateTimeField(blank=True, null=True, verbose_name=_("Event end"),
                                        help_text=_("Second date / time optional"))

    created = models.DateTimeField(auto_now=True)
    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Maximum capacity"))
    max_per_user = models.PositiveSmallIntegerField(default=10,
                                                    verbose_name=_(
                                                        "Maximum bookings per user"),
                                                    help_text=_("The same email can be used for multiple tickets.")
                                                    )

    postal_address = models.ForeignKey(PostalAddress, on_delete=SET_NULL, blank=True, null=True)

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Short description"))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"))

    is_external = models.BooleanField(default=False, verbose_name=_("External event"), help_text=_(
        "The event is handled outside of this platform (ex: Facebook event)."))
    full_url = models.URLField(blank=True, null=True)

    published = models.BooleanField(default=True, verbose_name=_("Publish"))
    private = models.BooleanField(default=False, verbose_name=_("Évènement non fédérable"), help_text=_("Ne s'affichera pas sur les agendas partagés."))

    products = models.ManyToManyField(Product, blank=True, verbose_name=_("Products"))

    tag = models.ManyToManyField(Tag, blank=True, related_name="events", verbose_name=_("Tags"))

    options_radio = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_radio",
                                           verbose_name="Single choice menu")
    options_checkbox = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_checkbox",
                                              verbose_name="Multiple choice menu")

    # cashless = models.BooleanField(default=False, verbose_name="Proposer la recharge cashless")
    minimum_cashless_required = models.SmallIntegerField(default=0,
                                                         verbose_name=_(
                                                             "Minimum value of cashless refill"))

    img = StdImageField(upload_to='images/',
                        validators=[MaxSizeValidator(1920, 1920)],
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                        },
                        delete_orphans=True, verbose_name=_("Main image")
                        )

    carrousel = models.ManyToManyField(Carrousel, blank=True, verbose_name=_("Carousel slides"),
                                       related_name='events')

    CONCERT = "LIV"
    FESTIVAL = "FES"
    REUNION = "REU"
    CONFERENCE = "CON"
    RESTAURATION = "RES"
    CHANTIER = "CHT"
    ACTION = "ACT"
    TYPE_CHOICES = [
        (CONCERT, _('Concert')),
        (FESTIVAL, _('Festival')),
        (REUNION, _('Meeting')),
        (CONFERENCE, _('Conference')),
        (RESTAURATION, _('Catering')),
        (CHANTIER, _('Workcamp')),
        (ACTION, _('Volunteering')),
    ]

    categorie = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CONCERT,
                                 verbose_name=_("Event category"))

    # recurrent = models.ManyToManyField(Weekday, blank=True,
    #                                    help_text=_(
    #                                        "Selectionnez le jour de la semaine pour une récurence hebdomadaire. La date de l'évènement sera la date de fin de la récurence."),
    #                                    verbose_name=_("Jours de la semaine"))

    # La relation parent / enfant
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
        on_delete=models.CASCADE
    )

    easy_reservation = models.BooleanField(default=False, verbose_name=_("Quick booking"),
                                           help_text=_("One-click booking for logged-in user."))

    booking = models.BooleanField(default=False, verbose_name=_("Restaurant mode / scheduler"),
                                  help_text=_(
                                      "The event will be visible at the top of the home page, allowing the user to book a specific date."))

    """ Pour signer les tickets """
    rsa_key = models.OneToOneField(RsaKey, on_delete=models.SET_NULL, null=True, related_name='event')

    def get_private_key(self):
        if not self.rsa_key:
            self.rsa_key = RsaKey.generate()
            self.save()

        private_key = serialization.load_pem_private_key(
            self.rsa_key.private_pem.encode('utf-8'),
            password=settings.SECRET_KEY.encode('utf-8'),
        )
        return private_key

    def get_public_pem(self):
        if not self.rsa_key:
            self.rsa_key = RsaKey.generate()
            self.save()
        return self.rsa_key.public_pem

    def get_public_key(self):
        # Charger la clé publique au format PEM
        public_key = serialization.load_pem_public_key(
            self.get_public_pem().encode('utf-8'),
            backend=default_backend()
        )
        return public_key

    """ END Pour signer les tickets """

    def reservation_solo(self):
        if self.max_per_user == 1:
            if self.products.all().count() == 1:
                if self.products.first().prices.all().count() == 1:
                    return True
        return False

    def url(self):
        return f"https://{connection.tenant.get_primary_domain().domain}/event/{self.slug}/"

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
        elif self.artists.all().count() > 0:
            artist_on_event: Artist_on_event = self.artists.all()[0]
            tenant: Client = artist_on_event.artist
            with tenant_context(tenant):
                img = Configuration.get_solo().img

            return {
                'fhd': img.fhd.url,
                'hdr': img.hdr.url,
                'med': img.med.url,
                'thumbnail': img.thumbnail.url,
                'crop_hdr': img.crop_hdr.url,
                'crop': img.crop.url,

            }
        else:
            return {}

    def valid_tickets_count(self):
        """
        Renvoie la quantité de tous les ticket valide d'un évènement.
        Compte les billets achetés/réservés.
        """

        return Ticket.objects.filter(reservation__event__pk=self.pk) \
            .exclude(status=Ticket.CREATED) \
            .exclude(status=Ticket.NOT_ACTIV) \
            .count()

    def complet(self):
        """
        Un booléen pour savoir si l'évènement est complet ou pas.
        """

        if self.valid_tickets_count() >= self.jauge_max:
            return True
        else:
            return False

    # def check_serveur_cashless(self):
    #     config = Configuration.get_solo()
    #     return config.check_serveur_cashless()

    def next_datetime(self):
        # Création de la liste des prochaines récurences
        if self.recurrent.all().count() > 0:
            jours_recurence = [day.day for day in self.recurrent.all().order_by('day')]
            dates = [datetime.combine((timezone.localdate() + relativedelta(weekday=day)),
                                      self.datetime.time(), self.datetime.tzinfo)
                     for day in jours_recurence]
            dates.sort()
            return dates

        return [self.datetime, ]

    def save(self, *args, **kwargs):
        """
        Transforme le titre de l'evenemennt en slug, pour en faire une url lisible
        """
        config = Configuration.get_solo()
        timezone = pytz.timezone(config.fuseau_horaire)
        self.slug = slugify(f"{self.name} {self.datetime.astimezone(timezone).strftime('%y%m%d-%H%M')}")

        # Génère l'url de l'évènement si il n'est pas externe.
        # Nécéssaire pour le prefetch multi tenant
        if not self.is_external:
            self.full_url = f"https://{connection.tenant.get_primary_domain().domain}/event/{self.slug}/"

        # Si parent, on force la catégorie ACTION
        if self.parent:
            self.categorie = Event.ACTION
            self.easy_reservation = True

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.datetime.strftime('%d/%m')} {self.name}"

    class Meta:
        unique_together = ('name', 'datetime')
        ordering = ('datetime',)
        verbose_name = _('Event')
        verbose_name_plural = _('Events')


"""
@receiver(post_save, sender=Event)
def add_to_public_event_directory(sender, instance: Event, created, **kwargs):
    '''
    Vérifie que le priceSold est créé pour chaque price de chaque product présent dans l'évènement
    L'objet PriceSold est nécéssaire pour la création d'un ticket.
    '''
    for product in instance.products.all():
        # On va chercher le stripe id du product
        productsold, created = ProductSold.objects.get_or_create(
            event=instance,
            product=product
        )

        if created:
            productsold.get_id_product_stripe()
        logger.info(
            f"productsold {productsold.nickname()} created : {created}")

        for price in product.prices.all():
            # On va chercher le stripe id du price

            pricesold, created = PriceSold.objects.get_or_create(
                productsold=productsold,
                prix=price.prix,
                price=price,
            )

            if created:
                pricesold.get_id_price_stripe()
            logger.info(f"pricesold {pricesold.price.name} created : {created} - {pricesold.get_id_price_stripe()}")
"""


class Artist_on_event(models.Model):
    artist = models.ForeignKey(Client, on_delete=models.PROTECT)
    datetime = models.DateTimeField()
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="artists")

    def configuration(self):
        with tenant_context(self.artist):
            return Configuration.get_solo()


#
# @receiver(post_save, sender=Artist_on_event)
# def event_productsold_create(sender, instance: Artist_on_event, created, **kwargs):
#     place = connection.tenant
#     artist = instance.artist
#     with schema_context('public'):
#         event_directory, created = EventDirectory.objects.get_or_create(
#             datetime=instance.datetime,
#             event_uuid=instance.event.uuid,
#             place=place,
#             artist=artist,
#         )


class ProductSold(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)

    id_product_stripe = models.CharField(max_length=30, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True, blank=True)

    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    categorie_article = models.CharField(max_length=3, choices=Product.CATEGORIE_ARTICLE_CHOICES, default=Product.NONE,
                                         verbose_name=_("Product type"))

    def __str__(self):
        return self.product.name

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.categorie_article == Product.NONE and self.product:
            self.categorie_article = self.product.categorie_article
        super().save(force_insert, force_update, using, update_fields)

    def img(self):
        if self.product.img:
            return self.product.img
        elif self.event:
            if self.event.img:
                return self.event.img

        return Configuration.get_solo().img

    def nickname(self):
        if self.product.categorie_article == Product.BILLET:
            return f"{self.event.name} {self.event.datetime.strftime('%D')} - {self.product.name}"
        else:
            return f"{self.product.name}"

    def get_id_product_stripe(self,
                              force=False,
                              stripe_key=None,
                              ):

        if self.id_product_stripe and not force:
            return self.id_product_stripe

        stripe_key = RootConfiguration.get_solo().get_stripe_api()
        stripe.api_key = stripe_key

        client = connection.tenant
        # On est en mode test :
        domain_url = "lespass.tibillet.localhost" if type(client) == FakeTenant else client.get_primary_domain()

        # noinspection PyUnresolvedReferences
        images = []
        if self.img():
            images = [f"https://{domain_url}{self.img().med.url}", ]

        product = stripe.Product.create(
            name=f"{self.nickname()}",
            stripe_account=Configuration.get_solo().get_stripe_connect_account(),
            images=images
        )

        logger.info(f"product {product.name} created : {product.id}")
        self.id_product_stripe = product.id

        # On répertorie tout les produit pour savoir lequel incrémenter en cas de stripe webhook
        # Non utile en test
        # if type(connection.tenant) != FakeTenant:
        #     with schema_context('public'):
        #         product_directory, created = ProductDirectory.objects.get_or_create(
        #             place=client,
        #             product_sold_stripe_id=product.id,
        #         )

        self.save()
        return self.id_product_stripe

    def reset_id_stripe(self):
        self.id_product_stripe = None
        self.pricesold_set.all().update(id_price_stripe=None)
        self.save()


class PriceSold(models.Model):
    '''
    Un objet article vendu. Ne change pas si l'article original change.
    Différente de LigneArticle qui est la ligne comptable
    '''
    uuid = models.UUIDField(primary_key=True, default=uuid4)

    id_price_stripe = models.CharField(max_length=30, null=True, blank=True)

    productsold = models.ForeignKey(ProductSold, on_delete=models.PROTECT, verbose_name=_("Product"))
    price = models.ForeignKey(Price, on_delete=models.PROTECT)

    # TODO: A virer, inutile ici, c'est ligne article qui comptabilise les qty
    qty_solded = models.SmallIntegerField(default=0)

    prix = models.DecimalField(max_digits=6, decimal_places=2)
    gift = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        if self.productsold.event:
            str_name = f"{self.productsold.event.name} - {self.price.name}"
        else:
            str_name = self.price.name

        if not self.price.free_price:
            str_name += f" - {self.price.prix}€"
        return str_name

    def get_id_price_stripe(self, force=False):
        logger.info("get_id_price_stripe")
        if self.id_price_stripe and not force:
            return self.id_price_stripe

        stripe_key = RootConfiguration.get_solo().get_stripe_api()
        stripe.api_key = stripe_key

        try:
            product_stripe = self.productsold.get_id_product_stripe()
            stripe.Product.retrieve(product_stripe)
        except InvalidRequestError:
            product_stripe = self.productsold.get_id_product_stripe(force=True)

        data_stripe = {
            'unit_amount': f"{int(Decimal(self.prix) * 100)}",
            'currency': "eur",
            'product': product_stripe,
            'stripe_account': Configuration.get_solo().get_stripe_connect_account(),
            'nickname': f"{self.price.name}",
        }

        if self.price.subscription_type == Price.MONTH \
                and self.price.recurring_payment:
            data_stripe['recurring'] = {
                "interval": "month",
                "interval_count": 1
            }

        elif self.price.subscription_type == Price.YEAR \
                and self.price.recurring_payment:
            data_stripe['recurring'] = {
                "interval": "year",
                "interval_count": 1
            }

        if self.price.free_price:
            data_stripe.pop('unit_amount')
            data_stripe['billing_scheme'] = "per_unit"
            data_stripe['custom_unit_amount'] = {
                "enabled": "true",
                "minimum": f"{int(Decimal(self.prix) * 100)}",
                # "preset": f"{int(Decimal(self.prix) * 100)}",
            }

        price = stripe.Price.create(**data_stripe)

        self.id_price_stripe = price.id
        self.save()
        return self.id_price_stripe

    def reset_id_stripe(self):
        self.id_price_stripe = None
        self.save()

    # def total(self):
    #     return Decimal(self.prix) * Decimal(self.qty_solded)
    # class meta:
    #     unique_together = [['productsold', 'price']]


# @receiver(post_save, sender=OptionGenerale)
# def poids_option_generale(sender, instance: OptionGenerale, created, **kwargs):

# def save(self, force_insert=False, force_update=False, using=None,
#          update_fields=None):
#     if not self.id_price_stripe :
#         logger.info(f"PriceSold : {self.price.name} - Stripe : {self.get_id_price_stripe()}")

class Reservation(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)
    datetime = models.DateTimeField(auto_now=True)

    user_commande: AuthBillet.models.TibilletUser = models.ForeignKey(settings.AUTH_USER_MODEL,
                                                                      on_delete=models.PROTECT,
                                                                      related_name='reservations')

    event = models.ForeignKey(Event,
                              on_delete=models.PROTECT,
                              related_name="reservation")

    CANCELED, CREATED, UNPAID, FREERES, FREERES_USERACTIV, PAID, PAID_ERROR, PAID_NOMAIL, VALID, = 'C', 'R', 'U', 'F', 'FA', 'P', 'PE', 'PN', 'V'
    TYPE_CHOICES = [
        (CANCELED, _('Cancelled')),
        (CREATED, _('Created')),
        (UNPAID, _('Payment still pending')),
        (FREERES, _('Email verification still pending')),
        (FREERES_USERACTIV, _('Email verified')),
        (PAID, _('Payment confirmed')),
        (PAID_ERROR, _('Payment confirmed but invalid email')),
        (PAID_NOMAIL, _('Payment confirmed but email not sent')),
        (VALID, _('Confirmed')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Order status"))

    # Doit-on envoyer le ticket par mail ?
    to_mail = models.BooleanField(default=True)

    # Mail bien parti ?
    mail_send = models.BooleanField(default=False)

    # Mail parti, mais retour en erreur ?
    mail_error = models.BooleanField(default=False)

    # paiement = models.OneToOneField(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True,
    #                                 related_name='reservation')

    options = models.ManyToManyField(OptionGenerale, blank=True)

    class Meta:
        ordering = ('-datetime',)

    def user_mail(self):
        return self.user_commande.email

    def paiements_paid(self):
        return self.paiements.filter(
            Q(status=Paiement_stripe.PAID) | Q(status=Paiement_stripe.VALID)
        )

    def articles_paid(self):
        articles_paid = []
        for paiement in self.paiements.all():
            for ligne in paiement.lignearticles.filter(
                    Q(status=LigneArticle.PAID) | Q(status=LigneArticle.VALID)
            ):
                articles_paid.append(ligne)
        return articles_paid

    def total_paid(self):
        total_paid = 0
        for ligne_article in self.articles_paid():
            ligne_article: LigneArticle
            total_paid += dround(ligne_article.amount * ligne_article.qty)
        return total_paid

    def __str__(self):
        return f"{self.user_commande.email} - {str(self.uuid).partition('-')[0]}"

    # def total_billet(self):
    #     total = 0
    #     for ligne in self.paiements.all():
    #         if ligne.billet:
    #             total += ligne.qty
    #     return total
    #
    # def total_prix(self):
    #     total = 0
    #     for ligne in self.paiements.all():
    #         if ligne.product:
    #             total += ligne.qty * ligne.product.prix
    #
    #     return total
    #
    # def _options_(self):
    #     return " - ".join([f"{option.name}" for option in self.options.all()])
    #


class Ticket(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    first_name = models.CharField(max_length=200, blank=True, null=True)
    last_name = models.CharField(max_length=200, blank=True, null=True)

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="tickets")

    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE, blank=True, null=True)

    CREATED, NOT_ACTIV, NOT_SCANNED, SCANNED = 'C', 'N', 'K', 'S'
    SCAN_CHOICES = [
        (CREATED, _('Created')),
        (NOT_ACTIV, _('Inactive')),
        (NOT_SCANNED, _('Not scanned')),
        (SCANNED, _('Scanned')),
    ]

    status = models.CharField(max_length=1, choices=SCAN_CHOICES, default=CREATED,
                              verbose_name=_("Scanning status"))

    seat = models.CharField(max_length=20, default=_('L'))

    sale_origin = models.CharField(max_length=2, choices=SaleOrigin.choices, default=SaleOrigin.LESPASS,
                                   verbose_name=_("Payment source"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))

    def paid(self):
        if self.pricesold:
            if self.pricesold.price.free_price:
                return self.reservation.total_paid()
            return self.pricesold.price.prix
        return 0
        # return 666

    def pdf_filename(self):
        first_name = f"{self.first_name.upper()}" if self.first_name else ""
        last_name = f"{self.last_name.upper()}" if self.last_name else ""

        config = Configuration.get_solo()
        return f"{config.organisation.upper()} " \
               f"{self.reservation.event.name} " \
               f"{self.reservation.event.datetime.astimezone().strftime('%d/%m/%Y')} " \
               f"{first_name}" \
               f"{last_name}" \
               f"{self.status}-{self.numero_uuid()}-{self.seat}" \
               f".pdf"

    def pdf_url(self):
        domain = connection.tenant.domains.all().first().domain
        api_pdf = reverse("ticket_uuid_to_pdf", args=[f"{self.uuid}"])
        protocol = "https://"
        port = ""
        # if settings.DEBUG:
        #     protocol = "http://"
        #     port = ":8002"
        return f"{protocol}{domain}{port}{api_pdf}"

    def event_name(self):
        return self.reservation.event.name

    def event(self):
        return self.reservation.event

    event.allow_tags = True
    event.short_description = _('Event')
    event.admin_order_field = 'reservation__event'

    def datetime(self):
        return self.reservation.datetime

    datetime.allow_tags = True
    datetime.short_description = _('Booking date')
    datetime.admin_order_field = 'reservation__datetime'

    def numero_uuid(self):
        return f"{self.uuid}".split('-')[0]

    def options(self):
        return " - ".join([option.name for option in self.reservation.options.all()])

    def qrcode(self):
        qrcode_data = data_to_b64({'uuid': str(self.uuid), })
        signature = sign_message(
            qrcode_data,
            self.reservation.event.get_private_key(),
        ).decode('utf-8')

        # Ici, on s'autovérifie :
        # Assert volontaire. Si non effectué en prod, ce n'est pas grave.
        # logger.debug("_post verify_signature start")
        if not verify_signature(self.reservation.event.get_public_key(),
                                qrcode_data,
                                signature):
            raise Exception("Signature self-check failed")

        return f"{qrcode_data.decode('utf8')}:{signature}"

    class Meta:
        verbose_name = _('Ticket')
        verbose_name_plural = _('Tickets')


class FedowTransaction(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_index=False)
    hash = models.CharField(max_length=64, unique=True, editable=False)
    datetime = models.DateTimeField()


class Paiement_stripe(models.Model):
    """
    La commande
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)
    detail = models.CharField(max_length=50, blank=True, null=True)
    datetime = models.DateTimeField(auto_now=True)

    checkout_session_id_stripe = models.CharField(max_length=80, blank=True, null=True)
    payment_intent_id = models.CharField(max_length=80, blank=True, null=True)
    metadata_stripe = JSONField(blank=True, null=True)
    customer_stripe = models.CharField(max_length=20, blank=True, null=True)  # pas utile
    invoice_stripe = models.CharField(max_length=27, blank=True, null=True)
    subscription = models.CharField(max_length=28, blank=True, null=True)

    order_date = models.DateTimeField(auto_now_add=True, verbose_name="Order date")
    last_action = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True)

    NON, OPEN, PENDING, EXPIRE, PAID, VALID, NOTSYNC, CANCELED = 'N', 'O', 'W', 'E', 'P', 'V', 'S', 'C'
    STATUS_CHOICES = (
        (NON, 'Payment link not generated'),
        (OPEN, 'Sent to Stripe'),
        (PENDING, 'Waiting for payment'),
        (EXPIRE, 'Expired'),
        (PAID, 'Paid for'),
        (VALID, 'Paid and confirmed'),  # envoyé sur serveur cashless
        (NOTSYNC, 'Paid but issues with Stripe sync'),  # envoyé sur serveur cashless qui retourne une erreur
        (CANCELED, 'Cancelled'),
    )
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=NON, verbose_name="Order status")

    traitement_en_cours = models.BooleanField(default=False)
    NA, WEBHOOK, GET, WEBHOOK_INVOICE = 'N', 'W', 'G', 'I'

    SOURCE_CHOICES = (
        (NA, _('No processing ongoing')),
        (WEBHOOK, _('From Stripe webhook')),
        (GET, _('From Get')),
        (WEBHOOK_INVOICE, _('From invoice webhook')),
    )
    source_traitement = models.CharField(max_length=1, choices=SOURCE_CHOICES, default=NA,
                                         verbose_name="Processing origin")

    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, blank=True, null=True,
                                    related_name="paiements")

    QRCODE, API_BILLETTERIE, FRONT_BILLETTERIE, INVOICE, TRANSFERT = 'Q', 'B', 'F', 'I', 'T'
    SOURCE_CHOICES = (
        (QRCODE, _('From QR code scan')), # ancien api. A virer ?
        (API_BILLETTERIE, _('From API')),
        (FRONT_BILLETTERIE, _('From ticketing app')),
        (INVOICE, _('From invoice')),
        (TRANSFERT, _('Stripe Transfert')),

    )
    source = models.CharField(max_length=1, choices=SOURCE_CHOICES, default=API_BILLETTERIE,
                              verbose_name="Order source")

    fedow_transactions = models.ManyToManyField(FedowTransaction, blank=True, related_name="paiement_stripe")

    # total = models.FloatField(default=0)
    def total(self):
        if self.source == self.TRANSFERT: # c'est un transfert de compte stripe
            payload = json.loads(self.metadata_stripe)
            return dround(payload["data"]["object"]["amount"])
        return dround(self.lignearticles.all().aggregate(Sum('amount'))['amount__sum']) or 0

    def uuid_8(self):
        return f"{self.uuid}".partition('-')[0]

    def invoice_number(self):
        date = self.order_date.strftime('%y%m%d')
        return f"{date}-{self.uuid_8()}"

    def __str__(self):
        return self.uuid_8()

    def articles(self):
        return " - ".join(
            [
                f"{ligne.pricesold.productsold.product.name} / {ligne.pricesold.price.name} / {dround(ligne.qty * ligne.amount)}€"
                for ligne in self.lignearticles.all()])

    def get_checkout_session(self):
        config = Configuration.get_solo()
        # stripe.api_key = config.get_stripe_api()
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        checkout_session = stripe.checkout.Session.retrieve(
            self.checkout_session_id_stripe,
            stripe_account=config.get_stripe_connect_account()
        )
        return checkout_session

    def update_checkout_status(self) -> str:
        if self.status == Paiement_stripe.VALID:
            return self.status

        if self.traitement_en_cours:
            return self.status

        checkout_session = self.get_checkout_session()

        # Pas payé, on le met en attente
        if checkout_session.payment_status == "unpaid":
            self.status = Paiement_stripe.PENDING
            # Si le paiement est expiré
            if datetime.now().timestamp() > checkout_session.expires_at:
                self.status = Paiement_stripe.EXPIRE

        elif checkout_session.payment_status == "paid":
            self.status = Paiement_stripe.PAID
            self.last_action = timezone.now()
            self.traitement_en_cours = True

            # Dans le cas d'un nouvel abonnement
            # On va chercher le numéro de l'abonnement stripe
            # Et sa facture
            if checkout_session.mode == 'subscription':
                if bool(checkout_session.subscription):
                    self.subscription = checkout_session.subscription
                    subscription = stripe.Subscription.retrieve(
                        checkout_session.subscription,
                        stripe_account=Configuration.get_solo().get_stripe_connect_account()
                    )
                    self.invoice_stripe = subscription.latest_invoice

        else:
            self.status = Paiement_stripe.CANCELED

        # cela va déclencher des pre_save

        # le .save() lance le process pre_save BaseBillet.models.send_to_cashless
        # qui modifie le status de chaque ligne
        # et envoie les informations au serveur cashless.

        # si validé par le serveur cashless, alors la ligne sera VALID.
        # Si toute les lignes sont VALID, le paiement_stripe sera aussi VALID
        # grace au post_save BaseBillet.models.check_status_stripe

        # Reservation.VALID lorsque le mail est envoyé et non en erreur
        self.save()
        return self.status

    class Meta:
        verbose_name = _('Stripe payment')
        verbose_name_plural = _('Stripe payments')


class LigneArticle(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)
    datetime = models.DateTimeField(auto_now_add=True)

    # L'objet price sold. Contient l'id Stripe
    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE, verbose_name=_("Product sold"))

    qty = models.SmallIntegerField()
    amount = models.IntegerField(default=0, verbose_name=_("Value"))  # Centimes en entier (50.10€ = 5010)
    vat = models.DecimalField(max_digits=4, decimal_places=2, default=0, verbose_name=_("VAT"))

    carte = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, blank=True, null=True)

    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True,
                                        related_name="lignearticles")
    membership = models.ForeignKey("Membership", on_delete=models.PROTECT, blank=True, null=True,
                                   verbose_name=_("Linked subscription"), related_name="lignearticles")

    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))

    CANCELED, CREATED, UNPAID, PAID, FREERES, VALID, = 'C', 'O', 'U', 'P', 'F', 'V'
    TYPE_CHOICES = [
        (CANCELED, _('Cancelled')),
        (CREATED, _('Not sent to payment')),
        (UNPAID, _('Not paid')),
        (FREERES, _('Free booking')),
        (PAID, _('Paid but not confirmed')),
        (VALID, _('Confirmed')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Product entry status"))

    sended_to_laboutik = models.BooleanField(default=False, verbose_name=_("Sended to LaBoutik"))

    class Meta:
        ordering = ('-datetime',)

    def uuid_8(self):
        return f"{self.uuid}".partition('-')[0]

    def __str__(self):
        return self.uuid_8()

    def total(self) -> int:
        # Mise à jour de amount en cas de paiement stripe pour prix libre ( a virer après les migration ? )
        if self.amount == 0 and self.paiement_stripe and self.pricesold.price.free_price:
            if self.paiement_stripe.status in [Paiement_stripe.PAID, Paiement_stripe.VALID] :
                logger.info("Total == 0. free price ? go -> update_amount()")
                self.update_amount()
        return self.amount * self.qty

    def total_decimal(self):
        return dround(self.total())

    def get_stripe_checkout_session(self):
        paiement_stripe = self.paiement_stripe
        checkout_session = paiement_stripe.get_checkout_session()
        return checkout_session

    def update_amount(self):
        '''Dans le cas d'un prix libre, la somme payée n'est pas connu d'avance'''
        checkout_session = self.get_stripe_checkout_session()
        self.amount = checkout_session['amount_total']
        self.save()
        return self.amount

    def amount_decimal(self):
        return dround(self.amount)

    def status_stripe(self):
        if self.paiement_stripe:
            return self.paiement_stripe.status
        else:
            return _('No Stripe send')

    # def user_uuid_wallet(self):
    #     if self.paiement_stripe:
    #         user: "HumanUser" = self.paiement_stripe.user
    #         user.refresh_from_db()
    #         return user.wallet.uuid
    #     elif self.membership:
    #         user: "HumanUser" = self.membership.user
    #         user.refresh_from_db()
    #         return user.wallet.uuid
    #     return None

    def paiement_stripe_uuid(self):
        # LaBoutik récupère cet uuid comme commande
        # Si la vente à été prise dans l'admin, on prend l'uuid de l'objet
        if self.paiement_stripe:
            return f"{self.paiement_stripe.uuid}"
        return f"{self.uuid}"


class Membership(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             related_name='memberships', blank=True, null=True)
    price = models.ForeignKey(Price, on_delete=models.PROTECT, related_name='membership',
                              verbose_name=_('Product / price'),
                              null=True, blank=True)

    asset_fedow = models.UUIDField(null=True, blank=True)
    card_number = models.CharField(max_length=16, null=True, blank=True)

    date_added = models.DateTimeField(auto_now_add=True)

    last_contribution = models.DateTimeField(null=True, blank=True, verbose_name=_("Payment date"))
    first_contribution = models.DateTimeField(null=True, blank=True)  # encore utilisé ? On utilise last plutot ?

    last_action = models.DateTimeField(auto_now=True, verbose_name=_("Presence"))
    contribution_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                             verbose_name=_("Contribution"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))

    deadline = models.DateTimeField(null=True, blank=True, verbose_name=_("Subscription end"))

    first_name = models.CharField(
        db_index=True,
        max_length=200,
        verbose_name=_("First name"),
        null=True, blank=True
    )

    last_name = models.CharField(
        max_length=200,
        verbose_name=_("Last name"),
        null=True, blank=True
    )

    pseudo = models.CharField(max_length=50, null=True, blank=True)

    newsletter = models.BooleanField(
        default=True, verbose_name=_("I want to receive the collective's newsletter."))
    postal_code = models.IntegerField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)

    CANCELED, AUTO, ONCE, ADMIN, IMPORT, LABOUTIK = 'C', 'A', 'O', 'D', 'I', 'L'
    STATUS_CHOICES = [
        (ADMIN, _("Saved through the admin")),
        (IMPORT, _("Import from file")),
        (ONCE, _('Single online stripe payment')),
        (AUTO, _('Automatic stripe renewal')),
        (CANCELED, _('Cancelled')),
        (LABOUTIK, _('LaBoutik')),
    ]

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ONCE,
                              verbose_name=_("Origin"))

    option_generale = models.ManyToManyField(OptionGenerale,
                                             blank=True,
                                             related_name="membership_options")

    stripe_paiement = models.ManyToManyField(Paiement_stripe, blank=True, related_name="membership")
    stripe_id_subscription = models.CharField(
        max_length=28,
        null=True, blank=True
    )

    last_stripe_invoice = models.CharField(
        max_length=278,
        null=True, blank=True
    )

    fedow_transactions = models.ManyToManyField(FedowTransaction, blank=True, related_name="membership")

    class Meta:
        # unique_together = ('user', 'price')
        verbose_name = _('Subscription')
        verbose_name_plural = _('Subscriptions')

    def email(self):
        self.user: "HumanUser"
        if self.user:
            return str(self.user.email).lower()
        if self.card_number:
            return _('Anonymous ') + self.card_number
        return f'Anonymous'

    def member_name(self):
        if self.pseudo:
            return self.pseudo
        return f"{self.last_name} {self.first_name}"

    def set_deadline(self):
        deadline = None
        if self.last_contribution and self.price:
            if self.price.subscription_type == Price.HOUR:
                deadline = self.last_contribution + timedelta(hours=1)
            elif self.price.subscription_type == Price.DAY:
                deadline = self.last_contribution + timedelta(days=1)
            elif self.price.subscription_type == Price.MONTH:
                deadline = self.last_contribution + timedelta(days=31)
            elif self.price.subscription_type == Price.YEAR:
                deadline = self.last_contribution + timedelta(days=365)
            elif self.price.subscription_type == Price.CIVIL:
                # jusqu'au 31 decembre de cette année
                deadline = datetime.strptime(f'{self.last_contribution.year}-12-31', '%Y-%m-%d')
            elif self.price.subscription_type == Price.SCHOLAR:
                # Si la date de contribustion est avant septembre, alors on prend l'année de la contribution.
                if self.last_contribution.month < 9:
                    deadline = datetime.strptime(f'{self.last_contribution.year}-08-31', '%Y-%m-%d')
                # Si elle est après septembre, on prend l'année prochaine
                else:
                    deadline = datetime.strptime(f'{self.last_contribution.year + 1}-08-31', '%Y-%m-%d')
        self.deadline = deadline
        self.save()
        return deadline

    def get_deadline(self):
        if not self.deadline:
            return self.set_deadline()
        return self.deadline

    def is_valid(self):
        if self.get_deadline():
            if timezone.localtime() < self.deadline:
                return True
        return False

    is_valid.boolean = True

    def price_name(self):
        if self.price:
            return self.price.name
        return None

    def product_name(self):
        if self.price:
            if self.price.product:
                return self.price.product.name
        return None

    def product_uuid(self):
        if self.price:
            if self.price.product:
                return self.price.product.uuid
        return None

    def product_img(self):
        if self.price:
            if self.price.product:
                return self.price.product.img
        return None

    def options(self):
        return " - ".join([option.name for option in self.option_generale.all()])

    def payment_method_name(self):
        return self.get_payment_method_display()

    def status_name(self):
        return self.get_status_display()

    def __str__(self):
        if self.pseudo:
            return self.pseudo
        elif self.first_name:
            return f"{self.last_name} {self.first_name}"
        elif self.last_name:
            return f"{self.last_name}"
        elif self.user:
            return f"{self.user}"
        else:
            return "Anonymous"


#### MODEL POUR INTEROP ####

class ExternalApiKey(models.Model):
    name = models.CharField(max_length=30, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE,
                             blank=True, null=True,
                             help_text=_("User who created this key.")
                             )

    key = models.OneToOneField(APIKey,
                               on_delete=models.CASCADE,
                               blank=True, null=True,
                               related_name="api_key",
                               help_text=_(
                                   "Confirm to generate key. It will not appear before.")
                               )

    ip = models.GenericIPAddressField(
        blank=True, null=True,
        verbose_name=_("Ip source"),
        help_text=_("API key works with any IP unless specified.")
    )

    created = models.DateTimeField(auto_now=True)

    # read = models.BooleanField(default=True, verbose_name=_("Lecture"))

    # Droit des routes API (nom de variable doit être le basename de la route url vers le viewset)
    event = models.BooleanField(default=False, verbose_name=_("Events"))
    product = models.BooleanField(default=False, verbose_name=_("Products"))

    reservation = models.BooleanField(default=False, verbose_name=_("Bookings"))
    ticket = models.BooleanField(default=False, verbose_name=_("Tickets"))

    wallet = models.BooleanField(default=False, verbose_name=_("Wallets"))

    def api_permissions(self):
        return {
            # Basename ( regarder dans utils.py -> user_apikey_valid pour comprendre le mecanisme )
            "event": self.event,
            "product": self.product,
            "price": self.product,
            "reservation": self.reservation,
            "ticket": self.ticket,
            "wallet": self.wallet,
        }

    class Meta:
        verbose_name = _('Api key')
        verbose_name_plural = _('Api keys')

    def __str__(self):
        return f"{self.name} - {self.user} - {self.created.astimezone().strftime('%d-%m-%Y %H:%M:%S')}"


class Webhook(models.Model):
    active = models.BooleanField(default=False)
    url = models.URLField()

    RESERVATION_V, MEMBERSHIP_V = "RV", "MV"
    EVENT_CHOICES = [
        (MEMBERSHIP_V, _('Confirmed subscription')),
        (RESERVATION_V, _('Confirmed booking')),
    ]

    event = models.CharField(max_length=2, choices=EVENT_CHOICES, default=RESERVATION_V,
                             verbose_name=_("Event"))
    last_response = models.TextField(null=True, blank=True)


class FederatedPlace(models.Model):
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="Collective")
    tag_filter = models.ManyToManyField(Tag, blank=True, related_name="filtred", verbose_name=_("Tag filters"),
                                        help_text=_("Show only these tags."))
    tag_exclude = models.ManyToManyField(Tag, blank=True, related_name="excluded", verbose_name=_("Excluded tags"),
                                         help_text=_("Don't show those tags."))

    class Meta:
        verbose_name = _('Federated space')
        verbose_name_plural = _('Federated spaces')

    def __str__(self):
        return self.tenant.name


class History(models.Model):
    """
    Track change on user profile, event or membership
    """
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, blank=True, null=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True)
    datetime = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)
    link = models.URLField(null=True, blank=True)


### APP EXTERNE ###

class GhostConfig(SingletonModel):
    """
    Utilisé pour envoyer le mail des nouveaux adhérants automatiquement.
    Trigger : pre save adhésion sur BasBillet.triggers.LigneArticlePaid_ActionByCategorie.trigger_A
    Méthode async celery : BaseBillet.tasks.send_to_ghost
    """

    ghost_url = models.URLField(blank=True, null=True)
    ghost_key = models.CharField(max_length=400, blank=True, null=True)
    ghost_last_log = models.TextField(blank=True, null=True)

    def get_api_key(self):
        return fernet_decrypt(self.ghost_key) if self.ghost_key else None

    def set_api_key(self, string):
        self.ghost_key = fernet_encrypt(string)
        self.save()
        return True


# class DokosConfig(SingletonModel):
#     @classmethod
#     def get_cache_key(cls) -> str:
#         prefix = slugify(connection.tenant.pk)
#         return f"{prefix}:{cls.__module__.lower()}:{cls.__name__.lower()}"

#     dokos_id = models.CharField(max_length=100, blank=True, null=True, editable=False)

class FormbricksForms(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environmentId = models.CharField(max_length=30, help_text="Formbricks environment ID")
    trigger_name = models.CharField(max_length=30, help_text="Form trigger name")
    # Formulaire à l'achat d'une adhésion ou d'un billet d'evènement
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="formbricksform")

    class Meta:
        verbose_name = _('Formbricks form')
        verbose_name_plural = _('Formbricks forms')

    def __str__(self):
        return f"{self.product.name} : {self.trigger_name}"


class FormbricksConfig(SingletonModel):
    """
    Configuration de Formbricks pour les fomulaires sur mesures
    """



    api_key = models.CharField(max_length=200, blank=True, null=True)
    api_host = models.CharField(max_length=220, default="https://app.formbricks.com")

    def get_api_key(self):
        return fernet_decrypt(self.api_key) if self.api_key else None

    def set_api_key(self, string):
        self.api_key = fernet_encrypt(string)
        self.save()
        return True

    class Meta:
        verbose_name = _('Formbrick settings')
        verbose_name_plural = _('Formbrick settings')


class BrevoConfig(SingletonModel):


    api_key = models.CharField(max_length=400, blank=True, null=True)
    last_log = models.TextField(blank=True, null=True)

    def get_api_key(self):
        return fernet_decrypt(self.api_key) if self.api_key else None

    def set_api_key(self, string):
        self.api_key = fernet_encrypt(string)
        self.save()
        return True

    class Meta:
        verbose_name = _('Brevo setting')
        verbose_name_plural = _('Brevo settings')

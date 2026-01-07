# import os
import calendar
import json
import logging
import uuid
from calendar import month
from datetime import timedelta, datetime, tzinfo
from decimal import Decimal
from time import localtime
from uuid import uuid4
from functools import lru_cache

import pytz
import requests
import stripe
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db import models
from django.db.models import JSONField, SET_NULL, Sum
# Create your models here.
from django.db.models import Q
from django.db.models.query import QuerySet
from django.db.models.signals import post_save
from django.db.transaction import atomic
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _, activate
from django_tenants.postgresql_backend.base import FakeTenant
from django_tenants.utils import tenant_context
from rest_framework_api_key.models import APIKey, AbstractAPIKey
from django.core.cache import cache

from solo.models import SingletonModel

from stdimage import StdImageField
from stdimage.validators import MinSizeValidator
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
    QRCODE_MA = "QR", _("QrCode online")
    NFC_MA = "NF", _("NFC online")
    API = "AP", _("API")
    WEBHOOK = "WK", _("Webhook Stripe")


class PaymentMethod(models.TextChoices):
    UNKNOWN = "UK", _("Unknown")
    FREE = "NA", _("Offered")
    CC = "CC", _("Credit card: POS terminal")
    CASH = "CA", _("Cash")
    CHEQUE = "CH", _("Check")
    QRCODE_MA = "QR", _("QrCode or NFC")
    TRANSFER = "TR", _("Bank transfer")
    STRIPE_FED = "SF", _("Online: federated Stripe")
    STRIPE_NOFED = "SN", _("Online: Stripe CC")
    STRIPE_SEPA_NOFED = "SP", _("Online: Stripe SEPA")
    STRIPE_RECURENT = "SR", _("Recurring: Stripe")
    LOCAL_EURO = 'LE', _("Asset local fiat")
    LOCAL_GIFT = 'LG', _("Asset local gift")


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

    @classmethod
    def classic(cls):
        """Renvoie uniquement les choix pour un paiement comptoir"""
        return [
            (choice, label) for choice, label in cls.choices if
            choice in [cls.FREE, cls.CC, cls.CASH, cls.CHEQUE, cls.TRANSFER]
        ]


class Tag(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=50, verbose_name=_("Tag name"))
    slug = models.CharField(max_length=50, verbose_name=_("Tag slug"), db_index=True)
    color = models.CharField(max_length=7, verbose_name=_("Tag color"), default="#0dcaf0")

    @staticmethod
    def _clean_hex(value: str, default: str) -> str:
        try:
            v = (value or "").strip()
            if not v:
                return default
            if not v.startswith('#'):
                v = f"#{v}"
            if len(v) == 4:  # #abc -> #aabbcc
                v = f"#{v[1] * 2}{v[2] * 2}{v[3] * 2}"
            if len(v) != 7:
                return default
            int(v[1:], 16)  # validate
            return v.lower()
        except Exception:
            return default

    @property
    def color_bg(self):
        return self.color

    @property
    def contrast_fg(self) -> str:
        """Retourne '#000000' ou '#ffffff' selon le contraste avec color_bg (méthode YIQ)."""
        bg = self._clean_hex(self.color, "#0dcaf0")
        r = int(bg[1:3], 16)
        g = int(bg[3:5], 16)
        b = int(bg[5:7], 16)
        yiq = (r * 299 + g * 587 + b * 114) / 1000
        return "#000000" if yiq >= 128 else "#ffffff"

    @property
    def style_attr(self) -> str:
        """Inline style pour un badge coloré accessible."""
        bg = self._clean_hex(self.color_bg, "#0dcaf0")
        fg = self.contrast_fg
        return f"background-color:{bg};color:{fg};border:1px solid rgba(0,0,0,.1)"

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        self.color = self._clean_hex(self.color, "#0dcaf0")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

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

    img = StdImageField(upload_to='images/',
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                            'social_card': (1200, 630, True),
                        },
                        delete_orphans=True, verbose_name=_("Main image"),
                        help_text=_(
                            "The main image of the adress, displayed in the head of the event page if no image on event.")
                        )

    sticker_img = StdImageField(upload_to='images/',
                                blank=True, null=True,
                                variations={
                                    'fhd': (1920, 1920),
                                    'hdr': (1280, 1280),
                                    'med': (480, 480),
                                    'thumbnail': (150, 90),
                                    'crop_hdr': (960, 540, True),
                                    'crop': (480, 270, True),
                                },
                                delete_orphans=True, verbose_name=_("Sticker image"),
                                help_text=_(
                                    "The small image displayed in the events list if not img on event. If None, Main img will be displayed. 4x3 ratio.")
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
        max_digits=18,
        decimal_places=16,
        blank=True,
        null=True,
        verbose_name=_("Latitude"),
        help_text=_("GPS coordinate: latitude.")
    )
    longitude = models.DecimalField(
        max_digits=18,
        decimal_places=16,
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
        return f"{self.name}, {self.street_address}, {self.address_locality}"

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
            instance.poids = OptionGenerale.objects.all().count() + 1

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

    phone = models.CharField(max_length=20, verbose_name=_("Phone number"), blank=True, null=True)
    email = models.EmailField()

    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name=_('Terms and conditions document'))

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    map_img = StdImageField(upload_to='images/',
                            null=True, blank=True,
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
                            'social_card': (1200, 630, True),
                        },
                        delete_orphans=True,
                        verbose_name=_('Background image'),
                        )

    @property
    def get_med_img(self):
        # Cache key based on instance ID and method name
        cache_key = f'config_get_med_{self.pk}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        result = None
        if self.img:
            result = self.img.med.url
            # Cache the result for 1 hour (3600 seconds)
            cache.set(cache_key, result, 3600)

        return result

    @property
    def get_hdr_img(self):
        # Cache key based on instance ID and method name
        cache_key = f'config_get_hdr_{self.pk}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        result = None
        if self.img:
            result = self.img.hdr.url
            # Cache the result for 1 hour (3600 seconds)
            cache.set(cache_key, result, 3600)

        return result

    @property
    def get_social_card(self):
        # Cache key based on instance ID and method name
        cache_key = f'config_get_social_card_{self.pk}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        result = None
        if self.img:
            result = self.img.social_card.url
            # Cache the result for 1 hour (3600 seconds)
            cache.set(cache_key, result, 3600)

        return result

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

    def get_tzinfo(self):
        return pytz.timezone(self.fuseau_horaire)

    FRENCH, ENGLISH = 'fr', 'en'
    LANGUAGE_CHOICES = [
        (FRENCH, _('French')),
        (ENGLISH, _('English')),
    ]
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default=FRENCH)

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
                'social_card': self.img.social_card.url,
            }
        else:
            return {}

    logo = StdImageField(upload_to='images/',
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

    def full_url(self):
        return f"https://{connection.tenant.get_primary_domain().domain}/"

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

    additional_text_in_membership_mail = models.TextField(blank=True, null=True,
                                                          verbose_name=_("Additional text in membership mail"),
                                                          help_text=_(
                                                              "You can add additional information that will be e-mailed to you when you sign up."))

    """
    PERSONALISATION
    """

    membership_menu_name = models.CharField(max_length=200,
                                            blank=True, null=True,
                                            verbose_name=_("Subscription page name"),
                                            help_text=_("'Subscriptions' If empty."))

    event_menu_name = models.CharField(max_length=200,
                                       blank=True, null=True,
                                       verbose_name=_("Calendar page name"),
                                       help_text=_("'Calendar' If empty."))

    first_input_label_membership = models.CharField(max_length=200, blank=True, null=True,
                                                    verbose_name=_("Title of the first input on the membership form"),
                                                    help_text=_("'First name' If empty."))

    second_input_label_membership = models.CharField(max_length=200, blank=True, null=True,
                                                     verbose_name=_("Title of the second input on the membership form"),
                                                     help_text=_("'Last name or organization' If empty."))

    description_membership_page = models.TextField(blank=True, verbose_name=_("Description on the membership page"),
                                                   help_text=_("Displayed above membership products."))

    description_event_page = models.TextField(blank=True, verbose_name=_("Description on the event page"),
                                              help_text=_("Displayed above the search field."))

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
                else:
                    logger.error(f"{r.status_code} {r.content}")
                    return False
                    # raise Exception(f"{r.status_code} {r.content}")
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

    stripe_invoice = models.BooleanField(default=False, verbose_name=_("send a stripe invoice"),
                                         help_text=_("Send a stripe invoice to the customer"))

    stripe_mode_test = models.BooleanField(default=False)

    stripe_connect_account = models.CharField(max_length=21, blank=True, null=True)
    stripe_connect_account_test = models.CharField(max_length=21, blank=True, null=True)
    stripe_payouts_enabled = models.BooleanField(default=False)

    # A degager, on utilise uniquement le stripe account connect
    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)

    stripe_accept_sepa = models.BooleanField(default=False,
                                             verbose_name=_("Accept SEPA payments"),
                                             help_text=_(
                                                 "SEPA Direct Debit is a deferred payment method. Please check the current rates on the Stripe website and activate it at https://dashboard.stripe.com/settings/payment_methods. Payment validation may take between 3 and 4 business days. Currently available only for subscriptions and memberships. Contact the team if you wish to extend this option.")
                                             )

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

    def onboard_stripe(self):
        try:
            # on vérifie que le compte soit toujours lié et qu'il peut recevoir des paiements :
            if not self.stripe_payouts_enabled:
                tenant = connection.tenant
                tenant_url = tenant.get_primary_domain().domain
                msg = _('Link your stripe account to accept payment')
                return format_html(f"<a href='https://{tenant_url}/tenant/onboard_stripe_from_config'>{msg}</a>")
            return _("Stripe connected")
        except Exception as e:
            logger.error(_("Stripe error, check admin"))
            return format_html("<p>" + _("Stripe error, check admin") + "</p>")

    def clean_product_stripe_id(self):
        ProductSold.objects.all().update(id_product_stripe=None)
        PriceSold.objects.all().update(id_price_stripe=None)
        return True


    hide_refill_button = models.BooleanField(default=False, verbose_name=_("Hide refill button"))
    force_show_refill_button = models.BooleanField(default=False, verbose_name=_("Force show refill button"))

    def show_refill_button(self):
        if self.hide_refill_button:
            return False
        if self.force_show_refill_button:
            return True
        elif not self.stripe_payouts_enabled:
            return False
        return True

    """
    ### FEDERATION
    """

    # TODO: A virer, géré par une autre table
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

class Tva(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)
    tva_rate = models.DecimalField(max_digits=4, decimal_places=2, verbose_name=_("TVA rate"), unique=True)

    def __str__(self):
        return f"{self.tva_rate}%"

    def ht_from_ttc(self, prix):
        return dround(prix / (1 + (self.tva_rate / 100)))

    def tva_from_ttc(self, prix):
        return dround(prix - self.ht_from_ttc(prix))

    class Meta:
        ordering = ['tva_rate']
        verbose_name = _("TVA rate")
        verbose_name_plural = _("TVA rate")

class Product(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=500, verbose_name=_("Name"))
    tva = models.ForeignKey(Tva, on_delete=models.PROTECT, null=True, blank=True,
                            verbose_name=_("TVA rate"), help_text=_("Leave if zero VAT"))

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Short description"),
                                         help_text=_("Displayed only for membership/subscription products."))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"),
                                        help_text=_("Displayed only for membership/subscription products."))

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
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                            'social_card': (1200, 630, True),
                        },
                        delete_orphans=True,
                        verbose_name=_('Product image'),
                        )

    NONE, BILLET, PACK, RECHARGE_CASHLESS = 'N', 'B', 'P', 'R'
    RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION, BADGE = 'S', 'T', 'M', 'A', 'G'
    DON, FREERES, NEED_VALIDATION = 'D', 'F', 'V'
    QRCODE_MA = 'Q'

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
        (QRCODE_MA, _('QrCode paiement on my account')),
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

    max_per_user = models.PositiveSmallIntegerField(
        blank=True, null=True,
        verbose_name=_("Maximum per user"),
        help_text=_("Limit the quantity per user. Leave this field blank if the number is unlimited.")
    )

    def max_per_user_reached(self, user, event=None) -> bool:
        if not self.max_per_user:
            return False  # Aucune limite

        if self.categorie_article == self.ADHESION:
            # Adhésion: on compte uniquement les adhésions encore valides pour CE produit
            return user.memberships.filter(
                deadline__gte=timezone.now(),
                price__product__pk=self.pk,
            ).count() >= self.max_per_user

        # Billetterie / réservations gratuites: on compte tous les tickets de l'utilisateur (logique existante)
        elif self.categorie_article in [self.BILLET, self.FREERES] and event:
            # Compte direct des tickets liés aux réservations de l'utilisateur
            return Ticket.objects.filter(
                reservation__user_commande=user,
                reservation__event=event,
                pricesold__price__product__pk=self.pk,
                status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
            ).count() >= self.max_per_user

        return False

    validate_button_text = models.CharField(blank=True, null=True, max_length=20,
                                            verbose_name=_("Validate button text for membership"),
                                            help_text=_(
                                                "'Subscribe' If empty. Only useful for membership or subscription products."))


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


class PromotionalCode(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=200, verbose_name=_("Coupon name"),
                            help_text=_("Descriptive name for the discount coupon."), unique=True)

    discount_rate = models.DecimalField(max_digits=5, decimal_places=2,
                                        verbose_name=_("Discount rate (%)"),
                                        help_text=_("Discount percentage to apply (0-100)."))

    product = models.ForeignKey(Product, on_delete=models.CASCADE,
                                related_name="promotional_codes",
                                verbose_name=_("Product"),
                                help_text=_("Product to which this discount coupon applies."))

    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    usage_limit = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=_("Usage limit"),
        help_text=_("Maximum number of times this code can be used. Leave empty for unlimited usage.")
    )

    usage_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Usage count"),
        help_text=_("Number of times this code has been used.")
    )

    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation date"))

    def is_usable(self):
        """Check if the promotional code can still be used."""
        if not self.is_active:
            return False
        if self.usage_limit is None:
            return True
        return self.usage_count < self.usage_limit

    def remaining_uses(self):
        """Return the number of remaining uses, or None if unlimited."""
        if self.usage_limit is None:
            return None
        return max(0, self.usage_limit - self.usage_count)

    def __str__(self):
        return f"{self.name} - {self.discount_rate}% ({self.product.name})"

    class Meta:
        verbose_name = _('Promotional code')
        verbose_name_plural = _('Promotional codes')
        ordering = ('-date_created',)


@receiver(post_save, sender=Product)
def post_save_Product(sender, instance: Product, created, **kwargs):
    if created:
        # poids d'apparition
        if instance.poids == 0:
            instance.poids = len(Product.objects.all()) + 1
        instance.save()

    if instance.categorie_article == Product.FREERES:
        # On est sur un produit a réservation gratuite, on fabrique le price s'il n'existe pas ou s'il n'a pas été archivé
        if not instance.prices.filter(prix=0).exists():
            config = Configuration.get_solo()
            activate(config.language)
            Price.objects.create(product=instance, name=_("Free rate"), prix=0, publish=True)


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

    stock = models.SmallIntegerField(blank=True, null=True,
                                     verbose_name=_("Maximum capacity"),
                                     help_text=_(
                                         "Number of valid memberships possible simultaneously or maximum capacity for this price per event. Leave this field blank if the quantity is unlimited."),
                                     )

    def out_of_stock(self, event=None):
        if self.stock is None or self.stock < 1:
            return False

        if self.product.categorie_article == Product.ADHESION:
            return self.membership.filter(deadline__gt=timezone.localtime()).count() >= self.stock

        if self.product.categorie_article in [Product.FREERES, Product.BILLET]:
            return Ticket.objects.filter(
                reservation__event__pk=event.pk,
                pricesold__price__pk=self.pk,
                status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
            ).count() >= self.stock

        return False

    max_per_user = models.PositiveSmallIntegerField(
        blank=True, null=True,
        verbose_name=_("Maximum per user"),
        help_text=_("Limit the quantity per user. Leave this field blank if the number is unlimited.")
    )

    def max_per_user_reached(self, user, event=None) -> bool:
        # import ipdb; ipdb.set_trace()
        if not self.max_per_user:
            return False  # Aucune limite

        if self.product.categorie_article == self.product.ADHESION:
            # Adhésion: on compte uniquement les adhésions encore valides pour CE produit
            return user.memberships.filter(
                deadline__gte=timezone.now(),
                price__product__pk=self.pk,
            ).count() >= self.max_per_user

        # Billetterie / réservations gratuites: on compte tous les tickets de l'utilisateur (logique existante)
        elif self.product.categorie_article in [self.product.BILLET, self.product.FREERES] and event:
            # Compte direct des tickets liés aux réservations de l'utilisateur
            return Ticket.objects.filter(
                reservation__user_commande__pk=user.pk,
                reservation__event__pk=event.pk,
                pricesold__price__pk=self.pk,
                status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
            ).count() >= self.max_per_user

        return False
        pass

    # gauge_max = models.PositiveSmallIntegerField(blank=True, null=True,
    #                                                 verbose_name=_("Maximum all user"),
    #                                                 help_text=_("Limit the maximum number of memberships for all users. Leave blank for unlimited."))

    adhesion_obligatoire = models.ForeignKey(Product, on_delete=models.PROTECT,
                                             related_name="adhesion_obligatoire",
                                             verbose_name=_("Subscription required"),
                                             help_text=_(
                                                 "Rate available to suscribers only. Only works for reservation-type products. The rate will be visible if the user is logged in AND has paid their membership fees."),
                                             blank=True, null=True)

    NA, YEAR, MONTH = 'N', 'Y', 'M'
    CAL_MONTH, DAY, HOUR = 'O', 'D', 'H'
    WEEK, CIVIL, SCHOLAR = 'W', 'C', 'S'
    LIFE = 'L'
    SUB_CHOICES = [
        (NA, _('Non applicable')),
        (HOUR, _('1 hour')),
        (DAY, _('1 day')),
        (WEEK, _('1 week')),
        (MONTH, _('1 Month')),
        (CAL_MONTH, _('1st of the month')),
        (YEAR, _("365 days")),
        (CIVIL, _('Calendar year : 1st of January')),
        (SCHOLAR, _('School year: 1st of September')),
        (LIFE, _('valid for life')),
    ]

    subscription_type = models.CharField(max_length=1,
                                         choices=SUB_CHOICES,
                                         default=NA,
                                         verbose_name=_("Subscription duration"),
                                         help_text=_("Valid membership period for each payment")
                                         )

    recurring_payment = models.BooleanField(default=False,
                                            verbose_name=_("Recurring payment"),
                                            help_text=_(
                                                "Monthly payment through Stripe, limited to one product at checkout."),
                                            )
    iteration = models.PositiveSmallIntegerField(blank=True, null=True,
                                                 verbose_name=_("Max number of recurrences"),
                                                 help_text=_(
                                                     "A rate with a monthly period and iterations=2 will last two months with two payments: one on day D and another the following month."))
    commitment = models.BooleanField(default=False,
                                     verbose_name=_("Commitment to the duration of the iteration."),
                                     help_text=_(
                                         "If checked, the user will not be able to cancel the automatic debit from their account. You will always be able to interrupt the automatic debit on the Stripe interface.")
                                     )

    manual_validation = models.BooleanField(default=False,
                                            verbose_name=_("Need manual validation"),
                                            help_text=_(
                                                "If selected, an administrator will have to manually approve the membership before sending the payment link by email. An email will be sent to the administration address."))

    # Fedow reward after successful payment (membership products first)
    fedow_reward_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Top-up user wallet on payment (Fedow)"),
        help_text=_("If enabled, after a successful payment, the user wallet will receive tokens."),
    )

    reward_on_ticket_scanned = models.BooleanField(
        default=False,
        verbose_name=_("Reward user wallet on ticket scanning"),
        help_text=_("If enabled, after scanning a ticket, the user wallet will receive tokens."),
    )

    fedow_reward_asset = models.ForeignKey("fedow_public.AssetFedowPublic", on_delete=models.SET_NULL,
                                           blank=True,
                                           null=True,
                                           verbose_name=_("Fedow Asset"),
                                           help_text=_("Asset to send from the place to the user wallet."),
                                           )

    fedow_reward_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                              blank=True,
                                              null=True,
                                              verbose_name=_("Token amount to send"),
                                              help_text=_("Raw token amount."),
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
        # unique_together = ('name', 'product')
        ordering = ('order',)
        verbose_name = _('Rate')
        verbose_name_plural = _('Rates')

    def save(self, *args, **kwargs):
        if self.recurring_payment:
            self.max_per_user = 1
        super().save(*args, **kwargs)


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=200, verbose_name=_("Event name"))
    slug = models.SlugField(unique=True, db_index=True, blank=True, null=True, max_length=250)

    datetime = models.DateTimeField(verbose_name=_("Event start"))
    end_datetime = models.DateTimeField(blank=True, null=True, verbose_name=_("Event end"),
                                        help_text=_("Second date / time optional"))

    created = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                   verbose_name=_("Created by"))

    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Maximum capacity"))
    show_gauge = models.BooleanField(default=False, verbose_name=_("Show gauge"))

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
    archived = models.BooleanField(default=False, verbose_name=_("Archive"))
    private = models.BooleanField(default=False, verbose_name=_("Non-federable event"),
                                  help_text=_("Will not be displayed on shared calendars."))

    products = models.ManyToManyField(Product, blank=True, verbose_name=_("Products"))

    tag = models.ManyToManyField(Tag, blank=True, related_name="events", verbose_name=_("Tags"))

    options_radio = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_radio",
                                           verbose_name=_("Single choice menu"),
                                           help_text=_(
                                               "Des cases à cocher pendant la reservation. Un seul choix possible.")
                                           )
    options_checkbox = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_checkbox",
                                              verbose_name=_(
                                                  "Des cases à cocher pendant la reservation. Plusieurs choix possibles."), )

    # cashless = models.BooleanField(default=False, verbose_name="Proposer la recharge cashless")
    minimum_cashless_required = models.SmallIntegerField(default=0,
                                                         verbose_name=_(
                                                             "Minimum value of cashless refill"))

    reservation_button_name = models.CharField(max_length=150, blank=True, null=True,
                                               verbose_name=_("Button name for reservation"),
                                               help_text=_("If empty : I want to reserve one or more seats."))

    img = StdImageField(upload_to='images/',
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop_hdr': (960, 540, True),
                            'crop': (480, 270, True),
                            'social_card': (1200, 630, True),
                        },
                        delete_orphans=True, verbose_name=_("Main image"),
                        help_text=_(
                            "The main image of the event, displayed in the head of the event page and for social shares. If empty, the address image is displayed.")
                        )

    sticker_img = StdImageField(upload_to='images/',
                                blank=True, null=True,
                                variations={
                                    'fhd': (1920, 1920),
                                    'hdr': (1280, 1280),
                                    'med': (480, 480),
                                    'thumbnail': (150, 90),
                                    'crop_hdr': (960, 540, True),
                                    'crop': (480, 270, True),
                                },
                                delete_orphans=True, verbose_name=_("Sticker image"),
                                help_text=_(
                                    "The small image displayed in the events list. If None, img will be displayed. 4x3 ratio.")
                                )

    def get_social_card(self):
        # Cache key based on instance ID and method name
        cache_key = f'event_get_social_card_{self.pk}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        result = None
        if self.img:
            result = self.img.social_card.url
        elif self.postal_address:
            if self.postal_address.img:
                result = self.postal_address.img.social_card.url
        if not result:
            config = Configuration.get_solo()
            if config.img:
                result = config.img.social_card.url

        if result:
            # Cache the result for 1 hour (3600 seconds)
            cache.set(cache_key, result, 3600)
        return result

    def get_img(self):
        # Cache key based on instance ID and method name
        cache_key = f'event_get_img_{self.pk}'
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        # Algo pour récupérer l'image à afficher.
        result = None
        if self.img:
            result = self.img
        elif self.postal_address:
            if self.postal_address.img:
                result = self.postal_address.img
        else:
            config = Configuration.get_solo()
            if config.img:
                # logger.info("config img")
                result = config.img
            else:
                result = None

        # Cache the result for 1 hour (3600 seconds)
        cache.set(cache_key, result, 3600)
        return result

    def get_sticker_img(self):
        # Cache key based on instance ID and method name
        cache_key = f'event_get_sticker_img_{self.pk}'
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        # Algo pour récupérer l'image à afficher.
        if self.sticker_img:
            result = self.sticker_img
        elif self.postal_address and self.postal_address.sticker_img:
            result = self.postal_address.sticker_img
        else:
            config = Configuration.get_solo()
            if config.logo:
                result = config.logo
            else:
                # Au cas ou aucune image précédente, on prend les img classiques
                result = self.get_img()

        # Cache the result for 1 hour (3600 seconds)
        cache.set(cache_key, result, 3600)
        return result

    carrousel = models.ManyToManyField(Carrousel, blank=True, verbose_name=_("Carousel slides"),
                                       related_name='events',
                                       help_text=_("Images that will be displayed in the program section."))

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

    # La relation parent / enfant
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
        on_delete=models.CASCADE
    )

    refund_deadline = models.PositiveSmallIntegerField(default=7, verbose_name=_("Refund deadline (days)"),
                                                       help_text=_(
                                                           "Number of days before the event to obtain a refund."))

    easy_reservation = models.BooleanField(default=False, verbose_name=_("Quick booking"),
                                           help_text=_("One-click booking for logged-in user."))

    custom_confirmation_message = models.TextField(blank=True, null=True,
                                                   verbose_name=_(
                                                       "Personalized text in the booking confirmation e-mail."),
                                                   help_text=_(
                                                       "Not required: You can add additional information to be sent by e-mail."))

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
        return Ticket.objects.filter(reservation__event__pk=self.pk,
                                     status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]) \
            .distinct().count()

    def under_purchase(self):
        # Compte les reservation en cours de paiement ( < 15 min )
        return Ticket.objects.filter(reservation__event__pk=self.pk,
                                     status__in=[Ticket.CREATED, Ticket.NOT_ACTIV],
                                     reservation__datetime__gt=timezone.localtime() - timedelta(minutes=15)
                                     ).distinct().count()

    def complet(self):
        """
        Un booléen pour savoir si l'évènement est complet ou pas.
        Compte aussi les reservation en cours de paiement ( < 15 min )
        """

        valid_tickets_count = self.valid_tickets_count()
        under_purchase = self.under_purchase()

        if valid_tickets_count + under_purchase >= self.jauge_max:
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

    def published_prices(self) -> QuerySet:
        return Price.objects.filter(product__in=self.products.all(), publish=True)

    @property
    def pricesold_for_sections(self):
        from django.db.models import Q, F, Count, Sum, Window
        # Tickets-based rows: one row per price (using Ticket queryset with window aggregates)
        valid_statuses = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        return (
            Ticket.objects
            .filter(reservation__event=self, status__in=valid_statuses)
            .select_related('pricesold__price')
            .annotate(
                section_price_uuid=F('pricesold__price__uuid'),
                section_price_name=F('pricesold__price__name'),
                section_qty_reserved=Window(
                    expression=Count('pk'),
                    partition_by=[F('pricesold__price_id')],
                ),
                section_euros_total=Window(
                    expression=Sum(F('pricesold__price__prix')),
                    partition_by=[F('pricesold__price_id')],
                ),
            )
            .order_by('pricesold__price_id')
            .distinct('pricesold__price_id')
        )

    @property
    def children_pricesold_for_sections(self):
        from django.db.models import F, Count, Window
        # Render only when there are children; otherwise return empty queryset
        try:
            if not self.children.exists():
                return Ticket.objects.none()
        except Exception:
            return Ticket.objects.none()

        valid_statuses = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        return (
            Ticket.objects
            .filter(reservation__event__parent=self, status__in=valid_statuses)
            .select_related('pricesold__price')
            .annotate(
                section_price_uuid=F('pricesold__price__uuid'),
                section_price_name=F('pricesold__price__name'),
                section_qty_reserved=Window(
                    expression=Count('pk'),
                    partition_by=[F('pricesold__price_id')],
                ),
            )
            .order_by('pricesold__price_id')
            .distinct('pricesold__price_id')
        )

    def save(self, *args, **kwargs):
        """
        Transforme le titre de l'evenemennt en slug, pour en faire une url lisible
        """
        config = Configuration.get_solo()
        timezone = pytz.timezone(config.fuseau_horaire)
        if not self.uuid:
            self.uuid = uuid.uuid4()
        self.slug = slugify(
            f"{self.name} {self.datetime.astimezone(timezone).strftime('%y%m%d-%H%M')} {self.pk.hex[:8]}")

        # Génère l'url de l'évènement si il n'est pas externe.
        # Nécéssaire pour le prefetch multi tenant
        if not self.is_external:
            self.full_url = f"https://{connection.tenant.get_primary_domain().domain}/event/{self.slug}/"

        if not self.postal_address:
            if config.postal_address:
                self.postal_address = config.postal_address

        # Si parent, on force la catégorie ACTION
        if self.parent:
            self.categorie = Event.ACTION
            self.easy_reservation = True

        super().save(*args, **kwargs)

        # Clear the cache for get_img and get_sticker_img methods
        cache.delete(f'event_get_img_{self.pk}')
        cache.delete(f'event_get_sticker_img_{self.pk}')
        cache.delete(f'event_get_social_card_{self.pk}')

    # def get_absolute_url(self):
    #     return reverse("event-detail", args=[self.slug])

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
            try:
                images = [f"https://{domain_url}{self.img().med.url}", ]
            except Exception:
                images = []

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
            str_name = f"{self.productsold.event.datetime.strftime('%d/%m')} - {self.productsold.event.name} - {self.price.name}"
        else:
            str_name = self.price.name

        if not self.price.free_price:
            str_name += f" - {self.price.prix}€"
        return str_name

    def get_id_price_stripe(self, force=False):
        logger.info("get_id_price_stripe")
        if self.id_price_stripe and not force:
            return self.id_price_stripe

        config = Configuration.get_solo()
        currency_code = config.currency_code.lower()
        stripe_account = Configuration.get_solo().get_stripe_connect_account()

        stripe_key = RootConfiguration.get_solo().get_stripe_api()
        stripe.api_key = stripe_key

        try:
            product_stripe = self.productsold.get_id_product_stripe()
            stripe.Product.retrieve(product_stripe)
        except InvalidRequestError:
            product_stripe = self.productsold.get_id_product_stripe(force=True)

        data_stripe = {
            "unit_amount": f"{int(Decimal(self.prix) * 100)}",
            "currency": currency_code,
            "product": product_stripe,
            "stripe_account": stripe_account,
            "nickname": f"{self.price.name}",
        }

        if self.price.recurring_payment:
            data_stripe["recurring"] = {
                "interval_count": 1
            }
            if self.price.subscription_type == Price.DAY:
                data_stripe["recurring"]["interval"] = "day"
            elif self.price.subscription_type == Price.HOUR:
                data_stripe["recurring"]["interval"] = "hour"
            elif self.price.subscription_type == Price.WEEK:
                data_stripe["recurring"]["interval"] = "week"
            elif self.price.subscription_type in [Price.MONTH, Price.CAL_MONTH]:
                data_stripe["recurring"]["interval"] = "month"
            elif self.price.subscription_type == Price.YEAR:
                data_stripe["recurring"]["interval"] = "year"

        """ Les prix libres sont maintenant géré par le front
        # Si c'est récurrent et free price, le if précédent s'applique et celui non
        # Impossible de faire des prix libre et recurrent sur Stripe
        elif self.price.free_price:  
            data_stripe.pop('unit_amount')
            data_stripe['billing_scheme'] = "per_unit"
            data_stripe['custom_unit_amount'] = {
                "enabled": "true",
                "minimum": f"{int(Decimal(self.prix) * 100)}",
                # "preset": f"{int(Decimal(self.prix) * 100)}",
            }
        """

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
    custom_form = models.JSONField(null=True, blank=True, verbose_name=_('Custom Form'))

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
            for ligne in paiement.lignearticles.filter(status__in=[
                LigneArticle.PAID, LigneArticle.VALID, LigneArticle.REFUNDED
            ]):
                articles_paid.append(ligne)
        return articles_paid

    def total_paid(self):
        total_paid = 0
        for ligne_article in self.articles_paid():
            ligne_article: LigneArticle
            total_paid += int(ligne_article.amount * ligne_article.qty)  # int car on multiplie un int par un float
        return dround(total_paid)

    def can_refund(self):
        return timezone.localtime() < (self.event.datetime - timedelta(days=self.event.refund_deadline))

    def cancel_text(self):
        if self.can_refund():
            return _("You will be refunded to the credit card used to make the reservation.")
        else:
            return _("The deadline for getting a refund has passed.")

    @atomic
    def cancel_and_refund_resa(self):
        if self.tickets.filter(status=Ticket.SCANNED).exists():
            raise Exception(_("You cannot cancel a reservation that has been scanned."))

        if self.total_paid() > 0:
            config = Configuration.get_solo()
            # stripe.api_key = config.get_stripe_api()
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            for paiement in self.paiements.filter(status__in=[Paiement_stripe.VALID,
                                                              Paiement_stripe.PAID,
                                                              Paiement_stripe.NOTSYNC,
                                                              ]):
                paiement: Paiement_stripe
                checkout = paiement.get_checkout_session()
                payment_intent = checkout.payment_intent

                try:
                    refund = stripe.Refund.create(
                        payment_intent=payment_intent,
                        reason='requested_by_customer',
                        amount=checkout.amount_total,
                        stripe_account=config.get_stripe_connect_account()
                    )
                    logger.info(f"Refund stripe : {refund.status}")
                    paiement.status = Paiement_stripe.REFUNDED
                    paiement.save()

                    for lignearticle in paiement.lignearticles.filter(status=LigneArticle.VALID):
                        metadata = lignearticle.metadata if lignearticle.metadata else {}
                        metadata['original_lignearticle_uuid'] = str(lignearticle.uuid)
                        refunded_line = LigneArticle.objects.create(
                            datetime=timezone.now(),
                            pricesold=lignearticle.pricesold,
                            qty=-lignearticle.qty,  # ! Attention negative
                            amount=lignearticle.amount,
                            vat=lignearticle.vat,
                            paiement_stripe=paiement,
                            payment_method=lignearticle.payment_method,
                            asset=lignearticle.asset,
                            wallet=lignearticle.wallet,
                            status=LigneArticle.CREATED,
                            sended_to_laboutik=False,
                            metadata=metadata,
                            sale_origin=SaleOrigin.LESPASS,
                        )
                        refunded_line.status = LigneArticle.REFUNDED  # pour envoyer le trigger qui va informer LaBoutik
                        refunded_line.save()
                except InvalidRequestError as e:
                    logger.error(f"CheckoutStripe Refund InvalidRequestError {e}")
                    raise Exception(f"CheckoutStripe Refund InvalidRequestError {e}")
                except Exception as e:
                    logger.error(f"CheckoutStripe Refund Exception : {e}")
                    raise e

        self.status = Reservation.CANCELED
        for ticket in self.tickets.all():
            ticket.status = Ticket.CANCELED
            ticket.save()
        self.save()

        return self.cancel_text()

    @atomic
    def cancel_and_refund_ticket(self, ticket):
        """
        Cancel and refund a single ticket of this reservation.
        - Refunds only the matching LigneArticle amount via Stripe (partial refund)
        - Sets the LigneArticle to REFUNDED (if it was VALID) so signals trigger send_refund_to_laboutik
        - Sets the Ticket status to CANCELED
        """
        # Basic guards
        if ticket.reservation != self:
            raise Exception(_("Ticket does not belong to this reservation."))
        if ticket.status == Ticket.SCANNED:
            raise Exception(_("You cannot cancel a ticket that has been scanned."))

        refunded = False
        # If reservation had a payment try partial refund
        if self.total_paid() > 0:
            config = Configuration.get_solo()
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()

            # Find the paiement/lignearticle corresponding to this ticket
            for paiement in self.paiements.filter(status__in=[Paiement_stripe.VALID,
                                                              Paiement_stripe.PAID,
                                                              Paiement_stripe.NOTSYNC,
                                                              ]):
                try:
                    checkout = paiement.get_checkout_session()
                    payment_intent = checkout.payment_intent
                except Exception:
                    payment_intent = paiement.payment_intent_id

                ligne = paiement.lignearticles.filter(
                    pricesold=ticket.pricesold,
                    status__in=[LigneArticle.PAID, LigneArticle.VALID]
                ).first()
                if not ligne:
                    raise Exception(_("Ticket does not have a matching LigneArticle."))

                amount = ligne.amount * 1  # un seul ticket !
                try:
                    if amount > 0 and payment_intent:
                        refund = stripe.Refund.create(
                            payment_intent=payment_intent,
                            reason='requested_by_customer',
                            amount=amount,
                            stripe_account=config.get_stripe_connect_account()
                        )
                        logger.info(f"Partial refund stripe for one ticket: {refund.status}")
                    # Update accounting line status to REFUNDED if it was VALID to trigger signals
                    if ligne.status == LigneArticle.VALID:
                        metadata = ligne.metadata if ligne.metadata else {}
                        metadata['original_lignearticle_uuid'] = str(ligne.uuid)
                        refunded_line = LigneArticle.objects.create(
                            datetime=timezone.now(),
                            pricesold=ligne.pricesold,
                            qty=-1,  # ! Attention negative
                            amount=ligne.amount,
                            vat=ligne.vat,
                            paiement_stripe=paiement,
                            payment_method=ligne.payment_method,
                            asset=ligne.asset,
                            wallet=ligne.wallet,
                            status=LigneArticle.CREATED,
                            sended_to_laboutik=False,
                            metadata=metadata,
                            sale_origin=SaleOrigin.LESPASS,
                        )
                        refunded_line.status = LigneArticle.REFUNDED  # pour envoyer le trigger qui va informer LaBoutik
                        refunded_line.save()
                    refunded = True
                    break
                except InvalidRequestError as e:
                    logger.error(f"Partial Refund InvalidRequestError {e}")
                    raise Exception(f"Stripe refund error: {e}")
                except Exception as e:
                    logger.error(f"Partial Refund Exception : {e}")
                    raise e

        # Cancel the ticket regardless of refund result
        ticket.status = Ticket.CANCELED
        ticket.save()

        return self.cancel_text() if refunded else _("Ticket cancelled.")

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


### Pour App de scan Android

class ScannerAPIKey(AbstractAPIKey):
    class Meta:
        ordering = ("-created",)
        # unique_together = [['place', 'user', 'name']]


class ScanApp(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=30)
    key = models.OneToOneField(ScannerAPIKey,
                               on_delete=models.CASCADE,
                               blank=True, null=True,
                               related_name="scan_app",
                               )

    archive = models.BooleanField(default=False)
    qrcode = models.CharField(max_length=255, null=True, blank=True)
    claimed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Ticket(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    first_name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("First name"))
    last_name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Last name"))

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="tickets")

    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE, blank=True, null=True)

    CREATED, NOT_ACTIV, NOT_SCANNED, SCANNED, CANCELED = 'C', 'N', 'K', 'S', 'R'
    SCAN_CHOICES = [
        (CREATED, _('Created')),
        (NOT_ACTIV, _('Inactive')),
        (NOT_SCANNED, _('Valid and not scanned')),
        (SCANNED, _('Valid and scanned')),
        (CANCELED, _('Canceled')),
    ]

    status = models.CharField(max_length=1, choices=SCAN_CHOICES, default=CREATED,
                              verbose_name=_("Scanning status"))

    seat = models.CharField(max_length=20, default=_('L'))

    sale_origin = models.CharField(max_length=2, choices=SaleOrigin.choices, default=SaleOrigin.LESPASS,
                                   verbose_name=_("Payment source"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))

    scanned_by = models.ForeignKey(ScanApp, on_delete=models.PROTECT, blank=True, null=True, )
    metadata = models.JSONField(null=True, blank=True, verbose_name=_('Metadata'), help_text=_('Custom metadata'))

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

    NON, OPEN, PENDING, EXPIRE, FAILED, PAID, VALID, NOTSYNC, CANCELED, REFUNDED = 'N', 'O', 'W', 'E', 'F', 'P', 'V', 'S', 'C', 'R'
    STATUS_CHOICES = (
        (NON, _('Payment link not generated')),
        (OPEN, _('Sent to Stripe')),
        (PENDING, _('Waiting for payment')),
        (EXPIRE, _('Expired')),
        (FAILED, _('Failed')),
        (PAID, _('Paid')),
        (VALID, _('Paid and confirmed')),  # envoyé sur serveur cashless
        (NOTSYNC, _('Paid but issues with LaBoutik sync')),  # envoyé sur serveur cashless qui retourne une erreur
        (CANCELED, _('Cancelled')),
        (REFUNDED, _('Refunded')),
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
        (QRCODE, _('From QR code scan')),  # ancien api. A virer ?
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
        if self.source == self.TRANSFERT:  # c'est un transfert de compte stripe
            payload = json.loads(self.metadata_stripe)
            return dround(payload["data"]["object"]["amount"])

        total = 0
        for ligne in self.lignearticles.all():
            total += int(ligne.amount * ligne.qty)
        return dround(total)

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
                f"{ligne.pricesold.productsold.product.name} / {ligne.pricesold.price.name} / {dround(int(ligne.qty * ligne.amount))}€"
                for ligne in self.lignearticles.all()])

    def get_checkout_session(self):
        self.config = Configuration.get_solo()
        # stripe.api_key = config.get_stripe_api()
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        checkout_session = stripe.checkout.Session.retrieve(
            self.checkout_session_id_stripe,
            stripe_account=self.config.get_stripe_connect_account()
        )
        return checkout_session

    def update_checkout_status(self) -> str:
        """
        Fonction qui met à jour le statut juste après le webhook stripe de paiement reçu.
        """

        self.refresh_from_db()

        if self.status == Paiement_stripe.VALID:
            return self.status

        if self.traitement_en_cours:
            return self.status

        checkout_session = self.get_checkout_session()
        metadata = checkout_session.metadata

        # On vérifie le moyen de paiement. C'est peut être un SEPA
        if checkout_session.get('payment_method_types'):
            if 'sepa_debit' in checkout_session.get('payment_method_types'):
                payment_intent_id = checkout_session.get('payment_intent')
                if payment_intent_id:
                    payment_intent = stripe.PaymentIntent.retrieve(
                        payment_intent_id,
                        stripe_account=self.config.get_stripe_connect_account()
                    )
                    if 'sepa_debit' in payment_intent.get(
                            'payment_method_options') and 'sepa_debit' in payment_intent.get('payment_method_types'):
                        self.lignearticles.update(payment_method=PaymentMethod.STRIPE_SEPA_NOFED)

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
                    # La récurrence max est géré dans le webhook de renouvellement : BaseBillet.triggers.update_membership_state_after_stripe_paiement
                    # Ajout des metadata du checkout pour les futurs webhook de renouvellement
                    subscription = stripe.Subscription.modify(
                        f"{checkout_session.subscription}",
                        stripe_account=Configuration.get_solo().get_stripe_connect_account(),
                        metadata=metadata,
                    )

                    self.invoice_stripe = subscription.latest_invoice

        else:
            self.status = Paiement_stripe.CANCELED

        # le .save() lance le process BaseBillet.triggers.TRIGGER_LigneArticlePaid_ActionByCategorie
        # qui modifie le status de chaque ligne

        # si validé par le serveur cashless, alors la ligne sera VALID.
        # Si toute les lignes sont VALID, le paiement_stripe sera aussi VALID
        # grace au post_save BaseBillet.models.check_status_stripe

        # Reservation.VALID lorsque le mail est envoyé et non en erreur
        logger.info(f"Update status stripe metadata : {metadata}")
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

    qty = models.DecimalField(max_digits=12, decimal_places=6)
    amount = models.IntegerField(default=0, verbose_name=_("Value"))  # Centimes en entier (50.10€ = 5010)

    vat = models.DecimalField(max_digits=4, decimal_places=2, default=0, verbose_name=_("VAT"))
    promotional_code = models.ForeignKey(PromotionalCode, on_delete=models.PROTECT, blank=True, null=True,
                                         verbose_name=_("Promotional code"), related_name="lignearticles")


    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True,
                                        related_name="lignearticles")
    membership = models.ForeignKey("Membership", on_delete=models.PROTECT, blank=True, null=True,
                                   verbose_name=_("Linked subscription"), related_name="lignearticles")

    ### INFO DE PAIEMENT
    sale_origin = models.CharField(max_length=2, choices=SaleOrigin.choices, default=SaleOrigin.LESPASS,
                                   verbose_name=_("Payment source"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))
    asset = models.UUIDField(blank=True, null=True, verbose_name=_("Asset"))
    carte = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, blank=True, null=True)
    wallet = models.ForeignKey("AuthBillet.Wallet", blank=True, null=True, on_delete=models.PROTECT,
                               verbose_name=_("Wallet from"))

    CANCELED, REFUNDED, CREATED = 'C', 'R', 'O',
    UNPAID, PAID, FREERES = 'U', 'P', 'F'
    VALID, FAILED = 'V', 'D'

    TYPE_CHOICES = [
        (CANCELED, _('Cancelled')),
        (REFUNDED, _('Refunded')),
        (CREATED, _('Not sent to payment')),
        (UNPAID, _('Not paid')),
        (FREERES, _('Free booking')),
        (PAID, _('Paid but not confirmed')),
        (VALID, _('Confirmed')),
        (FAILED, _('Failed')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Product entry status"))

    sended_to_laboutik = models.BooleanField(default=False, verbose_name=_("Sended to LaBoutik"))

    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ('-datetime',)

    def uuid_8(self):
        return f"{self.uuid}".partition('-')[0]

    def __str__(self):
        return self.uuid_8()

    # -- TVA auto-fill on creation only --
    def _compute_default_vat(self) -> Decimal:
        """
        Determine default VAT for this line from related Product TVA if available,
        otherwise fallback to global configuration, else 0.00.
        """
        # 1) Product TVA via PriceSold -> ProductSold -> Product
        try:
            if self.pricesold and self.pricesold.productsold and self.pricesold.productsold.product:
                product = self.pricesold.productsold.product
                if getattr(product, 'tva', None):
                    return Decimal(product.tva.tva_rate)
        except Exception:
            pass

        # 2) Fallback to Configuration default VAT
        try:
            return Decimal(Configuration.get_solo().vat_taxe)
        except Exception:
            return Decimal('0.00')

    def save(self, *args, **kwargs):
        # Run only on creation; do not impact updates
        if getattr(self._state, 'adding', False):
            try:
                current_vat = Decimal(self.vat) if self.vat is not None else None
            except Exception:
                current_vat = None

            if current_vat is None or current_vat == Decimal('0.00'):
                self.vat = self._compute_default_vat()

        super().save(*args, **kwargs)

    def total(self) -> int:
        # Mise à jour de amount en cas de paiement stripe pour prix libre ( a virer après les migration ? )
        if self.amount == 0 and self.paiement_stripe and self.pricesold.price.free_price:
            if self.paiement_stripe.status in [Paiement_stripe.PAID, Paiement_stripe.VALID]:
                logger.info("Total == 0. free price ? go -> update_amount()")
                self.update_amount()
        return int(self.amount * self.qty)

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

    def user_email(self):
        if self.membership:
            if self.membership.user:
                return self.membership.user.email
        elif self.paiement_stripe:
            if self.paiement_stripe.user:
                return self.paiement_stripe.user.email
        return None

class Membership(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             related_name='memberships', blank=True, null=True)
    price = models.ForeignKey(Price, on_delete=models.PROTECT, related_name='membership',
                              verbose_name=_('Product / price'),
                              null=True, blank=True)

    asset_fedow = models.UUIDField(null=True, blank=True)
    card_number = models.CharField(max_length=16, null=True, blank=True)

    date_added = models.DateTimeField(auto_now_add=True, verbose_name=_('Date added'))

    last_contribution = models.DateTimeField(null=True, blank=True, verbose_name=_("Payment date"))
    first_contribution = models.DateTimeField(null=True, blank=True)  # utilisé dans le cas des iterations max
    max_iteration = models.IntegerField(null=True, blank=True)
    current_iteration = models.IntegerField(null=True, blank=True)

    last_action = models.DateTimeField(auto_now=True, verbose_name=_("Presence"))
    contribution_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                             verbose_name=_("Contribution"))

    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Payment method"))

    deadline = models.DateTimeField(null=True, blank=True, verbose_name=_("End of current subscription"))

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

    # Dynamic membership form data
    custom_form = models.JSONField(null=True, blank=True, verbose_name=_('Custom Form'))

    ### Pour le cas des adhésions à validation manuelle
    # TODO: A VIRER, un seul state ?
    WAITING_PAYMENT, ADMIN_CANCELED, ADMIN_VALID, ADMIN_WAITING, PAID_BY_USER, NO_ADMIN_VALID = "WP", "CA", "VA", "WA", "PA", "AU"
    STATE_CHOICES = [
        (WAITING_PAYMENT, _("Waiting for payment")),
        (ADMIN_CANCELED, _('Cancelled')),
        (ADMIN_WAITING, _('Waiting for admin validation')),
        (ADMIN_VALID, _('Confirmed by admin, waiting for payment')),
        (PAID_BY_USER, _('Paid by user')),
        (NO_ADMIN_VALID, _('Confirmed by system')),
    ]
    state = models.CharField(max_length=2, choices=STATE_CHOICES, default=WAITING_PAYMENT,
                             verbose_name=_("State"))


    WAITING_PAYMENT = 'WP'
    ADMIN, IMPORT, LABOUTIK = 'D', 'I', 'L'
    ADMIN_WAITING, ADMIN_VALID = 'AW', 'AV'
    ONCE, AUTO =  'A', 'O'
    CANCELED, ADMIN_CANCELED = 'C', 'AC'
    STATUS_CHOICES = [
        (WAITING_PAYMENT, _("En attente de paiement")),

        (ADMIN, _("Créé via l'administration")),
        (IMPORT, _("Importé depuis un fichier")),
        (LABOUTIK, _('Créé via la caisse')),

        # Pour les validations manuelles
        (ADMIN_WAITING, _('En attente de validation par un admin')),
        (ADMIN_VALID, _('Confirmé par un admin, en attente de paiement')),

        (ONCE, _('Payé en ligne')),
        (AUTO, _('Payé en ligne (récurrent)')),

        (CANCELED, _("Annulé par l'utilisateur")),
        (ADMIN_CANCELED, _('Annulé par un admin')),
    ]

    status = models.CharField(max_length=2, choices=STATUS_CHOICES, default=ONCE,
                              verbose_name=_("State"))

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

    # Options
    option_generale = models.ManyToManyField(OptionGenerale,
                                             blank=True,
                                             related_name="membership_options")

    archiver = models.BooleanField(default=False)

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
        dt = self.last_contribution
        tenant_tzinfo = Configuration.get_solo().get_tzinfo()
        if self.last_contribution and self.price:
            if self.price.subscription_type == Price.HOUR:
                deadline = dt + timedelta(hours=1)
            elif self.price.subscription_type == Price.DAY:
                deadline = dt + timedelta(days=1)
            elif self.price.subscription_type == Price.WEEK:
                deadline = dt + timedelta(weeks=1)
            elif self.price.subscription_type == Price.MONTH:
                deadline = dt + relativedelta(months=1)
            elif self.price.subscription_type == Price.CAL_MONTH:  # Valide uniquement jusqu'a la fin du mois en cours
                last_day = calendar.monthrange(dt.year, dt.month)[1]
                deadline = datetime(dt.year, dt.month, last_day, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)
            elif self.price.subscription_type == Price.YEAR:
                deadline = dt + relativedelta(months=12)
            elif self.price.subscription_type == Price.CIVIL:
                # jusqu'au 31 decembre de cette année (tz-aware, fin de journée)
                deadline = datetime(dt.year, 12, 31, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)
            elif self.price.subscription_type == Price.SCHOLAR:
                # Si la date de contribustion est avant septembre, alors on prend l'année de la contribution.
                if dt.month < 9:
                    year = dt.year
                # Si elle est après septembre, on prend l'année prochaine
                else:
                    year = dt.year + 1
                # Fin de l'année scolaire au 31 août 23:59:59.999999 (tz-aware)
                deadline = datetime(year, 8, 31, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)
            elif self.price.subscription_type == Price.LIFE:
                deadline = dt + relativedelta(months=1200)

        self.deadline = deadline
        self.save()
        return deadline

    def get_deadline(self):
        if not self.deadline:
            return self.set_deadline()
        return self.deadline

    def get_iteration_end_date(self, dt0=None):
        # Si pas de récurrence, pas d'itération max
        if not self.price or not self.price.recurring_payment:
            return None

        iteration: int | None = getattr(self.price, 'iteration', None)
        if not iteration or iteration < 1:
            return None

        # Date de premier paiement
        if not dt0:  # peut être appellé avec l'argument lors du retour webhook de stripe
            dt0 = self.first_contribution
        if not dt0:
            return None

        # Pour calculer la date de fin de la dernière itération, on réplique
        # la logique de set_deadline, en l'appliquant sur la "dernière"
        # contribution théorique.
        tenant_tzinfo = Configuration.get_solo().get_tzinfo()

        # Raccourcis
        sub = self.price.subscription_type

        # Cas simples: on additionne la période "iteration" fois à la
        # première contribution (car set_deadline fait dt + période).
        if sub == Price.HOUR:
            return dt0 + timedelta(hours=iteration)
        if sub == Price.DAY:
            return dt0 + timedelta(days=iteration)
        if sub == Price.WEEK:
            return dt0 + timedelta(weeks=iteration)
        if sub == Price.MONTH:
            return dt0 + relativedelta(months=iteration)
        if sub == Price.YEAR:
            return dt0 + relativedelta(months=12 * iteration)

        # Cas spéciaux alignés sur set_deadline
        if sub == Price.CAL_MONTH:
            # Dernière contribution se produit le (iteration-1)-ième mois après dt0
            target = dt0 + relativedelta(months=iteration - 1)
            last_day = calendar.monthrange(target.year, target.month)[1]
            return datetime(target.year, target.month, last_day, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)

        if sub == Price.CIVIL:
            # Fin au 31/12 de l'année de la dernière itération, tz-aware fin de journée
            target_year = dt0.year + (iteration - 1)
            return datetime(target_year, 12, 31, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)

        if sub == Price.SCHOLAR:
            # Année scolaire se terminant le 31/08.
            # Si contribution avant septembre -> fin 31/08 de la même année
            # Sinon -> 31/08 de l'année suivante. Puis + (iteration-1) années scolaires.
            base_year = dt0.year if dt0.month < 9 else dt0.year + 1
            target_year = base_year + (iteration - 1)
            # Retour tz-aware à la fin de la journée
            return datetime(target_year, 8, 31, 23, 59, 59, 999999, tzinfo=tenant_tzinfo)

        # Par défaut (NA ou autre): aucune itération applicable
        return None

    def is_valid(self):
        if self.status in [Membership.CANCELED, Membership.ADMIN_CANCELED]:
            return False
        elif self.get_deadline():
            if timezone.localtime() <= self.deadline:
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
    # Nouvelle route API pour les ventes (LigneArticle)
    sale = models.BooleanField(default=False, verbose_name=_("Sales"))

    def api_permissions(self):
        return {
            # Basename ( regarder dans utils.py -> user_apikey_valid pour comprendre le mecanisme )
            "event": self.event,
            # Autoriser l'accès aux adresses postales via la même permission que les events (pas de champ dédié)
            "postaladdress": self.event,
            "product": self.product,
            "price": self.product,
            "reservation": self.reservation,
            "ticket": self.ticket,
            "wallet": self.wallet,
            # Basename de la route des ventes
            "sale": self.sale,
        }

    class Meta:
        verbose_name = _('Api key')
        verbose_name_plural = _('Api keys')

    def __str__(self):
        return f"{self.name} - {self.user} - {self.created.astimezone().strftime('%d-%m-%Y %H:%M:%S')}"


class Webhook(models.Model):
    active = models.BooleanField(default=False)
    url = models.URLField(
        help_text=_(
            "Astuce Dev' : pour tester un webhook, lancez un petit serveur HTTP qui affiche le contenu de la requete : https://gist.github.com/mdonkers/63e115cc0c79b4f6b8b3a6b797e485c7"
        )
    )

    RESERVATION_V, MEMBERSHIP_V = "RV", "MV"
    EVENT_CHOICES = [
        (MEMBERSHIP_V, _('Confirmed subscription')),
        (RESERVATION_V, _('Confirmed booking')),
    ]

    event = models.CharField(max_length=2, choices=EVENT_CHOICES, default=RESERVATION_V,
                             verbose_name=_("Event"))
    last_response = models.TextField(null=True, blank=True)

### Fédérations

class FederatedPlace(models.Model):
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="Collective")
    tag_filter = models.ManyToManyField(Tag, blank=True, related_name="filtred", verbose_name=_("Tag filters"),
                                        help_text=_("Show only these tags."))

    tag_exclude = models.ManyToManyField(Tag, blank=True, related_name="excluded", verbose_name=_("Excluded tags"),
                                         help_text=_("Exclude those tags."))

    membership_visible = models.BooleanField(default=False, verbose_name=_("Federate memberships and subscriptions"),
                                             help_text=_("Display memberships and subscriptions for this site."))

    # initiative_visible = models.BooleanField(default=False, verbose_name=_("Federate initiatives"),
    #                                          help_text=_("Display the need for contributions from federated structures."))

    class Meta:
        verbose_name = _('Federated space')
        verbose_name_plural = _('Federated spaces')

    def __str__(self):
        return self.tenant.name

    def save(self, *args, **kwargs):
        cache.delete(f"federated_places")
        super().save(*args, **kwargs)


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

    ghost_url = models.URLField(blank=True, null=True, verbose_name="Ghost API URL")
    ghost_key = models.CharField(max_length=400, blank=True, null=True, verbose_name="Ghost Admin API key")
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


class ProductFormField(models.Model):
    """Definition de champs dynamiques pour les produits d'adhésion.
    Ces champs seront affichés dans le formulaire d'adhésion (offcanvas) et
    les réponses seront stockées dans Membership.custom_form (JSON).
    """

    class FieldType(models.TextChoices):
        SHORT_TEXT = 'ST', _('Short text')  # ex: pseudo
        LONG_TEXT = 'LT', _('Long text')  # ex: description 300 caractères
        SINGLE_SELECT = 'SS', _('Single select (menu)')  # sélecteur solo (menu déroulant)
        RADIO_SELECT = 'SR', _('Single select (radio)')  # sélection unique via boutons radio
        MULTI_SELECT = 'MS', _('Multiple select')  # sélecteur multiple
        BOOLEAN = 'BL', _('Switch on/off')  # question oui/non

    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='form_fields',
        verbose_name=_('Product')
    )

    # Identifiant machine lisible de la question/champ (clé utilisée dans le JSON Membership.custom_form)
    name = models.SlugField(max_length=64, verbose_name=_('Key'), help_text=_('Unique per product'), editable=False)

    # Libellé affiché à l’utilisateur
    label = models.CharField(max_length=255, verbose_name=_('Label'))

    help_text = models.CharField(max_length=500, blank=True, null=True, verbose_name=_('Help text'))
    # placeholder = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Placeholder'))

    field_type = models.CharField(max_length=2, choices=FieldType.choices, verbose_name=_('Field type'))
    required = models.BooleanField(default=False, verbose_name=_('Required'))

    # Ordre d’affichage
    order = models.PositiveSmallIntegerField(default=0, verbose_name=_('Display order'), db_index=True)

    # Pour les champs de type sélecteur: options affichées. Liste de valeurs.
    # Exemple: ["Rock", "Electro", "Jazz"]
    options = models.JSONField(blank=True, null=True, verbose_name=_('Options'))

    class Meta:
        ordering = ('order', 'uuid')
        verbose_name = _('Dynamic form field')
        verbose_name_plural = _('Dynamic form fields')
        constraints = [
            models.UniqueConstraint(fields=['product', 'name'], name='uniq_product_formfield_key')
        ]

    def __str__(self):
        return f"{self.product} • {self.label}"

    def save(self, *args, **kwargs):
        # Always derive the machine key from the label, unique per product
        base = slugify(self.label or "")[:64] if self.label else ""
        candidate = base or "field"
        suffix = 1
        # Ensure uniqueness per product by appending -2, -3 ... if needed
        while ProductFormField.objects.filter(product=self.product, name=candidate).exclude(pk=self.pk).exists():
            suffix += 1
            tail = f"-{suffix}"
            candidate = f"{base}{tail}"[:64]
        self.name = candidate
        super().save(*args, **kwargs)

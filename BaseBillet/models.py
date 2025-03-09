# import os

import logging
import uuid
from datetime import timedelta, datetime
from decimal import Decimal
from uuid import uuid4

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
        (0, _('Lundi')),
        (1, _('Mardi')),
        (2, _('Mercredi')),
        (3, _('Jeudi')),
        (4, _('Vendredi')),
        (5, _('Samedi')),
        (6, _('Dimanche')),
    ]
    day = models.IntegerField(choices=WEEK, unique=True)

    def __str__(self):
        return self.get_day_display()


class SaleOrigin(models.TextChoices):
    LESPASS = "LP", _("En ligne")
    LABOUTIK = "LB", _("Caisse")
    ADMIN = "AD", _("Administration")
    EXTERNAL = "EX", _("Extérieur")


class PaymentMethod(models.TextChoices):
    FREE = "NA", _("Aucun : offert")
    CC = "CC", _("Carte bancaire : TPE")
    CASH = "CA", _("Espèce")
    CHEQUE = "CH", _("Cheque bancaire")
    STRIPE_FED = "SF", _("En ligne : Stripe fédéré")
    STRIPE_NOFED = "SN", _("En ligne : Stripe account")
    STRIPE_RECURENT = "SR", _("Paiement récurent : Stripe account")

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
    name = models.CharField(max_length=50, verbose_name=_("Nom du tag"))
    slug = models.CharField(max_length=50, verbose_name=_("slug du tag"), db_index=True)
    color = models.CharField(max_length=7, verbose_name=_("Couleur du tag"), default="#000000")

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
    poids = models.PositiveIntegerField(default=0, verbose_name=_("Poids"), db_index=True)

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
                            verbose_name=_("Nom de l'adresse"),
                            help_text=_("Donnez un nom à cette adresse")
                            )

    street_address = models.TextField(
        verbose_name=_("Adresse de la rue"),
        help_text=_("Le numéro de la rue, le nom de la rue, etc.")
    )
    address_locality = models.CharField(
        max_length=255,
        verbose_name=_("Localité"),
        help_text=_("La ville ou la localité.")
    )
    address_region = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Région"),
        help_text=_("L'état, la province ou la région.")
    )
    postal_code = models.CharField(
        max_length=20,
        verbose_name=_("Code postal"),
        help_text=_("Le code postal ou code ZIP.")
    )
    address_country = models.CharField(
        max_length=255,
        verbose_name=_("Pays"),
        help_text=_("Le pays de l'adresse (en toutes lettres ou code ISO.")
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name=_("Latitude"),
        help_text=_("Coordonnée GPS : latitude.")
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name=_("Longitude"),
        help_text=_("Coordonnée GPS : longitude.")
    )
    comment = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Commentaire"),
        help_text=_("Un commentaire sur l'adresse.")
    )
    is_main = models.BooleanField(
        default=False,
        verbose_name=_("Adresse principale"),
    )

    def __str__(self):
        return f"{self.street_address}, {self.address_locality}, {self.address_country}"

    class Meta:
        verbose_name = _("Adresse postale")
        verbose_name_plural = _("Adresses postales")


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
    name = models.CharField(max_length=50, verbose_name=_("Nom de l'image"))
    img = StdImageField(upload_to='images/',
                        validators=[MinSizeValidator(720, 135)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                        },
                        delete_orphans=True,
                        verbose_name=_('Fichier image'),
                        )

    # publish = models.BooleanField(default=True, verbose_name=_("Publier"))
    on_event_list_page = models.BooleanField(default=True, verbose_name=_("Publier sur la page des évènements"))
    link = models.URLField(blank=True, null=True, verbose_name=_("URL de lien"))
    order = models.PositiveSmallIntegerField(verbose_name=_("Ordre d'apparition"), default=1000, )

    def __str__(self):
        return self.name


class Configuration(SingletonModel):
    def uuid(self):
        return connection.tenant.pk

    organisation = models.CharField(db_index=True, max_length=50, verbose_name=_("Nom de l'organisation"))

    slug = models.SlugField(max_length=50, default="")

    short_description = models.CharField(max_length=250, verbose_name=_("Description courte"), blank=True, null=True)
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Description longue"))

    postal_address = models.ForeignKey(PostalAddress, on_delete=SET_NULL, blank=True, null=True)

    adress = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Adresse"))
    postal_code = models.IntegerField(blank=True, null=True, verbose_name=_("Code postal"))
    city = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Ville"))
    tva_number = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Numéro de TVA"))
    siren = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Numéro de SIREN"))

    phone = models.CharField(max_length=20, verbose_name=_("Téléphone"))
    email = models.EmailField()

    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name=_('Statuts associatif'))

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
                            verbose_name=_('Carte géographique')
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
                                     verbose_name=_('Carte du restaurant')
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

    TZ_REUNION, TZ_PARIS = "Indian/Reunion", "Europe/Paris"
    TZ_CHOICES = [
        (TZ_REUNION, _('Indian/Reunion')),
        (TZ_PARIS, _('Europe/Paris')),
    ]

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

    """
    ######### OPTION GENERALES #########
    """

    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Jauge maximale"))

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="radiobutton")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="checkbox")

    need_name = models.BooleanField(default=True, verbose_name=_("Nom requis lors du scan qrcode"))

    """
    ######### CASHLESS #########
    """

    server_cashless = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name=_("Adresse du serveur Cashless")
    )

    key_cashless = models.CharField(
        max_length=41,
        blank=True,
        null=True,
        verbose_name=_("Clé d'API du serveur cashless")
    )

    laboutik_public_pem = models.CharField(max_length=512, editable=False, null=True, blank=True)

    def check_serveur_cashless(self):
        logger.info(f"On check le serveur cashless. Adresse : {self.server_cashless}")
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

            except Exception as e:
                # import ipdb; ipdb.set_trace()
                logger.error(f"    ERROR check_serveur_cashless : {e}")
        return False

    """
    ######### FEDOW #########
    """

    federated_cashless = models.BooleanField(default=False)

    server_fedow = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name=_("Adresse du serveur fedow")
    )

    key_fedow = models.CharField(
        max_length=41,
        blank=True,
        null=True,
        verbose_name=_("Clé d'API du serveur fedow")
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
            return "Stripe connected"
        except Exception as e:
            logger.error(f"Erreur stripe, check admin")
            return format_html(f"<p>Erreur stripe, check admin</p>")

    def clean_product_stripe_id(self):
        ProductSold.objects.all().update(id_product_stripe=None)
        PriceSold.objects.all().update(id_price_stripe=None)
        return True

    """
    ### FEDERATION
    """

    federated_with = models.ManyToManyField(Client, blank=True,
                                            verbose_name=_("Fédéré avec"),
                                            related_name="federated_with", help_text=_(
            "Affiche les évènements et les adhésions des structures fédérées."))

    """
    ### TVA ###
    """

    vat_taxe = models.DecimalField(max_digits=4, decimal_places=2, default=0)

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
        verbose_name = _('Paramètres')
        verbose_name_plural = _('Paramètres')

    def __str__(self):
        if self.organisation:
            return f"Paramètres de {self.organisation}"
        return f"Paramètres"


class Product(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=500, verbose_name=_("Nom"))

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description courte"))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Description longue"))

    publish = models.BooleanField(default=True, verbose_name=_("Publier"))
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Ordre"),
                                             help_text="Ordre d'apparition du plus leger au plus lourd")

    tag = models.ManyToManyField(Tag, blank=True, related_name="produit_tags")

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="produits_radio",
                                                   verbose_name=_("Option choix unique"),
                                                   help_text=_(
                                                       "Peux choisir entre une seule des options selectionnés."))

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="produits_checkbox",
                                                      verbose_name=_("Option choix multiple"),
                                                      help_text=_(
                                                          "Peux choisir plusieurs options selectionnés."))

    # TODO: doublon ?
    terms_and_conditions_document = models.URLField(blank=True, null=True)
    legal_link = models.URLField(blank=True, null=True, verbose_name=_("Lien vers mentions légales"),
                                 help_text=_("Non obligatoire"))

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
                        verbose_name=_('Image du produit'),
                        )

    NONE, BILLET, PACK, RECHARGE_CASHLESS = 'N', 'B', 'P', 'R'
    RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION, BADGE = 'S', 'T', 'M', 'A', 'G'
    DON, FREERES, NEED_VALIDATION = 'D', 'F', 'V'

    CATEGORIE_ARTICLE_CHOICES = [
        (NONE, _('Selectionnez une catégorie')),
        (BILLET, _('Billet pour reservation payante')),
        # (PACK, _("Pack d'objets")),
        # (RECHARGE_CASHLESS, _('Recharge cashless')),
        # (RECHARGE_FEDERATED, _('Recharge suspendue')),
        # (VETEMENT, _('Vetement')),
        # (MERCH, _('Merchandasing')),
        (ADHESION, _('Abonnement/Adhésion')),
        (BADGE, _('Badgeuse')),
        # (DON, _('Don')),
        (FREERES, _('Reservation gratuite')),
        # (NEED_VALIDATION, _('Nécessite une validation manuelle'))
    ]

    categorie_article = models.CharField(max_length=3, choices=CATEGORIE_ARTICLE_CHOICES, default=NONE,
                                         verbose_name=_("Type de produit"))

    nominative = models.BooleanField(default=False,
                                     verbose_name=_("Nominatif"),
                                     help_text=_("Nom/Prenom obligatoire par billet si plusieurs réservation."),
                                     )

    archive = models.BooleanField(default=False, verbose_name=_("Archiver"))

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
        verbose_name = _('Produit')
        verbose_name_plural = _('Produits')
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
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="prices", verbose_name=_("Produit"))

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    name = models.CharField(max_length=50, verbose_name=_("Précisez le nom du Tarif"))
    prix = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_("Prix"))
    free_price = models.BooleanField(default=False, verbose_name=_("Prix libre"),
                                     help_text=_("Si coché, le prix sera demandé sur la page de paiement stripe"))

    publish = models.BooleanField(default=True, verbose_name=_("Publier"))

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
                           verbose_name=_("Taux TVA"),
                           )

    stock = models.SmallIntegerField(blank=True, null=True)
    max_per_user = models.PositiveSmallIntegerField(default=10,
                                                    verbose_name=_(
                                                        "Nombre de reservation maximum par utilisateur·ices"),
                                                    help_text=_("ex : Un même email peut réserver plusieurs billets")
                                                    )

    adhesion_obligatoire = models.ForeignKey(Product, on_delete=models.PROTECT,
                                             related_name="adhesion_obligatoire",
                                             verbose_name=_("Adhésion obligatoire"),
                                             help_text=_(
                                                 "Ce tarif n'est possible que si l'utilisateur·ices est adhérant.e à "),
                                             blank=True, null=True)

    NA, YEAR, MONTH, DAY, HOUR, CIVIL, SCHOLAR = 'N', 'Y', 'M', 'D', 'H', 'C', 'S'
    SUB_CHOICES = [
        (NA, _('Non applicable')),
        (HOUR, _('1 Heure')),
        (MONTH, _('30 Jours')),
        (DAY, _('1 Jour')),
        (YEAR, _("365 Jours")),
        (CIVIL, _('Civile : 1er Janvier')),
        (SCHOLAR, _('Scolaire : 1er septembre')),
    ]

    subscription_type = models.CharField(max_length=1,
                                         choices=SUB_CHOICES,
                                         default=NA,
                                         verbose_name=_("durée d'abonnement"),
                                         )

    recurring_payment = models.BooleanField(default=False,
                                            verbose_name="Paiement récurrent",
                                            help_text="Paiement récurrent avec Stripe, "
                                                      "Ne peux être utilisé avec un autre article dans le même panier",
                                            )

    # def range_max(self):
    #     return range(self.max_per_user + 1)

    def __str__(self):
        return f"{self.product.name} {self.name}"

    class Meta:
        unique_together = ('name', 'product')
        ordering = ('prix',)
        verbose_name = _('Tarif')
        verbose_name_plural = _('Tarifs')


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=200, verbose_name=_("Nom de l'évènement"))
    slug = models.SlugField(unique=True, db_index=True, blank=True, null=True, max_length=250)

    datetime = models.DateTimeField(verbose_name=_("Date de début"))
    end_datetime = models.DateTimeField(blank=True, null=True, verbose_name=_("Date de fin"),
                                        help_text=_("Non obligatoire"))

    created = models.DateTimeField(auto_now=True)
    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Jauge maximale"))
    max_per_user = models.PositiveSmallIntegerField(default=10,
                                                    verbose_name=_(
                                                        "Nombre de reservation maximales par utilisateur·ices"),
                                                    help_text=_("ex : Un même email peut réserver plusieurs billets.")
                                                    )

    postal_address = models.ForeignKey(PostalAddress, on_delete=SET_NULL, blank=True, null=True)

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description courte"))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Description longue"))

    is_external = models.BooleanField(default=False, verbose_name=_("Billetterie/Reservation externe"), help_text=_(
        "Si l'évènement est géré par une autre billetterie ou un autre site de réservation. Ex : Un event Facebook"))
    full_url = models.URLField(blank=True, null=True)

    published = models.BooleanField(default=True, verbose_name=_("Publier"))

    products = models.ManyToManyField(Product, blank=True, verbose_name=_("Produits"))

    tag = models.ManyToManyField(Tag, blank=True, related_name="events", verbose_name=_("Tags"))

    options_radio = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_radio",
                                           verbose_name="Option choix unique")
    options_checkbox = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_checkbox",
                                              verbose_name="Options choix multiple")

    # cashless = models.BooleanField(default=False, verbose_name="Proposer la recharge cashless")
    minimum_cashless_required = models.SmallIntegerField(default=0,
                                                         verbose_name=_(
                                                             "Montant obligatoire minimum de la recharge cashless"))

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
                        delete_orphans=True, verbose_name=_("Image principale")
                        )

    carrousel = models.ManyToManyField(Carrousel, blank=True, verbose_name=_("Carrousel d'images"),
                                       related_name='events')

    CONCERT = "LIV"
    FESTIVAL = "FES"
    REUNION = "REU"
    CONFERENCE = "CON"
    RESTAURATION = "RES"
    ACTION = "ACT"
    TYPE_CHOICES = [
        (CONCERT, _('Concert')),
        (FESTIVAL, _('Festival')),
        (REUNION, _('Réunion')),
        (CONFERENCE, _('Conférence')),
        (RESTAURATION, _('Restauration')),
        (ACTION, _('Volontariat')),
    ]

    categorie = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CONCERT,
                                 verbose_name=_("Catégorie d'évènement"))

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

    easy_reservation = models.BooleanField(default=False, verbose_name=_("Réservation facile"),
                                           help_text=_("Mode réservation en un clic si utilisateur·ices connecté·e."))

    booking = models.BooleanField(default=False, verbose_name=_("Mode restauration/booking"),
                                  help_text=_(
                                      "Si activé, l'évènement sera visible en haut de la page d'accueil, l'utilisateur·ices pourra selectionner une date."))

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
        self.slug = slugify(f"{self.name} {self.datetime.strftime('%y%m%d-%H%M')}")

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
        verbose_name = _('Evenement')
        verbose_name_plural = _('Evenements')

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
                                         verbose_name=_("Type de produit"))

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

    productsold = models.ForeignKey(ProductSold, on_delete=models.PROTECT, verbose_name=_("Produit"))
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

        if not self.price.free_price :
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
        (CANCELED, _('Annulée')),
        (CREATED, _('Crée')),
        (UNPAID, _('Non payée')),
        (FREERES, _('Mail non vérifié')),
        (FREERES_USERACTIV, _('Mail user vérifié')),
        (PAID, _('Payée')),
        (PAID_ERROR, _('Payée mais mail non valide')),
        (PAID_NOMAIL, _('Payée mais mail non envoyé')),
        (VALID, _('Validée')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Status de la réservation"))

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
        (CREATED, _('Crée')),
        (NOT_ACTIV, _('Non actif')),
        (NOT_SCANNED, _('Non scanné')),
        (SCANNED, _('scanné')),
    ]

    status = models.CharField(max_length=1, choices=SCAN_CHOICES, default=CREATED,
                              verbose_name=_("Status du scan"))

    seat = models.CharField(max_length=20, default=_('L'))

    sale_origin = models.CharField(max_length=2, choices=SaleOrigin.choices, default=SaleOrigin.LESPASS,
                                   verbose_name=_("Origine du paiement"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Moyen de paiement"))

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
    event.short_description = 'Évènement'
    event.admin_order_field = 'reservation__event'

    def datetime(self):
        return self.reservation.datetime

    datetime.allow_tags = True
    datetime.short_description = 'Date de reservation'
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
            raise Exception("Signature auto verification failed")

        return f"{qrcode_data.decode('utf8')}:{signature}"

    class Meta:
        verbose_name = _('Billet')
        verbose_name_plural = _('Billets')


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

    order_date = models.DateTimeField(auto_now_add=True, verbose_name="Date")
    last_action = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True)

    NON, OPEN, PENDING, EXPIRE, PAID, VALID, NOTSYNC, CANCELED = 'N', 'O', 'W', 'E', 'P', 'V', 'S', 'C'
    STATUS_CHOICES = (
        (NON, 'Lien de paiement non créé'),
        (OPEN, 'Envoyée a Stripe'),
        (PENDING, 'En attente de paiement'),
        (EXPIRE, 'Expiré'),
        (PAID, 'Payée'),
        (VALID, 'Payée et validée'),  # envoyé sur serveur cashless
        (NOTSYNC, 'Payée mais problème de synchro cashless'),  # envoyé sur serveur cashless qui retourne une erreur
        (CANCELED, 'Annulée'),
    )
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=NON, verbose_name="Statut de la commande")

    traitement_en_cours = models.BooleanField(default=False)
    NA, WEBHOOK, GET, WEBHOOK_INVOICE = 'N', 'W', 'G', 'I'

    SOURCE_CHOICES = (
        (NA, _('Pas de traitement en cours')),
        (WEBHOOK, _('Depuis webhook stripe')),
        (GET, _('Depuis Get')),
        (WEBHOOK_INVOICE, _('Depuis webhook invoice')),
    )
    source_traitement = models.CharField(max_length=1, choices=SOURCE_CHOICES, default=NA,
                                         verbose_name="Source du traitement")

    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, blank=True, null=True,
                                    related_name="paiements")

    QRCODE, API_BILLETTERIE, FRONT_BILLETTERIE, INVOICE = 'Q', 'B', 'F', 'I'
    SOURCE_CHOICES = (
        (QRCODE, _('Depuis scan QR-Code')),
        (API_BILLETTERIE, _('Depuis API')),
        (FRONT_BILLETTERIE, _('Depuis billetterie')),
        (INVOICE, _('Depuis invoice')),

    )
    source = models.CharField(max_length=1, choices=SOURCE_CHOICES, default=API_BILLETTERIE,
                              verbose_name="Source de la commande")



    fedow_transactions = models.ManyToManyField(FedowTransaction, blank=True, related_name="paiement_stripe")

    # total = models.FloatField(default=0)
    def total(self):
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
        verbose_name = _('Paiement Stripe')
        verbose_name_plural = _('Paiements Stripe')


class LigneArticle(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)
    datetime = models.DateTimeField(auto_now_add=True)

    # L'objet price sold. Contient l'id Stripe
    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE, verbose_name=_("Article vendu"))

    qty = models.SmallIntegerField()
    amount = models.IntegerField(default=0, verbose_name=_("Montant"))  # Centimes en entier (50.10€ = 5010)
    vat = models.DecimalField(max_digits=4, decimal_places=2, default=0, verbose_name=_("TVA"))

    carte = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, blank=True, null=True)

    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True,
                                        related_name="lignearticles")
    membership = models.ForeignKey("Membership", on_delete=models.PROTECT, blank=True, null=True,
                                   verbose_name=_("Adhésion associée"), related_name="lignearticles")

    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Moyen de paiement"))

    CANCELED, CREATED, UNPAID, PAID, FREERES, VALID, = 'C', 'O', 'U', 'P', 'F', 'V'
    TYPE_CHOICES = [
        (CANCELED, _('Annulée')),
        (CREATED, _('Non envoyé en paiement')),
        (UNPAID, _('Non payée')),
        (FREERES, _('Reservation gratuite')),
        (PAID, _('Payée & non validée')),
        (VALID, _('Validée')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Status de ligne article"))

    class Meta:
        ordering = ('-datetime',)

    def uuid_8(self):
        return f"{self.uuid}".partition('-')[0]

    def __str__(self):
        return self.uuid_8()

    def total(self) -> int:
        # Mise à jour de amount en cas de paiement stripe pour prix libre ( a virer après les migration ? )
        if self.amount == 0 and self.paiement_stripe and self.pricesold.price.free_price :
            logger.info("Total 0 ? free price ? update_amount()")
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
            return _('no stripe send')

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
                              verbose_name=_('Produit/Prix'),
                              null=True, blank=True)

    asset_fedow = models.UUIDField(null=True, blank=True)
    card_number = models.CharField(max_length=16, null=True, blank=True)

    date_added = models.DateTimeField(auto_now_add=True)

    last_contribution = models.DateTimeField(null=True, blank=True, verbose_name=_("Date du paiement"))
    first_contribution = models.DateTimeField(null=True, blank=True)  # encore utilisé ? On utilise last plutot ?

    last_action = models.DateTimeField(auto_now=True, verbose_name=_("Présence"))
    contribution_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                             verbose_name=_("Contribution"))
    payment_method = models.CharField(max_length=2, choices=PaymentMethod.choices, blank=True, null=True,
                                      verbose_name=_("Moyen de paiement"))

    deadline = models.DateTimeField(null=True, blank=True, verbose_name=("Fin d'adhésion"))

    first_name = models.CharField(
        db_index=True,
        max_length=200,
        verbose_name=_("Prénom"),
        null=True, blank=True
    )

    last_name = models.CharField(
        max_length=200,
        verbose_name=_("Nom"),
        null=True, blank=True
    )

    pseudo = models.CharField(max_length=50, null=True, blank=True)

    newsletter = models.BooleanField(
        default=True, verbose_name=_("J'accepte de recevoir la newsletter de l'association"))
    postal_code = models.IntegerField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)

    CANCELED, AUTO, ONCE, ADMIN = 'C', 'A', 'O', 'D'
    STATUS_CHOICES = [
        (ADMIN, _("Enregistré via l'administration")),
        (ONCE, _('Paiement unique en ligne')),
        (AUTO, _('Renouvellement automatique')),
        (CANCELED, _('Annulée')),
    ]

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ONCE,
                              verbose_name=_("Origine"))

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
        verbose_name = _('Adhésion')
        verbose_name_plural = _('Adhésions')

    def email(self):
        self.user: "HumanUser"
        if self.user:
            return str(self.user.email).lower()
        if self.card_number:
            return f'Anonyme - {self.card_number}'
        return f'Anonyme'

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
                             help_text=_("Utilisateur·ice qui a créé cette clé.")
                             )

    key = models.OneToOneField(APIKey,
                               on_delete=models.CASCADE,
                               blank=True, null=True,
                               related_name="api_key",
                               help_text=_(
                                   "Validez l'enregistrement pour faire apparaitre la clé. Elle n'apparaitra qu'à la création.")
                               )

    ip = models.GenericIPAddressField(
        blank=True, null=True,
        verbose_name=_("Ip source"),
        help_text=_("Si non renseignée, la clé api fonctionnera depuis n'importe quelle ip.")
    )

    created = models.DateTimeField(auto_now=True)

    # read = models.BooleanField(default=True, verbose_name=_("Lecture"))

    # Droit des routes API (nom de variable doit être le basename de la route url vers le viewset)
    event = models.BooleanField(default=False, verbose_name=_("Évènements"))
    product = models.BooleanField(default=False, verbose_name=_("Produits"))

    reservation = models.BooleanField(default=False, verbose_name=_("Reservations"))
    ticket = models.BooleanField(default=False, verbose_name=_("Billets"))

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
        (MEMBERSHIP_V, _('Adhésion validée')),
        (RESERVATION_V, _('Réservation validée')),
    ]

    event = models.CharField(max_length=2, choices=EVENT_CHOICES, default=RESERVATION_V,
                             verbose_name=_("Évènement"))
    last_response = models.TextField(null=True, blank=True)


class FederatedPlace(models.Model):
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="Place")
    tag_filter = models.ManyToManyField(Tag, blank=True, related_name="filtred", verbose_name=_("Filtre de tags"),
                                        help_text=_("Si selectionnés, filtre uniquement ces tags"))
    tag_exclude = models.ManyToManyField(Tag, blank=True, related_name="excluded", verbose_name=_("Tags exclus"),
                                         help_text=_("Ces tags sont exclus"))

    class Meta:
        verbose_name = _('Espace fédéré')
        verbose_name_plural = _('Espaces fédérés')

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
#     dokos_id = models.CharField(max_length=100, blank=True, null=True, editable=False)

class FormbricksForms(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environmentId = models.CharField(max_length=30, help_text="Id d'environnement du projet Formbricks")
    trigger_name = models.CharField(max_length=30, help_text="Le nom du trigger qui va lancer le formulaire")
    # Formulaire à l'achat d'une adhésion ou d'un billet d'evènement
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="formbricksform")

    class Meta:
        verbose_name = _('Formulaire')
        verbose_name_plural = _('Formulaires')

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
        verbose_name = _('Configuration Formbrick')
        verbose_name_plural = _('Configurations Formbrick')

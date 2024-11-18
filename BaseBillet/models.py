# import os

import logging
import uuid
from uuid import uuid4
from datetime import timedelta, datetime
from decimal import Decimal
from django.utils.html import format_html

import requests
import stripe
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db import models
from django.db.models import JSONField
# Create your models here.
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.postgresql_backend.base import FakeTenant
from django_tenants.utils import tenant_context, schema_context
from rest_framework_api_key.models import APIKey
from solo.models import SingletonModel
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator, MinSizeValidator
from stripe.error import InvalidRequestError

import AuthBillet.models
from Customers.models import Client
from MetaBillet.models import EventDirectory, ProductDirectory
from QrcodeCashless.models import CarteCashless
from TiBillet import settings
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


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


class Tag(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=50, verbose_name=_("Nom du tag"), db_index=True)
    color = models.CharField(max_length=7, verbose_name=_("Couleur du tag"), default="#000000")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")


class OptionGenerale(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=250, blank=True, null=True)
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Poids"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Option')
        verbose_name_plural = _('Options')


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


class Configuration(SingletonModel):
    def uuid(self):
        return connection.tenant.pk

    organisation = models.CharField(db_index=True, max_length=50, verbose_name=_("Nom de l'organisation"))

    slug = models.SlugField(max_length=50, default="")

    short_description = models.CharField(max_length=250, verbose_name=_("Description courte"), blank=True, null=True)
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Description longue"))

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
                        verbose_name='Background image',
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
        return self.stripe_test_api_key if self.stripe_mode_test else self.stripe_api_key

    def get_stripe_connect_account(self):
        # Test ou pas test ?
        return self.stripe_connect_account_test if self.stripe_mode_test else self.stripe_connect_account


    # Vérifie que le compte stripe connect soit valide et accepte les paiements.
    def check_stripe_payouts(self):
        id_acc_connect = self.get_stripe_connect_account()
        if id_acc_connect:
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            if info_stripe and info_stripe.get('payouts_enabled'):
                self.stripe_payouts_enabled = info_stripe.get('payouts_enabled')
                self.save()
        return self.stripe_payouts_enabled

    def link_for_onboard_stripe(self):
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        # Si lien demandé depuis la meta :
        # le tenant n'existe pas encore, on utilise un retour sur la meta
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        # Si la procédure a déja été démmaré, le numero stripe connect a déja été créé.
        # Sinon, on en cherche un nouveau
        if not self.get_stripe_connect_account():
            acc_connect = stripe.Account.create(
                type="standard",
                country="FR",
            )
            id_acc_connect = acc_connect.get('id')
            self.stripe_connect_account = id_acc_connect
            self.save()

        url_onboard_stripe = stripe.AccountLink.create(
            account=self.stripe_connect_account,
            refresh_url=f"https://{tenant_url}/tenant/{self.stripe_connect_account}/onboard_stripe_return/",
            return_url=f"https://{tenant_url}/tenant/{self.stripe_connect_account}/onboard_stripe_return/",
            type="account_onboarding",
        )

        return url_onboard_stripe.url

    def onboard_stripe(self):
        # on vérifie que le compte soit toujours lié et qu'il peut recevoir des paiements :
        if self.check_stripe_payouts():
            return "Stripe connected"
        url_onboard_stripe = self.link_for_onboard_stripe()
        msg = _('Link your stripe account to accept payment')
        return format_html(f"<a href='{url_onboard_stripe}'>{msg}</a>")

    def clean_product_stripe_id(self):
        ProductSold.objects.all().update(id_product_stripe=None)
        PriceSold.objects.all().update(id_price_stripe=None)
        return True
    """
    ### TVA ###
    """

    vat_taxe = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    """
    ######### GHOST #########
    """

    ghost_url = models.URLField(blank=True, null=True)
    ghost_key = models.CharField(max_length=200, blank=True, null=True)
    ghost_last_log = models.TextField(blank=True, null=True)

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

    publish = models.BooleanField(default=True)
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Poids"),
                                             help_text="Ordre d'apparition du plus leger au plus lourd")

    tag = models.ManyToManyField(Tag, blank=True, related_name="produit_tags")

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="produits_radio")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="produits_checkbox")

    # TODO: doublon ?
    terms_and_conditions_document = models.URLField(blank=True, null=True)
    legal_link = models.URLField(blank=True, null=True, verbose_name=_("Mentions légales"))

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
        (BILLET, _('Billet payant')),
        (PACK, _("Pack d'objets")),
        (RECHARGE_CASHLESS, _('Recharge cashless')),
        (RECHARGE_FEDERATED, _('Recharge suspendue')),
        (VETEMENT, _('Vetement')),
        (MERCH, _('Merchandasing')),
        (ADHESION, _('Abonnement et/ou adhésion associative')),
        (BADGE, _('Badgeuse')),
        (DON, _('Don')),
        (FREERES, _('Reservation gratuite')),
        (NEED_VALIDATION, _('Nécessite une validation manuelle'))
    ]

    categorie_article = models.CharField(max_length=3, choices=CATEGORIE_ARTICLE_CHOICES, default=NONE,
                                         verbose_name=_("Type de produit"))

    nominative = models.BooleanField(default=True, help_text="Nom/Prenom obligatoire lors de la réservation.")

    archive = models.BooleanField(default=False)
    # TODO: A retirer, plus utilisé ?
    send_to_cashless = models.BooleanField(default=False,
                                           verbose_name="Envoyer au cashless",
                                           help_text="Produit checké par le serveur cashless.",
                                           )

    # id_product_stripe = models.CharField(max_length=30, null=True, blank=True)

    def fedow_category(self):
        self_category_map = {
            self.ADHESION: 'SUB',
            self.RECHARGE_CASHLESS: 'FED',
            self.BADGE: 'BDG',
        }
        return self_category_map.get(self.categorie_article, None)

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
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="prices")

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    name = models.CharField(max_length=50, verbose_name=_("Précisez le nom du Tarif"))
    prix = models.DecimalField(max_digits=6, decimal_places=2)
    free_price = models.BooleanField(default=False, verbose_name=_("Prix libre"),
                                     help_text=_("Si coché, le prix sera demandé sur la page de paiement stripe"))

    publish = models.BooleanField(default=True, verbose_name=_("Publié"))

    NA, DIX, VINGT, HUITCINQ, DEUXDEUX = 'NA', 'DX', 'VG', 'HC', 'DD'
    TVA_CHOICES = [
        (NA, _('Non applicable')),
        (DIX, _("10 %")),
        (VINGT, _('20 %')),
        (HUITCINQ, _('8.5 %')),
        (DEUXDEUX, _('2.2 %')),
    ]

    vat = models.CharField(max_length=2,
                           choices=TVA_CHOICES,
                           default=NA,
                           verbose_name=_("Taux TVA"),
                           )

    stock = models.SmallIntegerField(blank=True, null=True)
    max_per_user = models.PositiveSmallIntegerField(default=10,
                                                    verbose_name=_("Nombre de reservation maximum par utilisateur"),
                                                    help_text=_("ex : Un même email peut réserver plusieurs billets")
                                                    )

    adhesion_obligatoire = models.ForeignKey(Product, on_delete=models.PROTECT,
                                             related_name="adhesion_obligatoire",
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
        return f"{self.name}"

    class Meta:
        unique_together = ('name', 'product')
        ordering = ('prix',)
        verbose_name = _('Tarif')
        verbose_name_plural = _('Tarifs')


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, db_index=True, blank=True, null=True, max_length=250)
    datetime = models.DateTimeField()
    created = models.DateTimeField(auto_now=True)
    jauge_max = models.PositiveSmallIntegerField(default=50, verbose_name=_("Jauge maximale"))
    max_per_user = models.PositiveSmallIntegerField(default=10,
                                                    verbose_name=_("Nombre de reservation maximum par utilisateur"),
                                                    help_text=_("ex : Un même email peut réserver plusieurs billets.")
                                                    )

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    # event_facebook_url = models.URLField(blank=True, null=True)
    is_external = models.BooleanField(default=False, verbose_name=_("Billetterie/Reservation externe"), help_text=_(
        "Si l'évènement est géré par une autre billetterie ou un autre site de réservation. Ex : Un event Facebook"))
    url_external = models.URLField(blank=True, null=True)

    published = models.BooleanField(default=True, verbose_name=_("Publier"))

    products = models.ManyToManyField(Product, blank=True)

    tag = models.ManyToManyField(Tag, blank=True, related_name="events")

    options_radio = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_radio",
                                           verbose_name="Option choix unique")
    options_checkbox = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_checkbox",
                                              verbose_name="Options choix multiple")

    # cashless = models.BooleanField(default=False, verbose_name="Proposer la recharge cashless")
    minimum_cashless_required = models.SmallIntegerField(default=0,
                                                         verbose_name="Montant obligatoire minimum de la recharge cashless")

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
                        delete_orphans=True
                        )

    CONCERT = "LIV"
    FESTIVAL = "FES"
    REUNION = "REU"
    CONFERENCE = "CON"
    RESTAURATION = "RES"
    TYPE_CHOICES = [
        (CONCERT, _('Concert')),
        (FESTIVAL, _('Festival')),
        (REUNION, _('Réunion')),
        (CONFERENCE, _('Conférence')),
        (RESTAURATION, _('Restauration')),
    ]

    categorie = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CONCERT,
                                 verbose_name=_("Catégorie d'évènement"))

    recurrent = models.ManyToManyField(Weekday, blank=True,
                                       help_text=_(
                                           "Selectionnez le jour de la semaine pour une récurence hebdomadaire. La date de l'évènement sera la date de fin de la récurence."),
                                       verbose_name=_("Jours de la semaine"))

    booking = models.BooleanField(default=False, verbose_name=_("Mode restauration/booking"),
                                  help_text=_(
                                      "Si activé, l'évènement sera visible en haut de la page d'accueil, l'utilisateur pourra selectionner une date."))

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

    def reservations(self):
        """
        Renvoie toutes les réservations valide d'un évènement.
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

        if self.reservations() >= self.jauge_max:
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
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.datetime.strftime('%d/%m')} {self.name}"

    class Meta:
        unique_together = ('name', 'datetime')
        ordering = ('datetime',)
        verbose_name = _('Evenement')
        verbose_name_plural = _('Evenements')


@receiver(post_save, sender=Event)
def add_to_public_event_directory(sender, instance: Event, created, **kwargs):
    """
    Vérifie que le priceSold est créé pour chaque price de chaque product présent dans l'évènement
    """
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


class Artist_on_event(models.Model):
    artist = models.ForeignKey(Client, on_delete=models.PROTECT)
    datetime = models.DateTimeField()
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="artists")

    def configuration(self):
        with tenant_context(self.artist):
            return Configuration.get_solo()


@receiver(post_save, sender=Artist_on_event)
def add_to_public_event_directory(sender, instance: Artist_on_event, created, **kwargs):
    place = connection.tenant
    artist = instance.artist
    with schema_context('public'):
        event_directory, created = EventDirectory.objects.get_or_create(
            datetime=instance.datetime,
            event_uuid=instance.event.uuid,
            place=place,
            artist=artist,
        )


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
        if type(connection.tenant) != FakeTenant:
            with schema_context('public'):
                product_directory, created = ProductDirectory.objects.get_or_create(
                    place=client,
                    product_sold_stripe_id=product.id,
                )

        self.save()
        return self.id_product_stripe

    def reset_id_stripe(self):
        self.id_product_stripe = None
        self.pricesold_set.all().update(id_price_stripe=None)
        self.save()


class PriceSold(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)

    id_price_stripe = models.CharField(max_length=30, null=True, blank=True)

    productsold = models.ForeignKey(ProductSold, on_delete=models.PROTECT)
    price = models.ForeignKey(Price, on_delete=models.PROTECT)

    qty_solded = models.SmallIntegerField(default=0)
    prix = models.DecimalField(max_digits=6, decimal_places=2)
    gift = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.price.name

    def get_id_price_stripe(self,
                            force=False,
                            stripe_key=None,
                            ):

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

    def total(self):
        return Decimal(self.prix) * Decimal(self.qty_solded)
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
            total_paid += ligne_article.pricesold.price.prix * ligne_article.qty
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

    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="tickets")

    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE)

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

    def pdf_filename(self):
        config = Configuration.get_solo()
        return f"{config.organisation.upper()} " \
               f"{self.reservation.event.datetime.astimezone().strftime('%d/%m/%Y')} " \
               f"{self.first_name.upper()} " \
               f"{self.last_name.capitalize()}" \
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

    class Meta:
        verbose_name = _('Réservation')
        verbose_name_plural = _('Réservations')


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
    customer_stripe = models.CharField(max_length=20, blank=True, null=True)
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

    total = models.FloatField(default=0)

    fedow_transactions = models.ManyToManyField(FedowTransaction, blank=True, related_name="paiement_stripe")

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
                f"{ligne.pricesold.productsold.product.name} {ligne.pricesold.price.name} {ligne.qty * ligne.pricesold.price.prix}€"
                for ligne in self.lignearticles.all()])

    def update_checkout_status(self) -> str:
        if self.status == Paiement_stripe.VALID:
            return self.status

        config = Configuration.get_solo()
        stripe.api_key = config.get_stripe_api()
        checkout_session = stripe.checkout.Session.retrieve(
            self.checkout_session_id_stripe,
            stripe_account=config.get_stripe_connect_account()
        )

        # Pas payé, on le met en attente
        if checkout_session.payment_status == "unpaid":
            self.status = Paiement_stripe.PENDING

        elif checkout_session.payment_status == "paid":
            self.status = Paiement_stripe.PAID
            self.last_action = timezone.now()
            # cela va déclancher des pre_save :
            self.traitement_en_cours = True

            # Dans le cas d'un nouvel abonnement
            # On va chercher le numéro de l'abonnement stripe
            # Et sa facture
            if checkout_session.mode == 'subscription':
                if bool(checkout_session.subscription):
                    self.subscription = checkout_session.subscription
                    subscription = stripe.Subscription.retrieve(
                        checkout_session.subscription,
                        stripe_account=config.get_stripe_connect_account()
                    )
                    self.invoice_stripe = subscription.latest_invoice

        # Si le paiement est expiré
        elif datetime.now().timestamp() > checkout_session.expires_at:
            self.status = Paiement_stripe.EXPIRE

        self.save()
        return self.status

    class Meta:
        verbose_name = _('Paiement Stripe')
        verbose_name_plural = _('Paiements Stripe')


class LigneArticle(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)
    datetime = models.DateTimeField(auto_now=True)

    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE)

    qty = models.SmallIntegerField()
    vat = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    carte = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, blank=True, null=True)

    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True,
                                        related_name="lignearticles")

    CANCELED, CREATED, UNPAID, PAID, FREERES, VALID, = 'C', 'O', 'U', 'P', 'F', 'V'
    TYPE_CHOICES = [
        (CANCELED, _('Annulée')),
        (CREATED, _('Non envoyé en paiement')),
        (UNPAID, _('Non payée')),
        (FREERES, _('Reservation gratuite')),
        (PAID, _('Payée')),
        (VALID, _('Validée par serveur cashless')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=CREATED,
                              verbose_name=_("Status de ligne article"))

    class Meta:
        ordering = ('-datetime',)

    def total(self):
        return Decimal(self.pricesold.prix) * Decimal(self.qty)

    def status_stripe(self):
        if self.paiement_stripe:
            return self.paiement_stripe.status
        else:
            return _('no stripe send')

    def user_uuid_wallet(self):
        if self.paiement_stripe.user:
            user = self.paiement_stripe.user
            user.refresh_from_db()
            return user.wallet.uuid
        return None

    def paiement_stripe_uuid(self):
        if self.paiement_stripe:
            return f"{self.paiement_stripe.uuid}"


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             related_name='membership', blank=True, null=True)
    price = models.ForeignKey(Price, on_delete=models.PROTECT, related_name='user',
                              null=True, blank=True)

    asset_fedow = models.UUIDField(null=True, blank=True)
    card_number = models.CharField(max_length=16, null=True, blank=True)

    stripe_id_subscription = models.CharField(
        max_length=28,
        null=True, blank=True
    )

    last_stripe_invoice = models.CharField(
        max_length=278,
        null=True, blank=True
    )

    date_added = models.DateTimeField(auto_now_add=True)
    first_contribution = models.DateField(null=True, blank=True)
    last_contribution = models.DateField(null=True, blank=True)
    last_action = models.DateTimeField(auto_now=True, verbose_name="Présence")

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

    CANCELED, AUTO, ONCE = 'C', 'A', 'O'
    STATUS_CHOICES = [
        (ONCE, _('Paiement unique')),
        (AUTO, _('Renouvellement automatique')),
        (CANCELED, _('Annulée')),
    ]

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ONCE,
                              verbose_name=_("Status"))

    option_generale = models.ManyToManyField(OptionGenerale,
                                             blank=True,
                                             related_name="membership_options")

    stripe_paiement = models.ManyToManyField(Paiement_stripe, blank=True, related_name="membership")
    fedow_transactions = models.ManyToManyField(FedowTransaction, blank=True, related_name="membership")
    contribution_value = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # def last_contribution_value(self):
    #     last

    class Meta:
        # unique_together = ('user', 'price')
        verbose_name = _('Adhésion')
        verbose_name_plural = _('Adhésions')


    def email(self):
        if self.user:
            return self.user.email
        return None

    def member_name(self):
        if self.pseudo:
            return self.pseudo
        return f"{self.last_name} {self.first_name}"

    def deadline(self):
        if self.last_contribution and self.price:
            if self.price.subscription_type == Price.HOUR:
                return self.last_contribution + timedelta(hours=1)
            elif self.price.subscription_type == Price.DAY:
                return self.last_contribution + timedelta(days=1)
            elif self.price.subscription_type == Price.MONTH:
                return self.last_contribution + timedelta(days=31)
            elif self.price.subscription_type == Price.YEAR:
                return self.last_contribution + timedelta(days=365)
            elif self.price.subscription_type == Price.CIVIL:
                # jusqu'au 31 decembre de cette année
                return datetime.strptime(f'{self.last_contribution.year}-12-31', '%Y-%m-%d').date()
            elif self.price.subscription_type == Price.SCHOLAR:
                # Si la date de contribustion est avant septembre, alors on prend l'année de la contribution.
                if self.last_contribution.month < 9:
                    return datetime.strptime(f'{self.last_contribution.year}-08-31', '%Y-%m-%d').date()
                # Si elle est après septembre, on prend l'année prochaine
                else :
                    return datetime.strptime(f'{self.last_contribution.year+1}-08-31', '%Y-%m-%d').date()
        return None

    def is_valid(self):
        if self.deadline():
            if datetime.now().date() < self.deadline():
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
        return ", ".join([option.name for option in self.option_generale.all()])

    def __str__(self):
        if self.pseudo:
            return self.pseudo
        elif self.first_name:
            return f"{self.last_name} {self.first_name}"
        elif self.last_name:
            return f"{self.last_name}"
        elif self.user :
            return f"{self.user}"
        else :
            return "Anonymous"

class ExternalApiKey(models.Model):
    name = models.CharField(max_length=30, unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                blank=True, null=True)

    key = models.OneToOneField(APIKey,
                               on_delete=models.CASCADE,
                               blank=True, null=True,
                               related_name="api_key"
                               )

    ip = models.GenericIPAddressField(
        verbose_name="Ip source",
    )

    revoquer_apikey = models.BooleanField(
        default=False,
        verbose_name='Créer / Révoquer',
        help_text="Selectionnez et validez pour générer ou supprimer une clé API. La clé ne sera affiché qu'a la création, notez la bien !"
    )

    created = models.DateTimeField(auto_now=True)

    # En string : même nom que url basename
    # exemple dans DjangoFiles/ApiBillet/urls.py
    # router.register(r'events', api_view.EventsViewSet, basename='event')
    # Pour créer de nouvelles authorisations,
    # ajoutez un nouvel objet dans le dictionnaire permission correspondant au basename du viewset.

    event = models.BooleanField(default=False, verbose_name="Creation d'évènements")
    product = models.BooleanField(default=False, verbose_name="Creation de produits")
    place = models.BooleanField(default=False, verbose_name="Creation de nouvelles instances lieux")
    artist = models.BooleanField(default=False, verbose_name="Creation de nouvelles instances artiste")
    reservation = models.BooleanField(default=False, verbose_name="Lister les reservations")
    ticket = models.BooleanField(default=False, verbose_name="Lister et valider les billets")

    def api_permissions(self):
        return {
            "event": self.event,
            "product": self.product,
            "price": self.product,
            "place": self.place,
            "artist": self.artist,
            "reservation": self.reservation,
            "ticket": self.ticket,
        }

    class Meta:
        verbose_name = _('Api key')
        verbose_name_plural = _('Api keys')


class Webhook(models.Model):
    active = models.BooleanField(default=False)
    url = models.URLField()

    RESERVATION_V = "RV"
    EVENT_CHOICES = [
        (RESERVATION_V, _('Réservation validée')),
    ]

    event = models.CharField(max_length=2, choices=EVENT_CHOICES, default=RESERVATION_V,
                             verbose_name=_("Évènement"))
    last_response = models.TextField(null=True, blank=True)


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

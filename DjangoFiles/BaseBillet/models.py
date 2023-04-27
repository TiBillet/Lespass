import os

import uuid
from datetime import timedelta, datetime
from decimal import Decimal

import requests
from django.db import models

# Create your models here.
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from django.db.models import JSONField

from django.utils.text import slugify
from django_tenants.utils import tenant_context, schema_context
from rest_framework_api_key.models import APIKey
from solo.models import SingletonModel
from django.utils.translation import ugettext_lazy as _
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator, MinSizeValidator
from django.db import connection
from stripe.error import InvalidRequestError

import AuthBillet.models
from Customers.models import Client
from MetaBillet.models import EventDirectory, ProductDirectory
from QrcodeCashless.models import CarteCashless, FederatedCashless, Asset
from TiBillet import settings
import stripe

import logging

from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)

class Tag(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=50, verbose_name=_("Nom du tag"))

class OptionGenerale(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=30, unique=True)
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Poids"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Option Ticket')
        verbose_name_plural = _('Options Tickets')


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

    short_description = models.CharField(max_length=250, verbose_name=_("Description courte"))
    long_description = models.TextField(blank=True, null=True)

    adress = models.CharField(max_length=250, blank=True, null=True)
    postal_code = models.IntegerField(blank=True, null=True)
    city = models.CharField(max_length=250, blank=True, null=True)

    phone = models.CharField(max_length=20)
    email = models.EmailField()

    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name='Statuts associatif')

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    adhesion_obligatoire = models.BooleanField(default=False)
    button_adhesion = models.BooleanField(default=False)

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
                            verbose_name=_('Carte géorgraphique')
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

                        },
                        delete_orphans=True,
                        verbose_name='Background',
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

    # mollie_api_key = models.CharField(max_length=50,
    #                                   blank=True, null=True)



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

    federated_cashless = models.BooleanField(default=False)

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

                    if r.json().get('bill'):
                        # On récupère l'asset fédéré Stripe
                        asset, created = Asset.objects.get_or_create(
                            origin=Client.objects.get(categorie=Client.ROOT),
                            name="Stripe",
                            categorie=Asset.STRIPE_FED,
                            is_federated=True,
                        )
                        logger.info(f"    check_serveur_cashless - Stripe - Created {created}")

                        # on l'enregistre dans une table tenant public
                        fed_cash_conf, created = FederatedCashless.objects.get_or_create(
                            client=connection.tenant,
                            asset=asset,
                        )

                        # product, created = Product.objects.get_or_create(
                        #     name=f"Recharge Carte {carte.detail.origine.name} v{carte.detail.generation}",
                        #     categorie_article=Product.RECHARGE_FEDERATED,
                        #     img=carte.detail.img,
                        # )
                        #
                        # price, created = Price.objects.get_or_create(
                        #     product=product,
                        #     name=f"{montant_recharge}€",
                        #     prix=int(montant_recharge),
                        # )

                        if self.key_cashless != fed_cash_conf.key_cashless \
                                or self.server_cashless != fed_cash_conf.server_cashless:
                            fed_cash_conf.key_cashless = self.key_cashless
                            fed_cash_conf.server_cashless = self.server_cashless
                            fed_cash_conf.save()

                        return True

            except Exception as e:
                # import ipdb; ipdb.set_trace()
                logger.error(f"    ERROR check_serveur_cashless : {e}")
        return False

    ######### END CASHLESS #########

    """
    ######### STRIPE #########
    """

    stripe_connect_account = models.CharField(max_length=21, blank=True, null=True)
    stripe_connect_account_test = models.CharField(max_length=21, blank=True, null=True)
    stripe_payouts_enabled = models.BooleanField(default=False)

    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)

    stripe_mode_test = models.BooleanField(default=True)


    def get_stripe_api(self):
        if self.federated_cashless :
            return RootConfiguration.get_solo().get_stripe_api()
        tenant_stripe = self.stripe_test_api_key if self.stripe_mode_test else self.stripe_api_key

        if not tenant_stripe:
            logger.warning(f"Configuration.get_stripe_api() - No stripe api key for {connection.tenant}. On utilise celle de root.")
            return RootConfiguration.get_solo().get_stripe_api()
        return tenant_stripe

    def get_stripe_connect_account(self):
        if self.stripe_mode_test:
            return self.stripe_connect_account_test
        else:
            return self.stripe_connect_account

    # Vérifie que le compte stripe connect soit valide et accepte les paiements.
    def get_stripe_payouts(self):
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        id_acc_connect = self.get_stripe_connect_account()

        if id_acc_connect:
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            self.stripe_payouts_enabled = info_stripe.get('payout_enabled')
            self.save()

        return self.stripe_payouts_enabled




    ARNAUD, MASSIVELY, BLK_MVC = 'arnaud_mvc', 'html5up-masseively', 'blk-pro-mvc'
    CHOICE_TEMPLATE = [
        (ARNAUD, _('arnaud_mvc')),
        (MASSIVELY, _("html5up-masseively")),
        (BLK_MVC, _("blk-pro-mvc")),
    ]
    # choices=[(folder, folder) for folder in os.listdir(f"{settings.BASE_DIR}/BaseBillet/templates")],

    template_billetterie = models.CharField(
        choices=CHOICE_TEMPLATE,
        default=ARNAUD,
        max_length=250,
        blank=True,
        null=True,
        verbose_name=_("Template Billetterie")
    )

    template_meta = models.CharField(
        choices=CHOICE_TEMPLATE,
        default=MASSIVELY,
        max_length=250,
        blank=True,
        null=True,
        verbose_name=_("Template Meta")
    )

    ### MailJet ###

    activate_mailjet = models.BooleanField(default=False)
    email_confirm_template = models.IntegerField(default=3898061)

    ### Tenant fields :

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


class Product(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=500, verbose_name=_("Nom"))

    short_description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description courte"))
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Description longue"))

    terms_and_conditions_document = models.URLField(blank=True, null=True)

    publish = models.BooleanField(default=False)
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Poids"),
                                             help_text="Ordre d'apparition du plus leger au plus lourd")

    tag = models.ManyToManyField(Tag, blank=True, related_name="produit_tags")

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="produits_radio")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="produits_checkbox")

    img = StdImageField(upload_to='images/',
                        null=True, blank=True,
                        validators=[MaxSizeValidator(1920, 1920)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                        },
                        delete_orphans=True,
                        verbose_name=_('Image du produit'),
                        )

    NONE, BILLET, PACK, RECHARGE_CASHLESS = 'N', 'B', 'P', 'R'
    RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION  = 'S', 'T', 'M', 'A'
    ABONNEMENT, DON, FREERES = 'B', 'D', 'F'


    CATEGORIE_ARTICLE_CHOICES = [
        (NONE, _('Selectionnez une catégorie')),
        (BILLET, _('Billet')),
        (PACK, _("Pack d'objets")),
        (RECHARGE_CASHLESS, _('Recharge cashless')),
        (RECHARGE_FEDERATED, _('Recharge suspendue')),
        (VETEMENT, _('Vetement')),
        (MERCH, _('Merchandasing')),
        (ADHESION, _('Adhésions associative')),
        (ABONNEMENT, _('Abonnement')),
        (DON, _('Don')),
        (FREERES, _('Reservation gratuite'))
    ]

    categorie_article = models.CharField(max_length=3, choices=CATEGORIE_ARTICLE_CHOICES, default=NONE,
                                         verbose_name=_("Type d'article"))

    archive = models.BooleanField(default=False)

    send_to_cashless = models.BooleanField(default=False,
                                           verbose_name="Envoyer au cashless",
                                           help_text="Article qui doit être envoyé pour une comptabilité au cashless. Ex : Adhésions",
                                           )

    # id_product_stripe = models.CharField(max_length=30, null=True, blank=True)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Produit')
        verbose_name_plural = _('Produits')
        unique_together = ('categorie_article', 'name')


@receiver(post_save, sender=Product)
def poids_Product(sender, instance: Product, created, **kwargs):
    if created:
        # poids d'apparition
        if instance.poids == 0:
            instance.poids = len(Product.objects.all()) + 1

        instance.save()


class Price(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="prices")

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    name = models.CharField(max_length=50, verbose_name=_("Précisez le nom du Tarif"))
    prix = models.DecimalField(max_digits=6, decimal_places=2)

    NA, DIX, VINGT = 'NA', 'DX', 'VG'
    TVA_CHOICES = [
        (NA, _('Non applicable')),
        (DIX, _("10 %")),
        (VINGT, _('20 %')),
    ]

    vat = models.CharField(max_length=2,
                           choices=TVA_CHOICES,
                           default=NA,
                           verbose_name=_("Taux TVA"),
                           )

    # id_price_stripe = models.CharField(max_length=30, null=True, blank=True)

    stock = models.SmallIntegerField(blank=True, null=True)
    max_per_user = models.PositiveSmallIntegerField(default=10)

    adhesion_obligatoire = models.ForeignKey(Product, on_delete=models.PROTECT,
                                             related_name="adhesion_obligatoire",
                                             blank=True, null=True)

    NA, YEAR, MONTH, CIVIL = 'N', 'Y', 'M', 'C'
    SUB_CHOICES = [
        (NA, _('Non applicable')),
        (YEAR, _("365 Jours")),
        (MONTH, _('30 Jours')),
        (CIVIL, _('Civile')),
    ]

    subscription_type = models.CharField(max_length=1,
                                         choices=SUB_CHOICES,
                                         default=NA,
                                         verbose_name=_("durée d'abonnement"),
                                         )
    recurring_payment = models.BooleanField(default=False,
                                            verbose_name="Paiement récurrent",
                                            help_text="Paiement récurrent avec Stripe, "
                                                      "ne peux être utilisé avec un autre article dans le panier",
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

    short_description = models.CharField(max_length=250, blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)

    event_facebook_url = models.URLField(blank=True, null=True)
    published = models.BooleanField(default=False)

    products = models.ManyToManyField(Product, blank=True)

    options_radio = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_radio",
                                           verbose_name="Option choix unique")
    options_checkbox = models.ManyToManyField(OptionGenerale, blank=True, related_name="options_checkbox",
                                              verbose_name="Options choix multiple")

    cashless = models.BooleanField(default=False, verbose_name="Proposer la recharge cashless")
    minimum_cashless_required = models.SmallIntegerField(default=0, verbose_name="Montant obligatoire minimum de la recharge cashless")

    img = StdImageField(upload_to='images/',
                        validators=[MaxSizeValidator(1920, 1920)],
                        blank=True, null=True,
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                            'crop': (510, 310, True),
                        },
                        delete_orphans=True
                        )

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
            }
        else:
            return {}

    # reservations = models.PositiveSmallIntegerField(default=0)

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

    def save(self, *args, **kwargs):
        """
        Transforme le titre de l'evenemennt en slug, pour en faire une url lisible
        """

        # self.slug = slugify(f"{self.name} {self.datetime} {str(self.uuid).partition('-')[0]}")[:50]
        self.slug = slugify(f"{self.name} {self.datetime.strftime('%D %R')}")

        # On vérifie que le serveur cashless soit configuré et atteignable
        # if self.recharge_cashless:
        #     self.recharge_cashless = self.check_serveur_cashless()

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
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)

    id_product_stripe = models.CharField(max_length=30, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True, blank=True)

    product = models.ForeignKey(Product, on_delete=models.PROTECT)


    def __str__(self):
        return self.product.name

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

        if stripe_key == None:
            stripe_key = Configuration.get_solo().get_stripe_api()
        stripe.api_key = stripe_key
        # config = Configuration.get_solo()

        client = connection.tenant
        domain_url = client.domains.all()[0].domain
        # noinspection PyUnresolvedReferences
        images = []
        if self.img():
            images = [f"https://{domain_url}{self.img().med.url}", ]

        product = stripe.Product.create(
            name=f"{self.nickname()}",
            # stripe_account=config.get_stripe_connect_account(),
            images=images
        )
        self.id_product_stripe = product.id

        with schema_context('public'):
            product_directory, created = ProductDirectory.objects.get_or_create(
                place=client,
                product_sold_stripe_id=product.id,
            )

        self.save()

        return self.id_product_stripe

    def reset_id_stripe(self):
        self.id_product_stripe = None
        self.save()


class PriceSold(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)

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

        if stripe_key == None:
            stripe_key = Configuration.get_solo().get_stripe_api()
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
            # 'stripe_account': config.get_stripe_connect_account(),
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
            for ligne in paiement.lignearticle_set.filter(
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


class Paiement_stripe(models.Model):
    """
    La commande
    """
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)
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
    STATUT_CHOICES = (
        (NON, 'Lien de paiement non créé'),
        (OPEN, 'Envoyée a Stripe'),
        (PENDING, 'En attente de paiement'),
        (EXPIRE, 'Expiré'),
        (PAID, 'Payée'),
        (VALID, 'Payée et validée'),  # envoyé sur serveur cashless
        (NOTSYNC, 'Payée mais problème de synchro cashless'),  # envoyé sur serveur cashless qui retourne une erreur
        (CANCELED, 'Annulée'),
    )
    status = models.CharField(max_length=1, choices=STATUT_CHOICES, default=NON, verbose_name="Statut de la commande")

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

    QRCODE, API_BILLETTERIE, INVOICE = 'Q', 'B', 'I'
    SOURCE_CHOICES = (
        (QRCODE, _('Depuis scan QR-Code')),
        (API_BILLETTERIE, _('Depuis billetterie')),
        (INVOICE, _('Depuis invoice')),

    )
    source = models.CharField(max_length=1, choices=SOURCE_CHOICES, default=API_BILLETTERIE,
                              verbose_name="Source de la commande")

    total = models.FloatField(default=0)

    def uuid_8(self):
        return f"{self.uuid}".partition('-')[0]

    def __str__(self):
        return self.uuid_8()

    def articles(self):
        return " - ".join(
            [
                f"{ligne.pricesold.productsold.product.name} {ligne.pricesold.price.name} {ligne.qty * ligne.pricesold.price.prix}€"
                for ligne in self.lignearticle_set.all()])

    class Meta:
        verbose_name = _('Paiement Stripe')
        verbose_name_plural = _('Paiements Stripe')


class LigneArticle(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)
    datetime = models.DateTimeField(auto_now=True)

    pricesold = models.ForeignKey(PriceSold, on_delete=models.CASCADE)

    qty = models.SmallIntegerField()

    carte = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, blank=True, null=True)

    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True)

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


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='membership')
    price = models.ForeignKey(Price, on_delete=models.PROTECT, related_name='user',
                              null=True, blank=True)

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

    contribution_value = models.FloatField(null=True, blank=True)
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

    class Meta:
        unique_together = ('user', 'price')
        verbose_name = _('Adhésion')
        verbose_name_plural = _('Adhésions')

    def email(self):
        return self.user.email

    def deadline(self):
        if self.last_contribution and self.price:
            if self.price.subscription_type == Price.YEAR:
                return self.last_contribution + timedelta(days=365)
            if self.price.subscription_type == Price.MONTH:
                return self.last_contribution + timedelta(days=31)
            if self.price.subscription_type == Price.CIVIL:
                return datetime.strptime(f'{self.last_contribution.year}-12-31', '%Y-%m-%d').date()

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

    def __str__(self):
        if self.pseudo:
            return self.pseudo
        elif self.first_name:
            return f"{self.last_name} {self.first_name}"
        elif self.last_name:
            return f"{self.last_name}"
        else:
            return f"{self.user}"


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

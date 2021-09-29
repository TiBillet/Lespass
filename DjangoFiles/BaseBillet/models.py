import uuid

from django.contrib.auth import get_user_model
from django.db import models

# Create your models here.
from django.db.models.signals import post_save
from django.dispatch import receiver
from solo.models import SingletonModel
from django.utils.translation import ugettext_lazy as _
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator
from django.db import connection

from PaiementStripe.models import Paiement_stripe
from TiBillet import settings
import stripe


class OptionGenerale(models.Model):
    name = models.CharField(max_length=30)
    poids = models.PositiveSmallIntegerField(default=0, verbose_name=_("Poids"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poids',)
        verbose_name = _('Options Generales')
        verbose_name_plural = _('Options Generales')


@receiver(post_save, sender=OptionGenerale)
def poids_option_generale(sender, instance: OptionGenerale, created, **kwargs):
    if created:
        # poids d'apparition
        if instance.poids == 0:
            instance.poids = len(OptionGenerale.objects.all()) + 1

        instance.save()



class Configuration(SingletonModel):
    organisation = models.CharField(max_length=50)
    short_description = models.CharField(max_length=250)

    adresse = models.CharField(max_length=250)
    phone = models.CharField(max_length=20)
    email = models.EmailField()

    site_web = models.URLField(blank=True, null=True)

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    adhesion_obligatoire = models.BooleanField(default=False)
    cadeau_adhesion = models.FloatField(default=0, help_text="Recharge cadeau a l'adhésion")

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
                                     verbose_name='Carte du restaurant'
                                     )

    img = StdImageField(upload_to='images/',
                        null=True, blank=True,
                        # validators=[MaxSizeValidator(1920, 1920)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (720, 720),
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                        },
                        delete_orphans=True,
                        verbose_name='Background'
                        )

    mollie_api_key = models.CharField(max_length=50,
                                      blank=True, null=True)

    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_mode_test = models.BooleanField(default=True)

    activer_billetterie = models.BooleanField(default=True)

    jauge_max = models.PositiveSmallIntegerField(default=50)

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="radiobutton")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="checkbox")

    server_cashless = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name="Adresse du serveur Cashless"
    )

    key_cashless = models.CharField(
        max_length=41,
        blank=True,
        null=True,
        verbose_name="Clé d'API du serveur cashless"
    )


class Billet(models.Model):
    name = models.CharField(max_length=50,
                            blank=True, null=True)
    prix = models.FloatField()

    reservation_par_user_max = models.PositiveSmallIntegerField(default=6)

    def range_max(self):
        return range(self.reservation_par_user_max + 1)

    def __str__(self):
        return f"{self.name}"


class VAT(models.Model):
    """
    Les différents taux de TVA sont associés à des produits.
    """
    percent = models.FloatField(verbose_name="Taux de TVA (%)")

    class Meta:
        verbose_name = _('TVA')
        verbose_name_plural = _('TVA')

    def __str__(self):
        return f"{self.percent}%"


class Article(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=50,
                            blank=True, null=True)
    prix = models.FloatField()
    stock = models.SmallIntegerField(blank=True, null=True)

    reservation_par_user_max = models.PositiveSmallIntegerField(default=10)
    vat = models.ForeignKey(VAT, on_delete=models.PROTECT, verbose_name="TVA", null=True, blank=True)

    publish = models.BooleanField(default=False)

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
                        verbose_name='Image'
                        )

    BILLET, PACK, RECHARGE_CASHLESS, VETEMENT, MERCH, ADHESION = 'B', 'P', 'R', 'T', 'M', 'A'
    TYPE_CHOICES = [
        (BILLET, _('Billet')),
        (PACK, _("Pack d'objets")),
        (RECHARGE_CASHLESS, _('Recharge cashless')),
        (VETEMENT, _('Vetement')),
        (MERCH, _('Merchandasing')),
        (ADHESION, ('Adhésion')),
    ]

    categorie_article = models.CharField(max_length=3, choices=TYPE_CHOICES, default=BILLET,
                                         verbose_name=_("Type d'article"))

    id_product_stripe = models.CharField(max_length=30, null=True, blank=True)
    id_price_stripe = models.CharField(max_length=30, null=True, blank=True)

    def range_max(self):
        return range(self.reservation_par_user_max + 1)

    def get_id_product_stripe(self):
        configuration = Configuration.get_solo()
        if configuration.stripe_api_key and not self.id_product_stripe:
            if configuration.stripe_mode_test:
                stripe.api_key = configuration.stripe_test_api_key
            else:
                stripe.api_key = configuration.stripe_api_key

            if self.img :
                # noinspection PyUnresolvedReferences
                domain_url = connection.tenant.domains.all()[0].domain
                images = [f"https://{domain_url}{self.img.med.url}",]
            else:
                images = []

            product = stripe.Product.create(
                name=f"{self.name}",
                images=images
            )
            self.id_product_stripe = product.id
            self.save()
            return self.id_product_stripe

        elif self.id_product_stripe:
            return self.id_product_stripe
        else:
            return False

    def get_id_price_stripe(self):
        configuration = Configuration.get_solo()
        if configuration.stripe_api_key and not self.id_price_stripe:
            if configuration.stripe_mode_test:
                stripe.api_key = configuration.stripe_test_api_key
            else:
                stripe.api_key = configuration.stripe_api_key

            price = stripe.Price.create(
                unit_amount=int("{0:.2f}".format(self.prix).replace('.', '')),
                currency="eur",
                product=self.get_id_product_stripe(),
            )

            self.id_price_stripe = price.id
            self.save()
            return self.id_price_stripe

        elif self.id_price_stripe:
            return self.id_price_stripe
        else:
            return False

    def reset_id_stripe(self):
        self.id_price_stripe = None
        self.id_product_stripe = None
        self.save()

    def __str__(self):
        return f"{self.name}"


class Event(models.Model):
    name = models.CharField(max_length=200)
    short_description = models.CharField(max_length=250)
    long_description = models.TextField(blank=True, null=True)
    datetime = models.DateTimeField()
    billets = models.ManyToManyField(Billet)
    articles = models.ManyToManyField(Article)

    img = StdImageField(upload_to='images/',
                        null=True, blank=True,
                        validators=[MaxSizeValidator(1920, 1920)],
                        variations={
                            'fhd': (1920, 1920),
                            'hdr': (1280, 1280),
                            'crop': (510, 310, True),
                        },
                        delete_orphans=True
                        )

    reservations = models.PositiveSmallIntegerField(default=0)

    def complet(self):
        # TODO: Benchmarker et tester si c'est pas mieux dans template
        if self.reservations >= Configuration.get_solo().jauge_max:
            return True
        else:
            return False

    def __str__(self):
        return f"{self.datetime.strftime('%d/%m')} {self.name}"

    class Meta:
        ordering = ('datetime',)
        verbose_name = _('Evenement')
        verbose_name_plural = _('Evenements')


class Reservation(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)

    user_commande = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    event = models.ForeignKey(Event,
                              on_delete=models.PROTECT,
                              related_name="reservation")

    ANNULEE, MAIL_NON_VALIDEE, NON_PAYEE, VALIDEE, PAYEE = 'NAN', 'MNV', 'NPA', 'VAL', 'PAY'
    TYPE_CHOICES = [
        (ANNULEE, _('Annulée')),
        (MAIL_NON_VALIDEE, _('Email non validé')),
        (NON_PAYEE, _('Non payée')),
        (VALIDEE, _('Validée')),
        (PAYEE, _('Payée')),
    ]

    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=NON_PAYEE,
                              verbose_name=_("Status de la réservation"))

    options = models.ManyToManyField(OptionGenerale)

    def __str__(self):
        return self.user_commande.email

    def user_mail(self):
        return self.user_commande.email

    def total_billet(self):
        total = 0
        for ligne in self.lignearticle_set.all():
            if ligne.billet:
                total += ligne.qty
        return total

    def total_prix(self):
        total = 0
        for ligne in self.lignearticle_set.all():
            if ligne.article:
                total += ligne.qty * ligne.article.prix
            if ligne.billet:
                total += ligne.qty * ligne.billet.prix

        return total

    def _options_(self):
        return " - ".join([f"{option.name}" for option in self.options.all()])


@receiver(post_save, sender=Reservation)
def verif_mail_valide(sender, instance: Reservation, created, **kwargs):
    if created:
        if not instance.user_commande.is_active:
            instance.status = instance.MAIL_NON_VALIDEE
            instance.save()


class LigneArticle(models.Model):
    uuid = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, blank=True, null=True)
    billet = models.ForeignKey(Billet, on_delete=models.CASCADE, blank=True, null=True)
    qty = models.SmallIntegerField()
    paiement_stripe = models.ForeignKey(Paiement_stripe, on_delete=models.PROTECT, blank=True, null=True)
    datetime = models.DateTimeField(auto_now=True)

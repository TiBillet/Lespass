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

    id_acc_connect = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe connect ID"))

    laboutik_wanted = models.BooleanField(default=False)
    payment_wanted = models.BooleanField(default=False)
    email_confirmed = models.BooleanField(default=False)

    dns_choice = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Domain name choice"))

    ### Ex method :
    slug = models.SlugField(max_length=50, default="")

    short_description = models.CharField(max_length=250, verbose_name=_("Short description"), blank=True, null=True)
    long_description = models.TextField(blank=True, null=True, verbose_name=_("Long description"))

    adress = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Address"))
    postal_code = models.IntegerField(blank=True, null=True, verbose_name=_("Zip code"))
    city = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("City"))

    phone = models.CharField(max_length=20, verbose_name=_("Phone number"))

    site_web = models.URLField(blank=True, null=True)
    legal_documents = models.URLField(blank=True, null=True, verbose_name='By-laws')

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

    # adhesion_obligatoire = models.BooleanField(default=False, verbose_name="Proposer l'adhésion lors d'un scan de QRCode de carte NFC")
    # button_adhesion = models.BooleanField(default=False)

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
    onboard_stripe_finished = models.BooleanField(default=False)
    created = models.BooleanField(default=False)
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name=_('Tenant'), related_name='waiting_config', blank=True, null=True)

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
        self.created = True
        self.tenant = tenant
        self.save()

    def __str__(self):
        return f"{self.organisation} - {self.email} -> {self.slug}"

    class Meta:
        verbose_name = _('Settings')
        verbose_name_plural = _('Settings')

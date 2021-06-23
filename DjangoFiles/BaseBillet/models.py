from django.db import models

# Create your models here.
from django.db.models.signals import post_save
from django.dispatch import receiver
from solo.models import SingletonModel
from django.utils.translation import ugettext_lazy as _
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator


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
def poids_option_generaler(sender, instance: OptionGenerale, created, **kwargs):
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

    twitter = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)

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

    reservation_par_user_max = models.PositiveSmallIntegerField(default=6)

    jauge_max = models.PositiveSmallIntegerField(default=50)

    option_generale_radio = models.ManyToManyField(OptionGenerale,
                                                   blank=True,
                                                   related_name="radiobutton")

    option_generale_checkbox = models.ManyToManyField(OptionGenerale,
                                                      blank=True,
                                                      related_name="checkbox")


class Event(models.Model):
    name = models.CharField(max_length=200)
    short_description = models.CharField(max_length=250)
    long_description = models.TextField(blank=True, null=True)
    datetime = models.DateTimeField()

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

    class Meta:
        ordering = ('datetime',)
        verbose_name = _('Evenement')
        verbose_name_plural = _('Evenements')


class reservation(models.Model):
    event = models.ForeignKey(Event,
                              on_delete=models.CASCADE,
                              related_name="reservation")

    ANNULEE, NON_VALIDEE, VALIDEE, PAYEE = 'NAN', 'NOV', 'VAL', 'PAY'
    TYPE_CHOICES = [
        (ANNULEE, _('Annulée')),
        (NON_VALIDEE, _('Email non validé')),
        (VALIDEE, _('Validée')),
        (PAYEE, _('Payée')),
    ]
    status = models.CharField(max_length=3, choices=TYPE_CHOICES, default=NON_VALIDEE,
                              verbose_name=_("Status de la réservation"))

    qty = models.IntegerField()

from django.db import models
from django.utils.translation import gettext_lazy as _

# Create your models here.
from solo.models import SingletonModel


class RootConfiguration(SingletonModel):


    TZ_REUNION, TZ_PARIS = "Indian/Reunion", "Europe/Paris"
    TZ_CHOICES = [
        (TZ_REUNION, _('Indian/Reunion')),
        (TZ_PARIS, _('Europe/Paris')),
    ]

    fuseau_horaire = models.CharField(default=TZ_REUNION,
                                      max_length=50,
                                      choices=TZ_CHOICES,
                                      )

    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)

    stripe_mode_test = models.BooleanField(default=True)


    """
    FEDOW
    """

    fedow_domain = models.URLField(blank=True, null=True, editable=False)
    fedow_ip = models.GenericIPAddressField(blank=True, null=True, editable=False)


    def get_stripe_api(self):
        if self.stripe_mode_test:
            return self.stripe_test_api_key
        else:
            return self.stripe_api_key
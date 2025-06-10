from django.utils import timezone

from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from django.utils.translation import gettext_lazy as _
import uuid

class Client(TenantMixin):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=100, unique=True, db_index=True)
    created_on = models.DateField(auto_now_add=True)

    paid_until =  models.DateField(default=timezone.now)
    on_trial = models.BooleanField(default=False)

    ARTISTE, SALLE_SPECTACLE, FESTIVAL, TOURNEUR, PRODUCTEUR, META, WAITING_CONFIG, ROOT = 'A', 'S', 'F', 'T', 'P', 'M', 'W', 'R'
    CATEGORIE_CHOICES = [
        (ARTISTE, _('Artist')),
        (SALLE_SPECTACLE, _("Scene")),
        (FESTIVAL, _('Festival')),
        (TOURNEUR, _('Tour operator')),
        (PRODUCTEUR, _('Producer')),
        (META, _('Event aggregator')),
        (WAITING_CONFIG, _('Waiting configuration')),
        (ROOT, _('Root public tenant')),
    ]

    categorie = models.CharField(max_length=3, choices=CATEGORIE_CHOICES, default=SALLE_SPECTACLE,
                                         verbose_name=_("Category"))

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return f"{self.name}"

class Domain(DomainMixin):
    pass

import random
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PairingDevice(models.Model):
    """
    Appareil en attente d'appairage via code PIN.
    Device waiting to be paired via PIN code.

    Le PIN est généré côté admin (schéma tenant),
    et réclamé via la route publique /api/discovery/claim/.
    The PIN is generated from the tenant admin,
    and claimed via the public route /api/discovery/claim/.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=100,
        verbose_name=_("Device name"),
        help_text=_("Name of the device to pair, e.g. 'Cash register 1'"),
    )

    tenant = models.ForeignKey(
        'Customers.Client',
        on_delete=models.CASCADE,
        related_name='pairing_devices',
        verbose_name=_("Tenant"),
    )

    pin_code = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("PIN code"),
        help_text=_("6-digit pairing code, cleared after claim"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created at"),
    )

    claimed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Claimed at"),
        help_text=_("Set when a device claims this PIN"),
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Pairing device")
        verbose_name_plural = _("Pairing devices")

    def __str__(self):
        if self.is_claimed:
            return f"{self.name} ({_('claimed')})"
        return f"{self.name} - PIN {self.pin_code} ({_('available')})"

    @property
    def is_claimed(self):
        return self.claimed_at is not None

    def claim(self):
        """Marquer le PIN comme consommé et le vider (plus utile).
        Mark the PIN as consumed and clear it (no longer needed)."""
        self.claimed_at = timezone.now()
        self.pin_code = None
        self.save(update_fields=['claimed_at', 'pin_code'])

    @staticmethod
    def generate_unique_pin():
        """
        Génère un PIN unique à 6 chiffres (100000-999999).
        Generate a unique 6-digit PIN (100000-999999).
        """
        max_attempts = 50
        for _attempt in range(max_attempts):
            random_pin = random.randint(100000, 999999)
            pin_already_exists = PairingDevice.objects.filter(pin_code=random_pin).exists()
            if not pin_already_exists:
                return random_pin
        raise RuntimeError("Unable to generate a unique PIN after multiple attempts")

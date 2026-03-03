from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from discovery.models import PairingDevice


class PinClaimSerializer(serializers.Serializer):
    """
    Valide un code PIN à 6 chiffres pour l'appairage d'un terminal.
    Validates a 6-digit PIN code for device pairing.
    """

    pin_code = serializers.CharField(
        min_length=6,
        max_length=6,
        help_text=_("6-digit pairing PIN"),
    )

    def validate_pin_code(self, value):
        # Vérifier que c'est bien un nombre / Check it's digits only
        pin_contains_only_digits = value.isdigit()
        if not pin_contains_only_digits:
            raise serializers.ValidationError(_("PIN must contain only digits."))

        pin_code_as_integer = int(value)

        # Chercher le device associé à ce PIN (non consommé)
        # Look up the device for this PIN (not yet claimed)
        # Note : un PIN consommé est vidé (pin_code=None),
        # donc il ne sera jamais trouvé ici.
        # A claimed PIN is cleared (pin_code=None),
        # so it will never be found here.
        try:
            pairing_device = PairingDevice.objects.select_related('tenant').get(
                pin_code=pin_code_as_integer,
                claimed_at__isnull=True,
            )
        except PairingDevice.DoesNotExist:
            raise serializers.ValidationError(_("Invalid or already used PIN code."))

        # Stocker le device pour que la vue puisse y accéder
        # Store the device so the view can access it
        self.device = pairing_device
        return pin_code_as_integer

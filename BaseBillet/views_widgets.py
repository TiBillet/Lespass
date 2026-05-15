"""
Vues utilitaires pour les widgets réutilisables (carte adresse, etc.).
/ Utility views for reusable widgets (address map, etc.).

LOCALISATION: BaseBillet/views_widgets.py

ViewSet DRF explicite (`viewsets.ViewSet`, PAS `ModelViewSet`) — cf. djc.
Endpoint POST /widgets/geocode-reverse/ : géocodage inverse Nominatim
avec cache Redis. Consommé par `static/widgets/widget_carte_adresse.js`.
"""

import logging

from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from BaseBillet.services_geocode import reverse_geocode

logger = logging.getLogger(__name__)


# Throttle dédié au reverse geocode : on respecte la politique Nominatim
# (max 1 requête/seconde par IP). On déclare `rate` directement sur la
# classe pour ne pas dépendre de DEFAULT_THROTTLE_RATES dans settings.
# / Dedicated throttle: 1 req/s per IP per Nominatim policy.
class WidgetReverseGeocodeRateThrottle(AnonRateThrottle):
    """1 requête/seconde/IP — politique Nominatim/OpenStreetMap."""

    rate = "1/second"


class WidgetReverseGeocodeBodySerializer(serializers.Serializer):
    """
    Validation du body POST : `lat` et `lng` floats dans les ranges WGS84.
    / POST body validation: `lat` and `lng` as floats within WGS84 ranges.
    """

    lat = serializers.FloatField(min_value=-90, max_value=90, required=True)
    lng = serializers.FloatField(min_value=-180, max_value=180, required=True)


class WidgetReverseGeocodeViewSet(viewsets.ViewSet):
    """
    ViewSet pour le widget carte adresse — géocodage inverse seulement.

    POST /widgets/geocode-reverse/
    Body: {"lat": float, "lng": float}
    Response 200: {"display_name": str, "address": dict}
    Response 400: {"detail": "..."} (validation error)
    Response 429: throttled
    """

    # Widget public : pas d'auth requise (le wizard onboard est lui-meme
    # accessible sans login). La protection contre l'abuse repose sur le
    # throttle 1 req/s/IP ci-dessous (politique Nominatim).
    # / Public widget: no auth required (onboard wizard itself is open).
    # Abuse protection comes from the 1 req/s/IP throttle below (Nominatim policy).
    permission_classes = [permissions.AllowAny]
    throttle_classes = [WidgetReverseGeocodeRateThrottle]

    @action(detail=False, methods=["POST"], url_path="geocode-reverse")
    def geocode_reverse(self, request):
        """
        POST /widgets/geocode-reverse/ — proxy serveur vers Nominatim.
        / POST /widgets/geocode-reverse/ — server proxy to Nominatim.
        """
        serializer = WidgetReverseGeocodeBodySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        latitude = serializer.validated_data["lat"]
        longitude = serializer.validated_data["lng"]

        # `reverse_geocode` ne raise jamais — renvoie un payload vide en
        # cas d'échec. On propage tel quel (le client JS gère).
        # / `reverse_geocode` never raises — returns empty payload on
        # failure. We propagate as-is (JS client handles it).
        payload = reverse_geocode(latitude, longitude)
        return Response(payload, status=status.HTTP_200_OK)

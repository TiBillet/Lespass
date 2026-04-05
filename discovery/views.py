import logging

from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from BaseBillet.models import LaBoutikAPIKey
from discovery.serializers import PinClaimSerializer

logger = logging.getLogger(__name__)


class DiscoveryClaimThrottle(AnonRateThrottle):
    """10 requêtes/min max pour éviter le brute-force des PINs.
    10 requests/min max to prevent PIN brute-force."""
    rate = '10/min'


class ClaimPinView(APIView):
    """
    Route publique : un terminal envoie un PIN 6 chiffres
    et reçoit l'URL du tenant + une clé API LaBoutik.
    Public route: a terminal sends a 6-digit PIN
    and receives the tenant URL + a LaBoutik API key.
    """
    permission_classes = [AllowAny]
    throttle_classes = [DiscoveryClaimThrottle]

    def post(self, request):
        serializer = PinClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pairing_device = serializer.device
        tenant_for_this_device = pairing_device.tenant

        # Récupérer le domaine principal du tenant
        # Get the tenant's primary domain
        primary_domain = tenant_for_this_device.get_primary_domain()
        if not primary_domain:
            logger.error(
                f"Discovery claim: tenant {tenant_for_this_device.name} has no primary domain"
            )
            return Response(
                {"error": "Tenant configuration error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        server_url = f"https://{primary_domain.domain}"

        # Basculer dans le schéma du tenant pour créer la clé API
        # Le type de clé dépend de l'association du device :
        # - TireuseAPIKey si le PairingDevice est lié à une TireuseBec
        # - LaBoutikAPIKey sinon (terminal de caisse)
        # / Switch to tenant schema to create the API key
        # Key type depends on device association:
        # - TireuseAPIKey if PairingDevice is linked to a TireuseBec
        # - LaBoutikAPIKey otherwise (cash register terminal)
        tireuse_uuid = None
        try:
            with tenant_context(tenant_for_this_device):
                # Vérifier si une tireuse est liée à ce PairingDevice
                # / Check if a tap is linked to this PairingDevice
                from controlvanne.models import TireuseBec, TireuseAPIKey
                tireuse = TireuseBec.objects.filter(
                    pairing_device=pairing_device
                ).first()

                if tireuse:
                    _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                        name=f"discovery-tireuse-{pairing_device.uuid}"
                    )
                    tireuse_uuid = str(tireuse.uuid)
                else:
                    _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
                        name=f"discovery-{pairing_device.uuid}"
                    )
        except Exception as error:
            logger.error(
                f"Discovery claim: failed to create API key "
                f"for tenant {tenant_for_this_device.name}: {error}"
            )
            return Response(
                {"error": "Failed to create device credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Marquer le PIN comme consommé / Mark PIN as claimed
        pairing_device.claim()

        logger.info(
            f"Discovery: device '{pairing_device.name}' "
            f"paired to tenant '{tenant_for_this_device.name}'"
        )

        response_data = {
            "server_url": server_url,
            "api_key": api_key_string,
            "device_name": pairing_device.name,
        }
        # Si le device est lié à une tireuse, inclure l'UUID
        # / If the device is linked to a tap, include the UUID
        if tireuse_uuid:
            response_data["tireuse_uuid"] = tireuse_uuid

        return Response(response_data, status=status.HTTP_200_OK)

import logging

from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

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

        # Basculer dans le schéma du tenant pour créer les credentials.
        # Le type de credentials dépend du rôle du terminal (terminal_role) :
        # - LB (LaBoutik POS) : TermUser + LaBoutikAPIKey liée
        # - TI (Tireuse)      : TireuseAPIKey (flow inchangé)
        # - KI (Kiosque)      : TermUser + LaBoutikAPIKey liée (même pipeline que LB)
        # / Switch to tenant schema to create credentials.
        # Credential type depends on terminal_role:
        # - LB (LaBoutik POS): TermUser + linked LaBoutikAPIKey
        # - TI (Tireuse)     : TireuseAPIKey (unchanged flow)
        # - KI (Kiosk)       : TermUser + linked LaBoutikAPIKey (same pipeline as LB)
        tireuse_uuid = None
        try:
            with tenant_context(tenant_for_this_device):
                # Routage selon terminal_role du PairingDevice
                # / Routing based on PairingDevice.terminal_role
                from AuthBillet.models import TibilletUser

                if pairing_device.terminal_role == TibilletUser.ROLE_LABOUTIK:
                    # Flow Laboutik V2 : TermUser + clé liée
                    # / Laboutik V2 flow: TermUser + linked key
                    api_key_string = _create_laboutik_terminal(pairing_device)

                elif pairing_device.terminal_role == TibilletUser.ROLE_TIREUSE:
                    # Flow Tireuse INCHANGÉ pour cette phase
                    # / Tireuse flow UNCHANGED for this phase
                    from controlvanne.models import TireuseBec, TireuseAPIKey
                    tireuse = TireuseBec.objects.filter(
                        pairing_device=pairing_device
                    ).first()
                    if not tireuse:
                        raise ValueError(
                            "Pairing role TIREUSE but no TireuseBec linked"
                        )
                    _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                        name=f"discovery-{pairing_device.uuid}"
                    )
                    tireuse_uuid = str(tireuse.uuid)

                elif pairing_device.terminal_role == TibilletUser.ROLE_KIOSQUE:
                    # Flow Kiosque : pour l'instant on réutilise le helper Laboutik
                    # (TermUser + LaBoutikAPIKey). Une spécialisation pourra
                    # venir dans une phase ultérieure si les besoins divergent.
                    # / Kiosk flow: for now we reuse the Laboutik helper
                    # (TermUser + LaBoutikAPIKey). A dedicated flow may come
                    # later if kiosk requirements diverge.
                    api_key_string = _create_laboutik_terminal(pairing_device)

                else:
                    # Filet de sécurité : rôle inconnu (non prévu dans le modèle).
                    # Ne JAMAIS laisser passer silencieusement un rôle inattendu.
                    # / Safety net: unknown role (not expected in the model).
                    # NEVER silently accept an unexpected role.
                    raise ValueError(
                        f"Unknown PairingDevice.terminal_role: "
                        f"{pairing_device.terminal_role!r}"
                    )
        except Exception as error:
            logger.error(
                f"Discovery claim: failed to create credentials "
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


def _create_laboutik_terminal(pairing_device):
    """
    Crée un TermUser (rôle LaBoutik ou Kiosque) et sa clé API liée.
    / Creates a TermUser (LaBoutik or Kiosk role) and its linked API key.

    LOCALISATION : discovery/views.py

    Appelée dans tenant_context() par ClaimPinView.
    / Called inside tenant_context() by ClaimPinView.

    :param pairing_device: L'objet PairingDevice en cours de claim
    :return: La clé API string (à retourner au client)
    """
    from AuthBillet.models import TermUser
    from BaseBillet.models import LaBoutikAPIKey

    # Email synthétique : <pairing_uuid>@terminals.local
    # Format filtrable, jamais confondu avec un vrai email humain
    # / Synthetic email: <pairing_uuid>@terminals.local
    # Filterable format, never confused with a real human email
    email_synthetique = f"{pairing_device.uuid}@terminals.local"

    # NOTE : TibilletUser.username est unique — on le synchronise avec l'email
    # synthétique (TibilletManager._create_user fait pareil, mais on n'utilise
    # pas create_user ici car un TermUser n'a ni mot de passe ni workflow
    # d'activation).
    # / NOTE: TibilletUser.username is unique — we sync it with the synthetic
    # email (TibilletManager._create_user does the same, but we don't call
    # create_user here because a TermUser has no password nor activation flow).
    term_user = TermUser.objects.create(
        email=email_synthetique,
        username=email_synthetique,
        terminal_role=pairing_device.terminal_role,
        accept_newsletter=False,
    )
    # espece=TE et client_source=tenant auto-posés par TermUser.save()
    # / espece=TE and client_source=tenant auto-set by TermUser.save()

    _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
        name=f"discovery-{pairing_device.uuid}",
        user=term_user,
    )
    return api_key_string

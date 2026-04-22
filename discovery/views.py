import logging

from django.conf import settings
from django.contrib.auth import login as django_login
from django.db import connection
from django.shortcuts import redirect
from django.views import View
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

        # En DEBUG, renvoyer l'URL de la requête entrante (IP locale, http://).
        # Permet au GSM de se connecter directement à l'IP du Mac sans HTTPS.
        # En production, utiliser le domaine principal du tenant (HTTPS obligatoire).
        # / In DEBUG, return the incoming request URL (local IP, http://).
        # Allows the phone to connect directly to the Mac IP without HTTPS.
        # In production, use the tenant's primary domain (HTTPS required).
        if settings.DEBUG:
            server_url = request.build_absolute_uri('/').rstrip('/')
        else:
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

class PinCodeLaBoutikView(APIView):
    """
    Endpoint de découverte pour l'APK LaBoutik mobile (Cordova).
    / Discovery endpoint for the LaBoutik mobile APK (Cordova).

    L'APK envoie le PIN en form-urlencoded et reçoit l'URL du serveur.
    C'est différent de /api/discovery/claim/ (JSON, pour les terminaux Pi).
    / The APK sends the PIN as form-urlencoded and receives the server URL.
    Different from /api/discovery/claim/ (JSON, for Pi terminals).

    Protocole APK :
    POST /pin_code/  Content-Type: application/x-www-form-urlencoded
    Body: pin_code=123456&hostname=samsung-galaxy&username=samsung-...
    Réponse: {"server_url": "http://..../", "server_public_pem": "<api_key>", "locale": "fr"}

    L'APK navigue ensuite vers server_url + "wv/login_hardware".
    / The APK then navigates to server_url + "wv/login_hardware".
    """
    permission_classes = [AllowAny]
    throttle_classes = [DiscoveryClaimThrottle]

    def post(self, request):
        # Extraire les champs form-encodés (ou JSON)
        # / Extract form-encoded fields (or JSON)
        pin_code_raw = request.data.get('pin_code') or request.POST.get('pin_code')
        hostname = request.data.get('hostname', '')
        username = request.data.get('username', '')

        if not pin_code_raw:
            return Response(
                {"error": "pin_code is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valider le PIN via le serializer existant / Validate PIN via existing serializer
        serializer = PinClaimSerializer(data={'pin_code': str(pin_code_raw)})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid or already used PIN code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pairing_device = serializer.device
        tenant_for_this_device = pairing_device.tenant

        # Construire l'URL du serveur (avec slash final pour la concaténation APK)
        # / Build server URL (with trailing slash for APK concatenation)
        primary_domain = tenant_for_this_device.get_primary_domain()
        if primary_domain:
            server_url = f"https://{primary_domain.domain}/"
        elif settings.DEBUG:
            server_url = request.build_absolute_uri('/').rstrip('/').replace('http://', 'https://') + '/'
        else:
            logger.error(f"PinCode: tenant {tenant_for_this_device.name} a pas de domaine principal")
            return Response({"error": "Tenant configuration error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Créer la clé API LaBoutik dans le contexte du tenant
        # / Create LaBoutik API key in tenant context
        device_label = hostname or username or str(pairing_device.uuid)
        try:
            with tenant_context(tenant_for_this_device):
                from BaseBillet.models import LaBoutikAPIKey
                _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
                    name=f"apk-{device_label[:50]}"
                )
        except Exception as error:
            logger.error(
                f"PinCode: échec création clé API "
                f"pour tenant {tenant_for_this_device.name}: {error}"
            )
            return Response(
                {"error": "Failed to create device credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Marquer le PIN comme consommé / Mark PIN as claimed
        pairing_device.claim()

        logger.info(
            f"PinCode APK: appareil '{device_label}' "
            f"appairé au tenant '{tenant_for_this_device.name}'"
        )

        # L'APK stocke server_public_pem — on y met la clé API pour usage futur.
        # L'APK naviguera ensuite vers server_url + "wv/login_hardware".
        # / The APK stores server_public_pem — we put the API key there for future use.
        # The APK will then navigate to server_url + "wv/login_hardware".
        return Response({
            "server_url": server_url,
            "server_public_pem": api_key_string,
            "locale": "fr",
        }, status=status.HTTP_200_OK)


class WvLoginHardwareView(View):
    """
    Point d'entrée WebView après appairage PIN pour l'APK LaBoutik.
    / WebView entry point after PIN pairing for the LaBoutik APK.

    L'APK navigue ici après un échange PIN réussi (server_url + "wv/login_hardware").

    Deux choses nécessaires avant d'accéder à la caisse :
    1. Session Django : l'admin est connecté automatiquement en DEBUG.
    2. localStorage.laboutik : nfc.js lit storage.mode_nfc pour choisir
       le mode de lecture NFC. Sans cette clé, le NFC reste muet.
       En mode Cordova (APK Android), il faut mode_nfc = "NFCMC".

    / Two things needed before accessing the caisse:
    1. Django session: admin auto-logged-in in DEBUG.
    2. localStorage.laboutik: nfc.js reads storage.mode_nfc to choose
       the NFC reading mode. Without this key, NFC stays silent.
       In Cordova mode (Android APK), mode_nfc must be "NFCMC".
    """

    def get(self, request):
        if settings.DEBUG:
            current_tenant = connection.tenant

            # Chercher un admin du tenant (shared schema, toujours accessible)
            # / Find a tenant admin (shared schema, always accessible)
            from AuthBillet.models import TibilletUser
            admin_user = TibilletUser.objects.filter(
                client_admin=current_tenant,
            ).first()

            if admin_user:
                admin_user.backend = 'django.contrib.auth.backends.ModelBackend'
                django_login(request, admin_user)
                logger.info(
                    f"WvLoginHardware DEBUG: auto-login {admin_user.email} "
                    f"sur {current_tenant.schema_name}"
                )

        # Renvoyer une page HTML minimaliste qui :
        # 1. Initialise localStorage.laboutik avec mode_nfc = "NFCMC"
        #    (obligatoire : nfc.js lit cette valeur pour activer le lecteur Cordova)
        # 2. Redirige vers la caisse via JS (la session cookie est déjà posée)
        # / Return a minimal HTML page that:
        # 1. Initialises localStorage.laboutik with mode_nfc = "NFCMC"
        #    (required: nfc.js reads this value to activate the Cordova reader)
        # 2. Redirects to the caisse via JS (session cookie already set)
        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
// Initialise le mode NFC pour l'APK Cordova.
// nfc.js lit localStorage.getItem('laboutik').mode_nfc.
// Sans cette valeur, le lecteur NFC reste muet.
// / Initialise NFC mode for the Cordova APK.
// nfc.js reads localStorage.getItem('laboutik').mode_nfc.
// Without this value, the NFC reader stays silent.
var laboutikConf = localStorage.getItem('laboutik');
if (!laboutikConf) {
    localStorage.setItem('laboutik', JSON.stringify({
        mode_nfc: 'NFCMC',
        front_type: 'FMO'
    }));
} else {
    try {
        var conf = JSON.parse(laboutikConf);
        if (!conf.mode_nfc) {
            conf.mode_nfc = 'NFCMC';
            conf.front_type = conf.front_type || 'FMO';
            localStorage.setItem('laboutik', JSON.stringify(conf));
        }
    } catch(e) {
        localStorage.setItem('laboutik', JSON.stringify({mode_nfc: 'NFCMC', front_type: 'FMO'}));
    }
}
window.location.replace('/laboutik/caisse/');
</script>
</body>
</html>"""
        from django.http import HttpResponse
        return HttpResponse(html, content_type='text/html')


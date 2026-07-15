import logging

from django.db import transaction
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

        # Basculer dans le schema du lieu pour REMPLIR le terminal.
        #
        # Le terminal existe DEJA : le gestionnaire l'a cree dans l'admin, et c'est cette
        # creation qui a fabrique le code PIN. Le claim ne cree donc rien de materiel — il
        # pose sur ce terminal le compte et la cle qui lui manquaient pour travailler.
        #
        # Les trois roles suivent le meme chemin. Seule la CLASSE de la cle change, parce
        # que les permissions de la tireuse s'appuient sur une classe distincte.
        # / The terminal ALREADY exists: the manager created it, and that is what issued the
        # PIN. The claim fills it in — it creates nothing physical.
        tireuse_uuid = None
        try:
            with tenant_context(tenant_for_this_device):
                api_key_string, tireuse_uuid = _remplir_le_terminal(pairing_device)

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


def _remplir_le_terminal(pairing_device):
    """
    Pose sur le terminal le compte et la cle qui lui manquaient pour travailler.
    / Fills the terminal in with the account and key it was missing.

    LOCALISATION : discovery/views.py

    Appelee DANS un tenant_context() par ClaimPinView.
    / Called INSIDE a tenant_context() by ClaimPinView.

    Le terminal n'est PAS cree ici : il existe deja. Le gestionnaire l'a cree dans l'admin,
    et c'est cette creation qui a fabrique le code PIN qu'on est en train de reclamer. Le
    code PIN porte l'identifiant du terminal a remplir dans `cible_uuid`.

    Deux objets naissent ici :
    - le TermUser : le COMPTE de l'appareil. Il vit dans le schema public, Django n'acceptant
      qu'un seul modele d'utilisateur pour tout le projet ;
    - la cle d'API : c'est elle que l'appareil presentera a chaque appel.

    La classe de la cle depend du role : une tireuse recoit une TireuseAPIKey, une caisse ou
    une borne une LaBoutikAPIKey. Les deux systemes restent separes — les permissions de
    controlvanne s'appuient sur une classe distincte, et les fusionner elargirait la surface
    d'attaque sans rien apporter.

    Tout se fait dans une transaction : si la cle echoue, le compte ne doit pas rester
    orphelin.

    :param pairing_device: le code PIN en cours de reclamation
    :return: (la cle d'API, l'identifiant de la tireuse ou None) — renvoyes a l'appareil
    :raises ValueError: si le code ne designe aucun terminal, si le terminal a ete supprime,
                        s'il est deja appaire, ou si son role est inconnu
    """
    from AuthBillet.models import TermUser, TibilletUser
    from laboutik.models import Terminal

    if not pairing_device.cible_uuid:
        raise ValueError(
            "Ce code PIN ne designe aucun terminal (cible_uuid vide)."
        )

    terminal = Terminal.objects.filter(id=pairing_device.cible_uuid).first()
    if terminal is None:
        raise ValueError(
            f"Le terminal {pairing_device.cible_uuid} de cet appairage n'existe plus : "
            f"il a ete supprime pendant que le code PIN circulait."
        )

    # Deja appaire : on refuse. Protege d'un etat incoherent, et d'une course entre deux
    # appareils qui reclameraient le meme code en meme temps.
    # / Already paired: refuse. Guards against an inconsistent state and a race between two
    # devices claiming the same PIN at once.
    if terminal.est_appaire():
        raise ValueError(
            f"Le terminal '{terminal.name}' est deja appaire."
        )

    role = pairing_device.terminal_role
    roles_connus = (
        TibilletUser.ROLE_LABOUTIK,
        TibilletUser.ROLE_KIOSQUE,
        TibilletUser.ROLE_TIREUSE,
    )
    if role not in roles_connus:
        # Ne JAMAIS laisser passer un role inattendu en silence.
        # / NEVER silently accept an unexpected role.
        raise ValueError(f"Role d'appairage inconnu : {role!r}")

    with transaction.atomic():
        # Email synthetique : <uuid du code PIN>@terminals.local
        # Filtrable, jamais confondu avec l'email d'un humain. Comme chaque appairage a son
        # propre identifiant, re-appairer un appareil ne peut pas entrer en collision avec
        # l'ancien compte.
        # / Synthetic email. Each pairing has its own uuid, so re-pairing never collides.
        email_synthetique = f"{pairing_device.uuid}@terminals.local"

        # On n'utilise pas create_user : un terminal n'a ni mot de passe ni activation.
        # first_name porte le nom lisible — l'email etant synthetique, c'est le seul endroit
        # ou l'admin peut lire un nom humain.
        # / No create_user: a terminal has no password nor activation. first_name carries
        # the readable name.
        term_user = TermUser.objects.create(
            email=email_synthetique,
            username=email_synthetique,
            first_name=terminal.name or pairing_device.name,
            terminal_role=role,
            accept_newsletter=False,
        )
        # espece=TE et client_source=lieu courant sont auto-poses par TermUser.save()
        # / espece=TE and client_source are auto-set by TermUser.save()

        api_key_string = _creer_la_cle_du_terminal(pairing_device, term_user, role)

        terminal.term_user = term_user
        terminal.save(update_fields=["term_user"])

    # Une tireuse doit recevoir son identifiant : son Raspberry Pi le stocke dans son .env
    # et s'en sert a chaque appel.
    # / A tap must receive its id: the Pi stores it in its .env and uses it on every call.
    tireuse_uuid = None
    if role == TibilletUser.ROLE_TIREUSE:
        tireuse = getattr(terminal, "tireuse", None)
        if tireuse is None:
            raise ValueError(
                f"Le terminal '{terminal.name}' a le role Tireuse mais aucune tireuse "
                f"ne le designe."
            )
        tireuse_uuid = str(tireuse.uuid)

    return api_key_string, tireuse_uuid


def _creer_la_cle_du_terminal(pairing_device, term_user, role):
    """
    Cree la cle d'API du terminal, de la classe qui correspond a son role.
    / Creates the terminal's API key, of the class matching its role.

    LOCALISATION : discovery/views.py

    Les deux classes de cles restent SEPAREES : les permissions de controlvanne
    (HasTireuseAccess) s'appuient sur TireuseAPIKey. Les fusionner permettrait a une cle de
    caisse de piloter une vanne.
    / The two key classes stay SEPARATE: merging them would let a POS key drive a valve.

    :return: la cle d'API en clair (str), a renvoyer a l'appareil
    """
    from AuthBillet.models import TibilletUser

    nom_de_la_cle = f"discovery-{pairing_device.uuid}"

    if role == TibilletUser.ROLE_TIREUSE:
        from controlvanne.models import TireuseAPIKey

        _cle, api_key_string = TireuseAPIKey.objects.create_key(
            name=nom_de_la_cle,
            user=term_user,
        )
        return api_key_string

    from BaseBillet.models import LaBoutikAPIKey

    _cle, api_key_string = LaBoutikAPIKey.objects.create_key(
        name=nom_de_la_cle,
        user=term_user,
    )
    return api_key_string

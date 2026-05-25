import datetime
import re
import uuid as uuid_module

from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.cache import cache

from ApiBillet.permissions import TenantAdminApiPermission
from ApiBillet.views import get_permission_Api_ALL_Admin
from AuthBillet.models import TibilletUser
from BaseBillet.models import Event, PostalAddress, LigneArticle, Product, Reservation, Membership, logger, \
    Configuration
from crowds.models import Initiative, BudgetItem, Participation, Vote
from .permissions import SemanticApiKeyPermission
from .serializers import (
    EventSchemaSerializer,
    EventCreateSerializer,
    PostalAddressAsSchemaSerializer,
    PostalAddressCreateSerializer, SemanticProductFromSaleLineSerializer,
    ProductCreateSerializer,
    ProductSchemaSerializer,
    ReservationCreateSerializer,
    ReservationSchemaSerializer,
    MembershipCreateSerializer,
    MembershipSchemaSerializer,
    MembershipStatusSerializer,
    WalletRefillCreateSerializer,
    InitiativeSchemaSerializer,
    InitiativeCreateSerializer,
    BudgetItemSchemaSerializer,
    BudgetItemCreateSerializer,
    ParticipationSchemaSerializer,
    ParticipationCreateSerializer,
)


def get_objet_par_uuid_ou_404(model, uuid_recu, **filtres_supplementaires):
    """
    Recupere un objet via son uuid, ou leve Http404 si l'uuid est mal forme.
    / Get an object by its uuid, or raise Http404 if the uuid is malformed.

    LOCALISATION : api_v2/views.py

    Pourquoi : le routeur DRF capture n'importe quelle chaine dans l'URL
    (regex `[^/.]+`). Un robot peut appeler /api/v2/events/<slug>/ avec un
    slug au lieu d'un uuid. Sans cette verification, Django essaie de
    convertir le slug en UUID pour le filtre ORM, leve ValidationError,
    et renvoie une 500. On veut une 404 propre : la ressource n'existe pas.
    / The DRF router captures any string in the URL. A crawler may pass a
    slug instead of a uuid. Without this guard Django raises ValidationError
    on the UUIDField (-> HTTP 500). We want a clean 404 instead.

    Voir piege 9.76 (tests/PIEGES.md) : meme correctif sur detail_vente().
    / See pitfall 9.76: same fix applied to detail_vente().
    """
    # On verifie d'abord que la chaine recue est un uuid valide.
    # / First check the received string is a valid uuid.
    try:
        uuid_module.UUID(str(uuid_recu))
    except (ValueError, TypeError, AttributeError):
        # uuid mal forme -> la ressource ne peut pas exister -> 404
        # / malformed uuid -> resource cannot exist -> 404
        raise Http404("Invalid identifier")

    return get_object_or_404(model, uuid=uuid_recu, **filtres_supplementaires)


def get_event_par_identifiant_ou_404(identifiant):
    """
    Resout un evenement a partir d'un identifiant qui peut etre un uuid OU le slug
    utilise par le controleur front (EventMVT). Leve Http404 si rien ne correspond.
    / Resolve an event from an identifier that can be a uuid OR the front slug.

    LOCALISATION : api_v2/views.py

    Deux formes acceptees, comme cote front (cf EventMVT.retrieve dans BaseBillet) :
    - uuid complet (ex: 7d51dee7-1234-...) -> lookup direct par uuid ;
    - slug (ex: mon-evenement-260620-0900-7d51dee7) -> les 8 derniers caracteres
      hex sont le debut de l'uuid (Event.slug se termine par uuid.hex[:8]). On
      cherche via uuid__startswith (un LIKE texte : pas de ValidationError), puis
      en dernier recours via slug__startswith.
    / Two accepted forms, like the front: a full uuid, or the slug whose last 8 hex
      are the start of the uuid (uuid__startswith), with a slug__startswith fallback.

    Pas de filtre `published` : on resout n'importe quel evenement, comme
    EventMVT.retrieve. / No `published` filter: resolve any event, like the front.
    """
    identifiant = str(identifiant)

    # 1. Identifiant deja sous forme d'uuid valide -> lookup direct.
    # / Identifier is already a valid uuid -> direct lookup.
    try:
        uuid_module.UUID(identifiant)
        event = Event.objects.filter(uuid=identifiant).first()
        if event is None:
            raise Http404("Event not found")
        return event
    except (ValueError, TypeError, AttributeError):
        # Pas un uuid : on tente la resolution par slug.
        # / Not a uuid: fall through to slug resolution.
        pass

    # 2. Slug front : les 8 derniers caracteres hex sont le debut de l'uuid.
    # / Front slug: the last 8 hex characters are the start of the uuid.
    correspondance_hex8 = re.search(r'([0-9a-fA-F]{8})$', identifiant)
    if correspondance_hex8:
        debut_uuid = correspondance_hex8.group(1)
        event = Event.objects.filter(uuid__startswith=debut_uuid).first()
        if event is not None:
            return event

    # 3. Dernier recours : recherche par slug complet.
    # / Last resort: lookup by full slug.
    event = Event.objects.filter(slug__startswith=identifiant).first()
    if event is None:
        raise Http404("Event not found")
    return event


class CrowdInitiativeViewSet(viewsets.ViewSet):
    """
    Semantic Project API for Crowds initiatives.

    Header: Authorization: Api-Key <key>
    Response: schema.org/Project-like JSON.
    """

    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        queryset = Initiative.objects.filter(archived=False)
        serializer = InitiativeSchemaSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        serializer = InitiativeSchemaSerializer(initiative)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = InitiativeCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        initiative = input_serializer.save()
        output_serializer = InitiativeSchemaSerializer(initiative)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid)
        initiative.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="budget-items")
    def budget_items(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid)
        if request.method.lower() == "get":
            items = initiative.budget_items.all().order_by("-created_at")
            serializer = BudgetItemSchemaSerializer(items, many=True)
            return Response({"results": serializer.data})

        input_serializer = BudgetItemCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        state = input_serializer.validated_data.get("actionStatus") or BudgetItem.State.REQUESTED
        if state in [BudgetItem.State.APPROVED, BudgetItem.State.REJECTED]:
            if not (request.user.is_staff or request.user.is_superuser):
                state = BudgetItem.State.REQUESTED
        item = BudgetItem.objects.create(
            initiative=initiative,
            contributor=request.user,
            description=input_serializer.validated_data.get("description") or "",
            amount=input_serializer.amount or 0,
            state=state,
            validator=request.user if state == BudgetItem.State.APPROVED else None,
        )
        serializer = BudgetItemSchemaSerializer(item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="votes")
    def votes(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        if request.method.lower() == "post":
            obj, created = Vote.objects.get_or_create(initiative=initiative, user=request.user)
            count = Vote.objects.filter(initiative=initiative).count()
            return Response({"count": count, "created": created}, status=status.HTTP_201_CREATED)
        count = Vote.objects.filter(initiative=initiative).count()
        return Response({"count": count})

    @action(detail=True, methods=["get", "post"], url_path="participations")
    def participations(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        if request.method.lower() == "post":
            input_serializer = ParticipationCreateSerializer(data=request.data, context={"request": request})
            input_serializer.is_valid(raise_exception=True)
            participation = Participation.objects.create(
                initiative=initiative,
                participant=request.user,
                description=input_serializer.validated_data.get("description") or "",
                amount=getattr(input_serializer, "amount", None),
                state=Participation.State.REQUESTED,
            )
            serializer = ParticipationSchemaSerializer(participation)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        items = initiative.participations.select_related("participant").all()
        serializer = ParticipationSchemaSerializer(items, many=True)
        return Response({"results": serializer.data})


class EventViewSet(viewsets.ViewSet):
    """
    Semantic Event API (list + retrieve + create + delete) implemented with classic ViewSet.

    Header: Authorization: Api-Key <key>
    Response: JSON-LD compliant with https://schema.org/Event
    """

    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        only_futur = request.GET.get("only_futur", None)
        filter = request.GET.get("filter", None)

        queryset = Event.objects.filter(published=True)
        if only_futur:
            timezone = Configuration.get_solo().get_tzinfo()

            # Get the timezone
            now = datetime.now()
            # Convert it to the tenant configured timezone
            now = now.astimezone(timezone)
            # Remove one day to it to also show recent events
            now = now.replace(day=now.day-1)

            queryset = queryset.filter(
                Q(datetime__gte=now) |
                Q(end_datetime__gte=now)
            )

        if filter:
            # Filter by name and descriptions
            queryset = queryset.filter(
                Q(name__icontains=filter) |
                Q(short_description__icontains=filter) |
                Q(long_description__icontains=filter)
            )

        serializer = EventSchemaSerializer(queryset, many=True)
        # Non-paginated wrapper for consistency with tests
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        # Accepte un uuid OU le slug du front (cf EventMVT.retrieve cote front).
        # / Accepts a uuid OR the front slug (see EventMVT.retrieve on the front).
        event = get_event_par_identifiant_ou_404(uuid)
        serializer = EventSchemaSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = EventCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        event = input_serializer.save()
        # Handle optional image uploads (multipart) with strict validation
        updated_fields = []
        if hasattr(request, "FILES"):
            img_f = request.FILES.get("img")
            if img_f:
                # validated in serializer.validate()
                event.img = img_f
                updated_fields.append("img")
            sticker_f = request.FILES.get("sticker_img")
            if sticker_f:
                event.sticker_img = sticker_f
                updated_fields.append("sticker_img")
            if updated_fields:
                event.save(update_fields=updated_fields)
        output_serializer = EventSchemaSerializer(event)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, uuid=None):
        event = get_objet_par_uuid_ou_404(Event, uuid)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="link-address", permission_classes=[SemanticApiKeyPermission])
    def link_address(self, request, uuid=None, **kwargs):
        """
        Link a PostalAddress to this Event.
        Accepts either:
        - {"postalAddressId": <int>} to link an existing address, or
        - a schema.org PostalAddress payload to create & link on the fly.
        Returns the updated Event representation.
        """
        event = get_objet_par_uuid_ou_404(Event, uuid)
        addr_id = request.data.get("postalAddressId")
        address = None
        if addr_id:
            try:
                address = PostalAddress.objects.get(id=int(addr_id))
            except (PostalAddress.DoesNotExist, ValueError, TypeError):
                return Response({"detail": "postalAddressId not found"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Try to create from schema.org body
            pa_serializer = PostalAddressCreateSerializer(data=request.data, context={"request": request})
            if not pa_serializer.is_valid():
                return Response(pa_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            address = pa_serializer.save()
        # Link and save
        event.postal_address = address
        event.save(update_fields=["postal_address"]) 
        return Response(EventSchemaSerializer(event).data, status=status.HTTP_200_OK)


class PostalAddressViewSet(viewsets.ViewSet):
    """
    Semantic PostalAddress API (list, retrieve, create, delete) using classic ViewSet.

    Header: Authorization: Api-Key <key>
    Representation: schema.org/PostalAddress
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        qs = PostalAddress.objects.all()
        ser = PostalAddressAsSchemaSerializer(qs, many=True)
        # Keep the same list wrapper convention as Events
        return Response({"results": ser.data})

    def retrieve(self, request, pk=None):
        instance = get_object_or_404(PostalAddress, id=pk)
        data = PostalAddressAsSchemaSerializer(instance).data
        return Response(data)

    def create(self, request):
        ser = PostalAddressCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        addr = ser.save()
        # Handle optional image uploads (multipart)
        if hasattr(request, "FILES"):
            updated = []
            img_f = request.FILES.get("img")
            if img_f:
                addr.img = img_f
                updated.append("img")
            sticker_f = request.FILES.get("sticker_img")
            if sticker_f:
                addr.sticker_img = sticker_f
                updated.append("sticker_img")
            if updated:
                addr.save(update_fields=updated)
        out = PostalAddressAsSchemaSerializer(addr).data
        return Response(out, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        instance = get_object_or_404(PostalAddress, id=pk)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductViewSet(viewsets.ViewSet):
    """
    Semantic Product API (list + retrieve + create).
    API Produit semantique (liste + detail + creation).

    Header: Authorization: Api-Key <key>
    Response: JSON-LD compliant with https://schema.org/Product
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        queryset = Product.objects.filter(archive=False, publish=True)
        serializer = ProductSchemaSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        product = get_object_or_404(Product, uuid=uuid, archive=False)
        serializer = ProductSchemaSerializer(product)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = ProductCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        product = input_serializer.save()
        output_serializer = ProductSchemaSerializer(product)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)



class ReservationViewSet(viewsets.ViewSet):
    """
    Semantic Reservation API (create + retrieve).
    API Reservation semantique (creation + detail).
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    lookup_field = "uuid"

    def create(self, request):
        input_serializer = ReservationCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        reservation = input_serializer.save()
        output_serializer = ReservationSchemaSerializer(reservation)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, uuid=None):
        reservation = get_object_or_404(Reservation, uuid=uuid)
        serializer = ReservationSchemaSerializer(reservation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MembershipViewSet(viewsets.ViewSet):
    """
    Semantic Membership API (create + retrieve).
    API Adhesion semantique (creation + detail).
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    lookup_field = "uuid"

    def create(self, request):
        input_serializer = MembershipCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        membership = input_serializer.save()
        output_serializer = MembershipSchemaSerializer(membership)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, uuid=None):
        membership = get_object_or_404(Membership, uuid=uuid)
        serializer = MembershipSchemaSerializer(membership)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=False, methods=["get"], url_path="by-wallet")
    def by_wallet(self, request):
        """
        Liste les adhesions d'un porteur a partir de son wallet Fedow.
        / Lists a holder's memberships from their Fedow wallet uuid.
        Auth + IP + permission `membership` geres par SemanticApiKeyPermission.
        """
        wallet_uuid = request.query_params.get("wallet_uuid")
        if not wallet_uuid:
            return Response({"detail": "wallet_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        user = TibilletUser.objects.filter(wallet__uuid=wallet_uuid).first()
        memberships = user.memberships.all() if user else Membership.objects.none()
        serializer = MembershipStatusSerializer(memberships, many=True)
        return Response(
            {"wallet_uuid": wallet_uuid, "memberships": serializer.data},
            status=status.HTTP_200_OK,
        )


# Plafond par recharge cadeau, en unite brute (cf SPEC API_GIFT_REFILL).
# / Per-call gift refill cap, in raw unit.
GIFT_REFILL_MAX_AMOUNT = 10000


class WalletRefillViewSet(viewsets.ViewSet):
    """
    Recharge de tokens cadeau (TNF) sur la tirelire d'un user.
    / Gift token (TNF) wallet refill.

    LOCALISATION : api_v2/views.py

    Header : Authorization: Api-Key <key> (cle restreinte a un asset cadeau via
    ExternalApiKey.gift_asset).
    Header optionnel : Idempotency-Key (anti double-credit, cache best-effort).

    FLUX :
    1. Recupere l'objet cle API pour connaitre l'asset cadeau autorise.
    2. Valide le payload (email, asset uuid, amount entier positif).
    3. Resout l'asset et verifie qu'il est de categorie cadeau (TNF).
    4. Verifie que l'asset demande est bien celui autorise sur la cle.
    5. Verifie le plafond.
    6. Idempotence (cache par tenant).
    7. Cree/recupere l'user, verifie Fedow, credite la tirelire.
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request):
        from ApiBillet.permissions import get_apikey_valid
        from fedow_public.models import AssetFedowPublic
        from fedow_connect.models import FedowConfig
        from fedow_connect.fedow_api import FedowAPI
        from AuthBillet.utils import get_or_create_user

        # 1. Recupere l'objet cle API pour connaitre l'asset autorise
        # / Get the API key object to know the allowed asset
        api_key = get_apikey_valid(self)
        if not api_key or not api_key.gift_asset_id:
            return Response({"detail": _("API key not allowed for gift refill.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 2. Validation du payload / Validate payload
        input_serializer = WalletRefillCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        email = input_serializer.validated_data["email"]
        asset_uuid = input_serializer.validated_data["asset"]
        amount = input_serializer.validated_data["amount"]

        # 3. Resolution de l'asset / Resolve asset
        asset = get_object_or_404(AssetFedowPublic, uuid=asset_uuid)

        # 4. Categorie rechargeable obligatoire (non adossee a l'euro)
        # / Refillable category required (not euro-backed)
        if asset.category not in AssetFedowPublic.REFILLABLE_CATEGORIES:
            return Response({"detail": _("This asset category cannot be topped up.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 5. L'asset doit etre celui autorise sur la cle / Must match key asset
        if asset.uuid != api_key.gift_asset_id:
            return Response({"detail": _("Asset not allowed for this API key.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 6. Plafond / Cap
        if amount > GIFT_REFILL_MAX_AMOUNT:
            return Response({"detail": _("Amount above the maximum allowed.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 7. Idempotence (cache best-effort, cle par tenant)
        # / Idempotency (best-effort cache, per-tenant key)
        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        cache_key = None
        if idempotency_key:
            cache_key = f"api:gift_refill:idem:{connection.tenant.pk}:{idempotency_key}"
            cached = cache.get(cache_key)
            if cached is not None:
                # Rejeu idempotent : la transaction a deja ete creee, on renvoie
                # la reponse stockee sans recrediter. 208 = deja traite.
                # / Idempotent replay: transaction already created, return the
                # stored response without re-crediting. 208 = already reported.
                return Response(cached, status=status.HTTP_208_ALREADY_REPORTED)

        # 8. User / User
        user = get_or_create_user(email)
        if not user:
            return Response({"detail": _("Invalid email.")},
                            status=status.HTTP_406_NOT_ACCEPTABLE)

        # 9. Fedow dispo ? / Fedow available?
        if not FedowConfig.get_solo().can_fedow():
            return Response({"detail": _("Fedow service unavailable.")},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # 10. Credit / Refill
        fedowAPI = FedowAPI()
        metadata = {
            "reason": f"API gift refill: {amount} {asset.name}",
            "api_key": api_key.name,
        }
        if idempotency_key:
            metadata["idempotency_key"] = idempotency_key
        reward_tx = fedowAPI.transaction.refill_from_lespass_to_user_wallet(
            user=user, amount=amount, asset=asset, metadata=metadata,
        )

        # 11. Reponse schema.org MoneyTransfer
        payload = {
            "@context": "https://schema.org",
            "@type": "MoneyTransfer",
            "identifier": str(reward_tx.get("uuid")),
            "amount": amount,
            "asset": str(asset.uuid),
            "recipient": {"@type": "Person", "email": email},
        }
        if cache_key:
            cache.set(cache_key, payload, timeout=60 * 60 * 48)  # 48h
        return Response(payload, status=status.HTTP_201_CREATED)


class SaleViewSet(viewsets.ViewSet):
    """
    Ventes (LigneArticle) — LIST et RETRIEVE uniquement.

    - Permission: clé API + administrateur du tenant (TenantAdminApiPermission).
    - LIST: nécessite deux paramètres de requête obligatoires `start` et `end` au format ISO 8601
      avec fuseau horaire (TZ aware). Exemple: 2025-01-01T00:00:00+01:00
      Filtre les ventes dont `datetime` est comprise dans l'intervalle [start, end].
    - RETRIEVE: retourne une vente (ligne) par son UUID.

    Sémantique schema.org: chaque élément correspond à un OrderItem (ligne de commande).

    Commentaire FALC (Facile À Lire et à Comprendre):
    - Cette route liste des lignes de vente.
    - Pour la liste, vous devez donner un début et une fin de période avec l'heure et le fuseau (ex: +01:00).
    - Vous devez utiliser une clé API autorisée et être administrateur du tenant.
    """

    permission_classes = [TenantAdminApiPermission]

    def list(self, request):
        # Récupère les paramètres de dates (chaînes ISO 8601 avec TZ)
        start_str = request.query_params.get('start')
        end_str = request.query_params.get('end')

        if not start_str or not end_str:
            return Response({
                'detail': "Paramètres 'start' et 'end' obligatoires (ISO 8601, avec fuseau horaire).",
                'exemple': "?start=2025-01-01T00:00:00+01:00&end=2025-01-31T23:59:59+01:00",
            }, status=status.HTTP_400_BAD_REQUEST)

        # Parse et validation TZ-aware
        from django.utils.dateparse import parse_datetime
        try:
            start_dt = parse_datetime(start_str)
            end_dt = parse_datetime(end_str)
        except Exception:
            start_dt = None
            end_dt = None

        if not start_dt or not end_dt or start_dt.tzinfo is None or end_dt.tzinfo is None:
            return Response({
                'detail': "Dates invalides. Utilisez un format ISO 8601 avec fuseau horaire (TZ aware).",
                'exemple': "2025-01-01T00:00:00+01:00",
            }, status=status.HTTP_400_BAD_REQUEST)

        if end_dt < start_dt:
            return Response({
                'detail': "La date de fin doit être postérieure à la date de début.",
            }, status=status.HTTP_400_BAD_REQUEST)

        # Paramètre de filtre status (par défaut: uniquement VALID)
        status_param = (request.query_params.get('status') or '').strip()

        # Mapping nom lisible -> code interne
        status_map = {
            'CANCELED': 'C', 'CANCELLED': 'C', 'C': 'C',
            'REFUNDED': 'R', 'R': 'R',
            'CREATED': 'O', 'O': 'O',
            'UNPAID': 'U', 'U': 'U',
            'FREERES': 'F', 'F': 'F',
            'PAID': 'P', 'P': 'P',
            'VALID': 'V', 'V': 'V',
            'FAILED': 'D', 'D': 'D',
            'ALL': 'ALL',
        }

        # Normalise et valide
        normalized = 'V'  # défaut: VALID uniquement
        if status_param:
            key = status_param.upper()
            if key not in status_map:
                return Response({
                    'detail': "Paramètre 'status' invalide. Valeurs acceptées: ALL, CANCELED, REFUNDED, CREATED, UNPAID, FREERES, PAID, VALID, FAILED (ou leurs codes C,R,O,U,F,P,V,D).",
                }, status=status.HTTP_400_BAD_REQUEST)
            normalized = status_map[key]

        # Mise en cache de la liste pour atténuer les charges (anti DDoS applicatif)
        # Clé de cache par tenant + paramètres (inclut le filtre de status)
        schema = getattr(connection, 'schema_name', 'public')
        cache_key = f"api:sales:list:{schema}:{start_dt.isoformat()}:{end_dt.isoformat()}:{normalized}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Filtre des lignes de vente dans l'intervalle inclusif, avec select_related pour éviter le N+1
        queryset = (
            LigneArticle.objects
            .select_related(
                'pricesold',
                'pricesold__productsold',
                'pricesold__productsold__product',
                'pricesold__price',
            )
            .filter(datetime__gte=start_dt, datetime__lte=end_dt)
            .order_by('-datetime')
        )

        # Applique le filtre de statut, sauf si ALL
        if normalized != 'ALL':
            queryset = queryset.filter(status=normalized)

        # Sérialisation sémantique obligatoire (schema.org Product)
        items = [
            SemanticProductFromSaleLineSerializer(obj, context={'request': request}).data
            for obj in queryset
        ]

        payload = {
            '@context': 'https://schema.org',
            '@type': 'ItemList',
            'itemListElement': items,
            'startDate': start_dt.isoformat(),
            'endDate': end_dt.isoformat(),
        }

        # Cache court (60s)
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)

    def retrieve(self, request, pk=None):
        # Cache du détail, par tenant + pk
        schema = getattr(connection, 'schema_name', 'public')
        cache_key = f"api:sales:detail:{schema}:{pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # pk est un UUID de LigneArticle — on optimise les relations nécessaires au sérializer
        qs = (
            LigneArticle.objects
            .select_related(
                'pricesold',
                'pricesold__productsold',
                'pricesold__productsold__product',
                'pricesold__price',
            )
        )
        ligne = get_object_or_404(qs, pk=pk)

        # Retour sémantique Product obligatoire
        data = SemanticProductFromSaleLineSerializer(ligne, context={'request': request}).data

        # Cache léger (120s)
        cache.set(cache_key, data, timeout=120)
        return Response(data)

    def get_permissions(self):
        # Pour toutes les actions (LIST et RETRIEVE dans ce ViewSet), on exige:
        # - clé API valide avec droit "sale"
        # - utilisateur admin du tenant
        return get_permission_Api_ALL_Admin(self)

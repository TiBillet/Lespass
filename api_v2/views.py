from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.cache import cache

from ApiBillet.permissions import TenantAdminApiPermission
from ApiBillet.views import get_permission_Api_ALL_Admin
from BaseBillet.models import Event, PostalAddress, LigneArticle
from .permissions import SemanticApiKeyPermission
from .serializers import (
    EventSchemaSerializer,
    EventCreateSerializer,
    PostalAddressAsSchemaSerializer,
    PostalAddressCreateSerializer, SemanticProductFromSaleLineSerializer,
)


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
        queryset = Event.objects.filter(published=True)
        serializer = EventSchemaSerializer(queryset, many=True)
        # Non-paginated wrapper for consistency with tests
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        # Router passes {pk}; our lookup is by uuid
        event = get_object_or_404(Event, uuid=uuid, published=True)
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
        event = get_object_or_404(Event, uuid=uuid)
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
        event = get_object_or_404(Event, uuid=uuid)
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


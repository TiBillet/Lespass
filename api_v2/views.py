from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from BaseBillet.models import Event, PostalAddress
from .permissions import SemanticApiKeyPermission
from .serializers import (
    EventSchemaSerializer,
    EventCreateSerializer,
    PostalAddressAsSchemaSerializer,
    PostalAddressCreateSerializer,
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

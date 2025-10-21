from rest_framework import viewsets, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from BaseBillet.models import Event
from .permissions import SemanticApiKeyPermission
from .serializers import EventSchemaSerializer


class EventViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Semantic Event API (retrieve only)

    Header: Authorization: Api-Key <key>
    Response: JSON-LD compliant with https://schema.org/Event
    """

    queryset = Event.objects.filter(published=True)
    lookup_field = "uuid"
    serializer_class = EventSchemaSerializer
    permission_classes = [SemanticApiKeyPermission]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

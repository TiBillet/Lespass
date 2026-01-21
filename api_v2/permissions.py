from rest_framework.permissions import BasePermission
from rest_framework.viewsets import ViewSet

from ApiBillet.permissions import get_apikey_valid
import logging
logger = logging.getLogger(__name__)


class SemanticApiKeyPermission(BasePermission):
    """
    API v2 semantic permission using ExternalApiKey.
    - Authenticate using Authorization: Api-Key <key>
    - Authorize based on ExternalApiKey.api_permissions()[view.basename]
    On success attaches the key's user to request for downstream logic.
    """

    message = "API key invalid or insufficient permissions for this resource"

    def has_permission(self, request, view: ViewSet) -> bool:
        api_key = get_apikey_valid(view)

        if not api_key:
            return False
        # Attach the key user for later usage
        request.user = api_key.user
        return True

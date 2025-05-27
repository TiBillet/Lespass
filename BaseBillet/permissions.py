import logging
import typing

from django.http import HttpRequest
from rest_framework_api_key.permissions import BaseHasAPIKey

from BaseBillet.models import ScannerAPIKey

logger = logging.getLogger(__name__)


class HasPlaceKeyAndWalletSignature(BaseHasAPIKey):
    # Permission pour billetterie : Place Api key + wallet user signature
    model = ScannerAPIKey

    def get_key(self, request: HttpRequest) -> typing.Optional[str]:
        return super().get_key(request)

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        import ipdb; ipdb.set_trace()
        # appreil is not archived
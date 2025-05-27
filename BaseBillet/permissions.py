import logging
import typing

from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework_api_key.permissions import BaseHasAPIKey

from BaseBillet.models import ScannerAPIKey, ScanApp

logger = logging.getLogger(__name__)


class HasScanApi(BaseHasAPIKey):
    # Permission pour billetterie : Place Api key + wallet user signature
    model = ScannerAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)
        scan_app: ScanApp = key.scan_app
        if scan_app.archive:
            raise PermissionDenied("App is archived.")
        request.scan_app = scan_app
        return super().has_permission(request, view)

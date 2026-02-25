import logging
import typing

from django.db import connection
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework_api_key.permissions import BaseHasAPIKey

from BaseBillet.models import ScannerAPIKey, ScanApp, LaBoutikAPIKey

logger = logging.getLogger(__name__)


class HasScanApi(BaseHasAPIKey):
    # Permission pour billetterie : Place Api key + wallet user signature
    model = ScannerAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)
        try :
            api_key = ScannerAPIKey.objects.get_from_key(key)
            scan_app: ScanApp = api_key.scan_app
            if scan_app.archive:
                raise PermissionDenied("App is archived.")
        except AttributeError:
            raise PermissionDenied("No app associated with this key.")

        request.scan_app = scan_app
        return super().has_permission(request, view)


class HasLaBoutikApi(BaseHasAPIKey):
    model = LaBoutikAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)
        if not key:
            raise PermissionDenied("Missing LaBoutik API key.")
        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(key)
        except LaBoutikAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid LaBoutik API key.")

        request.laboutik_api_key = api_key
        return super().has_permission(request, view)


class HasLaBoutikAccess(BaseHasAPIKey):
    """Accepte soit une clé API LaBoutik, soit un admin tenant connecté."""
    model = LaBoutikAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        # 1. Admin tenant connecté via session → autorisé
        if request.user and request.user.is_authenticated and request.user.is_tenant_admin(connection.tenant):
            return True

        # 2. Clé API LaBoutik (header Authorization: Api-Key xxx)
        key = self.get_key(request)
        if not key:
            raise PermissionDenied("Missing LaBoutik API key or admin session.")
        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(key)
        except LaBoutikAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid LaBoutik API key.")

        request.laboutik_api_key = api_key
        return super().has_permission(request, view)

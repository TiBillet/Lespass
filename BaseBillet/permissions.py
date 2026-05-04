# BaseBillet/permissions.py
# Permissions DRF basées sur des clés API (djangorestframework-api-key).
# DRF permissions based on API keys (djangorestframework-api-key).
#
# Tenant-aware : chaque modèle de clé (ScannerAPIKey, LaBoutikAPIKey) est dans
# une TENANT_APP (BaseBillet). django-tenants isole automatiquement les requêtes
# par schéma PostgreSQL. Une clé créée sur un tenant n'existe pas sur un autre.
# Tenant-aware: each key model (ScannerAPIKey, LaBoutikAPIKey) is in a
# TENANT_APP (BaseBillet). django-tenants automatically isolates queries
# by PostgreSQL schema. A key created on one tenant doesn't exist on another.

import logging
import typing

from django.db import connection
from django.http import HttpRequest
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework_api_key.permissions import BaseHasAPIKey

from BaseBillet.models import ScannerAPIKey, ScanApp, LaBoutikAPIKey

logger = logging.getLogger(__name__)


class HasScanApi(BaseHasAPIKey):
    """
    Permission pour l'app de scan billetterie.
    Permission for the ticket scanning app.

    Vérifie que la clé API correspond à une ScanApp active (non archivée).
    Checks that the API key corresponds to an active (non-archived) ScanApp.
    """
    model = ScannerAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)
        try:
            api_key = ScannerAPIKey.objects.get_from_key(key)
            scan_app: ScanApp = api_key.scan_app
            if scan_app.archive:
                raise PermissionDenied("App is archived.")
        except AttributeError:
            raise PermissionDenied("No app associated with this key.")

        request.scan_app = scan_app
        return super().has_permission(request, view)


class HasLaBoutikApi(BaseHasAPIKey):
    """
    Permission stricte par clé API LaBoutik uniquement.
    Strict permission by LaBoutik API key only.

    Utilisée pour les endpoints qui ne doivent être accessibles que par
    un terminal de caisse authentifié via Discovery (PIN pairing).
    Used for endpoints that should only be accessible by a cash register
    terminal authenticated via Discovery (PIN pairing).
    """
    model = LaBoutikAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)

        # Pas de header Authorization → refusé
        # No Authorization header → denied
        if not key:
            raise PermissionDenied("Missing LaBoutik API key.")

        # Clé invalide ou inconnue sur ce tenant → refusé
        # Invalid or unknown key on this tenant → denied
        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(key)
        except LaBoutikAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid LaBoutik API key.")

        # Attacher la clé à la requête pour usage dans les vues
        # Attach the key to the request for use in views
        request.laboutik_api_key = api_key
        return super().has_permission(request, view)


class HasLaBoutikAccess(BaseHasAPIKey):
    """
    Permission souple : accepte une clé API LaBoutik OU un admin tenant connecté.
    Flexible permission: accepts a LaBoutik API key OR a logged-in tenant admin.

    Deux chemins d'accès / Two access paths :
    1. Clé API (header Authorization: Api-Key xxx) → terminal de caisse
       API key (Authorization: Api-Key xxx header) → cash register terminal
    2. Session admin tenant (cookie sessionid) → accès navigateur pour debug/admin
       Tenant admin session (sessionid cookie) → browser access for debug/admin
    """
    model = LaBoutikAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        # Chemin 1 : admin tenant connecté via session navigateur
        # Path 1: tenant admin logged in via browser session
        utilisateur = request.user
        if utilisateur and utilisateur.is_authenticated:
            est_admin_du_tenant = utilisateur.is_tenant_admin(connection.tenant)
            if est_admin_du_tenant:
                return True

        # Chemin 2 : clé API LaBoutik (header Authorization: Api-Key xxx)
        # Path 2: LaBoutik API key (Authorization: Api-Key xxx header)
        key = self.get_key(request)
        if not key:
            raise PermissionDenied("Missing LaBoutik API key or admin session.")

        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(key)
        except LaBoutikAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid LaBoutik API key.")

        # Attacher la clé à la requête pour usage dans les vues
        # Attach the key to the request for use in views
        request.laboutik_api_key = api_key
        return super().has_permission(request, view)


class HasLaBoutikTerminalAccess(permissions.BasePermission):
    """
    Permission V2 : accepte les TermUser authentifiés via le bridge (session),
    avec fallback V1 sur HasLaBoutikAccess (admin session OU header Api-Key).
    / V2 permission: accepts bridge-authenticated TermUsers (session),
    with V1 fallback on HasLaBoutikAccess (admin session OR Api-Key header).

    LOCALISATION : BaseBillet/permissions.py

    Utilisée sur les routes Laboutik V2 qui adoptent le pattern bridge→session.
    Les routes V1 legacy continuent d'utiliser HasLaBoutikAccess directement.
    / Used on V2 Laboutik routes that adopt the bridge→session pattern.
    Legacy V1 routes keep using HasLaBoutikAccess directly.
    """

    def has_permission(self, request, view):
        from AuthBillet.models import TibilletUser

        user = request.user

        # Chemin V2 : TermUser avec rôle LaBoutik lié à ce tenant
        # / V2 path: TermUser with LaBoutik role linked to this tenant
        if user and user.is_authenticated:
            if user.espece == TibilletUser.TYPE_TERM:
                if user.terminal_role == TibilletUser.ROLE_LABOUTIK:
                    if user.client_source_id == connection.tenant.pk:
                        return True

        # Fallback V1 : délègue à HasLaBoutikAccess
        # / V1 fallback: delegate to HasLaBoutikAccess
        return HasLaBoutikAccess().has_permission(request, view)

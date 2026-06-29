"""
Permissions DRF pour le module tireuse connectée (controlvanne).
/ DRF permissions for the connected tap module (controlvanne).

LOCALISATION : controlvanne/permissions.py

Pattern : même logique que HasLaBoutikAccess (BaseBillet/permissions.py)
mais avec TireuseAPIKey au lieu de LaBoutikAPIKey.
/ Pattern: same logic as HasLaBoutikAccess (BaseBillet/permissions.py)
but with TireuseAPIKey instead of LaBoutikAPIKey.
"""

import typing

from django.db import connection
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework_api_key.permissions import BaseHasAPIKey

from controlvanne.models import TireuseAPIKey


class HasTireuseAccess(BaseHasAPIKey):
    """
    Permission souple : accepte une clé API tireuse OU un admin tenant connecté.
    / Flexible permission: accepts a tap API key OR a logged-in tenant admin.

    Deux chemins d'accès / Two access paths :
    1. Clé API (header Authorization: Api-Key xxx) → Raspberry Pi de la tireuse
       API key (Authorization: Api-Key xxx header) → tap Raspberry Pi
    2. Session admin tenant (cookie sessionid) → accès navigateur pour debug/admin
       Tenant admin session (sessionid cookie) → browser access for debug/admin
    """

    model = TireuseAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        # Chemin 1 : admin tenant connecté via session navigateur
        # / Path 1: tenant admin logged in via browser session
        utilisateur = request.user
        if utilisateur and utilisateur.is_authenticated:
            est_admin_du_tenant = utilisateur.is_tenant_admin(connection.tenant)
            if est_admin_du_tenant:
                return True

        # Chemin 2 : clé API Tireuse (header Authorization: Api-Key xxx)
        # / Path 2: Tap API key (Authorization: Api-Key xxx header)
        key = self.get_key(request)
        if not key:
            raise PermissionDenied("Missing Tireuse API key or admin session.")

        try:
            api_key = TireuseAPIKey.objects.get_from_key(key)
        except TireuseAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid Tireuse API key.")

        # Attacher la clé à la requête pour usage dans les vues
        # / Attach the key to the request for use in views
        request.tireuse_api_key = api_key
        return super().has_permission(request, view)

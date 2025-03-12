from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.viewsets import ViewSet
from rest_framework_api_key.models import AbstractAPIKey, APIKey
from urllib3 import request

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_client_ip
from BaseBillet.models import ExternalApiKey
from Customers.models import Client
import logging

logger = logging.getLogger(__name__)


###

def get_apikey_valid(view: ViewSet) -> AbstractAPIKey or None:
    try:
        # Récupération de la clé API et vérification qu'elle existe pour le tenant
        key = view.request.META["HTTP_AUTHORIZATION"].split()[1]
        api_key = APIKey.objects.get_from_key(key)
        tenant_apikey = get_object_or_404(ExternalApiKey, key=api_key)

        # Vérification si une ip est déclarée dans la clé :
        ip = get_client_ip(view.request)
        if tenant_apikey.ip:
            if ip != tenant_apikey.ip:
                return False

        logger.info(
            f"is_apikey_valid : "
            f"ip request : {ip} - "
            f"basename : {view.basename} : {tenant_apikey.api_permissions().get(view.basename)}"
        )

        # Vérification des droits donnés lors de la création de la clé
        # view.basename == url.basename
        # avec dict qui liste les basenames (déclarés dans urls) autorisés
        # Renvoi True si basename est dans les permissions de la clé
        if tenant_apikey.api_permissions().get(view.basename):
            return tenant_apikey

    except:
        return None


### PERMISSIONS pour les routes avec clé API ###

# Pas utilisé
def RootPermissionWithRequest(request):
    user: TibilletUser = request.user
    return all([user.is_authenticated, user.is_superuser])


# Mis à l'extérieur pour pouvoir être utilisé tout seul sans RESTframework
# Par exemple utilisé par l'admin Unfold ( settings.UNFOLD.SIDEBAR )
def TenantAdminPermissionWithRequest(request):
    # Vérifie que l'user existe et est admin du tenant
    if request.user:
        if request.user.is_superuser:
            return True # le super user peut
        elif request.user.is_authenticated:
            return all([
                connection.tenant in request.user.client_admin.all(),
                request.user.is_staff,
                request.user.is_active,
                request.user.espece == TibilletUser.TYPE_HUM
            ])
    return False


class TenantAdminApiPermission(permissions.BasePermission):
    message = 'User no admin in tenant'

    # clé API + admin tenant pour tout

    def has_permission(self, request, view):
        # Vérification de la clé API
        api_key = get_apikey_valid(view)
        if not api_key:
            return False

        # On ajoute l'user de la clé sur request
        request.user = api_key.user

        # Mis à l'extérieur pour pouvoir être utilisé tout seul sans RESTframework
        # Vérifie que l'user de la requête est bien admin du tenant
        return TenantAdminPermissionWithRequest(request)


class TerminalScanPermission(permissions.BasePermission):
    message = "Termnal must be validated by an admin"

    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return any([
                all([
                    connection.tenant in request.user.client_admin.all(),
                    request.user.is_active,
                    request.user.user_parent().is_staff,
                    request.user.espece == TibilletUser.TYPE_TERM
                ]),
                # Pour l'user ROOT qui peut tout faire
                all([
                    request.user.client_source.categorie == Client.ROOT,
                    request.user.is_superuser,
                ]),
            ])
        else:
            return False

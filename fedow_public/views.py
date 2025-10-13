import json
import logging
from uuid import UUID

from django.db import connection
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from Customers.models import Client
from fedow_connect.fedow_api import FedowAPI
from fedow_public.models import AssetFedowPublic
from django.utils import timezone


# Create your views here.
logger = logging.getLogger(__name__)


class AssetViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['GET'])
    def retrieve_bank_deposits(self, request, pk):
        this_tenant: Client = connection.tenant
        if not request.user.is_tenant_admin(this_tenant):
            raise PermissionDenied

        asset_uuid = UUID(pk) # on valide : NTUI
        asset = get_object_or_404(AssetFedowPublic, pk=asset_uuid)

        fedow = FedowAPI()

        ## Les données de l'asset à un instant T -> ce qu'il y a dans les lieux
        fedow_data = fedow.asset.total_by_place_with_uuid(uuid=f"{asset.uuid}")
        # fedow_data is a JSON string; parse it to dict
        total_by_place_with_uuid = json.loads(fedow_data) if isinstance(fedow_data, (str, bytes)) else (
            fedow_data or {}
        )
        logger.info(f"fedow_data : {fedow_data}")

        # Les transaction de type BANK DEPOSITS:
        retrieve_bank_deposits = fedow.asset.retrieve_bank_deposits(asset=asset)



        context = {
            "asset": asset,
            "total_by_place_with_uuid": total_by_place_with_uuid,
            "retrieve_bank_deposits": retrieve_bank_deposits or [],
            "now": timezone.now(),
        }
        return render(request, "fedow_public/retrieve_bank_deposits.html", context)




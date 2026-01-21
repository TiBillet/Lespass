import json
import logging
from datetime import timedelta
from uuid import UUID

from django.db import connection
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ApiBillet.permissions import TenantAdminPermission
from Customers.models import Client
from fedow_connect.fedow_api import FedowAPI
from fedow_public.models import AssetFedowPublic
from django.utils import timezone


# Create your views here.
logger = logging.getLogger(__name__)


class AssetViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [TenantAdminPermission, ]

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

        # Compute defaults for the transactions filter form
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


        context = {
            "asset": asset,
            "total_by_place_with_uuid": total_by_place_with_uuid,
            "retrieve_bank_deposits": retrieve_bank_deposits or [],
            "now": now,
            "start_of_month": start_of_month,
        }
        return render(request, "fedow_public/retrieve_bank_deposits.html", context)


    @action(detail=False, methods=['POST'])
    def retrieve_transactions(self, request):
        class Validator(serializers.Serializer):
            asset_uuid = serializers.UUIDField()
            start_date = serializers.DateTimeField()
            end_date = serializers.DateTimeField()

            def validate(self, attrs):
                start = attrs.get('start_date')
                end = attrs.get('end_date')
                if start and end and end < start:
                    raise serializers.ValidationError({
                        'end_date': 'La date de fin doit être postérieure à la date de début.'
                    })
                return attrs

        validator = Validator(data=request.data)
        if not validator.is_valid():
            # Render the partial template with serializer errors so HTMX can swap it into the target
            context = {
                'errors': validator.errors,
                'transactions': [],
            }
            return render(request, "fedow_public/transactions_table.html", context)

        asset = get_object_or_404(AssetFedowPublic, pk=validator.validated_data['asset_uuid'])

        fedow = FedowAPI()
        transactions = fedow.transaction.list_by_asset(
            asset=asset,
            user=request.user,
            start_date=validator.validated_data['start_date'],
            end_date=validator.validated_data['end_date'],
        )

        # Ensure chronological order (ascending by datetime)
        try:
            transactions = sorted(transactions or [], key=lambda t: t.get('datetime'))
        except Exception:
            pass

        context = {
            'transactions': transactions,
            'errors': {},
        }
        return render(request, "fedow_public/transactions_table.html", context)

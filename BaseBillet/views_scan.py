from django.core.signing import TimestampSigner
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from BaseBillet.models import ScannerAPIKey, ScanApp
from BaseBillet.permissions import HasScanApi



class check_allow_any(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        return Response({"allow_any": True})

class check_api_scan(APIView):
    permission_classes = [HasScanApi]

    def get(self, request):
        """Retrieve a project based on the request API key."""
        key = request.META["HTTP_AUTHORIZATION"].split()[1]
        api_key = ScannerAPIKey.objects.get_from_key(key)
        response = Response({"scan_app": api_key.scan_app.name})
        return response


class Pair(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            signer = TimestampSigner()
            scanapp_uuid = signer.unsign(urlsafe_base64_decode(pk).decode('utf8'), max_age=(300000))
            scannapp = get_object_or_404(ScanApp, uuid=scanapp_uuid, claimed=False)

            scannapp.claimed = True
            scannapp.key, api_key_string = ScannerAPIKey.objects.create_key(name=f"{scannapp.uuid}")
            scannapp.save()

            # Return success response with API key
            response = Response({
                "success": True,
                "message": "Device successfully paired",
                "api_key": api_key_string,
                "device_uuid": str(scannapp.uuid),
                "device_name": scannapp.name
            }, status=status.HTTP_200_OK)
            return response


        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
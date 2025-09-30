from uuid import UUID

from django.core.signing import TimestampSigner
from django.utils.http import urlsafe_base64_decode
from rest_framework import status, serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from BaseBillet.models import ScannerAPIKey, ScanApp, Ticket
from BaseBillet.permissions import HasScanApi
from django.db.models import Q, CharField
from django.db.models.functions import Cast



class check_allow_any(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        response = Response({"allow_any": True})
        return response

class check_allow_any_widlcard(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        response = Response({"allow_any": True})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

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


class check_ticket(APIView):
    permission_classes = [HasScanApi]

    def post(self, request):
        try:
            # Get the QR code data from the request
            qrcode_data = request.data.get('qrcode_data')

            if not qrcode_data:
                return Response(
                    {"error": "QR code data is required"},
                    status=status.HTTP_406_NOT_ACCEPTABLE
                )

            # Split the QR code data to get the base64-encoded JSON and the signature
            try:
                data_b64, signature = qrcode_data.split(':')
            except ValueError:
                return Response(
                    {"error": "Invalid QR code format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Decode the base64 JSON to get the ticket UUID
            try:
                import json
                import base64
                data_json = json.loads(base64.b64decode(data_b64).decode('utf-8'))
                ticket_uuid = data_json.get('uuid')
                if not ticket_uuid:
                    return Response(
                        {"error": "Ticket UUID not found in QR code data"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {"error": f"Error decoding QR code data: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Find the ticket by UUID
            try:
                ticket = Ticket.objects.get(uuid=ticket_uuid)
            except Ticket.DoesNotExist:
                return Response(
                    {"error": "Ticket not found"},
                    status=status.HTTP_404_NOT_FOUND
                )



            # Verify the signature using the event's public key
            from fedow_connect.utils import verify_signature
            data_b64_bytes = data_b64.encode('utf-8')
            if not verify_signature(
                    ticket.reservation.event.get_public_key(),
                    data_b64_bytes,
                    signature
            ):
                return Response(
                    {"error": "Invalid ticket signature"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Count the number of tickets in the same reservation
            reservation_tickets_count = ticket.reservation.tickets.count()

            # Return a JSON response with the ticket details and reservation tickets count
            return Response({
                "success": True,
                "message": "Ticket information retrieved",
                "ticket": {
                    "uuid": str(ticket.uuid),
                    "status": ticket.get_status_display(),
                    "is_scanned": ticket.status == Ticket.SCANNED,
                    "event": ticket.reservation.event.name,
                    "first_name": ticket.first_name,
                    "last_name": ticket.last_name,
                    "price": ticket.pricesold.price.name if ticket.pricesold else None,
                    "product": ticket.pricesold.productsold.product.name if ticket.pricesold and hasattr(
                        ticket.pricesold, 'productsold') else None,
                    "scanned_by": str(ticket.scanned_by.uuid) if ticket.scanned_by else None
                },
                "reservation": {
                    "uuid": str(ticket.reservation.uuid),
                    "tickets_count": reservation_tickets_count
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ticket(APIView):
    permission_classes = [HasScanApi]
    def post(self, request):
        try:
            # Get the QR code data from the request
            qrcode_data = request.data.get('qrcode_data')
            event_uuid = request.data.get('event_uuid')

            if not event_uuid:
                return Response(
                    {"error": "Event uuid is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not qrcode_data:
                return Response(
                    {"error": "QR code data is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Split the QR code data to get the base64-encoded JSON and the signature
            try:
                data_b64, signature = qrcode_data.split(':')
            except ValueError:
                return Response(
                    {"error": "Invalid QR code format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Decode the base64 JSON to get the ticket UUID
            try:
                import json
                import base64
                data_json = json.loads(base64.b64decode(data_b64).decode('utf-8'))
                ticket_uuid = data_json.get('uuid')
                if not ticket_uuid:
                    return Response(
                        {"error": "Ticket UUID not found in QR code data"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {"error": f"Error decoding QR code data: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Find the ticket by UUID
            try:
                ticket = Ticket.objects.get(uuid=ticket_uuid)
            except Ticket.DoesNotExist:
                return Response(
                    {"error": "Ticket not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            try :
                assert ticket.reservation.event.uuid == UUID(event_uuid)
            except Exception as e:
                return Response(
                    {"error": "Event error"},
                    status=status.HTTP_406_NOT_ACCEPTABLE
                )

            # Verify the signature using the event's public key
            from fedow_connect.utils import verify_signature
            data_b64_bytes = data_b64.encode('utf-8')
            if not verify_signature(
                    ticket.reservation.event.get_public_key(),
                    data_b64_bytes,
                    signature
            ):
                return Response(
                    {"error": "Invalid ticket signature"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Count the number of tickets in the same reservation
            reservation_tickets_count = ticket.reservation.tickets.count()

            # Check if the ticket is already scanned
            if ticket.status == Ticket.SCANNED:
                return Response({
                    "success": False,
                    "message": "Ticket already scanned",
                    "ticket": {
                        "uuid": str(ticket.uuid),
                        "status": ticket.get_status_display(),
                        "event": ticket.reservation.event.name,
                        "first_name": ticket.first_name,
                        "last_name": ticket.last_name,
                        "price": ticket.pricesold.price.name if ticket.pricesold else None,
                        "product": ticket.pricesold.productsold.product.name if ticket.pricesold and hasattr(
                            ticket.pricesold, 'productsold') else None,
                        "scanned_by": str(ticket.scanned_by.uuid) if ticket.scanned_by else None
                    },
                    "reservation": {
                        "uuid": str(ticket.reservation.uuid),
                        "tickets_count": reservation_tickets_count
                    }
                }, status=status.HTTP_200_OK)

            # Update the ticket's status to SCANNED and set the scanned_by field
            scan_app = request.scan_app  # Set by HasScanApi permission
            ticket.status = Ticket.SCANNED
            ticket.scanned_by = scan_app
            ticket.save()

            # Return a JSON response with the ticket details
            return Response({
                "success": True,
                "message": "Ticket successfully scanned",
                "ticket": {
                    "uuid": str(ticket.uuid),
                    "status": ticket.get_status_display(),
                    "event": ticket.reservation.event.name,
                    "first_name": ticket.first_name,
                    "last_name": ticket.last_name,
                    "price": ticket.pricesold.price.name if ticket.pricesold else None,
                    "product": ticket.pricesold.productsold.product.name if ticket.pricesold and hasattr(
                        ticket.pricesold, 'productsold') else None
                },
                "reservation": {
                    "uuid": str(ticket.reservation.uuid),
                    "tickets_count": reservation_tickets_count
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Allowed fields for ordering in list_tickets to prevent unsafe ORM field injection
ALLOWED_ORDER_FIELDS = (
    'reservation__datetime',
    'last_name',
    'first_name',
    'uuid',
    'status',
    'reservation__uuid',
)

class ListTicketsSerializer(serializers.Serializer):
    event_uuid = serializers.UUIDField(required=True)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=200, default=40)
    order_by = serializers.ChoiceField(required=False, choices=ALLOWED_ORDER_FIELDS, default='reservation__datetime')
    order_dir = serializers.ChoiceField(required=False, choices=("asc", "desc"), default='desc')

class list_tickets(APIView):
    permission_classes = [HasScanApi]

    def post(self, request):
        """
        Exemple de requête (POST) avec la librairie requests et un dictionnaire de données:

        import requests

        url = "https://<votre-domaine>/scan/list_tickets/"
        headers = {"Authorization": "Api-Key <VOTRE_CLE_API>", "Content-Type": "application/json"}
        data = {
            "event_uuid": "<UUID-EVENEMENT>",
            "page": 1,
            "page_size": 40,
            "order_by": "reservation__datetime",
            "order_dir": "desc",
        }
        resp = requests.post(url, headers=headers, json=data)
        print(resp.status_code)
        print(resp.json())

        Paramètres:
        - event_uuid (requis): UUID de l'événement.
        - page (optionnel, défaut 1): numéro de page (> 0).
        - page_size (optionnel, défaut 40, max 200): nombre d'éléments par page.
        - order_by (optionnel, défaut "reservation__datetime"): champ d'ordre (whitelist).
        - order_dir (optionnel, défaut "desc"): sens d'ordre, "asc" ou "desc".

        Réponse: JSON avec métadonnées de pagination et liste des tickets.
        """
        try:
            serializer = ListTicketsSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            data = serializer.validated_data
            event_uuid = str(data.get('event_uuid'))
            page = data.get('page', 1)
            page_size = data.get('page_size', 40)
            order_by = data.get('order_by', 'reservation__datetime')
            order_dir = data.get('order_dir', 'desc')

            ordering = f"{'-' if order_dir == 'desc' else ''}{order_by}"

            # Base queryset restricted to the event
            qs = Ticket.objects.filter(reservation__event__uuid=event_uuid).select_related(
                'reservation', 'reservation__event', 'reservation__user_commande',
                'pricesold', 'pricesold__price', 'pricesold__productsold', 'pricesold__productsold__product'
            ).order_by(ordering)

            total = qs.count()
            start = (page - 1) * page_size
            end = start + page_size
            items = qs[start:end]

            results = []
            for t in items:
                results.append({
                    "uuid": str(t.uuid),
                    "first_name": t.first_name,
                    "last_name": t.last_name,
                    "email": getattr(getattr(t.reservation, 'user_commande', None), 'email', None),
                    "price": t.pricesold.price.name if t.pricesold else None,
                    "product": t.pricesold.productsold.product.name if t.pricesold and getattr(t.pricesold, 'productsold', None) else None,
                    "reservation_uuid": str(t.reservation.uuid),
                    "status": t.get_status_display(),
                    "reservation_datetime": getattr(t.reservation, 'datetime', None),
                })

            total_pages = (total + page_size - 1) // page_size if page_size else 1

            return Response({
                "success": True,
                "count": len(results),
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "ordering": {
                    "order_by": order_by,
                    "order_dir": order_dir,
                },
                "results": results,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class search_ticket(APIView):
    permission_classes = [HasScanApi]

    def post(self, request):
        try:
            search = request.data.get('search')
            event_uuid = request.data.get('event_uuid')

            if not event_uuid:
                return Response({"error": "Event uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

            if search is None or str(search).strip() == "":
                return Response({"error": "Search string is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Validate UUID format (will raise ValueError if bad)
            try:
                _ = UUID(str(event_uuid))
            except Exception:
                return Response({"error": "Invalid event uuid"}, status=status.HTTP_400_BAD_REQUEST)

            # Base queryset restricted to the event
            qs = Ticket.objects.filter(reservation__event__uuid=event_uuid)

            # Annotate uuids as text for prefix search
            qs = qs.annotate(
                uuid_text=Cast('uuid', CharField()),
                reservation_uuid_text=Cast('reservation__uuid', CharField()),
            )

            # Build OR filters for the search string
            s = str(search).strip()
            filters = (
                Q(uuid_text__istartswith=s) |
                Q(first_name__icontains=s) |
                Q(last_name__icontains=s) |
                Q(reservation__user_commande__email__icontains=s) |
                Q(pricesold__price__name__icontains=s) |
                Q(pricesold__productsold__product__name__icontains=s) |
                Q(reservation_uuid_text__istartswith=s)
            )

            qs = qs.filter(filters).select_related(
                'reservation', 'reservation__event', 'reservation__user_commande',
                'pricesold', 'pricesold__price', 'pricesold__productsold', 'pricesold__productsold__product'
            ).order_by('last_name', 'first_name')[:50]

            results = []
            for t in qs:
                results.append({
                    "uuid": str(t.uuid),
                    "first_name": t.first_name,
                    "last_name": t.last_name,
                    "email": getattr(getattr(t.reservation, 'user_commande', None), 'email', None),
                    "price": t.pricesold.price.name if t.pricesold else None,
                    "product": t.pricesold.productsold.product.name if t.pricesold and getattr(t.pricesold, 'productsold', None) else None,
                    "reservation_uuid": str(t.reservation.uuid),
                    "status": t.get_status_display(),
                })

            return Response({
                "success": True,
                "count": len(results),
                "results": results,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

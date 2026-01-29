import json
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from BaseBillet.models import Reservation, Membership, Ticket, Product, LigneArticle
from AuthBillet.models import TibilletUser

class Command(BaseCommand):
    help = "Vérifie les données en base de données pour les tests E2E / Verify DB data for E2E tests"

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Email de l\'utilisateur / User email')
        parser.add_argument('--type', type=str, choices=['reservation', 'membership', 'tokens'], help='Type de vérification / Type of verification')
        parser.add_argument('--event', type=str, required=False, help='Nom de l\'événement / Event name')
        parser.add_argument('--product', type=str, required=False, help='Nom du produit / Product name')
        parser.add_argument('--tenant', type=str, default='lespass', help='Schéma du tenant / Tenant schema')

    def handle(self, *args, **options):
        email = options['email']
        check_type = options['type']
        event_name = options.get('event')
        product_name = options.get('product')
        tenant = options['tenant']

        with schema_context(tenant):
            result = {"status": "error", "message": "Unknown error"}

            if check_type == 'reservation':
                # On cherche les tickets liés à cet email pour cet événement
                # We look for tickets linked to this email for this event
                qs = Ticket.objects.filter(reservation__user_commande__email=email)
                if event_name:
                    qs = qs.filter(reservation__event__name__icontains=event_name)
                
                count = qs.count()
                if count > 0:
                    ticket = qs.first()
                    result = {
                        "status": "success",
                        "count": count,
                        "event": ticket.reservation.event.name,
                        "ticket_status": ticket.status,
                        "custom_form": ticket.reservation.custom_form
                    }
                else:
                    result = {"status": "not_found", "message": f"No reservation found for {email}"}

            elif check_type == 'membership':
                # On cherche les adhésions pour cet email
                # We look for memberships for this email
                qs = Membership.objects.filter(user__email=email)
                if product_name:
                    qs = qs.filter(price__product__name__icontains=product_name)
                
                count = qs.count()
                if count > 0:
                    m = qs.first()
                    result = {
                        "status": "success",
                        "count": count,
                        "product": m.price.product.name,
                        "valid": m.is_valid(),
                        "membership_status": m.status,
                        "custom_form": m.custom_form
                    }
                else:
                    result = {"status": "not_found", "message": f"No membership found for {email}"}
            
            elif check_type == 'tokens':
                # Vérification des jetons (wallet)
                # Wallet/Tokens verification
                try:
                    user = TibilletUser.objects.get(email=email)
                    wallet = user.wallet
                    
                    from fedow_connect.fedow_api import FedowAPI
                    api = FedowAPI()
                    balance = api.wallet.get_total_fiducial_and_all_federated_token(wallet)
                    
                    result = {
                        "status": "success",
                        "email": email,
                        "has_wallet": bool(wallet),
                        "balance": balance
                    }
                except TibilletUser.DoesNotExist:
                    result = {"status": "not_found", "message": "User not found"}
                except Exception as e:
                    result = {"status": "error", "message": str(e)}

            self.stdout.write(json.dumps(result, indent=2))

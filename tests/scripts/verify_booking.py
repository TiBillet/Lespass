import sys
import json
from django_tenants.utils import schema_context
from BaseBillet.models import Event, Ticket, Reservation

def verify_booking(email, event_name=None):
    with schema_context('lespass'):
        qs = Reservation.objects.filter(user_commande__email=email)
        if event_name:
            qs = qs.filter(event__name=event_name)
        
        res = qs.first()
        if not res:
            return {"status": "not_found"}
        
        tickets = Ticket.objects.filter(reservation=res)
        return {
            "status": "found",
            "reservation_uuid": str(res.uuid),
            "event": res.event.name,
            "tickets_count": tickets.count(),
            "amount": float(res.total_amount() if hasattr(res, 'total_amount') else 0)
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Email required"}))
        sys.exit(1)
    
    email = sys.argv[1]
    event_name = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(verify_booking(email, event_name)))

import sys
import json
from django_tenants.utils import schema_context
from AuthBillet.models import TibilletUser

def get_balance(email):
    with schema_context('lespass'):
        try:
            user = TibilletUser.objects.get(email=email)
            wallet = user.wallet
            # Fedow tokens balance
            from fedow_connect.fedow_api import FedowAPI
            api = FedowAPI()
            balance = api.wallet.get_total_fiducial_and_all_federated_token(wallet)
            
            # Detailed assets if possible
            assets = []
            # This depends on how the wallet stores different assets, 
            # usually it involves calling Fedow API for a list.
            
            return {
                "status": "found",
                "email": email,
                "balance_cents": balance,
            }
        except TibilletUser.DoesNotExist:
            return {"status": "user_not_found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Email required"}))
        sys.exit(1)
    
    email = sys.argv[1]
    print(json.dumps(get_balance(email)))

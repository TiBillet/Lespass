import sys
import json
from django_tenants.utils import schema_context
from BaseBillet.models import Membership

def verify_membership(email, product_name=None):
    with schema_context('lespass'):
        qs = Membership.objects.filter(user__email=email)
        if product_name:
            qs = qs.filter(price__product__name=product_name)
        
        m = qs.first()
        if not m:
            return {"status": "not_found"}
        
        return {
            "status": "found",
            "product": m.price.product.name,
            "price_name": m.price.name,
            "deadline": str(m.deadline),
            "valid": m.deadline >= m.date_start if m.deadline else False
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Email required"}))
        sys.exit(1)
    
    email = sys.argv[1]
    product_name = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(verify_membership(email, product_name)))

from django_tenants.utils import schema_context
from BaseBillet.models import Product, Price
with schema_context('lespass'):
    p = Product.objects.get(name='Caisse de sécurité sociale alimentaire')
    pr = Price.objects.get(product=p, name='Souscription mensuelle')
    print(f"Recurring payment: {pr.recurring_payment}")
    print(f"Manual validation: {pr.manual_validation}")
    print(f"Subscription type: {pr.subscription_type}")

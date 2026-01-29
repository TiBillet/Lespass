import os
import django

def list_products():
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product
    
    with schema_context('lespass'):
        products = Product.objects.filter(categorie_article='A')
        print(f"Total memberships in 'lespass': {products.count()}")
        for p in products:
            print(f"Name: '{p.name}', UUID: {p.uuid}")

if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
    django.setup()
    list_products()

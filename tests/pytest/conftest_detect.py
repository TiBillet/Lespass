"""Plugin pytest qui check l'état de la Configuration lespass après chaque test."""
import pytest

def pytest_runtest_teardown(item, nextitem):
    try:
        from django_tenants.utils import tenant_context
        from Customers.models import Client
        from BaseBillet.models import Configuration
        tenant = Client.objects.get(schema_name='lespass')
        with tenant_context(tenant):
            count = Configuration.objects.filter(pk=1).count()
            if count == 0:
                import sys
                print(f"\n*** CONFIG LESPASS VIDE APRES : {item.nodeid} ***", flush=True, file=sys.stderr)
    except Exception as e:
        pass

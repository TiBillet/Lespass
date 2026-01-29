from django_tenants.utils import schema_context
from BaseBillet.models import Membership, Tva
with schema_context('lespass'):
    # Let's check why 'valid' is False even after admin check
    m = Membership.objects.filter(price__product__name='Adhésion à validation sélective').latest('date_start')
    print(f"Membership: {m.user.email} | Validated: {m.validated} | Valid method: {m.is_valid()}")
    # Check if there is a 'validated' field vs 'valid' logic
    for f in m._meta.fields:
        if 'valid' in f.name:
            print(f"  {f.name}: {getattr(m, f.name)}")

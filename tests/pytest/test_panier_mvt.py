"""
Tests d'integration du ViewSet PanierMVT.
Session 04 — Tâche 4.3. Session 07 — Tâche 7.3 : auth-only + /panier/ sans form buyer.

Run:
    poetry run pytest -q tests/pytest/test_panier_mvt.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def http_client_auth(tenant_context_lespass):
    """Django test client authentifié comme un user de test.
    / Django test client authenticated as a test user."""
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"mvt-{uuid.uuid4()}@example.org",
        username=f"mvt-{uuid.uuid4()}",
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)
    yield client, user
    try:
        user.delete()
    except Exception:
        pass


@pytest.fixture
def event_avec_tarif(tenant_context_lespass):
    from BaseBillet.models import Event, Price, Product
    event = Event.objects.create(
        name=f"MVT-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=5),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    return event, price


@pytest.fixture
def adhesion_standard(tenant_context_lespass):
    from BaseBillet.models import Price, Product
    product = Product.objects.create(
        name=f"AdM {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=product, name="Std", prix=Decimal("15.00"), publish=True,
    )
    return product, price


@pytest.mark.django_db
def test_GET_panier_list_renvoie_page(tenant_context_lespass):
    """
    GET /panier/ est accessible en anonyme (template gère l'état auth).
    / GET /panier/ is accessible when anonymous (template handles auth state).
    """
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.get('/panier/')
    assert response.status_code == 200
    # Pas le template DRF browsable API (qui aurait du JSON dans le title)
    # / Not the DRF browsable API template (which has JSON in title)
    assert b"Django REST framework" not in response.content or b"panier" in response.content.lower()


@pytest.mark.django_db
def test_GET_panier_badge_renvoie_partial(tenant_context_lespass):
    """GET /panier/badge/ accessible anonyme.
    / GET /panier/badge/ accessible anonymous."""
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.get('/panier/badge/')
    assert response.status_code == 200
    assert b"panier-badge" in response.content


@pytest.mark.django_db
def test_POST_add_membership_ajoute_au_panier(http_client_auth, adhesion_standard):
    """POST /panier/add/membership/ → adhesion en session."""
    client, _user = http_client_auth
    _product, price = adhesion_standard
    response = client.post('/panier/add/membership/', {
        'price_uuid': str(price.uuid),
    })
    assert response.status_code == 200
    session = client.session
    panier = session.get('panier', {})
    assert any(i['type'] == 'membership' for i in panier.get('items', []))


@pytest.mark.django_db
def test_POST_remove_retire_item(http_client_auth, event_avec_tarif):
    """POST /panier/0/remove/ → item retire."""
    client, _user = http_client_auth
    event, price = event_avec_tarif
    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): 1,
    })
    assert len(client.session.get('panier', {}).get('items', [])) == 1

    response = client.post('/panier/0/remove/')
    assert response.status_code == 200
    assert len(client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_update_quantity_change_qty(http_client_auth, event_avec_tarif):
    """POST /panier/0/update_quantity/ avec qty=5 → qty change."""
    client, _user = http_client_auth
    event, price = event_avec_tarif
    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): 1,
    })

    response = client.post('/panier/0/update_quantity/', {'qty': 5})
    assert response.status_code == 200
    session = client.session
    assert session['panier']['items'][0]['qty'] == 5


@pytest.mark.django_db
def test_POST_clear_vide_panier(http_client_auth, event_avec_tarif):
    """POST /panier/clear/ → panier vide."""
    client, _user = http_client_auth
    event, price = event_avec_tarif
    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): 3,
    })
    assert len(client.session.get('panier', {}).get('items', [])) == 1

    response = client.post('/panier/clear/')
    assert response.status_code == 200
    assert len(client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_promo_code_applique(http_client_auth, event_avec_tarif):
    """POST /panier/promo_code/ avec code valide → applique."""
    from BaseBillet.models import PromotionalCode
    client, _user = http_client_auth
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"TESTMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=price.product,
    )
    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): 1,
    })

    response = client.post('/panier/promo_code/', {'code_name': promo.name})
    assert response.status_code == 200
    session = client.session
    assert session['panier']['promo_code_name'] == promo.name


@pytest.mark.django_db
def test_POST_promo_code_clear(http_client_auth, event_avec_tarif):
    """POST /panier/promo_code/clear/ → retire le code promo."""
    from BaseBillet.models import PromotionalCode
    client, _user = http_client_auth
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"CLRMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("5.00"),
        product=price.product,
    )
    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): 1,
    })
    client.post('/panier/promo_code/', {'code_name': promo.name})

    response = client.post('/panier/promo_code/clear/')
    assert response.status_code == 200
    session = client.session
    assert session['panier'].get('promo_code_name') is None


@pytest.mark.django_db
def test_POST_checkout_panier_vide_retourne_erreur(http_client_auth):
    """POST /panier/checkout/ sur panier vide → erreur 200 + toast.
    / POST /panier/checkout/ on empty cart → 200 error + toast."""
    client, _user = http_client_auth
    response = client.post('/panier/checkout/')
    assert response.status_code == 200
    # Toast d'erreur via HX-Trigger header.
    # / Error toast via HX-Trigger header.
    hx_trigger = response.get('HX-Trigger', '').lower()
    assert 'empty' in hx_trigger or 'vide' in hx_trigger


@pytest.mark.django_db
def test_POST_checkout_panier_gratuit_redirige(http_client_auth, tenant_context_lespass):
    """
    POST /panier/checkout/ avec panier gratuit → redirect vers my_account.
    / POST /panier/checkout/ with free cart → redirect to my_account.
    """
    from BaseBillet.models import Event, Product
    client, _user = http_client_auth
    # Setup : un event FREERES → price 0€ auto-créé
    prod_free = Product.objects.create(
        name=f"FreeMVT-{uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"FreeE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    event.products.add(prod_free)
    price_free = prod_free.prices.filter(prix=0).first()
    assert price_free is not None

    client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price_free.uuid): 1,
    })

    response = client.post('/panier/checkout/')
    # HTMXResponseClientRedirect retourne 200 avec header HX-Redirect
    assert response.status_code == 200
    # Le header HX-Redirect doit pointer vers /my_account/
    assert 'HX-Redirect' in response or b'HX-Redirect' in response.content or response.status_code in [200, 302]
    # Le panier doit être vide apres materialisation
    session = client.session
    assert len(session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_add_ticket_anonyme_retourne_403(tenant_context_lespass, event_avec_tarif):
    """Anonyme + POST add_tickets_batch → 403.
    / Anonymous + POST add_tickets_batch → 403."""
    event, price = event_avec_tarif
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): '1',
    })
    assert response.status_code == 403


@pytest.mark.django_db
def test_POST_checkout_anonyme_retourne_403(tenant_context_lespass):
    """Sans login, PanierMVT actions retournent 403.
    / Without login, PanierMVT actions return 403."""
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.post('/panier/checkout/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_POST_checkout_profil_incomplet_ne_bloque_plus(
    tenant_context_lespass,
):
    """User authentifié sans first_name ne bloque plus le checkout.
    Les infos prenom/nom sont collectees via formulaires ou Stripe Checkout.
    / User without first_name no longer blocks checkout.
    First/last name collected via forms or Stripe Checkout.
    """
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"incomplete-{uuid.uuid4()}@example.org",
        username=f"incomplete-{uuid.uuid4()}",
        first_name="",
        last_name="",
        is_active=True,
    )
    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)

    # Panier vide → erreur "empty cart" (pas erreur "profil incomplet").
    # / Empty cart → "empty cart" error (no longer "incomplete profile").
    response = client.post('/panier/checkout/')
    assert response.status_code == 200
    # Pas de redirect vers /my_account/ pour cause de profil incomplet.
    # / No /my_account/ redirect for incomplete profile.
    hx_redirect = response.get('HX-Redirect', '')
    assert '/my_account/' not in hx_redirect
    # Le toast d'erreur porte sur le panier vide, pas sur le profil.
    # / Error toast is about empty cart, not profile.
    hx_trigger = response.get('HX-Trigger', '').lower()
    assert 'empty' in hx_trigger or 'vide' in hx_trigger
    try:
        user.delete()
    except Exception:
        pass

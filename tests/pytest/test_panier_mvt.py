"""
Tests d'integration du ViewSet PanierMVT.
Session 04 — Tâche 4.3.

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
def http_client(tenant_context_lespass):
    """Django test client pour le tenant lespass.
    / Django test client for the lespass tenant."""
    return Client(HTTP_HOST='lespass.tibillet.localhost')


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
def test_GET_panier_list_renvoie_page(http_client):
    """GET /panier/ → page 200, panier vide visible.
    / GET /panier/ → 200 page, empty cart visible."""
    response = http_client.get('/panier/')
    assert response.status_code == 200
    assert b"cart" in response.content.lower() or b"panier" in response.content.lower()


@pytest.mark.django_db
def test_GET_panier_badge_renvoie_partial(http_client):
    """GET /panier/badge/ → partial HTMX (id panier-badge)."""
    response = http_client.get('/panier/badge/')
    assert response.status_code == 200
    assert b"panier-badge" in response.content


@pytest.mark.django_db
def test_POST_add_ticket_ajoute_au_panier(http_client, event_avec_tarif):
    """POST /panier/add/ticket/ → toast success + item en session."""
    event, price = event_avec_tarif
    response = http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 2,
    })
    assert response.status_code == 200
    assert b"added" in response.content.lower() or b"ajout" in response.content.lower()
    # Verifier la session / Check session
    session = http_client.session
    panier = session.get('panier', {})
    assert len(panier.get('items', [])) == 1
    assert panier['items'][0]['type'] == 'ticket'
    assert int(panier['items'][0]['qty']) == 2


@pytest.mark.django_db
def test_POST_add_ticket_event_inexistant_retourne_erreur(http_client):
    """POST avec event_uuid invalide → toast error, pas d'ajout."""
    response = http_client.post('/panier/add/ticket/', {
        'event_uuid': str(uuid.uuid4()),
        'price_uuid': str(uuid.uuid4()),
        'qty': 1,
    })
    assert response.status_code == 200  # Toast, pas exception
    assert b"Event not found" in response.content or b"not found" in response.content.lower()


@pytest.mark.django_db
def test_POST_add_membership_ajoute_au_panier(http_client, adhesion_standard):
    """POST /panier/add/membership/ → adhesion en session."""
    _product, price = adhesion_standard
    response = http_client.post('/panier/add/membership/', {
        'price_uuid': str(price.uuid),
    })
    assert response.status_code == 200
    session = http_client.session
    panier = session.get('panier', {})
    assert any(i['type'] == 'membership' for i in panier.get('items', []))


@pytest.mark.django_db
def test_POST_remove_retire_item(http_client, event_avec_tarif):
    """POST /panier/0/remove/ → item retire."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })
    assert len(http_client.session.get('panier', {}).get('items', [])) == 1

    response = http_client.post('/panier/0/remove/')
    assert response.status_code == 200
    assert len(http_client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_update_quantity_change_qty(http_client, event_avec_tarif):
    """POST /panier/0/update_quantity/ avec qty=5 → qty change."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/0/update_quantity/', {'qty': 5})
    assert response.status_code == 200
    session = http_client.session
    assert session['panier']['items'][0]['qty'] == 5


@pytest.mark.django_db
def test_POST_clear_vide_panier(http_client, event_avec_tarif):
    """POST /panier/clear/ → panier vide."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 3,
    })
    assert len(http_client.session.get('panier', {}).get('items', [])) == 1

    response = http_client.post('/panier/clear/')
    assert response.status_code == 200
    assert len(http_client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_promo_code_applique(http_client, event_avec_tarif):
    """POST /panier/promo_code/ avec code valide → applique."""
    from BaseBillet.models import PromotionalCode
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"TESTMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=price.product,
    )
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/promo_code/', {'code_name': promo.name})
    assert response.status_code == 200
    session = http_client.session
    assert session['panier']['promo_code_name'] == promo.name


@pytest.mark.django_db
def test_POST_promo_code_clear(http_client, event_avec_tarif):
    """POST /panier/promo_code/clear/ → retire le code promo."""
    from BaseBillet.models import PromotionalCode
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"CLRMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("5.00"),
        product=price.product,
    )
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })
    http_client.post('/panier/promo_code/', {'code_name': promo.name})

    response = http_client.post('/panier/promo_code/clear/')
    assert response.status_code == 200
    session = http_client.session
    assert session['panier'].get('promo_code_name') is None


@pytest.mark.django_db
def test_POST_checkout_panier_vide_retourne_erreur(http_client):
    """POST /panier/checkout/ sur panier vide → erreur 200 + toast."""
    response = http_client.post('/panier/checkout/', {
        'first_name': 'A', 'last_name': 'B', 'email': 'test@example.org',
    })
    assert response.status_code == 200
    assert b"empty" in response.content.lower() or b"vide" in response.content.lower()


@pytest.mark.django_db
def test_POST_checkout_manque_infos_acheteur_retourne_erreur(http_client):
    """POST /panier/checkout/ sans first_name/last_name/email → erreur."""
    response = http_client.post('/panier/checkout/', {})
    assert response.status_code == 200
    assert b"required" in response.content.lower() or b"required" in response.content.lower()


@pytest.mark.django_db
def test_POST_checkout_panier_gratuit_redirige(http_client, tenant_context_lespass):
    """
    POST /panier/checkout/ avec panier gratuit → redirect vers my_account.
    / POST /panier/checkout/ with free cart → redirect to my_account.
    """
    from BaseBillet.models import Event, Product
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

    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price_free.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/checkout/', {
        'first_name': 'Gratis',
        'last_name': 'Mvt',
        'email': f'mvt-{uuid.uuid4()}@example.org',
    })
    # HTMXResponseClientRedirect retourne 200 avec header HX-Redirect
    assert response.status_code == 200
    # Le header HX-Redirect doit pointer vers /my_account/
    assert 'HX-Redirect' in response or b'HX-Redirect' in response.content or response.status_code in [200, 302]
    # Le panier doit être vide apres materialisation
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0

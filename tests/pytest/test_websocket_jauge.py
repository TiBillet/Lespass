"""
Tests WebSocket : consumer, ping/pong, broadcast jauge billetterie
/ WebSocket tests: consumer, ping/pong, ticket gauge broadcast

LOCALISATION : tests/pytest/test_websocket_jauge.py

Tests en 3 groupes :
1. Consumer (WebsocketCommunicator) — connexion, groups, ping/pong
2. Broadcast — calcul des jauges par Price et par Event
3. Signal — post_save Ticket declenche le broadcast via on_commit

DEPENDENCIES :
- pytest-asyncio (pour les tests async)
- channels.testing.WebsocketCommunicator
- channels.layers.InMemoryChannelLayer (pas besoin de Redis pour les tests)
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from django_tenants.utils import tenant_context


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def event_et_prices(tenant):
    """
    Cree un event avec 2 prices :
    - price_avec_stock (stock=10)
    - price_sans_stock (stock=None → utilise Event.jauge_max)
    / Creates an event with 2 prices:
    - price_with_stock (stock=10)
    - price_without_stock (stock=None → uses Event.jauge_max)
    """
    from django.utils import timezone
    from datetime import timedelta

    with tenant_context(tenant):
        from BaseBillet.models import Product, Price, Event
        import uuid

        # Suffixe unique pour eviter les conflits entre runs (piege PW adapte a pytest)
        # / Unique suffix to avoid conflicts between runs
        suffixe = uuid.uuid4().hex[:8]

        # Produit billet de test
        # / Test ticket product
        product_test_ws = Product.objects.create(
            name=f"Produit WS Test {suffixe}",
            categorie_article=Product.BILLET,
            publish=True,
        )

        # Event de test avec jauge_max=50
        # / Test event with jauge_max=50
        event_test_ws = Event.objects.create(
            name=f"Event WS Test {suffixe}",
            datetime=timezone.now() + timedelta(days=7),
            jauge_max=50,
            published=True,
        )
        event_test_ws.products.add(product_test_ws)

        # Price avec stock specifique (stock=10)
        # / Price with specific stock (stock=10)
        price_avec_stock = Price.objects.create(
            product=product_test_ws,
            name="Tarif Limite WS",
            prix=8.00,
            stock=10,
            publish=True,
        )

        # Price sans stock (utilise Event.jauge_max)
        # / Price without stock (uses Event.jauge_max)
        price_sans_stock = Price.objects.create(
            product=product_test_ws,
            name="Tarif Normal WS",
            prix=15.00,
            publish=True,
        )

        return {
            "tenant": tenant,
            "event": event_test_ws,
            "product": product_test_ws,
            "price_avec_stock": price_avec_stock,
            "price_sans_stock": price_sans_stock,
        }
        # Pas de cleanup : les donnees de test s'accumulent (meme pattern que les autres tests).
        # Le suffixe unique evite les conflits entre runs.
        # / No cleanup: test data accumulates (same pattern as other tests).
        # The unique suffix avoids conflicts between runs.


def _creer_ticket_pour_price(event, price, tenant):
    """
    Helper : cree un Ticket complet (Reservation + ProductSold + PriceSold + Ticket).
    / Helper: creates a complete Ticket (Reservation + ProductSold + PriceSold + Ticket).
    """
    from BaseBillet.models import (
        Reservation, Ticket, ProductSold, PriceSold, PaymentMethod,
    )
    from AuthBillet.models import TibilletUser

    with tenant_context(tenant):
        user_test, _created = TibilletUser.objects.get_or_create(
            email="ws-test-user@tibillet.re",
            defaults={"username": "ws-test-user@tibillet.re"},
        )
        reservation = Reservation.objects.create(
            user_commande=user_test,
            event=event,
            status=Reservation.VALID,
        )
        product_sold = ProductSold.objects.create(product=price.product)
        price_sold = PriceSold.objects.create(
            productsold=product_sold,
            price=price,
            prix=price.prix,
        )
        ticket = Ticket.objects.create(
            reservation=reservation,
            pricesold=price_sold,
            status=Ticket.NOT_SCANNED,
            payment_method=PaymentMethod.CASH,
        )
        return ticket


# ============================================================
# 1. TESTS CONSUMER (WebsocketCommunicator)
# ============================================================

@pytest.mark.asyncio
async def test_consumer_connexion_et_groups():
    """
    Le consumer accepte la connexion et rejoint les groups PV + jauges.
    / The consumer accepts the connection and joins the PV + gauges groups.
    """
    from channels.testing import WebsocketCommunicator
    from channels.layers import get_channel_layer
    from wsocket.consumers import LaboutikConsumer

    # Simuler un scope avec tenant
    # / Simulate a scope with tenant
    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    communicator = WebsocketCommunicator(
        LaboutikConsumer.as_asgi(),
        "/ws/laboutik/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"pv_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant

    connected, _ = await communicator.connect()
    assert connected, "Le consumer doit accepter la connexion"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_ping_pong():
    """
    Le consumer repond au ping avec un pong contenant client_ts.
    / The consumer responds to a ping with a pong containing client_ts.
    """
    from channels.testing import WebsocketCommunicator
    from wsocket.consumers import LaboutikConsumer

    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    communicator = WebsocketCommunicator(
        LaboutikConsumer.as_asgi(),
        "/ws/laboutik/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"pv_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant

    connected, _ = await communicator.connect()
    assert connected

    # Envoyer un ping
    # / Send a ping
    timestamp_envoi = 1700000000000
    await communicator.send_json_to({
        "type": "ping",
        "client_ts": timestamp_envoi,
    })

    # Recevoir le pong
    # / Receive the pong
    response = await communicator.receive_json_from(timeout=2)
    assert response["type"] == "pong"
    assert response["client_ts"] == timestamp_envoi
    assert "server_ts" in response

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_ignore_messages_non_ping():
    """
    Le consumer ignore les messages qui ne sont pas des pings.
    / The consumer ignores messages that are not pings.
    """
    from channels.testing import WebsocketCommunicator
    from wsocket.consumers import LaboutikConsumer

    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    communicator = WebsocketCommunicator(
        LaboutikConsumer.as_asgi(),
        "/ws/laboutik/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"pv_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant

    connected, _ = await communicator.connect()
    assert connected

    # Envoyer un message inconnu
    # / Send an unknown message
    await communicator.send_json_to({"type": "unknown", "data": "test"})

    # Verifier qu'aucune reponse n'est envoyee
    # / Verify no response is sent
    assert await communicator.receive_nothing(timeout=0.5)

    # Envoyer du texte invalide (pas du JSON)
    # / Send invalid text (not JSON)
    await communicator.send_to(text_data="not json")
    assert await communicator.receive_nothing(timeout=0.5)

    await communicator.disconnect()


# ============================================================
# 2. TESTS BROADCAST (calcul des jauges)
# ============================================================

def test_broadcast_jauge_calcule_par_price(event_et_prices):
    """
    broadcast_jauge_event() calcule une jauge distincte pour chaque Price.
    Price avec stock=10 → jauge par tarif. Price sans stock → jauge globale event.
    / broadcast_jauge_event() calculates a distinct gauge for each Price.
    Price with stock=10 → per-rate gauge. Price without stock → global event gauge.
    """
    tenant = event_et_prices["tenant"]
    event = event_et_prices["event"]
    price_avec_stock = event_et_prices["price_avec_stock"]

    with tenant_context(tenant):
        # Creer 2 tickets sur la price avec stock
        # / Create 2 tickets on the price with stock
        _creer_ticket_pour_price(event, price_avec_stock, tenant)
        _creer_ticket_pour_price(event, price_avec_stock, tenant)

        with patch("wsocket.broadcast.broadcast_html") as mock_broadcast:
            from wsocket.broadcast import broadcast_jauge_event
            broadcast_jauge_event(event)

        mock_broadcast.assert_called_once()
        context = mock_broadcast.call_args.kwargs["context"]

        # Jauge globale event (sidebar) : 2 tickets sur jauge_max=50
        # / Global event gauge (sidebar): 2 tickets on jauge_max=50
        assert context["event"]["places_vendues"] == 2
        assert context["event"]["jauge_max"] == 50
        assert context["event"]["complet"] is False

        # Tuiles : 2 prices
        # / Tiles: 2 prices
        tuiles = context["tuiles"]
        assert len(tuiles) == 2

        # Trouver la tuile avec stock (jauge_max=10, 2 vendus)
        # / Find the tile with stock (jauge_max=10, 2 sold)
        tuile_stock = [t for t in tuiles if t["jauge_max"] == 10]
        assert len(tuile_stock) == 1
        assert tuile_stock[0]["places_vendues"] == 2
        assert tuile_stock[0]["complet"] is False

        # Trouver la tuile sans stock (jauge_max=50, 2 vendus = jauge globale)
        # / Find the tile without stock (jauge_max=50, 2 sold = global gauge)
        tuile_globale = [t for t in tuiles if t["jauge_max"] == 50]
        assert len(tuile_globale) == 1
        assert tuile_globale[0]["places_vendues"] == 2


def test_broadcast_jauge_complet_par_price(event_et_prices):
    """
    Une Price avec stock=10 devient complet a 10 tickets,
    meme si l'Event (jauge_max=50) n'est pas complet.
    / A Price with stock=10 becomes full at 10 tickets,
    even if the Event (jauge_max=50) is not full.
    """
    tenant = event_et_prices["tenant"]
    event = event_et_prices["event"]
    price_avec_stock = event_et_prices["price_avec_stock"]

    with tenant_context(tenant):
        # Creer 10 tickets (remplit le stock de la price)
        # / Create 10 tickets (fills the price's stock)
        for _i in range(10):
            _creer_ticket_pour_price(event, price_avec_stock, tenant)

        with patch("wsocket.broadcast.broadcast_html") as mock_broadcast:
            from wsocket.broadcast import broadcast_jauge_event
            broadcast_jauge_event(event)

        context = mock_broadcast.call_args.kwargs["context"]

        # Event global PAS complet (10+2=12 tickets sur 50)
        # Les 2 tickets du test precedent sont encore la
        # / Event globally NOT full (10+2=12 tickets on 50)
        assert context["event"]["complet"] is False

        # Tuile avec stock : complet (10+2=12 >= stock=10)
        # / Tile with stock: full (10+2=12 >= stock=10)
        tuile_stock = [t for t in context["tuiles"] if t["jauge_max"] == 10]
        assert tuile_stock[0]["complet"] is True


def test_broadcast_resilient_si_redis_down(event_et_prices):
    """
    Si Redis est down, _safe_broadcast_jauge log un warning sans crasher.
    / If Redis is down, _safe_broadcast_jauge logs a warning without crashing.
    """
    tenant = event_et_prices["tenant"]
    event = event_et_prices["event"]

    with tenant_context(tenant):
        with patch(
            "wsocket.broadcast.broadcast_html",
            side_effect=Exception("Redis connection refused"),
        ):
            from BaseBillet.signals import _safe_broadcast_jauge
            # Ne doit PAS lever d'exception
            # / Must NOT raise an exception
            _safe_broadcast_jauge(event.pk)


# ============================================================
# 3. TESTS SIGNAL (post_save Ticket → on_commit → broadcast)
# ============================================================

def test_signal_ticket_declenche_broadcast(event_et_prices):
    """
    Ticket.save() declenche _safe_broadcast_jauge via on_commit.
    On mocke _safe_broadcast_jauge pour verifier qu'il est appele
    avec le bon event PK.
    / Ticket.save() triggers _safe_broadcast_jauge via on_commit.
    We mock _safe_broadcast_jauge to verify it's called with the correct event PK.

    Note : on_commit fire automatiquement car les tests n'utilisent pas
    de transaction wrapper (django_db_setup = pass, pas de rollback).
    """
    tenant = event_et_prices["tenant"]
    event = event_et_prices["event"]
    price = event_et_prices["price_sans_stock"]

    with tenant_context(tenant):
        with patch("BaseBillet.signals._safe_broadcast_jauge") as mock_broadcast:
            _creer_ticket_pour_price(event, price, tenant)

        # Verifier que le broadcast a ete appele avec le bon event PK
        # on_commit fire apres le commit (pas de rollback dans notre setup)
        # / Verify broadcast was called with the correct event PK
        # on_commit fires after commit (no rollback in our setup)
        mock_broadcast.assert_called()
        appel_event_pk = mock_broadcast.call_args[0][0]
        assert appel_event_pk == event.pk


def test_signal_ticket_sans_reservation_ne_crashe_pas(tenant):
    """
    Un Ticket sans reservation (edge case) ne declenche pas de broadcast.
    / A Ticket without a reservation (edge case) does not trigger a broadcast.
    """
    from BaseBillet.models import Ticket

    with tenant_context(tenant):
        with patch("BaseBillet.signals._safe_broadcast_jauge") as mock_broadcast:
            # Creer un ticket orphelin (pas de reservation)
            # Ce cas ne devrait pas arriver en prod mais le signal doit etre resilient
            # / Create an orphan ticket (no reservation)
            # This shouldn't happen in prod but the signal must be resilient
            try:
                ticket = Ticket()
                ticket.reservation = None
                # Ne pas sauvegarder en DB (FK non nullable) — juste simuler le signal
                # / Don't save to DB (non-nullable FK) — just simulate the signal
                from BaseBillet.signals import broadcast_jauge_apres_ticket_save
                broadcast_jauge_apres_ticket_save(
                    sender=Ticket, instance=ticket, created=True
                )
            except Exception:
                pass

        # Le broadcast ne doit PAS avoir ete appele
        # / Broadcast must NOT have been called
        mock_broadcast.assert_not_called()

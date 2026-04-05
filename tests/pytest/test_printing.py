"""
Tests du module d'impression LaBoutik.
Backends (Cloud, LAN, Inner), builder ESC/POS, formatters, dispatch.
/ Tests for the LaBoutik printing module.
Backends (Cloud, LAN, Inner), ESC/POS builder, formatters, dispatch.

LOCALISATION : tests/pytest/test_printing.py

Tous les tests mockent les appels HTTP et le channel layer Redis.
Pas besoin d'imprimante physique ni de serveur Daphne.
"""
import uuid as uuid_module
from unittest.mock import MagicMock, patch

import pytest
from django_tenants.utils import schema_context

from laboutik.models import Printer, LaboutikConfiguration


# --- Fixtures ---
# Les modeles laboutik sont dans TENANT_APPS → schema 'lespass' (pas 'public').
# / laboutik models are in TENANT_APPS → 'lespass' schema (not 'public').

TENANT_SCHEMA = 'lespass'


@pytest.fixture
def printer_cloud():
    """Cree une imprimante Sunmi Cloud avec un SN. / Creates a Sunmi Cloud printer with a SN."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Cuisine Cloud Test",
            printer_type=Printer.SUNMI_CLOUD,
            dots_per_line=576,
            sunmi_serial_number="N31TEST000001",
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def printer_cloud_sans_serial():
    """Imprimante Cloud sans numero de serie. / Cloud printer without serial number."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Cloud sans SN Test",
            printer_type=Printer.SUNMI_CLOUD,
            dots_per_line=576,
            sunmi_serial_number="",
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def printer_lan():
    """Cree une imprimante Sunmi LAN avec une IP. / Creates a Sunmi LAN printer with an IP."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Bar LAN Test",
            printer_type=Printer.SUNMI_LAN,
            dots_per_line=576,
            ip_address="192.168.1.100",
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def printer_lan_sans_ip():
    """Imprimante LAN sans adresse IP. / LAN printer without IP address."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="LAN sans IP Test",
            printer_type=Printer.SUNMI_LAN,
            dots_per_line=576,
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def printer_inner():
    """Cree une imprimante Sunmi Inner. / Creates a Sunmi Inner printer."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Tablette Inner Test",
            printer_type=Printer.SUNMI_INNER,
            dots_per_line=384,
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def ticket_data_simple():
    """Dict ticket_data minimal pour les tests. / Minimal ticket_data dict for tests."""
    return {
        "header": {
            "title": "TEST",
            "subtitle": "Sous-titre",
            "date": "24/03/2026 14:00",
        },
        "articles": [
            {"name": "Biere", "qty": 2, "price": 350, "total": 700},
            {"name": "Eau", "qty": 1, "price": 100, "total": 100},
        ],
        "total": {
            "amount": 800,
            "label": "Especes",
        },
        "qrcode": "https://example.com/test",
        "footer": ["Merci !"],
    }


# --- Tests SunmiCloudBackend.can_print ---


def test_sunmi_cloud_can_print_sans_serial(printer_cloud_sans_serial):
    """can_print retourne False si le numero de serie est vide."""
    from laboutik.printing.sunmi_cloud import SunmiCloudBackend
    backend = SunmiCloudBackend()
    with schema_context(TENANT_SCHEMA):
        ok, error = backend.can_print(printer_cloud_sans_serial)
    assert ok is False
    assert "serie" in error.lower() or "serial" in error.lower()


def test_sunmi_cloud_can_print_sans_credentials(printer_cloud):
    """can_print retourne False si les credentials Sunmi ne sont pas configurees."""
    from laboutik.printing.sunmi_cloud import SunmiCloudBackend
    backend = SunmiCloudBackend()

    with schema_context(TENANT_SCHEMA):
        # LaboutikConfiguration est un singleton — les champs sont vides par defaut
        # / LaboutikConfiguration is a singleton — fields are empty by default
        config = LaboutikConfiguration.get_solo()
        config.sunmi_app_id = None
        config.sunmi_app_key = None
        config.save()

        ok, error = backend.can_print(printer_cloud)
    assert ok is False
    assert "app id" in error.lower() or "App ID" in error


def test_sunmi_cloud_can_print_ok(printer_cloud):
    """can_print retourne True si SN + credentials sont configures."""
    from laboutik.printing.sunmi_cloud import SunmiCloudBackend
    from fedow_connect.utils import fernet_encrypt
    backend = SunmiCloudBackend()

    with schema_context(TENANT_SCHEMA):
        # Configurer les credentials
        # / Configure credentials
        config = LaboutikConfiguration.get_solo()
        config.sunmi_app_id = fernet_encrypt("test_app_id")
        config.sunmi_app_key = fernet_encrypt("test_app_key")
        config.save()

        ok, error = backend.can_print(printer_cloud)

        # Nettoyer / Cleanup
        config.sunmi_app_id = None
        config.sunmi_app_key = None
        config.save()

    assert ok is True
    assert error is None


# --- Tests SunmiLanBackend.can_print ---


def test_sunmi_lan_can_print_sans_ip(printer_lan_sans_ip):
    """can_print retourne False si l'adresse IP est vide."""
    from laboutik.printing.sunmi_lan import SunmiLanBackend
    backend = SunmiLanBackend()
    ok, error = backend.can_print(printer_lan_sans_ip)
    assert ok is False
    assert "ip" in error.lower()


def test_sunmi_lan_can_print_ok(printer_lan):
    """can_print retourne True si l'adresse IP est configuree."""
    from laboutik.printing.sunmi_lan import SunmiLanBackend
    backend = SunmiLanBackend()
    ok, error = backend.can_print(printer_lan)
    assert ok is True
    assert error is None


# --- Tests SunmiInnerBackend ---


def test_sunmi_inner_send_commands(printer_inner, ticket_data_simple):
    """print_ticket envoie les commandes JSON via le channel layer."""
    from laboutik.printing.sunmi_inner import SunmiInnerBackend

    # Mocker le channel layer pour intercepter l'appel group_send
    # / Mock the channel layer to intercept the group_send call
    mock_channel_layer = MagicMock()
    mock_channel_layer.group_send = MagicMock()

    with patch("laboutik.printing.sunmi_inner.get_channel_layer", return_value=mock_channel_layer):
        with patch("laboutik.printing.sunmi_inner.async_to_sync", side_effect=lambda f: f):
            backend = SunmiInnerBackend()
            result = backend.print_ticket(printer_inner, ticket_data_simple)

    assert result["ok"] is True
    # Verifier que group_send a ete appele avec le bon group name
    # / Verify group_send was called with the correct group name
    mock_channel_layer.group_send.assert_called_once()
    call_args = mock_channel_layer.group_send.call_args
    group_name = call_args[0][0]
    message = call_args[0][1]
    assert group_name == f"printer-{printer_inner.uuid}"
    assert message["type"] == "print.ticket"
    assert isinstance(message["commands"], list)
    assert len(message["commands"]) > 0


# --- Tests formatters ---


def test_formatter_ticket_vente():
    """formatter_ticket_vente retourne un dict avec la bonne structure."""
    from laboutik.printing.formatters import formatter_ticket_vente

    # Creer des mocks pour les LigneArticle
    # / Create mocks for LigneArticle objects
    ligne1 = MagicMock()
    ligne1.qty = 2
    ligne1.amount = 350
    ligne1.pricesold = MagicMock(__str__=lambda self: "Biere pression")

    ligne2 = MagicMock()
    ligne2.qty = 1
    ligne2.amount = 100
    ligne2.pricesold = MagicMock(__str__=lambda self: "Eau plate")

    pv = MagicMock()
    pv.name = "Bar Festival"

    operateur = MagicMock()
    operateur.email = "caissier@test.com"

    result = formatter_ticket_vente([ligne1, ligne2], pv, operateur, "Especes")

    assert "header" in result
    assert result["header"]["title"] == "Bar Festival"
    assert "articles" in result
    assert len(result["articles"]) == 2
    assert result["articles"][0]["qty"] == 2
    assert result["articles"][0]["total"] == 700
    assert result["total"]["amount"] == 800
    assert result["total"]["label"] == "Especes"
    assert result["qrcode"] is None
    assert isinstance(result["footer"], list)


def test_formatter_ticket_billet_avec_qrcode():
    """formatter_ticket_billet retourne un dict avec QR code = UUID du ticket."""
    from laboutik.printing.formatters import formatter_ticket_billet

    ticket_uuid = uuid_module.uuid4()
    qrcode_signe = "dGVzdA==:signature_test"

    ticket = MagicMock()
    ticket.uuid = ticket_uuid
    ticket.pricesold = MagicMock(__str__=lambda self: "Plein tarif")
    ticket.qrcode = MagicMock(return_value=qrcode_signe)

    reservation = MagicMock()
    reservation.user_commande = MagicMock()
    reservation.user_commande.email = "client@test.com"

    event = MagicMock()
    event.name = "Concert Jazz"
    event.datetime = None

    result = formatter_ticket_billet(ticket, reservation, event)

    assert result["header"]["title"] == "Concert Jazz"
    assert result["qrcode"] == qrcode_signe
    assert "client@test.com" in result["footer"]


# --- Tests MockBackend ---


@pytest.fixture
def printer_mock():
    """Cree une imprimante Mock pour les tests. / Creates a Mock printer for tests."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Console Test",
            printer_type=Printer.MOCK,
            dots_per_line=576,
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


def test_mock_pretty_print(printer_mock, ticket_data_simple, caplog):
    """Le MockBackend affiche un ticket ASCII dans les logs."""
    from laboutik.printing.mock import MockBackend
    backend = MockBackend()

    import logging
    with caplog.at_level(logging.INFO):
        result = backend.print_ticket(printer_mock, ticket_data_simple)

    assert result["ok"] is True
    # Verifier que le ticket ASCII est dans les logs
    # / Verify that the ASCII ticket is in the logs
    assert "╔" in caplog.text
    assert "╚" in caplog.text
    assert "TEST" in caplog.text
    assert "Biere" in caplog.text
    assert "7.00EUR" in caplog.text
    assert "TOTAL: 8.00 EUR" in caplog.text
    assert "[QR CODE:" in caplog.text


def test_mock_dispatch_via_imprimer(printer_mock, ticket_data_simple, caplog):
    """imprimer() dispatch correctement vers MockBackend."""
    from laboutik.printing import imprimer

    import logging
    with caplog.at_level(logging.INFO):
        with schema_context(TENANT_SCHEMA):
            result = imprimer(printer_mock, ticket_data_simple)

    assert result["ok"] is True
    assert "MOCK PRINTER" in caplog.text


# --- Tests ESC/POS builder ---


def test_build_escpos_contient_utf8_mode(ticket_data_simple):
    """Le builder active le mode UTF-8 (obligatoire pour les accents francais)."""
    from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

    escpos_bytes = build_escpos_from_ticket_data(576, ticket_data_simple)

    assert isinstance(escpos_bytes, bytes)
    assert len(escpos_bytes) > 0

    # La commande UTF-8 ON est : 1D 28 45 03 00 06 03 01
    # / The UTF-8 ON command is: 1D 28 45 03 00 06 03 01
    utf8_on_command = b'\x1d\x28\x45\x03\x00\x06\x03\x01'
    assert utf8_on_command in escpos_bytes


# --- Tests dispatch ---


def test_imprimer_dispatch_cloud(printer_cloud, ticket_data_simple):
    """imprimer() dispatch vers SunmiCloudBackend quand printer_type == SC."""
    from laboutik.printing import imprimer

    with schema_context(TENANT_SCHEMA):
        with patch("laboutik.printing.sunmi_cloud.SunmiCloudBackend.can_print", return_value=(True, None)):
            with patch("laboutik.printing.sunmi_cloud.SunmiCloudBackend.print_ticket", return_value={"ok": True}) as mock_print:
                result = imprimer(printer_cloud, ticket_data_simple)

    assert result["ok"] is True
    mock_print.assert_called_once_with(printer_cloud, ticket_data_simple)


# --- Tests Celery retry ---


def test_celery_retry_on_failure(printer_cloud, ticket_data_simple):
    """imprimer_async leve une exception quand le backend echoue (pour retry Celery)."""
    from laboutik.printing.tasks import imprimer_async

    # Mocker imprimer() pour retourner un echec
    # / Mock imprimer() to return a failure
    with patch("laboutik.printing.imprimer", return_value={"ok": False, "error": "Test error"}):
        with pytest.raises(Exception):
            # Appeler la tache directement (pas via .delay) pour tester le retry
            # / Call the task directly (not via .delay) to test retry
            imprimer_async(
                str(printer_cloud.pk),
                ticket_data_simple,
                TENANT_SCHEMA,
            )


# --- Tests DoesNotExist (pas de retry) ---


def test_imprimer_async_printer_inexistant(ticket_data_simple):
    """imprimer_async abandonne sans retry si l'imprimante n'existe plus."""
    from laboutik.printing.tasks import imprimer_async

    # UUID bidon — l'imprimante n'existe pas
    # / Fake UUID — printer does not exist
    fake_pk = str(uuid_module.uuid4())

    # Ne doit PAS lever d'exception (pas de retry)
    # / Should NOT raise (no retry)
    result = imprimer_async(fake_pk, ticket_data_simple, TENANT_SCHEMA)
    assert result is None


# --- Tests articles offerts (total=0 avec prix > 0) ---


def test_escpos_article_offert_affiche_zero():
    """Un article offert (price > 0, total = 0) affiche '0.00EUR', pas le format cuisine."""
    from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

    ticket_data = {
        "header": {"title": "Test", "subtitle": "", "date": ""},
        "articles": [
            {"name": "Biere offerte", "qty": 1, "price": 350, "total": 0},
        ],
        "total": {"amount": 0, "label": "Offert"},
        "qrcode": None,
        "footer": [],
    }
    escpos_bytes = build_escpos_from_ticket_data(576, ticket_data)
    # Decoder les bytes pour verifier le contenu
    # / Decode bytes to verify content
    texte = escpos_bytes.decode('utf-8', errors='ignore')

    # L'article offert doit afficher le format vente (avec prix) et non cuisine
    # / Free article should show sale format (with price), not kitchen format
    assert "0.00EUR" in texte
    assert "Biere offerte x1" in texte

    # Le total 0 doit etre affiche (pas masque)
    # / Total 0 should be displayed (not hidden)
    assert "TOTAL: 0.00 EUR" in texte


def test_escpos_article_cuisine_sans_prix():
    """Un article cuisine (price=0, total=0) affiche le format 'qty x nom'."""
    from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

    ticket_data = {
        "header": {"title": "CUISINE", "subtitle": "", "date": "14:30"},
        "articles": [
            {"name": "Burger", "qty": 2, "price": 0, "total": 0},
        ],
        "total": {},
        "qrcode": None,
        "footer": [],
    }
    escpos_bytes = build_escpos_from_ticket_data(576, ticket_data)
    texte = escpos_bytes.decode('utf-8', errors='ignore')

    # Format cuisine : "2 x Burger", pas de prix
    # / Kitchen format: "2 x Burger", no price
    assert "2 x Burger" in texte
    assert "EUR" not in texte


def test_escpos_article_avec_weight_detail():
    """Un article avec weight_detail affiche la sous-ligne de poids/volume."""
    from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

    ticket_data = {
        "header": {"title": "Point de vente", "subtitle": "", "date": ""},
        "articles": [
            {
                "name": "Comte AOP",
                "qty": 1,
                "price": 980,
                "total": 980,
                "weight_detail": "  350g x 28.00E/kg"
            },
        ],
        "total": {"amount": 980, "label": "Especes"},
        "qrcode": None,
        "footer": [],
    }
    escpos_bytes = build_escpos_from_ticket_data(576, ticket_data)
    texte = escpos_bytes.decode('utf-8', errors='ignore')

    # L'article doit afficher le format vente SANS qty (puisqu'on a weight_detail)
    # / Article should show sale format WITHOUT qty (since we have weight_detail)
    assert "Comte AOP" in texte
    assert "9.80EUR" in texte
    # La sous-ligne doit etre presente
    # / Sub-line should be present
    assert "350g x 28.00E/kg" in texte
    # On ne doit PAS afficher "x1" puisqu'on a weight_detail
    # / Should NOT show "x1" since we have weight_detail
    assert "Comte AOP x1" not in texte


# --- Tests SunmiLanBackend ---


def test_sunmi_lan_print_ticket_connection_error(printer_lan, ticket_data_simple):
    """SunmiLanBackend retourne erreur si l'imprimante est injoignable."""
    from laboutik.printing.sunmi_lan import SunmiLanBackend
    import requests

    backend = SunmiLanBackend()

    # Mocker requests.post pour simuler une imprimante injoignable
    # / Mock requests.post to simulate unreachable printer
    with patch("laboutik.printing.sunmi_lan.requests.post", side_effect=requests.ConnectionError("refused")):
        result = backend.print_ticket(printer_lan, ticket_data_simple)

    assert result["ok"] is False
    assert "injoignable" in result["error"].lower() or "refused" in result["error"].lower()


def test_sunmi_lan_print_ticket_ok(printer_lan, ticket_data_simple):
    """SunmiLanBackend retourne OK si le POST HTTP reussit."""
    from laboutik.printing.sunmi_lan import SunmiLanBackend

    backend = SunmiLanBackend()

    # Mocker requests.post pour simuler un succes
    # / Mock requests.post to simulate success
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("laboutik.printing.sunmi_lan.requests.post", return_value=mock_response):
        result = backend.print_ticket(printer_lan, ticket_data_simple)

    assert result["ok"] is True


# --- Tests formatter_ticket_commande ---


def test_formatter_ticket_commande():
    """formatter_ticket_commande retourne le bon format cuisine."""
    from laboutik.printing.formatters import formatter_ticket_commande

    commande = MagicMock()
    commande.uuid = uuid_module.uuid4()
    commande.table = MagicMock()
    commande.table.name = "Table 5"

    article1 = MagicMock()
    article1.product = MagicMock()
    article1.product.name = "Burger"
    article1.qty = 2

    article2 = MagicMock()
    article2.product = MagicMock()
    article2.product.name = "Frites"
    article2.qty = 1

    printer_mock_obj = MagicMock()
    printer_mock_obj.name = "CUISINE"

    result = formatter_ticket_commande(commande, [article1, article2], printer_mock_obj)

    assert result["header"]["title"] == "CUISINE"
    assert "Table 5" in result["header"]["subtitle"]
    assert len(result["articles"]) == 2
    assert result["articles"][0]["name"] == "Burger"
    assert result["articles"][0]["qty"] == 2
    assert result["articles"][0]["total"] == 0  # Pas de prix en cuisine
    assert result["qrcode"] is None


# --- Tests formatter_ticket_cloture ---


def test_formatter_ticket_cloture():
    """formatter_ticket_cloture retourne les totaux par moyen de paiement."""
    from laboutik.printing.formatters import formatter_ticket_cloture
    from django.utils import timezone

    now = timezone.now()

    cloture = MagicMock()
    cloture.point_de_vente = MagicMock()
    cloture.point_de_vente.name = "Bar"
    cloture.total_especes = 5000
    cloture.total_carte_bancaire = 15000
    cloture.total_cashless = 3000
    cloture.total_general = 23000
    cloture.nombre_transactions = 42
    cloture.datetime_ouverture = now
    cloture.datetime_cloture = now

    result = formatter_ticket_cloture(cloture)

    assert "CLOTURE" in result["header"]["title"]
    assert result["header"]["subtitle"] == "Bar"
    assert len(result["articles"]) == 3  # Especes, CB, Cashless
    assert result["total"]["amount"] == 23000
    assert "42" in result["total"]["label"]


# --- Tests PrinterConsumer auth ---


@pytest.mark.asyncio
async def test_printer_consumer_refuse_anonyme():
    """PrinterConsumer refuse la connexion si l'utilisateur n'est pas authentifie."""
    from channels.testing import WebsocketCommunicator
    from wsocket.consumers import PrinterConsumer

    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    communicator = WebsocketCommunicator(
        PrinterConsumer.as_asgi(),
        "/ws/printer/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"printer_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant
    # Pas d'utilisateur → AnonymousUser
    # / No user → AnonymousUser
    from django.contrib.auth.models import AnonymousUser
    communicator.scope["user"] = AnonymousUser()

    connected, _ = await communicator.connect()
    # La connexion est acceptee par Channels mais le consumer appelle close()
    # On verifie qu'aucun message n'est recu (le consumer a ferme)
    # / Connection is accepted by Channels but consumer calls close()
    # We verify no message is received (consumer closed)
    assert await communicator.receive_nothing(timeout=0.5) is True

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_printer_consumer_accepte_user_authentifie():
    """PrinterConsumer accepte la connexion si l'utilisateur est authentifie."""
    from channels.testing import WebsocketCommunicator
    from wsocket.consumers import PrinterConsumer

    mock_tenant = MagicMock()
    mock_tenant.schema_name = "lespass"

    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.email = "test@test.com"

    communicator = WebsocketCommunicator(
        PrinterConsumer.as_asgi(),
        "/ws/printer/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/",
    )
    communicator.scope["url_route"] = {
        "kwargs": {"printer_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    }
    communicator.scope["tenant"] = mock_tenant
    communicator.scope["user"] = mock_user

    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.disconnect()

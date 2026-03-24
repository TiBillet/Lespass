"""
Tests du bouton d'impression et du champ uuid_transaction.
/ Tests for the print button and uuid_transaction field.

LOCALISATION : tests/pytest/test_print_button.py

Pieges multi-tenant :
- Les modeles laboutik et BaseBillet sont dans TENANT_APPS → schema_context obligatoire.
- La DB de test est la DB dev existante (django_db_setup = pass).
- Nettoyer les objets crees dans les fixtures (yield + delete).
"""
import uuid as uuid_module
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django_tenants.utils import schema_context

from laboutik.models import Printer, PointDeVente

TENANT_SCHEMA = 'lespass'


# --- Fixtures ---


@pytest.fixture
def printer_mock_pour_bouton():
    """Imprimante mock pour tester le bouton d'impression.
    / Mock printer for testing the print button."""
    with schema_context(TENANT_SCHEMA):
        printer = Printer.objects.create(
            name="Mock Bouton Test",
            printer_type=Printer.MOCK,
            dots_per_line=576,
            active=True,
        )
    yield printer
    with schema_context(TENANT_SCHEMA):
        printer.delete()


@pytest.fixture
def pv_avec_imprimante(printer_mock_pour_bouton):
    """PV avec imprimante mock assignee.
    / POS with mock printer assigned."""
    with schema_context(TENANT_SCHEMA):
        pv = PointDeVente.objects.create(
            name="PV Test Impression",
            comportement=PointDeVente.DIRECT,
            printer=printer_mock_pour_bouton,
        )
    yield pv
    with schema_context(TENANT_SCHEMA):
        pv.delete()


@pytest.fixture
def pv_sans_imprimante():
    """PV sans imprimante.
    / POS without printer."""
    with schema_context(TENANT_SCHEMA):
        pv = PointDeVente.objects.create(
            name="PV Test Sans Imprimante",
            comportement=PointDeVente.DIRECT,
        )
    yield pv
    with schema_context(TENANT_SCHEMA):
        pv.delete()


# --- Tests uuid_transaction sur LigneArticle ---


def test_uuid_transaction_sur_lignearticle():
    """On peut filtrer les LigneArticle par uuid_transaction."""
    from BaseBillet.models import LigneArticle

    with schema_context(TENANT_SCHEMA):
        # Verifier que le champ existe et est filtrable
        # / Verify the field exists and is filterable
        uuid_test = uuid_module.uuid4()
        count = LigneArticle.objects.filter(uuid_transaction=uuid_test).count()
        assert count == 0


# --- Tests formatter billet avec QR code signe ---


def test_formatter_ticket_billet_qrcode_signe():
    """Le formatter utilise ticket.qrcode() (signe) quand disponible."""
    from laboutik.printing.formatters import formatter_ticket_billet

    ticket_uuid = uuid_module.uuid4()
    qrcode_signe = "dGVzdA==:signature_rsa_256"

    ticket = MagicMock()
    ticket.uuid = ticket_uuid
    ticket.pricesold = MagicMock(__str__=lambda self: "Plein tarif")
    ticket.qrcode = MagicMock(return_value=qrcode_signe)

    reservation = MagicMock()
    reservation.user_commande = MagicMock()
    reservation.user_commande.email = "test@test.com"

    event = MagicMock()
    event.name = "Concert"
    event.datetime = None

    result = formatter_ticket_billet(ticket, reservation, event)

    # Le QR code doit contenir la signature, pas l'UUID brut
    # / QR code should contain the signature, not raw UUID
    assert result["qrcode"] == qrcode_signe
    ticket.qrcode.assert_called_once()


def test_formatter_ticket_billet_qrcode_fallback():
    """Si ticket.qrcode() echoue, le formatter utilise l'UUID brut."""
    from laboutik.printing.formatters import formatter_ticket_billet

    ticket_uuid = uuid_module.uuid4()

    ticket = MagicMock()
    ticket.uuid = ticket_uuid
    ticket.pricesold = MagicMock(__str__=lambda self: "Tarif reduit")
    ticket.qrcode = MagicMock(side_effect=Exception("Pas de cle RSA"))

    reservation = MagicMock()
    reservation.user_commande = None

    event = MagicMock()
    event.name = "Festival"
    event.datetime = None

    result = formatter_ticket_billet(ticket, reservation, event)

    # Fallback vers l'UUID brut
    # / Fallback to raw UUID
    assert result["qrcode"] == str(ticket_uuid)


# --- Tests endpoint imprimer_ticket ---


def test_endpoint_imprimer_ticket_sans_imprimante(pv_sans_imprimante, admin_client):
    """POST imprimer_ticket sans imprimante → message warning."""
    from django.urls import reverse

    with schema_context(TENANT_SCHEMA):
        uuid_transaction = uuid_module.uuid4()
        url = reverse("laboutik-paiement-imprimer_ticket")
        response = admin_client.post(url, {
            "uuid_transaction": str(uuid_transaction),
            "uuid_pv": str(pv_sans_imprimante.uuid),
        })

    assert response.status_code == 200
    content = response.content.decode()
    assert "imprimante" in content.lower() or "printer" in content.lower()


def test_endpoint_imprimer_ticket_ok(pv_avec_imprimante, admin_client):
    """POST imprimer_ticket avec imprimante mock → tache Celery lancee."""
    from django.urls import reverse
    from BaseBillet.models import LigneArticle, ProductSold, PriceSold, Product, Price
    from decimal import Decimal

    with schema_context(TENANT_SCHEMA):
        # Creer une LigneArticle avec uuid_transaction
        # / Create a LigneArticle with uuid_transaction
        uuid_transaction = uuid_module.uuid4()

        # Recuperer un produit existant (cree par create_test_pos_data)
        # / Get an existing product (created by create_test_pos_data)
        product = Product.objects.filter(methode_caisse=Product.VENTE).first()
        if not product:
            pytest.skip("Pas de produit VENTE en base — lancer create_test_pos_data")

        price = Price.objects.filter(product=product).first()
        if not price:
            pytest.skip("Pas de Price pour le produit")

        product_sold, _ = ProductSold.objects.get_or_create(
            product=product, event=None,
            defaults={"categorie_article": product.categorie_article},
        )
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold, price=price,
            defaults={"prix": price.prix},
        )

        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=500,
            status=LigneArticle.VALID,
            uuid_transaction=uuid_transaction,
        )

        url = reverse("laboutik-paiement-imprimer_ticket")

        # Mocker imprimer_async.delay pour verifier l'appel sans broker Celery
        # / Mock imprimer_async.delay to verify the call without Celery broker
        with patch("laboutik.printing.tasks.imprimer_async.delay") as mock_delay:
            response = admin_client.post(url, {
                "uuid_transaction": str(uuid_transaction),
                "uuid_pv": str(pv_avec_imprimante.uuid),
            })

        assert response.status_code == 200
        content = response.content.decode()
        assert "print-confirmation" in content

        # Verifier que la tache Celery a ete appelee
        # / Verify that the Celery task was called
        mock_delay.assert_called_once()
        call_args = mock_delay.call_args
        printer_pk_arg = call_args[0][0]
        assert printer_pk_arg == str(pv_avec_imprimante.printer.pk)

        # Nettoyer / Cleanup
        ligne.delete()

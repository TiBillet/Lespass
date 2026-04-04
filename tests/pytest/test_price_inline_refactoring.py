"""
tests/pytest/test_price_inline_refactoring.py — Tests PriceInline StackedInline par proxy.
/ Tests for proxy-specific StackedInline PriceInlines.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()


from django_tenants.utils import schema_context

from BaseBillet.models import Product

TENANT_SCHEMA = 'lespass'


class TestPriceInlineSmoke:
    """Smoke tests : les 4 change pages admin chargent avec le formset Price.
    / Smoke tests: all 4 admin change pages load with the Price formset."""

    def test_product_change_page_has_price_formset(self, admin_client):
        """ProductAdmin change page contient le formset prices.
        / ProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.exclude(
                categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]
            ).first()
            assert product is not None, "Aucun Product en base"
            resp = admin_client.get(f'/admin/BaseBillet/product/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_ticketproduct_change_page_has_price_formset(self, admin_client):
        """TicketProductAdmin change page contient le formset prices.
        / TicketProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            # Le proxy model n'a pas de manager filtre — filtrer comme l'admin
            # / Proxy model has no filtered manager — filter like the admin does
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.FREERES]
            ).first()
            assert product is not None, "Aucun TicketProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/ticketproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_membershipproduct_change_page_has_price_formset(self, admin_client):
        """MembershipProductAdmin change page contient le formset prices.
        / MembershipProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article=Product.ADHESION
            ).first()
            assert product is not None, "Aucun MembershipProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/membershipproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_posproduct_change_page_has_price_formset(self, admin_client):
        """POSProductAdmin change page contient le formset prices.
        / POSProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                methode_caisse__isnull=False
            ).first()
            assert product is not None, "Aucun POSProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/posproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"


def _get_inline_fields(html):
    """Extrait les noms de champs du premier tarif inline (prices-0-*).
    / Extract field names from the first inline price (prices-0-*)."""
    import re
    # Cherche tous les name="prices-0-xxx" dans le HTML
    # / Find all name="prices-0-xxx" in the HTML
    matches = re.findall(r'name="prices-0-(\w+)"', html)
    # Deduplique et retire les champs Django internes
    # / Deduplicate and remove internal Django fields
    skip = {'id', 'product', 'uuid', 'DELETE'}
    return set(m for m in matches if m not in skip)


class TestTicketPriceInlineFields:
    """TicketPriceInline : stock, max_per_user, adhesions_obligatoires, free_price.
    Pas de : subscription_type, recurring_payment, iteration, commitment, contenance."""

    def test_ticket_fields_present(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.FREERES],
                prices__isnull=False,
            ).first()
            assert product is not None, "Aucun TicketProduct avec tarif en base"
            resp = admin_client.get(f'/admin/BaseBillet/ticketproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            # Champs attendus / Expected fields
            for f in ('name', 'prix', 'free_price', 'stock', 'max_per_user',
                      'adhesions_obligatoires', 'publish', 'order'):
                assert f in fields, f"Champ {f} absent de TicketPriceInline"

    def test_ticket_fields_absent(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.FREERES],
                prices__isnull=False,
            ).first()
            resp = admin_client.get(f'/admin/BaseBillet/ticketproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            # Champs interdits / Forbidden fields
            for f in ('subscription_type', 'recurring_payment', 'iteration',
                      'commitment', 'contenance'):
                assert f not in fields, f"Champ {f} ne devrait pas etre dans TicketPriceInline"


class TestMembershipPriceInlineFields:
    """MembershipPriceInline : subscription_type, recurring_payment, iteration,
    commitment, stock, max_per_user. Pas de : contenance, adhesions_obligatoires."""

    def test_membership_fields_present(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article=Product.ADHESION,
                prices__isnull=False,
            ).first()
            assert product is not None, "Aucun MembershipProduct avec tarif en base"
            resp = admin_client.get(f'/admin/BaseBillet/membershipproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('name', 'prix', 'free_price', 'subscription_type',
                      'recurring_payment', 'iteration', 'commitment',
                      'stock', 'max_per_user', 'publish', 'order'):
                assert f in fields, f"Champ {f} absent de MembershipPriceInline"

    def test_membership_fields_absent(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article=Product.ADHESION,
                prices__isnull=False,
            ).first()
            resp = admin_client.get(f'/admin/BaseBillet/membershipproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('contenance', 'adhesions_obligatoires'):
                assert f not in fields, f"Champ {f} ne devrait pas etre dans MembershipPriceInline"


class TestPOSPriceInlineFields:
    """POSPriceInline : contenance. Pas de : free_price, stock, max_per_user,
    subscription_type, recurring_payment, iteration, commitment, adhesions_obligatoires."""

    def test_pos_fields_present(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                methode_caisse__isnull=False,
                prices__isnull=False,
            ).first()
            assert product is not None, "Aucun POSProduct avec tarif en base"
            resp = admin_client.get(f'/admin/BaseBillet/posproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('name', 'prix', 'contenance', 'publish', 'order'):
                assert f in fields, f"Champ {f} absent de POSPriceInline"

    def test_pos_fields_absent(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                methode_caisse__isnull=False,
                prices__isnull=False,
            ).first()
            resp = admin_client.get(f'/admin/BaseBillet/posproduct/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('free_price', 'stock', 'max_per_user', 'subscription_type',
                      'recurring_payment', 'iteration', 'commitment',
                      'adhesions_obligatoires'):
                assert f not in fields, f"Champ {f} ne devrait pas etre dans POSPriceInline"


class TestBasePriceInlineFields:
    """BasePriceInline (ProductAdmin) : name, prix, free_price, publish, order.
    Pas de champs specialises."""

    def test_base_fields_present(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.ADHESION],
                prices__isnull=False,
            ).first()
            assert product is not None, "Aucun Product avec tarif en base"
            resp = admin_client.get(f'/admin/BaseBillet/product/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('name', 'prix', 'free_price', 'publish', 'order'):
                assert f in fields, f"Champ {f} absent de BasePriceInline"

    def test_base_fields_absent(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.ADHESION],
                prices__isnull=False,
            ).first()
            resp = admin_client.get(f'/admin/BaseBillet/product/{product.pk}/change/')
            fields = _get_inline_fields(resp.content.decode())
            for f in ('stock', 'max_per_user', 'contenance', 'subscription_type',
                      'recurring_payment', 'iteration', 'commitment',
                      'adhesions_obligatoires'):
                assert f not in fields, f"Champ {f} ne devrait pas etre dans BasePriceInline"

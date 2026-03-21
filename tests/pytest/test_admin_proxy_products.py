"""
tests/pytest/test_admin_proxy_products.py — Tests proxy admin TicketProduct / MembershipProduct.
tests/pytest/test_admin_proxy_products.py — Proxy admin tests for TicketProduct / MembershipProduct.

Converti depuis : tests/playwright/tests/admin/29-admin-proxy-products.spec.ts
Converted from: tests/playwright/tests/admin/29-admin-proxy-products.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_proxy_products.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest

from django_tenants.utils import schema_context

from BaseBillet.models import TicketProduct


TENANT_SCHEMA = 'lespass'


class TestAdminProxyProducts:
    """Tests des vues admin proxy pour produits billetterie et adhesion.
    / Tests for proxy admin views for ticket and membership products."""

    def test_ticketproduct_list(self, admin_client):
        """Liste TicketProduct accessible, au moins 1 produit en base.
        / TicketProduct list accessible, at least 1 product in DB."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/ticketproduct/')
            assert resp.status_code == 200
            count = TicketProduct.objects.count()
            assert count > 0, "TicketProduct doit avoir au moins 1 produit"

    def test_membershipproduct_list(self, admin_client):
        """Liste MembershipProduct accessible → 200.
        / MembershipProduct list accessible → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/membershipproduct/')
            assert resp.status_code == 200

    def test_ticketproduct_add_form_restricts_types(self, admin_client):
        """Formulaire ajout TicketProduct : contient value="B", pas value="A".
        / TicketProduct add form: contains value="B", not value="A"."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/ticketproduct/add/')
            assert resp.status_code == 200
            html = resp.content.decode()
            # Le formulaire doit proposer Billet (B) mais pas Adhesion (A)
            # / Form must offer Billet (B) but not Adhesion (A)
            assert 'value="B"' in html, "Billet (B) absent du formulaire"
            assert 'value="A"' not in html, "Adhesion (A) ne doit pas etre dans le formulaire ticket"

    def test_membershipproduct_add_form_forces_type(self, admin_client):
        """Formulaire ajout MembershipProduct : champ categorie hidden avec value="A".
        / MembershipProduct add form: hidden category field with value="A"."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/membershipproduct/add/')
            assert resp.status_code == 200
            html = resp.content.decode()
            # Le champ categorie doit etre hidden avec la valeur A
            # / The category field must be hidden with value A
            assert 'type="hidden"' in html, "Champ hidden absent"
            assert 'value="A"' in html, "Adhesion (A) absente du hidden field"

    def test_original_product_admin_accessible(self, admin_client):
        """L'admin Product original reste accessible → 200.
        / Original Product admin still accessible → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/product/')
            assert resp.status_code == 200

    def test_dashboard_has_proxy_links(self, admin_client):
        """Le dashboard admin contient des liens vers ticketproduct et membershipproduct
        quand les modules billetterie et adhesion sont actifs.
        / Admin dashboard contains links to ticketproduct and membershipproduct
        when ticketing and membership modules are active."""
        from BaseBillet.models import Configuration
        with schema_context(TENANT_SCHEMA):
            # Activer les modules pour que la sidebar affiche les liens
            # / Enable modules so the sidebar shows the links
            config = Configuration.get_solo()
            old_billetterie = config.module_billetterie
            old_adhesion = config.module_adhesion
            config.module_billetterie = True
            config.module_adhesion = True
            config.save()
            try:
                resp = admin_client.get('/admin/')
                assert resp.status_code == 200
                html = resp.content.decode()
                assert '/admin/BaseBillet/ticketproduct/' in html, "Lien ticketproduct absent"
                assert '/admin/BaseBillet/membershipproduct/' in html, "Lien membershipproduct absent"
            finally:
                # Restaurer l'etat original / Restore original state
                config.module_billetterie = old_billetterie
                config.module_adhesion = old_adhesion
                config.save()

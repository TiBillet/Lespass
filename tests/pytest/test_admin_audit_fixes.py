"""
tests/pytest/test_admin_audit_fixes.py — Smoke tests pages admin (Unfold).
tests/pytest/test_admin_audit_fixes.py — Admin page smoke tests (Unfold).

Verifie que chaque page admin renvoie 200 (pas 500).
Verifies each admin page returns 200 (not 500).

Converti depuis : tests/playwright/tests/admin/33-admin-audit-fixes.spec.ts
Converted from: tests/playwright/tests/admin/33-admin-audit-fixes.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_audit_fixes.py -v
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django_tenants.utils import schema_context


TENANT_SCHEMA = 'lespass'


class TestAdminPagesLoad:
    """Smoke tests — chaque page admin doit charger sans erreur 500.
    / Smoke tests — each admin page must load without 500 error."""

    def test_dashboard(self, admin_client):
        """Page d'accueil admin → 200.
        / Admin dashboard → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/')
            assert resp.status_code == 200, f"Dashboard: {resp.status_code}"

    def test_humanuser_changelist(self, admin_client):
        """Liste des utilisateurs (HumanUser) → 200.
        / User list (HumanUser) → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/AuthBillet/humanuser/')
            assert resp.status_code == 200, f"HumanUser list: {resp.status_code}"

    def test_paiement_stripe_changelist(self, admin_client):
        """Liste des paiements Stripe → 200.
        / Stripe payments list → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/paiement_stripe/')
            assert resp.status_code == 200, f"Paiement_stripe list: {resp.status_code}"

    def test_initiative_changelist(self, admin_client):
        """Liste des initiatives (crowds) → 200.
        / Initiatives list (crowds) → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/crowds/initiative/')
            assert resp.status_code == 200, f"Initiative list: {resp.status_code}"

    def test_humanuser_filter_client_admin(self, admin_client):
        """Filtre IsTenantAdmin sur HumanUser → 200.
        / IsTenantAdmin filter on HumanUser → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/AuthBillet/humanuser/?client_admin=Y')
            assert resp.status_code == 200, f"HumanUser filter client_admin: {resp.status_code}"

    def test_humanuser_filter_initiate_payment(self, admin_client):
        """Filtre CanInitPaiement sur HumanUser → 200.
        / CanInitPaiement filter on HumanUser → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/AuthBillet/humanuser/?initiate_payment=Y')
            assert resp.status_code == 200, f"HumanUser filter initiate_payment: {resp.status_code}"

    def test_event_changelist(self, admin_client):
        """Liste des evenements → 200.
        / Event list → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/event/')
            assert resp.status_code == 200, f"Event list: {resp.status_code}"

    def test_price_changelist(self, admin_client):
        """Liste des tarifs → 200.
        / Price list → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/price/')
            assert resp.status_code == 200, f"Price list: {resp.status_code}"

    def test_membership_changelist(self, admin_client):
        """Liste des adhesions → 200.
        / Membership list → 200."""
        with schema_context(TENANT_SCHEMA):
            resp = admin_client.get('/admin/BaseBillet/membership/')
            assert resp.status_code == 200, f"Membership list: {resp.status_code}"

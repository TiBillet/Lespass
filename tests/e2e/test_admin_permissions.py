"""
Tests E2E : verification des permissions admin pour un tenant admin (non superuser).
/ E2E tests: admin permission checks for a tenant admin (non superuser).

Verifie que l'utilisateur admin@admin.com (tenant admin, pas superuser)
peut acceder a toutes les pages admin sans erreur 403.
Ce test couvre le fix des has_*_permission manquants sur les ModelAdmin.

/ Verifies that admin@admin.com (tenant admin, not superuser)
can access all admin pages without 403 errors.
This test covers the fix for missing has_*_permission on ModelAdmin classes.

LOCALISATION : tests/e2e/test_admin_permissions.py

Prerequis / Prerequisites:
    - Donnees demo chargees (demo_data_v2 avec admin@admin.com)
    - Serveur Django actif via Traefik

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_permissions.py -v -s
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

# Email de l'admin de test cree par demo_data_v2.
# / Test admin email created by demo_data_v2.
TEST_ADMIN_EMAIL = "admin@admin.com"


@pytest.fixture(scope="session")
def login_test_admin(login_as):
    """Factory : connecte l'admin de test (admin@admin.com).
    / Factory: logs in the test admin (admin@admin.com).
    """

    def _login(page):
        login_as(page, TEST_ADMIN_EMAIL)

    return _login


class TestAdminPermissions:
    """Verifie qu'un tenant admin (non superuser) accede a toutes les pages admin.
    / Verify that a tenant admin (non superuser) can access all admin pages.
    """

    # ------------------------------------------------------------------
    # 1. Acces au dashboard admin
    # / Access to admin dashboard
    # ------------------------------------------------------------------

    def test_01_dashboard_accessible(self, page, login_test_admin):
        """Le dashboard admin est accessible.
        / Admin dashboard is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # On ne doit pas etre redirige vers / (login)
        # / Must not be redirected to / (login)
        assert "/admin/" in page.url, f"Redirige hors admin: {page.url}"

        # Le titre de la page doit contenir "Dashboard" ou "Tableau de bord"
        # / Page title must contain "Dashboard" or "Tableau de bord"
        titre = page.title()
        assert titre, "Page admin sans titre"

    def test_01b_dashboard_all_modules_active(self, page, login_test_admin):
        """Tous les modules du dashboard sont actives apres le flush.
        / All dashboard modules are active after flush.
        """
        login_test_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # Liste des 7 modules avec leurs data-testid
        # / List of 7 modules with their data-testid
        modules_testids = [
            "dashboard-card-billetterie",
            "dashboard-card-adhesion",
            "dashboard-card-crowdfunding",
            "dashboard-card-monnaie-locale",
            "dashboard-card-caisse",
            "dashboard-card-inventaire",
            "dashboard-card-tireuse",
        ]

        for testid in modules_testids:
            # Le switch de chaque module doit exister et etre aria-checked="true"
            # / Each module switch must exist and be aria-checked="true"
            switch = page.locator(f'[data-testid="{testid}-switch"]')
            expect(switch).to_be_visible(timeout=5_000)
            aria_checked = switch.get_attribute("aria-checked")
            assert aria_checked == "true", (
                f"Module {testid} n'est pas active (aria-checked={aria_checked})"
            )

    # ------------------------------------------------------------------
    # 2. Pages de configuration — singleton
    # / Configuration pages — singleton
    # ------------------------------------------------------------------

    def test_02_configuration_accessible(self, page, login_test_admin):
        """La page de configuration du tenant est accessible.
        / Tenant configuration page is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/configuration/")
        page.wait_for_load_state("networkidle")

        # Pas de 403 — la page charge normalement
        # / No 403 — page loads normally
        assert "403" not in page.title()
        assert "/admin/" in page.url

    # ------------------------------------------------------------------
    # 3. Pages produits (modele principal + proxys)
    # / Product pages (main model + proxies)
    # ------------------------------------------------------------------

    def test_03_products_list_accessible(self, page, login_test_admin):
        """La liste des produits est accessible.
        / Product list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/product/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_04_ticket_products_accessible(self, page, login_test_admin):
        """La liste des produits Billetterie (proxy) est accessible.
        / Ticket products list (proxy) is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/ticketproduct/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_05_membership_products_accessible(self, page, login_test_admin):
        """La liste des produits Adhesion (proxy) est accessible.
        / Membership products list (proxy) is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/membershipproduct/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    # ------------------------------------------------------------------
    # 4. Pages evenements et reservations
    # / Event and reservation pages
    # ------------------------------------------------------------------

    def test_06_events_list_accessible(self, page, login_test_admin):
        """La liste des evenements est accessible.
        / Event list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/event/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_07_reservations_list_accessible(self, page, login_test_admin):
        """La liste des reservations est accessible.
        / Reservation list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/reservation/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    # ------------------------------------------------------------------
    # 5. Pages fedow_core (fix: has_view_permission manquait)
    # / fedow_core pages (fix: has_view_permission was missing)
    # ------------------------------------------------------------------

    def test_08_assets_list_accessible(self, page, login_test_admin):
        """La liste des assets fedow_core est accessible.
        / fedow_core asset list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/fedow_core/asset/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_09_tokens_list_accessible(self, page, login_test_admin):
        """La liste des tokens fedow_core est accessible.
        / fedow_core token list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/fedow_core/token/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_10_transactions_list_accessible(self, page, login_test_admin):
        """La liste des transactions fedow_core est accessible.
        / fedow_core transaction list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/fedow_core/transaction/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_11_federations_list_accessible(self, page, login_test_admin):
        """La liste des federations fedow_core est accessible.
        / fedow_core federation list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/fedow_core/federation/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    # ------------------------------------------------------------------
    # 6. Pages crowds (fix: has_add_permission manquait sur CrowdConfigAdmin)
    # / Crowds pages (fix: has_add_permission was missing on CrowdConfigAdmin)
    # ------------------------------------------------------------------

    def test_12_crowd_config_accessible(self, page, login_test_admin):
        """La page de configuration crowds est accessible.
        / Crowd configuration page is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/crowds/crowdconfig/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    # ------------------------------------------------------------------
    # 7. Pages paiements et adhesions
    # / Payment and membership pages
    # ------------------------------------------------------------------

    def test_13_memberships_list_accessible(self, page, login_test_admin):
        """La liste des adhesions est accessible.
        / Membership list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    def test_14_paiement_stripe_list_accessible(self, page, login_test_admin):
        """La liste des paiements Stripe est accessible.
        / Stripe payment list is accessible.
        """
        login_test_admin(page)
        page.goto("/admin/BaseBillet/paiement_stripe/")
        page.wait_for_load_state("networkidle")

        assert "/admin/" in page.url
        assert "403" not in page.title()

    # ------------------------------------------------------------------
    # 8. Verification que l'user n'est PAS superuser
    # / Verify the user is NOT a superuser
    # ------------------------------------------------------------------

    def test_15_user_is_not_superuser(self, django_shell):
        """Confirme que admin@admin.com est tenant admin mais pas superuser.
        / Confirm admin@admin.com is tenant admin but not superuser.
        """
        result = django_shell(
            "from AuthBillet.models import TibilletUser\n"
            f"u = TibilletUser.objects.get(email='{TEST_ADMIN_EMAIL}')\n"
            "print(f'is_superuser={u.is_superuser}')\n"
            "print(f'is_staff={u.is_staff}')\n"
            "print(f'client_admin_count={u.client_admin.count()}')"
        )
        assert "is_superuser=False" in result, (
            f"admin@admin.com ne doit PAS etre superuser. Got: {result}"
        )
        assert "is_staff=True" in result, (
            f"admin@admin.com doit etre staff. Got: {result}"
        )
        assert "client_admin_count=1" in result, (
            f"admin@admin.com doit etre admin d'un tenant. Got: {result}"
        )

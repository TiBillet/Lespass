"""
Tests E2E : federation d'assets cross-tenant (Lespass ↔ Chantefrein).
/ E2E tests: cross-tenant asset federation (Lespass ↔ Chantefrein).

Conversion de tests/playwright/tests/admin/31-admin-asset-federation.spec.ts

Prérequis / Prerequisites:
- Tenants lespass et chantefrein existent
- Admin superuser (ADMIN_EMAIL) a accès aux deux
- module_monnaie_locale sera activé automatiquement si besoin
"""

import os
import random
import re
import string
from urllib.parse import quote

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
LESPASS_BASE = f"https://{SUB}.{DOMAIN}"
CHANTEFREIN_BASE = f"https://chantefrein.{DOMAIN}"


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=5))


def _login_on_tenant(page, base_url, admin_email):
    """Login manuel sur un tenant spécifique (URLs absolues).
    / Manual login on a specific tenant (absolute URLs).
    """
    page.goto(f"{base_url}/")
    page.wait_for_load_state("networkidle")

    login_button = page.locator(
        '.navbar button:has-text("Log in"), '
        '.navbar button:has-text("Connexion")'
    ).first
    expect(login_button).to_be_visible(timeout=10_000)
    login_button.click()

    email_input = page.locator("#loginEmail")
    expect(email_input).to_be_visible(timeout=5_000)
    email_input.fill(admin_email)

    submit_button = page.locator('#loginForm button[type="submit"]')
    submit_button.click()

    test_mode_link = page.locator('a:has-text("TEST MODE")')
    test_mode_link.wait_for(state="visible", timeout=10_000)
    test_mode_link.click()
    page.wait_for_load_state("networkidle")


class TestAssetFederation:
    """Federation d'assets cross-tenant / Cross-tenant asset federation."""

    def test_full_per_asset_invitation_flow(
        self, page, login_as_admin, admin_email, django_shell
    ):
        """Flow complet : créer asset sur Lespass, inviter Chantefrein,
        accepter l'invitation, vérifier la fédération des deux côtés.
        / Full flow: create asset on Lespass, invite Chantefrein,
        accept invitation, verify federation on both sides.
        """
        run_id = _random_id()
        asset_name = f"PW Test Fed {run_id}"

        # --- Setup : activer module_monnaie_locale sur chantefrein ---
        django_shell(
            "from BaseBillet.models import Configuration\n"
            "c = Configuration.get_solo()\n"
            "c.module_monnaie_locale = True\n"
            "c.save(update_fields=['module_monnaie_locale'])\n"
            "print(f'OK module_monnaie_locale={c.module_monnaie_locale}')",
            schema="chantefrein",
        )

        # --- Étape 1 : Login admin sur Lespass ---
        login_as_admin(page)

        # --- Étape 2 : Naviguer vers la changelist Asset ---
        page.goto("/admin/fedow_core/asset/")
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(re.compile(r"/admin/fedow_core/asset/"))

        # --- Étape 3 : Créer un nouvel asset ---
        add_button = page.locator('a[href$="/admin/fedow_core/asset/add/"]').first
        add_button.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(re.compile(r"/admin/fedow_core/asset/add/"))

        page.locator('input[name="name"]').fill(asset_name)
        page.locator('input[name="currency_code"]').fill("EUR")
        page.locator('select[name="category"]').select_option("TLF")

        page.locator('input[name="_save"], button[name="_save"]').click()
        page.wait_for_load_state("networkidle")

        # --- Étape 4 : Éditer l'asset → inviter Chantefrein via Tom Select ---
        page.goto(f"/admin/fedow_core/asset/?q={quote(asset_name)}")
        page.wait_for_load_state("networkidle")

        asset_link = page.locator(f'#result_list a:has-text("{asset_name}")').first
        expect(asset_link).to_be_visible(timeout=10_000)
        asset_link.click()
        page.wait_for_load_state("networkidle")

        # Tom Select : chercher et sélectionner Chantefrein
        search_box = page.get_by_role("searchbox").last
        expect(search_box).to_be_visible(timeout=5_000)
        search_box.click()
        search_box.fill("Chantefrein")

        chantefrein_option = page.get_by_role("option", name=re.compile(r"Chantefrein", re.IGNORECASE)).first
        expect(chantefrein_option).to_be_visible(timeout=10_000)
        chantefrein_option.click()

        # Sauvegarder
        page.locator('input[name="_save"], button[name="_save"]').click()
        page.wait_for_load_state("networkidle")

        # --- Étape 5 : Vérifier changelist Lespass — Lespass seul dans "Lieux fédérés" ---
        page.goto(f"/admin/fedow_core/asset/?q={quote(asset_name)}")
        page.wait_for_load_state("networkidle")

        asset_row = page.locator(f'#result_list tr:has-text("{asset_name}")').first
        expect(asset_row).to_be_visible()
        row_text = asset_row.text_content()
        assert "Lespass" in row_text, f"Lespass absent de la ligne: {row_text[:100]}"
        assert "Chantefrein" not in row_text, (
            f"Chantefrein ne devrait pas être fédéré avant acceptation: {row_text[:100]}"
        )

        # --- Étapes 6-7 : Login sur Chantefrein (URLs absolues) ---
        _login_on_tenant(page, CHANTEFREIN_BASE, admin_email)

        # --- Étape 8 : Vérifier invitation visible sur Chantefrein ---
        page.goto(f"{CHANTEFREIN_BASE}/admin/fedow_core/asset/")
        page.wait_for_load_state("networkidle")

        invitations_panel = page.locator('[data-testid="asset-invitations-panel"]')
        expect(invitations_panel).to_be_visible(timeout=10_000)
        expect(invitations_panel.locator(f"text={asset_name}")).to_be_visible()

        # --- Étape 9 : Accepter l'invitation ---
        invitation_row = page.locator('[data-testid^="asset-invitation-"]').filter(
            has_text=asset_name
        )
        accept_button = invitation_row.locator('button[type="submit"]')
        expect(accept_button).to_be_visible(timeout=10_000)
        accept_button.click()
        page.wait_for_load_state("networkidle")

        # Vérifier le message de succès
        expect(page.get_by_text("Invitation acceptee")).to_be_visible(timeout=10_000)

        # --- Étape 10 : Vérifier asset dans changelist Chantefrein ---
        page.goto(
            f"{CHANTEFREIN_BASE}/admin/fedow_core/asset/?q={quote(asset_name)}"
        )
        page.wait_for_load_state("networkidle")

        asset_row_cf = page.locator(f'#result_list tr:has-text("{asset_name}")').first
        expect(asset_row_cf).to_be_visible(timeout=10_000)
        row_text_cf = asset_row_cf.text_content()
        assert "Lespass" in row_text_cf, f"Lespass absent chez Chantefrein: {row_text_cf[:100]}"
        assert "Chantefrein" in row_text_cf, f"Chantefrein absent chez Chantefrein: {row_text_cf[:100]}"

        # --- Étape 11 : Vérifier lecture seule pour Chantefrein ---
        asset_link_cf = page.locator(f'#result_list a:has-text("{asset_name}")').first
        asset_link_cf.click()
        page.wait_for_load_state("networkidle")

        save_button = page.locator(
            'input[name="_save"], button[name="_save"], '
            'input[name="_continue"], button[name="_continue"]'
        )
        if save_button.count() > 0:
            # Si le bouton existe, vérifier que les champs sont protégés
            name_field = page.locator('input[name="name"]')
            if name_field.count() > 0:
                is_disabled = name_field.is_disabled()
                is_readonly = name_field.get_attribute("readonly") is not None
                assert is_disabled or is_readonly, (
                    "Le champ name devrait être readonly/disabled pour Chantefrein"
                )

        # --- Étape 12 : Retour sur Lespass — vérifier fédération ---
        # La session Lespass est toujours active (cookies per-subdomain)
        page.goto(f"{LESPASS_BASE}/admin/fedow_core/asset/?q={quote(asset_name)}")
        page.wait_for_load_state("networkidle")

        asset_row_final = page.locator(f'#result_list tr:has-text("{asset_name}")').first
        expect(asset_row_final).to_be_visible(timeout=10_000)
        row_text_final = asset_row_final.text_content()
        assert "Lespass" in row_text_final, f"Lespass absent: {row_text_final[:100]}"
        assert "Chantefrein" in row_text_final, (
            f"Chantefrein absent après acceptation: {row_text_final[:100]}"
        )

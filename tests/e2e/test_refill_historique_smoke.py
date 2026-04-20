"""
Test E2E smoke : golden path Recharge FED V2 + tokens V2 + historique V2.
E2E smoke test: golden path FED refill V2 + tokens V2 + history V2.

LOCALISATION : tests/e2e/test_refill_historique_smoke.py

Couvre le flow user nominal de bout en bout, en un seul test, sur les
3 dernieres sessions livrees :

- Session 31 (Recharge FED V2) :
  * Clic chip 20 € -> preview + input mis a jour (fix bug #1)
  * Redirection Stripe reussie (fix bug #2 : plus de doublon Asset FED)
  * Retour atterrit sur /my_account/balance/ (fix : pas /my_account/)

- Session 32 (Tokens table V2) :
  * Assertion du sous-tableau tokens-v2-fiduciaires avec "TiBillets" +
    badge "Utilisable partout"

- Session 33 (Historique transactions V2) :
  * Clic "Historique des transactions" -> affichage du tableau V2
  * Ligne "Recharge" avec montant vert, asset "TiBillets", structure "TiBillet"

/ Covers the nominal user flow end-to-end, in a single test, across the
3 most recent sessions (31, 32, 33).

PREREQUIS :
- Serveur Django actif via Traefik
- Carte Stripe test : 4242 4242 4242 4242, 12/42, 424, Douglas Adams
- Tenant federation_fed + Asset FED crees (bootstrap_fed_asset)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_refill_historique_smoke.py -v -s
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestRefillHistoriqueSmoke:
    """Golden path smoke test / Test smoke flow nominal."""

    def test_smoke_golden_path_sessions_31_32_33(
        self, page, login_as_admin, fill_stripe_card, admin_email
    ):
        """
        Flow : login admin -> clic Recharger -> chip 20€ -> Stripe 4242 ->
        retour sur balance -> verif token FED -> clic Historique ->
        verif ligne Recharge V2.

        / Flow: admin login -> click Refill -> chip 20€ -> Stripe 4242 ->
        return to balance -> verify FED token -> click History ->
        verify V2 Refill row.

        Timeouts genereux (120s par defaut) : Stripe peut etre lent.
        / Generous timeouts (120s default): Stripe can be slow.
        """
        page.set_default_timeout(120_000)

        # === 1. Login admin + navigation balance ===
        # / 1. Admin login + balance navigation
        login_as_admin(page)
        page.goto("/my_account/balance/")
        page.wait_for_load_state("domcontentloaded")

        # === 2. Ouvrir le form de recharge (Session 31 UI V2) ===
        # / 2. Open refill form (Session 31 UI V2)
        refill_btn = page.locator('[data-testid="refill-btn-open"]').first
        expect(refill_btn).to_be_visible(timeout=30_000)
        refill_btn.click()

        # Le form V2 remplace la section tirelire via hx-swap="outerHTML".
        # / V2 form replaces the tirelire section via hx-swap="outerHTML".
        form_container = page.locator('[data-testid="refill-form-container"]')
        expect(form_container).to_be_visible(timeout=10_000)

        # === 3. Clic chip 20€ + verif preview + input (Session 31 bug #1 fix) ===
        # / 3. Click chip 20€ + verify preview + input (Session 31 bug #1 fix)
        chip_20 = page.locator('[data-testid="refill-chip-20"]')
        expect(chip_20).to_be_visible()
        chip_20.click()

        # Input "Autre montant" doit etre rempli a "20".
        # / "Other amount" input must be filled with "20".
        amount_input = page.locator('[data-testid="refill-input-amount"]')
        expect(amount_input).to_have_value("20")

        # Preview grand affichage doit montrer "20".
        # / Big amount preview must show "20".
        preview = page.locator("#refill-amount-preview")
        expect(preview).to_have_text("20")

        # === 4. Clic Payer -> redirection Stripe (Session 31 bug #2 fix) ===
        # / 4. Click Pay -> Stripe redirection (Session 31 bug #2 fix)
        submit_btn = page.locator('[data-testid="refill-btn-submit"]')
        expect(submit_btn).to_be_enabled()
        submit_btn.click()

        # Redirection vers checkout.stripe.com.
        # / Redirect to checkout.stripe.com.
        page.wait_for_url(
            re.compile(r"checkout\.stripe\.com"),
            timeout=30_000,
        )
        # domcontentloaded plutot que networkidle : Stripe maintient des
        # connexions persistantes qui empechent networkidle de resoudre.
        # / domcontentloaded over networkidle: Stripe keeps persistent
        # connections that prevent networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")

        # === 5. Remplir la carte Stripe 4242 ===
        # / 5. Fill Stripe card 4242
        fill_stripe_card(page, admin_email)

        stripe_submit = page.locator('button[type="submit"]').first
        expect(stripe_submit).to_be_enabled(timeout=30_000)
        stripe_submit.click()

        # === 6. Retour sur /my_account/balance/ (fix Session 31 retour) ===
        # Avant le fix : on atterrissait sur /my_account/. Maintenant :
        # directement sur /my_account/balance/ pour voir sa tirelire.
        # / 6. Return to /my_account/balance/ (Session 31 fix).
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url
                        and "/my_account/balance/" in url,
            timeout=60_000,
        )
        page.wait_for_load_state("domcontentloaded")

        # === 7. Verif Tokens Table V2 (Session 32) ===
        # Le tableau tokens est charge via HTMX `hx-trigger="revealed"`
        # (chargement lazy au scroll). On scroll jusqu'a l'ancre
        # #detail-monnaies pour declencher le trigger.
        # / 7. Verify Tokens Table V2 (Session 32)
        # The tokens table is lazily loaded via HTMX `hx-trigger="revealed"`.
        # Scroll to #detail-monnaies to trigger the load.
        page.locator("#detail-monnaies").scroll_into_view_if_needed()

        fiduciaires_table = page.locator('[data-testid="tokens-v2-fiduciaires"]')
        expect(fiduciaires_table).to_be_visible(timeout=15_000)
        expect(fiduciaires_table).to_contain_text("TiBillets")
        # Badge "Utilisable partout" (FR) ou "Usable everywhere" (EN)
        # selon la locale active en test.
        # / "Utilisable partout" (FR) or "Usable everywhere" (EN).
        expect(fiduciaires_table).to_contain_text(
            re.compile(r"Utilisable partout|Usable everywhere")
        )

        # === 8. Clic "Historique des transactions" ===
        # Bouton de la page balance.html qui fait hx-get /transactions_table/
        # et swap la section #transactionHistory.
        # / 8. Click "Transaction history"
        historique_btn = page.locator(
            'a[hx-get="/my_account/transactions_table/"]'
        ).first
        historique_btn.scroll_into_view_if_needed()
        historique_btn.click()

        # === 9. Verif section V2 historique (Session 33) ===
        # Le conteneur V2 (data-testid="tx-v2-container") remplace le
        # bouton via hx-swap="outerHTML" sur #transactionHistory.
        # / 9. Verify V2 history section (Session 33)
        tx_container = page.locator('[data-testid="tx-v2-container"]')
        expect(tx_container).to_be_visible(timeout=15_000)

        # La table V2 doit etre rendue (pas l'empty state).
        # / V2 table must be rendered (not empty state).
        tx_table = page.locator('[data-testid="tx-v2-table"]')
        expect(tx_table).to_be_visible()

        # === 10. Verif ligne Recharge (la plus recente) ===
        # Apres une recharge fraiche, il y a au moins 1 ligne.
        # La 1ere ligne (tri desc) doit etre la recharge qu'on vient de faire.
        # / 10. Verify latest Refill row.
        tx_rows = page.locator('[data-testid="tx-v2-row"]')
        assert tx_rows.count() >= 1, (
            "Au moins 1 ligne attendue apres recharge / "
            "At least 1 row expected after refill"
        )

        premiere_ligne = tx_rows.first

        # Action = "Recharge" (FR) ou "Refill" (EN) — get_action_display
        # traduit selon la locale active.
        # / Action = "Recharge" (FR) or "Refill" (EN).
        expect(premiere_ligne).to_contain_text(re.compile(r"Recharge|Refill"))

        # Asset affiche en "TiBillets" (override FED).
        # / Asset displayed as "TiBillets" (FED override).
        expect(premiere_ligne).to_contain_text("TiBillets")

        # Structure affiche "TiBillet" (label convention mainteneur).
        # / Structure displays "TiBillet" (maintainer convention label).
        expect(premiere_ligne).to_contain_text("TiBillet")

        # Le montant est positif (signe +, couleur verte text-success).
        # On ne teste pas la couleur directement (CSS), mais le signe "+"
        # dans la span .tx-v2-amount-number.
        # / Amount is positive (+ sign, green text-success).
        amount_span = premiere_ligne.locator(".tx-v2-amount-number")
        expect(amount_span).to_contain_text("+")
        # Format montant : peut etre "20.00" ou "20,00" selon la locale
        # active cote Stripe/retour. Pour robustesse : regex.
        # / Amount format: "20.00" or "20,00" depending on active locale.
        # For robustness: regex.
        expect(amount_span).to_contain_text(re.compile(r"\+20[.,]00"))

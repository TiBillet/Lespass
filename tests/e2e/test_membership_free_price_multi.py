"""
Tests E2E : adhésion multi prix libre — vérification Stripe.
/ E2E tests: multi free-price membership — Stripe verification.

Conversion de tests/playwright/tests/17-membership-free-price-multi.spec.ts

Objectifs / Objectives :
1. Prix libre simple (Prix Libre 1) → vérifier le montant sur Stripe.
2. Sélection du deuxième prix libre (Prix Libre 2) → vérifier le montant sur Stripe.
3. Changer du prix 1 au prix 2 → vérifier que le montant Stripe = prix 2.
4. Changer du prix 2 au prix 1 → vérifier que le montant Stripe = prix 1.

Le produit est créé via l'API avant tous les tests.
/ Product is created via API before all tests.

Important : les scénarios 3 et 4 vérifient aussi le comportement JS
(l'input du premier prix doit être vidé quand on change de radio).
/ Scenarios 3 and 4 also verify JS behavior
(input of first price must be cleared when switching radio).
"""

import random
import re
import string

import pytest
import requests as http_requests

from playwright.sync_api import expect

import os
import shutil


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Même logique que conftest.py : depuis le container, on passe par le Docker
# gateway (Traefik) avec un header Host ; depuis l'hôte, URL directe.
# / Same logic as conftest.py: from container, go through Docker gateway
# (Traefik) with Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = (
    f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
)
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Génère un suffixe court unique (DB dev partagée, pas de rollback).
    / Generates a short unique suffix (shared dev DB, no rollback).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification pour l'API v2.
    / Builds authentication headers for the API v2.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_free_price_product(api_key, product_name):
    """Crée un produit adhésion avec 2 tarifs prix libre via l'API v2.
    Retourne le dict réponse (ok, status, uuid, offers, data).
    / Creates a membership product with 2 free-price offers via API v2.
    Returns response dict (ok, status, uuid, offers, data).
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product_name,
        "category": "Subscription or membership",
        "description": "Adhésion multi prix libre créée pour tests E2E.",
        "offers": [
            {
                "@type": "Offer",
                "name": "Prix Libre 1",
                "price": "5.00",
                "priceCurrency": "EUR",
                "freePrice": True,
            },
            {
                "@type": "Offer",
                "name": "Prix Libre 2",
                "price": "8.00",
                "priceCurrency": "EUR",
                "freePrice": True,
            },
        ],
    }
    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/products/",
        headers=_api_headers(api_key),
        json=payload,
        verify=False,
        timeout=30,
    )
    data = None
    try:
        data = resp.json()
    except ValueError:
        pass

    # Extraire l'UUID du produit depuis les données retournées ou l'URL de redirection.
    # / Extract product UUID from returned data or Location redirect header.
    product_uuid = ""
    if data and isinstance(data, dict):
        product_uuid = data.get("uuid") or data.get("identifier") or ""

    # Extraire les offres (tarifs) depuis la réponse.
    # / Extract offers (prices) from the response.
    offers = []
    if data and isinstance(data, dict):
        raw_offers = data.get("offers") or data.get("hasOfferCatalog", {}).get("offers") or []
        for o in raw_offers:
            offers.append({
                "name": o.get("name") or o.get("Name") or "",
                "identifier": o.get("identifier") or o.get("@id") or "",
            })

    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "uuid": product_uuid,
        "offers": offers,
        "data": data,
    }


def _ouvrir_offcanvas_adhesion(page, product_name, product_uuid=None):
    """Navigue vers /memberships/ et ouvre l'offcanvas pour le produit donné.
    Si product_uuid est fourni, utilise data-testid ; sinon cherche la carte par texte.
    / Navigates to /memberships/ and opens the offcanvas for the given product.
    If product_uuid is provided, uses data-testid; otherwise finds card by text.
    """
    page.goto("/memberships/")
    page.wait_for_load_state("domcontentloaded")

    if product_uuid:
        # Bouton avec data-testid="membership-open-<uuid>" (voir test_stripe_smoke.py).
        # / Button with data-testid="membership-open-<uuid>" (see test_stripe_smoke.py).
        subscribe_btn = page.locator(f'[data-testid="membership-open-{product_uuid}"]')
        if subscribe_btn.is_visible(timeout=5_000):
            subscribe_btn.click()
        else:
            # Fallback : chercher la carte par texte du produit.
            # / Fallback: find card by product name text.
            card = page.locator(f'.card:has-text("{product_name}")').first
            card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click()
    else:
        # Chercher la carte par le nom du produit.
        # / Find card by product name.
        card = page.locator(f'.card:has-text("{product_name}")').first
        card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click()

    # Attendre que l'offcanvas s'ouvre et que le formulaire HTMX charge.
    # / Wait for offcanvas to open and HTMX form to load.
    page.wait_for_selector("#subscribePanel.show", state="visible", timeout=15_000)
    page.wait_for_selector("#membership-form", state="visible", timeout=10_000)


def _remplir_formulaire_base(page, email, firstname, lastname):
    """Remplit les champs email, confirm-email, prénom, nom dans l'offcanvas.
    / Fills email, confirm-email, firstname, lastname fields in the offcanvas.
    """
    # Email : l'input peut avoir id="membership-email" ou name="email"
    # selon les versions du template.
    # / Email: the input may have id="membership-email" or name="email"
    # depending on template version.
    email_input = page.locator(
        '#membership-email, #subscribePanel input[name="email"]'
    ).first
    email_input.fill(email)

    confirm_input = page.locator(
        '#confirm-email, #subscribePanel input[name="confirm-email"]'
    ).first
    confirm_input.fill(email)

    page.locator('#subscribePanel input[name="firstname"]').fill(firstname)
    page.locator('#subscribePanel input[name="lastname"]').fill(lastname)


def _selectionner_prix_libre(page, label_text):
    """Clique sur le label du tarif prix libre pour sélectionner son radio.
    / Clicks the free-price label to select the radio button.
    """
    price_label = page.locator(f'label:has-text("{label_text}")').first
    price_label.click()


def _remplir_montant_libre(page, label_text, amount):
    """Remplit l'input de montant libre pour le tarif spécifié.
    L'input est dans .custom-amount-container adjacent au div contenant le label.
    / Fills the free-price amount input for the specified price.
    Input is in .custom-amount-container adjacent to the div containing the label.
    """
    container = page.locator(
        f'div:has(label:has-text("{label_text}")) + .custom-amount-container'
    )
    container.locator('input[type="number"]').fill(amount)


def _soumettre_et_attendre_stripe(page):
    """Soumet le formulaire adhésion et attend la redirection vers checkout.stripe.com.
    / Submits the membership form and waits for checkout.stripe.com redirect.
    """
    page.locator("#membership-submit").click()

    # Attente de la redirection Stripe — callback reçoit une STRING (piège clé).
    # / Wait for Stripe redirect — callback receives a STRING (key pitfall).
    page.wait_for_url(
        lambda url: "checkout.stripe.com" in url,
        timeout=40_000,
    )


def _verifier_montant_sur_stripe(page, amount):
    """Vérifie que le montant attendu apparaît sur la page Stripe checkout.
    domcontentloaded (pas networkidle) : Stripe maintient des connexions persistantes.
    / Verifies the expected amount appears on the Stripe checkout page.
    domcontentloaded (not networkidle): Stripe keeps persistent connections.
    """
    page.wait_for_load_state("domcontentloaded")

    # Regex tolérant : "12,00" ou "12.00" selon la locale de Stripe.
    # / Tolerant regex: "12,00" or "12.00" depending on Stripe locale.
    price_regex = re.compile(rf"{amount}[.,]00")
    expect(page.locator("body")).to_contain_text(price_regex, timeout=20_000)


class TestMembershipFreePriceMulti:
    """Adhésion multi prix libre — vérification des montants sur Stripe.
    / Multi free-price membership — Stripe amount verification.
    """

    # Attributs de classe partagés entre les 4 tests.
    # / Class attributes shared between the 4 tests.
    _product_name: str = ""
    _product_uuid: str = ""
    _created: bool = False

    @pytest.fixture(autouse=True)
    def _setup_product(self, api_key):
        """Crée le produit adhésion multi prix libre avant le premier test.
        Les tests suivants réutilisent le produit existant (DB partagée, pas de rollback).
        / Creates the multi free-price membership product before the first test.
        Subsequent tests reuse the existing product (shared DB, no rollback).
        """
        if TestMembershipFreePriceMulti._created:
            # Produit déjà créé lors d'un test précédent.
            # / Product already created during a previous test.
            return

        rid = _random_id()
        product_name = f"Adhesion Multi-Prix Libre {rid}"

        result = _create_free_price_product(api_key, product_name)
        assert result["ok"], (
            f"Création du produit multi prix libre échouée : "
            f"status={result['status']}, data={result['data']}"
        )

        TestMembershipFreePriceMulti._product_name = product_name
        TestMembershipFreePriceMulti._product_uuid = result["uuid"]
        TestMembershipFreePriceMulti._created = True

    # ─────────────────────────────────────────────────────────────
    # Scénario 1 : Prix libre simple — sélectionner "Prix Libre 1"
    # → vérifier le montant sur Stripe
    # ─────────────────────────────────────────────────────────────
    def test_scenario1_prix_libre_simple(self, page):
        """Prix libre simple : sélection Prix Libre 1 → montant correct sur Stripe.
        / Simple free price: select Prix Libre 1 → correct amount on Stripe.
        """
        rid = _random_id()
        user_email = f"jturbeaux+multi1{rid}@pm.me"
        amount = "12"

        page.set_default_timeout(60_000)

        # Étape 1 : Ouvrir la page liste et l'offcanvas du produit.
        # / Step 1: Open the list page and the product offcanvas.
        _ouvrir_offcanvas_adhesion(
            page,
            self._product_name,
            self._product_uuid,
        )

        # Étape 2 : Remplir les champs identité.
        # / Step 2: Fill identity fields.
        _remplir_formulaire_base(page, user_email, "Multi", "One")

        # Étape 3 : Sélectionner "Prix Libre 1" et remplir le montant.
        # / Step 3: Select "Prix Libre 1" and fill the amount.
        _selectionner_prix_libre(page, "Prix Libre 1")
        _remplir_montant_libre(page, "Prix Libre 1", amount)

        # Étape 4 : Soumettre et attendre Stripe.
        # / Step 4: Submit and wait for Stripe.
        _soumettre_et_attendre_stripe(page)

        # Étape 5 : Vérifier que Stripe affiche le bon montant.
        # / Step 5: Verify Stripe shows the correct amount.
        _verifier_montant_sur_stripe(page, amount)

    # ─────────────────────────────────────────────────────────────
    # Scénario 2 : Sélection du deuxième prix libre
    # → vérifier le montant sur Stripe (= Prix Libre 2)
    # ─────────────────────────────────────────────────────────────
    def test_scenario2_selection_deuxieme_prix_libre(self, page):
        """Sélection Prix Libre 2 → montant correct sur Stripe.
        / Selecting Prix Libre 2 → correct amount on Stripe.
        """
        rid = _random_id()
        user_email = f"jturbeaux+multi2{rid}@pm.me"
        amount = "18"

        page.set_default_timeout(60_000)

        # Étape 1 : Ouvrir l'offcanvas.
        # / Step 1: Open the offcanvas.
        _ouvrir_offcanvas_adhesion(
            page,
            self._product_name,
            self._product_uuid,
        )

        # Étape 2 : Remplir identité.
        # / Step 2: Fill identity.
        _remplir_formulaire_base(page, user_email, "Multi", "Two")

        # Étape 3 : Sélectionner "Prix Libre 2" et remplir le montant.
        # / Step 3: Select "Prix Libre 2" and fill the amount.
        _selectionner_prix_libre(page, "Prix Libre 2")
        _remplir_montant_libre(page, "Prix Libre 2", amount)

        # Étape 4 : Soumettre et attendre Stripe.
        # / Step 4: Submit and wait for Stripe.
        _soumettre_et_attendre_stripe(page)

        # Étape 5 : Vérifier le montant sur Stripe.
        # / Step 5: Verify amount on Stripe.
        _verifier_montant_sur_stripe(page, amount)

    # ─────────────────────────────────────────────────────────────
    # Scénario 3 : Changer du premier au second prix libre
    # → Stripe doit afficher le montant de Prix Libre 2
    # → L'input de Prix Libre 1 doit être vidé par le JS lors du changement
    # ─────────────────────────────────────────────────────────────
    def test_scenario3_changer_du_premier_au_second_prix_libre(self, page):
        """Sélectionner Prix 1, remplir, changer vers Prix 2 → Stripe = Prix 2.
        Vérifie aussi que l'input Prix 1 est vidé par le JS.
        / Select Price 1, fill, switch to Price 2 → Stripe = Price 2.
        Also verifies that Price 1 input is cleared by JS.
        """
        rid = _random_id()
        user_email = f"jturbeaux+multi3{rid}@pm.me"
        amount1 = "13"
        amount2 = "22"

        page.set_default_timeout(60_000)

        # Étape 1 : Ouvrir l'offcanvas.
        # / Step 1: Open the offcanvas.
        _ouvrir_offcanvas_adhesion(
            page,
            self._product_name,
            self._product_uuid,
        )

        # Étape 2 : Remplir identité.
        # / Step 2: Fill identity.
        _remplir_formulaire_base(page, user_email, "Multi", "Three")

        # Étape 3a : Sélectionner "Prix Libre 1" et remplir montant1.
        # / Step 3a: Select "Prix Libre 1" and fill amount1.
        _selectionner_prix_libre(page, "Prix Libre 1")
        _remplir_montant_libre(page, "Prix Libre 1", amount1)

        # Localiser l'input Prix Libre 1 pour vérification ultérieure.
        # / Locate the Prix Libre 1 input for later verification.
        container1 = page.locator(
            'div:has(label:has-text("Prix Libre 1")) + .custom-amount-container'
        )
        input1 = container1.locator('input[type="number"]')

        # Étape 3b : Changer vers "Prix Libre 2" et remplir montant2.
        # / Step 3b: Switch to "Prix Libre 2" and fill amount2.
        _selectionner_prix_libre(page, "Prix Libre 2")

        # Vérifier que le JS a vidé l'input Prix Libre 1 lors du changement de radio.
        # / Verify JS cleared Prix Libre 1 input when switching radio.
        expect(input1).to_have_value("")

        _remplir_montant_libre(page, "Prix Libre 2", amount2)

        # Étape 4 : Soumettre et attendre Stripe.
        # / Step 4: Submit and wait for Stripe.
        _soumettre_et_attendre_stripe(page)

        # Étape 5 : Vérifier que Stripe affiche amount2 (pas amount1).
        # / Step 5: Verify Stripe shows amount2 (not amount1).
        _verifier_montant_sur_stripe(page, amount2)

    # ─────────────────────────────────────────────────────────────
    # Scénario 4 : Changer du second au premier prix libre
    # → Stripe doit afficher le montant de Prix Libre 1
    # → L'input de Prix Libre 2 doit être vidé par le JS
    # ─────────────────────────────────────────────────────────────
    def test_scenario4_changer_du_second_au_premier_prix_libre(self, page):
        """Sélectionner Prix 2, remplir, changer vers Prix 1 → Stripe = Prix 1.
        Vérifie aussi que l'input Prix 2 est vidé par le JS.
        / Select Price 2, fill, switch to Price 1 → Stripe = Price 1.
        Also verifies that Price 2 input is cleared by JS.
        """
        rid = _random_id()
        user_email = f"jturbeaux+multi4{rid}@pm.me"
        amount1 = "14"
        amount2 = "24"

        page.set_default_timeout(60_000)

        # Étape 1 : Ouvrir l'offcanvas.
        # / Step 1: Open the offcanvas.
        _ouvrir_offcanvas_adhesion(
            page,
            self._product_name,
            self._product_uuid,
        )

        # Étape 2 : Remplir identité.
        # / Step 2: Fill identity.
        _remplir_formulaire_base(page, user_email, "Multi", "Four")

        # Étape 3a : Sélectionner "Prix Libre 2" et remplir montant2.
        # / Step 3a: Select "Prix Libre 2" and fill amount2.
        _selectionner_prix_libre(page, "Prix Libre 2")
        _remplir_montant_libre(page, "Prix Libre 2", amount2)

        # Localiser l'input Prix Libre 2 pour vérification ultérieure.
        # / Locate the Prix Libre 2 input for later verification.
        container2 = page.locator(
            'div:has(label:has-text("Prix Libre 2")) + .custom-amount-container'
        )
        input2 = container2.locator('input[type="number"]')

        # Étape 3b : Changer vers "Prix Libre 1" et remplir montant1.
        # / Step 3b: Switch to "Prix Libre 1" and fill amount1.
        _selectionner_prix_libre(page, "Prix Libre 1")

        # Vérifier que le JS a vidé l'input Prix Libre 2 lors du changement de radio.
        # / Verify JS cleared Prix Libre 2 input when switching radio.
        expect(input2).to_have_value("")

        _remplir_montant_libre(page, "Prix Libre 1", amount1)

        # Étape 4 : Soumettre et attendre Stripe.
        # / Step 4: Submit and wait for Stripe.
        _soumettre_et_attendre_stripe(page)

        # Étape 5 : Vérifier que Stripe affiche amount1 (pas amount2).
        # / Step 5: Verify Stripe shows amount1 (not amount2).
        _verifier_montant_sur_stripe(page, amount1)

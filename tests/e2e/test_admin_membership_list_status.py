"""
Tests E2E : vue liste admin adhésions — statut et deadline après adhésion réussie.
/ E2E tests: admin membership list view — status and deadline after successful membership.

Conversion de tests/playwright/tests/35-admin-membership-list-status.spec.ts

Vérifie que la vue liste admin (/admin/BaseBillet/membership/) affiche
correctement le statut et la deadline pour 3 scénarios d'adhésion réussie.

/ Verifies that the admin list view (/admin/BaseBillet/membership/) displays
the correct status and deadline for 3 successful membership scenarios.

Scénarios :
1. Adhésion offerte via API (paymentMode FREE) → statut "Payé en ligne" + deadline date
2. Adhésion créée via formulaire admin (Offert 0€) → statut "Créé via l'administration" + deadline date
3. Adhésion prix libre 0€ via API → statut "Payé en ligne" + deadline date

Colonnes testées dans la liste :
- td.field-status          → statut lisible
- td.field-display_deadline → date de fin (format JJ/MM/AAAA, pas "-")
"""

import os
import random
import re
import shutil
import string

import pytest
import requests as http_requests
from playwright.sync_api import expect


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


def _create_membership_api(
    api_key,
    price_uuid,
    email,
    first_name="API",
    last_name="Test",
    payment_mode="FREE",
    custom_amount=None,
):
    """Crée une adhésion via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Équivalent de createMembershipApi dans utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Equivalent of createMembershipApi in utils/api.ts.

    Paramètres / Parameters:
    - custom_amount : montant libre en chaîne (ex: '0'), ajouté si fourni
    """
    additional_property = [
        {
            "@type": "PropertyValue",
            "name": "paymentMode",
            "value": payment_mode,
        }
    ]
    if custom_amount is not None:
        additional_property.append(
            {
                "@type": "PropertyValue",
                "name": "customAmount",
                "value": custom_amount,
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": first_name,
            "familyName": last_name,
        },
        "membershipPlan": {
            "@type": "Offer",
            "identifier": price_uuid,
        },
        "additionalProperty": additional_property,
    }

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/memberships/",
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
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "data": data,
        "text": resp.text[:500],
    }


def _rechercher_dans_liste_admin(page, email):
    """Cherche une adhésion dans la liste admin par email et retourne la ligne.
    Précondition : page est déjà sur /admin/BaseBillet/membership/
    / Searches for a membership in the admin list by email and returns the row.
    Precondition: page is already on /admin/BaseBillet/membership/
    """
    # Recherche via l'input q de la changelist Django admin.
    # / Search via the Django admin changelist q input.
    search_input = page.locator('input[name="q"]').first
    search_input.fill(email)
    search_input.press("Enter")
    page.wait_for_load_state("networkidle")
    return page.locator("#result_list tbody tr").filter(has_text=email)


class TestAdminMembershipListStatus:
    """Vue liste admin adhésions — statut et deadline.
    / Admin membership list view — status and deadline.
    """

    # Identifiant partagé entre les 3 tests du scénario (UUID léger suffixe).
    # On l'initialise ici ; il sera remplacé au setup du premier test.
    # / Shared identifier across the 3 scenario tests (light UUID suffix).
    # Initialized here; replaced during first test setup.
    _random_id: str = ""
    _price_uuid: str = ""

    @pytest.fixture(autouse=True)
    def _setup_membership_product(self, create_product, api_key):
        """Crée une fois le produit adhésion annuel et stocke l'UUID du tarif.
        Exécuté avant chaque test (mais la création réelle n'a lieu qu'une fois
        grâce à la vérification de _price_uuid).
        / Creates the annual membership product once and stores the price UUID.
        Runs before each test (but the actual creation happens only once,
        thanks to the _price_uuid check).
        """
        if TestAdminMembershipListStatus._price_uuid:
            # Déjà créé lors d'un test précédent — pas de doublon.
            # / Already created during a previous test — no duplicate.
            return

        # Générer un identifiant unique pour l'ensemble du scénario.
        # / Generate a unique identifier for the whole scenario.
        random_id = _random_id()
        TestAdminMembershipListStatus._random_id = random_id

        product_name = f"Adhesion Liste {random_id}"
        price_name = f"Annuel liste {random_id}"

        # Créer un produit adhésion annuel (subscription_type Y).
        # La deadline sera calculée = last_contribution + 12 mois.
        # / Create annual membership product (subscription_type Y).
        # Deadline will be calculated = last_contribution + 12 months.
        product_result = create_product(
            name=product_name,
            description="Test vue liste admin statut",
            category="Membership",
            offers=[
                {
                    "name": price_name,
                    "price": "15.00",
                    "subscriptionType": "Y",
                }
            ],
        )
        assert product_result["ok"], (
            f"Création du produit adhésion échouée : {product_result}"
        )

        # Récupérer l'UUID du tarif créé via la liste des offres retournées.
        # / Get the UUID of the created price from the returned offers list.
        offers = product_result.get("offers") or []
        price_uuid = ""
        for offer in offers:
            if offer.get("name") == price_name:
                price_uuid = offer.get("identifier") or ""
                break
        # Fallback : prendre le premier tarif si la recherche par nom échoue.
        # / Fallback: take the first price if name lookup fails.
        if not price_uuid and offers:
            price_uuid = offers[0].get("identifier") or ""

        assert price_uuid, (
            f"UUID du tarif introuvable dans les offres retournées : {offers}"
        )

        TestAdminMembershipListStatus._price_uuid = price_uuid

    # ─────────────────────────────────────────────────────────────
    # Scénario 1 : Adhésion offerte via API (paymentMode FREE)
    # → status ONCE → "Payé en ligne" + deadline active
    # ─────────────────────────────────────────────────────────────
    def test_api_free_statut_paye_en_ligne_et_deadline(
        self, page, login_as_admin, api_key
    ):
        """API FREE → 'Payé en ligne' + deadline date dans la liste admin.
        / API FREE → 'Paid online' + deadline date in admin list.
        """
        # Email unique pour ce scénario (suffixe partagé + numéro de scénario).
        # / Unique email for this scenario (shared suffix + scenario number).
        email = f"jturbeaux+list1{self._random_id}@pm.me"

        # --- Étape 1 : Créer l'adhésion via l'API (paymentMode FREE → status ONCE) ---
        # / Step 1: Create membership via API (paymentMode FREE → ONCE status)
        result = _create_membership_api(
            api_key=api_key,
            price_uuid=self._price_uuid,
            email=email,
            first_name="API",
            last_name="Test",
            payment_mode="FREE",
        )
        assert result["ok"], f"Création adhésion via API échouée : {result}"

        # --- Étape 2 : Connexion admin et navigation vers la liste ---
        # / Step 2: Admin login and navigate to the list
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        # --- Étape 3 : Rechercher l'adhésion dans la liste admin ---
        # / Step 3: Search for the membership in the admin list
        row = _rechercher_dans_liste_admin(page, email)
        expect(row).to_be_visible(timeout=10_000)

        # --- Étape 4 : Vérifier le statut "Payé en ligne" (status ONCE = 'A') ---
        # Tolérance FR/EN car la langue peut varier selon la config du tenant.
        # / Step 4: Verify "Payé en ligne" status (ONCE = 'A')
        # FR/EN tolerance because language can vary with tenant config.
        status_cell = row.locator("td.field-status")
        expect(status_cell).to_contain_text(
            re.compile(r"Pay[eé] en ligne|Paid online", re.IGNORECASE)
        )

        # --- Étape 5 : Vérifier que la deadline est une date (pas "-") ---
        # La deadline annuelle = last_contribution + 12 mois.
        # / Step 5: Verify that the deadline is a date (not "-")
        # Annual deadline = last_contribution + 12 months.
        deadline_cell = row.locator("td.field-display_deadline")
        deadline_text = deadline_cell.inner_text().strip()
        assert deadline_text != "-", (
            f"La deadline ne doit pas être '-', obtenu : '{deadline_text}'"
        )
        assert re.match(r"\d{2}/\d{2}/\d{4}", deadline_text), (
            f"La deadline doit être au format JJ/MM/AAAA, obtenu : '{deadline_text}'"
        )

    # ─────────────────────────────────────────────────────────────
    # Scénario 2 : Adhésion créée via formulaire admin (Offert, 0€)
    # → status ADMIN → "Créé via l'administration" + deadline active
    # ─────────────────────────────────────────────────────────────
    def test_formulaire_admin_statut_cree_via_administration_et_deadline(
        self, page, login_as_admin
    ):
        """Formulaire admin → 'Créé via l'administration' + deadline dans la liste.
        / Admin form → 'Created via administration' + deadline in list.
        """
        # Email unique pour ce scénario.
        # / Unique email for this scenario.
        email = f"jturbeaux+list2{self._random_id}@pm.me"

        # --- Étape 1 : Connexion admin et ouverture du formulaire d'ajout ---
        # / Step 1: Admin login and open the add form
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membership/add/")
        page.wait_for_load_state("networkidle")

        # --- Étape 2 : Remplir le formulaire admin d'ajout d'adhésion ---
        # Nom, prénom, email, tarif, contribution 0€, mode paiement NA.
        # / Step 2: Fill the admin membership add form
        # Last name, first name, email, price, contribution 0€, payment NA.
        page.locator("#id_last_name").fill("Admin")
        page.locator("#id_first_name").fill("Test")
        page.locator("#id_email").fill(email)

        # Tarif : sélection par UUID (valeur du <select>)
        # / Price: select by UUID (value of the <select>)
        page.locator("#id_price").select_option(self._price_uuid)

        # Contribution = 0 (adhésion offerte)
        # / Contribution = 0 (offered membership)
        page.locator("#id_contribution").fill("0")

        # Mode de paiement = NA (Offert) — déjà la valeur par défaut
        # / Payment method = NA (Offered) — already the default value
        page.locator("#id_payment_method").select_option("NA")

        # --- Étape 3 : Soumettre le formulaire ---
        # / Step 3: Submit the form
        save_button = page.locator('[name="_save"]').first
        save_button.click()
        page.wait_for_load_state("networkidle")

        # --- Étape 4 : Naviguer vers la liste admin et chercher l'adhésion ---
        # / Step 4: Navigate to admin list and search for the membership
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        row = _rechercher_dans_liste_admin(page, email)
        expect(row).to_be_visible(timeout=10_000)

        # --- Étape 5 : Vérifier le statut "Créé via l'administration" (ADMIN = 'D') ---
        # Le signal post_save crée une LigneArticle mais ne change pas le statut.
        # trigger_A appelle set_deadline().
        # / Step 5: Verify "Créé via l'administration" status (ADMIN = 'D')
        # The post_save signal creates a LigneArticle but does not change the status.
        # trigger_A calls set_deadline().
        status_cell = row.locator("td.field-status")
        expect(status_cell).to_contain_text(
            re.compile(
                r"Cr[eé][eé] via l.administration|Created via administration",
                re.IGNORECASE,
            )
        )

        # --- Étape 6 : Vérifier que la deadline est une date (pas "-") ---
        # / Step 6: Verify that the deadline is a date (not "-")
        deadline_cell = row.locator("td.field-display_deadline")
        deadline_text = deadline_cell.inner_text().strip()
        assert deadline_text != "-", (
            f"La deadline ne doit pas être '-', obtenu : '{deadline_text}'"
        )
        assert re.match(r"\d{2}/\d{2}/\d{4}", deadline_text), (
            f"La deadline doit être au format JJ/MM/AAAA, obtenu : '{deadline_text}'"
        )

    # ─────────────────────────────────────────────────────────────
    # Scénario 3 : Adhésion prix libre 0€ via API
    # → status ONCE → "Payé en ligne" + deadline active
    # ─────────────────────────────────────────────────────────────
    def test_api_prix_libre_zero_statut_paye_en_ligne_et_deadline(
        self, page, login_as_admin, api_key
    ):
        """API prix libre 0€ → 'Payé en ligne' + deadline dans la liste admin.
        / API free-price 0€ → 'Paid online' + deadline in admin list.
        """
        # Email unique pour ce scénario.
        # / Unique email for this scenario.
        email = f"jturbeaux+list3{self._random_id}@pm.me"

        # --- Étape 1 : Créer l'adhésion prix libre 0€ via API ---
        # customAmount='0' correspond au paymentMode FREE avec montant explicite.
        # / Step 1: Create free-price 0€ membership via API
        # customAmount='0' corresponds to FREE paymentMode with explicit amount.
        result = _create_membership_api(
            api_key=api_key,
            price_uuid=self._price_uuid,
            email=email,
            first_name="Zero",
            last_name="Euro",
            payment_mode="FREE",
            custom_amount="0",
        )
        assert result["ok"], f"Création adhésion prix libre 0€ échouée : {result}"

        # --- Étape 2 : Connexion admin et navigation vers la liste ---
        # / Step 2: Admin login and navigate to the list
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        # --- Étape 3 : Rechercher l'adhésion dans la liste admin ---
        # / Step 3: Search for the membership in the admin list
        row = _rechercher_dans_liste_admin(page, email)
        expect(row).to_be_visible(timeout=10_000)

        # --- Étape 4 : Vérifier le statut "Payé en ligne" (status ONCE = 'A') ---
        # Tolérance FR/EN (langue variable selon config tenant).
        # / Step 4: Verify "Payé en ligne" status (ONCE = 'A')
        # FR/EN tolerance (language varies with tenant config).
        status_cell = row.locator("td.field-status")
        expect(status_cell).to_contain_text(
            re.compile(r"Pay[eé] en ligne|Paid online", re.IGNORECASE)
        )

        # --- Étape 5 : Vérifier que la deadline est une date (pas "-") ---
        # / Step 5: Verify that the deadline is a date (not "-")
        deadline_cell = row.locator("td.field-display_deadline")
        deadline_text = deadline_cell.inner_text().strip()
        assert deadline_text != "-", (
            f"La deadline ne doit pas être '-', obtenu : '{deadline_text}'"
        )
        assert re.match(r"\d{2}/\d{2}/\d{4}", deadline_text), (
            f"La deadline doit être au format JJ/MM/AAAA, obtenu : '{deadline_text}'"
        )

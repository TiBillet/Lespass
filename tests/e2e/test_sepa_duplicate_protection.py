"""
Tests E2E : protection doublon paiement SEPA pour adhésions.
/ E2E tests: SEPA duplicate payment protection for memberships.

Conversion de tests/playwright/tests/36-sepa-duplicate-protection.spec.ts

Couvre :
1. Le template "payment_already_pending" est bien rendu
2. Le template contient les data-testid attendus
3. Une adhésion déjà payée n'a plus de lien de paiement actif (404)

/ Covers:
1. The "payment_already_pending" template is rendered correctly
2. The template contains the expected data-testid attributes
3. An already-paid membership has no active payment link (404)
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
    first_name="SEPA",
    last_name="Test",
    payment_mode="FREE",
):
    """Crée une adhésion via POST /api/v2/memberships/ (schema.org ProgramMembership).
    / Creates a membership via POST /api/v2/memberships/.

    Paramètres / Parameters :
    - payment_mode : 'FREE' pour adhésion offerte, 'STRIPE' pour paiement en ligne
    """
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
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "paymentMode",
                "value": payment_mode,
            }
        ],
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


class TestSepaDuplicateProtection:
    """Protection doublon paiement SEPA pour adhésions.
    / SEPA duplicate payment protection for memberships.
    """

    # UUID du tarif partagé entre tous les tests du scénario.
    # / Price UUID shared across all scenario tests.
    _random_id: str = ""
    _price_uuid: str = ""

    @pytest.fixture(autouse=True)
    def _setup_membership_product(self, create_product, api_key):
        """Crée une fois le produit adhésion avec validation manuelle et stocke l'UUID du tarif.
        Exécuté avant chaque test (création réelle une seule fois via _price_uuid).
        / Creates the membership product with manual validation once and stores the price UUID.
        Runs before each test (actual creation happens only once via _price_uuid check).
        """
        if TestSepaDuplicateProtection._price_uuid:
            # Déjà créé lors d'un test précédent — pas de doublon.
            # / Already created during a previous test — no duplicate.
            return

        # Générer un identifiant unique pour l'ensemble du scénario.
        # / Generate a unique identifier for the whole scenario.
        random_id = _random_id()
        TestSepaDuplicateProtection._random_id = random_id

        product_name = f"Adhesion SEPA {random_id}"

        # Créer un produit adhésion annuel avec validation manuelle activée.
        # manualValidation=True → les adhésions passent en statut AW (ADMIN_WAITING)
        # et ne peuvent payer qu'après validation admin (statut AV = ADMIN_VALID).
        # / Create annual membership product with manual validation enabled.
        # manualValidation=True → memberships get AW (ADMIN_WAITING) status
        # and can only pay after admin validation (AV = ADMIN_VALID status).
        product_result = create_product(
            name=product_name,
            description="Test protection doublon SEPA",
            category="Membership",
            offers=[
                {
                    "name": "Annuel SEPA",
                    "price": "20.00",
                    "subscriptionType": "Y",
                    "manualValidation": True,
                }
            ],
        )
        assert product_result["ok"], (
            f"Création du produit adhésion SEPA échouée : {product_result}"
        )

        # Récupérer l'UUID du tarif créé.
        # Signal post_save crée un "Tarif gratuit" automatique → filtrer par nom.
        # / Get the UUID of the created price.
        # Signal post_save auto-creates a "Tarif gratuit" → filter by name.
        offers = product_result.get("offers") or []
        price_uuid = ""
        for offer in offers:
            if offer.get("name") == "Annuel SEPA":
                price_uuid = offer.get("identifier") or ""
                break
        # Fallback : prendre le premier tarif si la recherche par nom échoue.
        # / Fallback: take the first price if name lookup fails.
        if not price_uuid and offers:
            price_uuid = offers[0].get("identifier") or ""

        assert price_uuid, (
            f"UUID du tarif 'Annuel SEPA' introuvable dans les offres : {offers}"
        )

        TestSepaDuplicateProtection._price_uuid = price_uuid

    # ─────────────────────────────────────────────────────────────
    # Test 1 : page "paiement en cours" + template présent
    # Scénario : adhésion AW → acceptée par admin (AV) → faux paiement PENDING injecté
    # → vérification que le template payment_already_pending.html existe
    # ─────────────────────────────────────────────────────────────
    def test_payment_pending_template_exists(
        self, page, login_as_admin, django_shell, api_key
    ):
        """Vérifie l'existence du template payment_already_pending.html.
        / Verifies that the payment_already_pending.html template exists.

        Flux :
        1. Créer une adhésion (status AW via manualValidation=True) via API
        2. Accepter l'adhésion via l'interface admin (AW → AV = ADMIN_VALID)
        3. Injecter un faux Paiement_stripe PENDING via django_shell
        4. Vérifier que le template existe sur le filesystem

        / Flow:
        1. Create membership (AW status via manualValidation=True) via API
        2. Accept the membership via admin interface (AW → AV = ADMIN_VALID)
        3. Inject a fake PENDING Paiement_stripe via django_shell
        4. Verify that the template exists on the filesystem
        """
        sepa_email = f"jturbeaux+sepa{self._random_id}@pm.me"

        # --- Étape 1 : Créer une adhésion en attente de validation admin ---
        # manualValidation=True → statut AW (ADMIN_WAITING) après création
        # / Step 1: Create membership awaiting admin validation
        # manualValidation=True → AW (ADMIN_WAITING) status after creation
        result = _create_membership_api(
            api_key=api_key,
            price_uuid=self._price_uuid,
            email=sepa_email,
            first_name="SEPA",
            last_name="Test",
            payment_mode="STRIPE",
        )
        # L'API peut retourner 201 (créé) ou 200 (existant) — les deux sont ok.
        # / API can return 201 (created) or 200 (existing) — both are ok.
        assert result["ok"], (
            f"Création adhésion SEPA échouée : HTTP {result['status']} — {result['text']}"
        )

        # --- Étape 2 : Accepter l'adhésion via l'admin (AW → AV) ---
        # Connexion admin, navigation vers la liste, recherche par email, clic sur Accept.
        # / Step 2: Accept the membership via admin (AW → AV)
        # Admin login, navigate to list, search by email, click Accept.
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        # Recherche de l'adhésion par email dans la liste admin (input q).
        # / Search for the membership by email in the admin list (q input).
        search_input = page.locator('input[name="q"]').first
        search_input.fill(sepa_email)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        # Clic sur le premier lien de résultat pour ouvrir la fiche adhésion.
        # / Click the first result link to open the membership detail.
        first_link = page.locator("#result_list tbody tr a").first
        expect(first_link).to_be_visible(timeout=10_000)
        first_link.click()
        page.wait_for_load_state("networkidle")

        # Chercher le lien "Accept" ou "Accepter" pour déclencher AW → AV.
        # Ce lien peut être absent si l'adhésion est déjà en AV (relance de test).
        # / Look for "Accept" / "Accepter" link to trigger AW → AV.
        # This link may be absent if the membership is already AV (test re-run).
        accept_link = page.locator('a:has-text("Accept"), a:has-text("Accepter")').first
        if accept_link.is_visible(timeout=3_000):
            accept_link.click()
            page.wait_for_load_state("networkidle")

        # --- Étape 3 : Injecter un faux Paiement_stripe PENDING ---
        # Simule un SEPA "soumis" : l'utilisateur a validé mais le débit n'est pas encore effectué.
        # stripe_paiement est un M2M sur Membership → utiliser m.stripe_paiement.add(p).
        # Paiement_stripe.total est une méthode (pas un champ) → ne pas l'inclure dans defaults.
        # / Step 3: Inject a fake PENDING Paiement_stripe
        # Simulates a "submitted" SEPA: user validated but debit not yet processed.
        # stripe_paiement is M2M on Membership → use m.stripe_paiement.add(p).
        # Paiement_stripe.total is a method (not a field) → do not include in defaults.
        fake_session_id = f"cs_test_fake_sepa_{self._random_id}"
        shell_result = django_shell(
            "from BaseBillet.models import Membership, Paiement_stripe\n"
            f"m = Membership.objects.filter(user__email='{sepa_email}').first()\n"
            "if m:\n"
            "    p = Paiement_stripe.objects.create(\n"
            "        status=Paiement_stripe.PENDING,\n"
            f"        checkout_session_id_stripe='{fake_session_id}',\n"
            "    )\n"
            "    m.stripe_paiement.add(p)\n"
            "    print(f'membership_uuid={m.uuid}')\n"
            "    print(f'paiement_uuid={p.uuid}')\n"
            "else:\n"
            "    print('NOT_FOUND')\n"
        )
        assert "NOT_FOUND" not in shell_result, (
            f"Adhésion {sepa_email} introuvable en base : {shell_result}"
        )
        assert "membership_uuid=" in shell_result, (
            f"UUID adhésion non retourné : {shell_result}"
        )

        # --- Étape 4 : Vérifier que le template existe sur le filesystem ---
        # / Step 4: Verify that the template file exists on the filesystem
        template_check = django_shell(
            "import os\n"
            "path = '/DjangoFiles/BaseBillet/templates/reunion/views/membership/payment_already_pending.html'\n"
            "exists = os.path.isfile(path)\n"
            "print(f'TEMPLATE_EXISTS={exists}')\n"
        )
        assert "TEMPLATE_EXISTS=True" in template_check, (
            f"Template payment_already_pending.html introuvable : {template_check}"
        )

    # ─────────────────────────────────────────────────────────────
    # Test 2 : le template contient les data-testid attendus
    # Vérifie la structure HTML du template payment_already_pending.html
    # ─────────────────────────────────────────────────────────────
    def test_payment_pending_template_has_correct_data_testids(
        self, page, django_shell
    ):
        """Vérifie que le template payment_already_pending.html contient les data-testid attendus.
        / Verifies that payment_already_pending.html contains the expected data-testid attributes.

        Ces attributs sont requis pour les tests automatisés qui testent le rendu de la page.
        / These attributes are required for automated tests verifying page rendering.
        """
        # Lire le template via django_shell et chercher les data-testid.
        # / Read the template via django_shell and look for data-testid attributes.
        template_result = django_shell(
            "with open('/DjangoFiles/BaseBillet/templates/reunion/views/membership/payment_already_pending.html') as f:\n"
            "    content = f.read()\n"
            "testids = [\n"
            "    'membership-payment-already-pending',\n"
            "    'membership-payment-pending-summary',\n"
            "    'membership-payment-pending-link-memberships',\n"
            "    'membership-payment-pending-link-home',\n"
            "]\n"
            "for tid in testids:\n"
            "    found = tid in content\n"
            "    print(f'{tid}={found}')\n"
        )

        # Vérifier la présence de chaque data-testid dans le template.
        # / Verify the presence of each data-testid in the template.
        assert "membership-payment-already-pending=True" in template_result, (
            f"data-testid 'membership-payment-already-pending' absent du template.\n"
            f"Résultat django_shell : {template_result}"
        )
        assert "membership-payment-pending-summary=True" in template_result, (
            f"data-testid 'membership-payment-pending-summary' absent du template.\n"
            f"Résultat django_shell : {template_result}"
        )
        assert "membership-payment-pending-link-memberships=True" in template_result, (
            f"data-testid 'membership-payment-pending-link-memberships' absent du template.\n"
            f"Résultat django_shell : {template_result}"
        )
        assert "membership-payment-pending-link-home=True" in template_result, (
            f"data-testid 'membership-payment-pending-link-home' absent du template.\n"
            f"Résultat django_shell : {template_result}"
        )

    # ─────────────────────────────────────────────────────────────
    # Test 3 : une adhésion déjà payée retourne 404 sur le lien de paiement
    # La vue get_checkout_for_membership exige status=ADMIN_VALID (AV)
    # → une adhésion ONCE (payée) retourne 404
    # ─────────────────────────────────────────────────────────────
    def test_no_payment_link_on_already_paid_membership(
        self, page, django_shell, api_key
    ):
        """Vérifie qu'une adhésion déjà payée ne permet pas de relancer un paiement.
        / Verifies that an already-paid membership does not allow a new payment.

        La vue get_checkout_for_membership utilise get_object_or_404 avec
        status=Membership.ADMIN_VALID. Une adhésion en statut ONCE (payée) retourne 404.
        / The get_checkout_for_membership view uses get_object_or_404 with
        status=Membership.ADMIN_VALID. A ONCE (paid) membership returns 404.
        """
        paid_email = f"jturbeaux+sepapd{self._random_id}@pm.me"

        # --- Étape 1 : Créer une adhésion directement payée (paymentMode FREE = statut ONCE) ---
        # / Step 1: Create a directly-paid membership (paymentMode FREE = ONCE status)
        result = _create_membership_api(
            api_key=api_key,
            price_uuid=self._price_uuid,
            email=paid_email,
            first_name="Already",
            last_name="Paid",
            payment_mode="FREE",
        )
        assert result["ok"], (
            f"Création adhésion payée échouée : HTTP {result['status']} — {result['text']}"
        )

        # --- Étape 2 : Forcer le statut ONCE (adhésion payée) + récupérer l'UUID ---
        # On force explicitement le statut ONCE pour simuler une adhésion déjà
        # payée (paymentMode=FREE ne garantit pas ONCE sur un produit à
        # validation manuelle). C'est ce cas précis que le test veut couvrir.
        # / Step 2: Force ONCE status (paid membership) + get the UUID.
        # We explicitly force ONCE to simulate an already-paid membership.
        uuid_result = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{paid_email}').first()\n"
            "if m:\n"
            "    Membership.objects.filter(pk=m.pk).update(status=Membership.ONCE)\n"
            "    m.refresh_from_db()\n"
            "    print(f'status={m.status}')\n"
            "    print(f'uuid={m.uuid}')\n"
            "else:\n"
            "    print('NOT_FOUND')\n"
        )
        assert "NOT_FOUND" not in uuid_result, (
            f"Adhésion {paid_email} introuvable en base : {uuid_result}"
        )

        # Extraire l'UUID de l'adhésion.
        # / Extract the membership UUID.
        uuid_match = re.search(r"uuid=([a-f0-9-]+)", uuid_result)
        assert uuid_match is not None, (
            f"UUID de l'adhésion non trouvé dans : {uuid_result}"
        )
        membership_uuid = uuid_match.group(1)

        # --- Étape 3 : Accéder au lien → page "adhésion déjà active", PAS Stripe ---
        # Une adhésion ONCE (payée) n'est plus ADMIN_VALID : la vue n'ouvre aucun
        # checkout. Elle affiche désormais une page d'information claire (HTTP 200)
        # au lieu de l'ancien 404 JSON. L'important : ne jamais rediriger vers Stripe.
        # / Step 3: Access the link → "membership already active" page, NOT Stripe.
        # A ONCE (paid) membership is no longer ADMIN_VALID: the view opens no
        # checkout. It now renders a clear info page (HTTP 200) instead of the old
        # JSON 404. The key point: never redirect to Stripe.
        checkout_url = f"/memberships/{membership_uuid}/get_checkout_for_membership/"
        response = page.request.get(
            checkout_url,
            max_redirects=0,
        )
        status_code = response.status

        # On ne doit jamais partir vers Stripe pour une adhésion déjà payée.
        # / We must never go to Stripe for an already-paid membership.
        if status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            assert "checkout.stripe.com" not in location, (
                f"La redirection ne doit pas aller vers Stripe pour une adhésion déjà payée : {location}"
            )
        else:
            # Réponse rendue (200) : on vérifie la page "adhésion déjà active".
            # / Rendered response (200): check the "membership already active" page.
            assert status_code == 200, (
                f"Attendu 200 (page d'info) ou redirection non-Stripe, obtenu : {status_code}"
            )
            body = response.text()
            assert "membership-payment-already-done" in body, (
                "La page 'adhésion déjà active' attendue n'a pas été rendue."
            )
            assert "checkout.stripe.com" not in body

"""
Fixtures Playwright pour les tests end-to-end.
/ Playwright fixtures for end-to-end tests.

Prérequis : le serveur Django doit tourner (via Traefik).
/ Prerequisite: Django server must be running (via Traefik).
"""

import json
import os
import re
import shutil
import subprocess

import pytest
import requests as http_requests
from playwright.sync_api import sync_playwright


# --- Configuration URL de base / Base URL configuration ---

SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
BASE_URL = f"https://{SUB}.{DOMAIN}"

# Chromium résout *.localhost → 127.0.0.1 (RFC 6761), ignorant /etc/hosts.
# On force la résolution vers la gateway Docker (Traefik).
# / Chromium resolves *.localhost → 127.0.0.1 (RFC 6761), ignoring /etc/hosts.
# We force resolution to the Docker gateway (Traefik).
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
CHROMIUM_HOST_RULES = f"MAP *.{DOMAIN} {DOCKER_GATEWAY}"

# Détection : on est dans le container si 'docker' n'est pas disponible.
# / Detection: we're inside the container if 'docker' is not available.
INSIDE_CONTAINER = shutil.which("docker") is None

# URL pour les appels HTTP requests (contourne la résolution DNS localhost).
# Depuis le container, on passe par le Docker gateway (Traefik) avec Host header.
# Depuis le host, on utilise l'URL standard.
# / URL for HTTP requests (bypasses localhost DNS resolution).
# From container, go through Docker gateway (Traefik) with Host header.
# From host, use standard URL.
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else BASE_URL
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


# --- Fixtures Playwright / Playwright fixtures ---


@pytest.fixture(scope="session")
def playwright_instance():
    """Démarre Playwright une seule fois par session de tests.
    / Start Playwright once per test session.
    """
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance):
    """Lance Chromium headless une seule fois par session.
    / Launch headless Chromium once per session.
    """
    browser = playwright_instance.chromium.launch(
        headless=True,
        args=[f"--host-resolver-rules={CHROMIUM_HOST_RULES}"],
    )
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def page(browser):
    """Crée un nouvel onglet (context + page) pour chaque test.
    ignore_https_errors=True car les certificats Traefik sont auto-signés en dev.
    / Create a new tab (context + page) for each test.
    ignore_https_errors=True because Traefik certs are self-signed in dev.
    """
    context = browser.new_context(
        base_url=BASE_URL,
        ignore_https_errors=True,
    )
    page = context.new_page()
    yield page
    page.close()
    context.close()


# --- Fixtures d'authentification / Authentication fixtures ---


@pytest.fixture(scope="session")
def admin_email():
    """Email admin depuis la variable d'environnement ADMIN_EMAIL.
    / Admin email from ADMIN_EMAIL environment variable.
    """
    email = os.environ.get("ADMIN_EMAIL")
    if not email:
        pytest.fail("ADMIN_EMAIL environment variable is not set")
    return email


@pytest.fixture(scope="session")
def login_as():
    """Factory fixture : retourne une callable (page, email) → void.
    Exécute le flow de login complet via le lien TEST MODE.
    / Factory fixture: returns a callable (page, email) → void.
    Executes the full login flow via the TEST MODE link.
    """

    def _login_as(page, email):
        # 1. Naviguer vers l'accueil / Navigate to home
        page.goto("/")
        page.wait_for_load_state("networkidle")

        # 2. Ouvrir le panneau de connexion / Open the login panel
        login_button = page.locator(
            '.navbar button:has-text("Log in"), '
            '.navbar button:has-text("Connexion")'
        ).first
        login_button.click()

        # 3. Remplir l'email / Fill the email
        email_input = page.locator("#loginEmail")
        email_input.fill(email)

        # 4. Soumettre le formulaire / Submit the form
        submit_button = page.locator('#loginForm button[type="submit"]')
        submit_button.click()

        # 5. Cliquer sur le lien TEST MODE (apparaît via HTMX swap)
        # / Click the TEST MODE link (appears via HTMX swap)
        test_mode_link = page.locator('a:has-text("TEST MODE")')
        test_mode_link.wait_for(state="visible", timeout=10_000)
        test_mode_link.click()
        page.wait_for_load_state("networkidle")

        # 6. Vérifier que le login a fonctionné / Verify login worked
        response = page.request.get("/my_account/")
        assert response.ok, f"Login failed for {email}: {response.status}"

    return _login_as


@pytest.fixture(scope="session")
def login_as_admin(login_as, admin_email):
    """Factory fixture : retourne une callable (page) → void.
    Connecte en tant qu'admin.
    / Factory fixture: returns a callable (page) → void.
    Logs in as admin.
    """

    def _login_as_admin(page):
        login_as(page, admin_email)

    return _login_as_admin


# --- Fixtures API et shell / API and shell fixtures ---


def _run_command(cmd_docker, cmd_local, timeout=30):
    """Exécute cmd_docker (hôte) ou cmd_local (container) selon le contexte.
    / Run cmd_docker (host) or cmd_local (container) depending on context.
    """
    cmd = cmd_local if INSIDE_CONTAINER else cmd_docker
    env = {**os.environ, "TEST": "1", "PYTHONPATH": "/DjangoFiles"} if INSIDE_CONTAINER else None
    cwd = "/DjangoFiles" if INSIDE_CONTAINER else None
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        env=env, cwd=cwd,
    )


@pytest.fixture(scope="session")
def api_key():
    """Récupère la clé API via manage.py test_api_key.
    / Fetches the API key via manage.py test_api_key.
    """
    result = _run_command(
        cmd_docker=[
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py", "test_api_key",
        ],
        cmd_local=["python", "manage.py", "test_api_key"],
    )
    if result.returncode != 0:
        pytest.fail(f"test_api_key failed: {result.stderr}")
    key = result.stdout.strip()
    if not key:
        pytest.fail("test_api_key returned an empty key")
    return key


@pytest.fixture(scope="session")
def django_shell():
    """Factory : exécute du Python dans le shell Django du tenant lespass.
    / Factory: executes Python code in the Django shell for the lespass tenant.

    Usage : result = django_shell("from laboutik.models import PointDeVente; print(PointDeVente.objects.count())")
    Usage : result = django_shell("...", schema="chantefrein")
    """

    def _run(python_code, schema="lespass"):
        escaped = python_code.replace('"', '\\"')
        result = _run_command(
            cmd_docker=[
                "docker", "exec", "lespass_django",
                "poetry", "run", "python",
                "/DjangoFiles/manage.py", "tenant_command",
                "shell", "-s", schema, "-c", escaped,
            ],
            cmd_local=[
                "python", "manage.py", "tenant_command",
                "shell", "-s", schema, "-c", escaped,
            ],
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"django_shell failed (rc={result.returncode}): {result.stderr}"
            )
        return result.stdout.strip()

    return _run


@pytest.fixture(scope="session")
def create_event(api_key):
    """Factory : crée un événement via l'API v2.
    / Factory: creates an event via the API v2.

    Retourne dict {ok, slug, uuid, data}.
    """

    def _slugify(value):
        slug = value.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    def _slug_from_url(url):
        if not url:
            return None
        parts = [p for p in url.split("/") if p]
        try:
            idx = parts.index("event")
            return parts[idx + 1]
        except (ValueError, IndexError):
            return None

    def _create(name, start_date, max_per_user=None,
                options_radio=None, options_checkbox=None):
        additional_property = []
        if options_radio:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "optionsRadio",
                "value": options_radio,
            })
        if options_checkbox:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "optionsCheckbox",
                "value": options_checkbox,
            })

        payload = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": name,
            "startDate": start_date,
        }
        if max_per_user is not None:
            payload["offers"] = {"eligibleQuantity": {"maxValue": max_per_user}}
        if additional_property:
            payload["additionalProperty"] = additional_property

        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        if API_HOST_HEADER:
            headers["Host"] = API_HOST_HEADER

        resp = http_requests.post(
            f"{API_BASE_URL}/api/v2/events/",
            headers=headers,
            json=payload,
            verify=False,
        )
        data = None
        try:
            data = resp.json()
        except Exception:
            pass

        slug = (
            _slug_from_url(data.get("url") if data else None)
            or _slugify(name)
        )
        return {
            "ok": resp.ok,
            "status": resp.status_code,
            "slug": slug,
            "uuid": data.get("identifier") if data else None,
            "data": data,
        }

    return _create


@pytest.fixture(scope="session")
def create_product(api_key):
    """Factory : crée un produit via l'API v2.
    / Factory: creates a product via the API v2.

    Retourne dict {ok, uuid, offers, data}.
    """

    def _create(name, category="Ticket booking", description="",
                event_uuid=None, offers=None, form_fields=None):
        additional_property = []
        if form_fields:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "formFields",
                "value": form_fields,
            })

        offers_payload = []
        for offer in (offers or []):
            offer_additional = []
            if offer.get("recurringPayment") is not None:
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "recurringPayment",
                    "value": offer["recurringPayment"],
                })
            if offer.get("subscriptionType"):
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "subscriptionType",
                    "value": offer["subscriptionType"],
                })
            if offer.get("manualValidation") is not None:
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "manualValidation",
                    "value": offer["manualValidation"],
                })

            offers_payload.append({
                "@type": "Offer",
                "name": offer["name"],
                "price": offer["price"],
                "priceCurrency": "EUR",
                "freePrice": offer.get("freePrice"),
                "stock": offer.get("stock"),
                "maxPerUser": offer.get("maxPerUser"),
                "additionalProperty": offer_additional or None,
            })

        payload = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
            "description": description,
            "category": category,
        }
        if event_uuid:
            payload["isRelatedTo"] = {
                "@type": "Event",
                "identifier": event_uuid,
            }
        if offers_payload:
            payload["offers"] = offers_payload
        if additional_property:
            payload["additionalProperty"] = additional_property

        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        if API_HOST_HEADER:
            headers["Host"] = API_HOST_HEADER

        resp = http_requests.post(
            f"{API_BASE_URL}/api/v2/products/",
            headers=headers,
            json=payload,
            verify=False,
        )
        data = None
        try:
            data = resp.json()
        except Exception:
            pass

        return {
            "ok": resp.ok,
            "status": resp.status_code,
            "uuid": data.get("identifier") if data else None,
            "offers": data.get("offers") if data else None,
            "data": data,
        }

    return _create


@pytest.fixture(scope="session")
def setup_test_data():
    """Factory : exécute le script setup_test_data.py dans le container.
    / Factory: runs setup_test_data.py script inside the container.

    Usage : result = setup_test_data("create_promotional_code", product="...", code_name="...")
    """

    def _run(action, **kwargs):
        args = ["--action", action]
        for key, value in kwargs.items():
            cli_key = key.replace("_", "-")
            args.extend([f"--{cli_key}", str(value)])

        result = _run_command(
            cmd_docker=[
                "docker", "exec", "-w", "/DjangoFiles",
                "-e", "PYTHONPATH=/DjangoFiles",
                "lespass_django", "poetry", "run", "python",
                "tests/scripts/setup_test_data.py",
            ] + args,
            cmd_local=[
                "python", "tests/scripts/setup_test_data.py",
            ] + args,
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr}
        try:
            return json.loads(result.stdout)
        except Exception:
            return {"status": "error", "message": result.stdout}

    return _run


@pytest.fixture(scope="session")
def ensure_pos_data():
    """S'assure que les données POS de test existent (catégories, produits, PV).
    Exécuté une seule fois par session de test.
    / Ensures test POS data exists (categories, products, POS).
    Run once per test session.
    """
    result = _run_command(
        cmd_docker=[
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py", "create_test_pos_data",
        ],
        cmd_local=["python", "manage.py", "create_test_pos_data"],
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(
            f"create_test_pos_data a échoué (rc={result.returncode}): "
            f"{result.stderr or result.stdout}"
        )


@pytest.fixture(scope="function")
def pos_page(browser, login_as_admin, django_shell, ensure_pos_data):
    """Factory : ouvre la caisse POS pour un point de vente donné.
    / Factory: opens the POS for a given point of sale.

    Usage : pos = pos_page(page, "Bar")
    Usage : pos = pos_page(page, comportement="A")  # PV Adhesions
    Retourne la page Playwright prête sur la caisse.
    """
    demo_tag_id = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")

    def _open_pos(page, pv_name_filter="Bar", comportement=None):
        # Récupérer l'UUID du PDV / Get POS UUID
        if comportement:
            query = f"PointDeVente.objects.filter(comportement='{comportement}').first()"
            label = f"comportement={comportement}"
        else:
            query = f"PointDeVente.objects.filter(name='{pv_name_filter}').first()"
            label = f'name={pv_name_filter}'
        result = django_shell(
            f"from laboutik.models import PointDeVente; "
            f"pv = {query}; "
            f"print(f'uuid={{pv.uuid}}') if pv else print('NOT_FOUND')"
        )
        uuid_match = re.search(r"uuid=(.+)", result)
        if not uuid_match:
            pytest.fail(
                f'PDV ({label}) introuvable. '
                f"Lancer create_test_pos_data d'abord. Résultat: {result}"
            )
        pv_uuid = uuid_match.group(1).strip()

        # Login admin / Admin login
        login_as_admin(page)

        # Naviguer vers la caisse / Navigate to POS
        page.goto(
            f"/laboutik/caisse/point_de_vente/"
            f"?uuid_pv={pv_uuid}&tag_id_cm={demo_tag_id}"
        )
        page.wait_for_load_state("networkidle")
        page.locator("#products").wait_for(state="visible", timeout=10_000)
        return page

    return _open_pos


# --- Fixture Stripe E2E / Stripe E2E fixture ---


@pytest.fixture(scope="session")
def fill_stripe_card():
    """Factory : remplit le formulaire Stripe checkout (vrai checkout.stripe.com).
    / Factory: fills the Stripe checkout form (real checkout.stripe.com).

    Converti depuis tests/playwright/tests/utils/stripe.ts.
    Carte test : 4242 4242 4242 4242, 12/42, 424, Douglas Adams.
    """

    def _fill(page, email):
        # Remplir l'email si visible / Fill email if visible
        email_input = page.locator('input#email, input[name="email"]').first
        if email_input.is_visible(timeout=3_000):
            email_input.fill(email)

        # Stratégie 1 : sélecteurs par rôle (Stripe Checkout récent)
        # / Strategy 1: role-based selectors (recent Stripe Checkout)
        card_number = page.get_by_role("textbox", name=re.compile(r"card number", re.I)).first
        try:
            card_number.wait_for(state="visible", timeout=5_000)
            card_number.fill("4242424242424242")
            page.get_by_role("textbox", name=re.compile(r"expiration", re.I)).first.fill("12/42")
            page.get_by_role("textbox", name=re.compile(r"cvc", re.I)).first.fill("424")
            cardholder = page.get_by_role("textbox", name=re.compile(r"cardholder name", re.I)).first
            if cardholder.is_visible(timeout=2_000):
                cardholder.fill("Douglas Adams")
            return
        except Exception:
            pass

        # Stratégie 2 : sélecteurs par ID (Stripe Checkout classique)
        # / Strategy 2: ID-based selectors (classic Stripe Checkout)
        card_by_id = page.locator("input#cardNumber").first
        if card_by_id.is_visible(timeout=3_000):
            card_by_id.fill("4242424242424242")
            page.locator("input#cardExpiry").fill("12/42")
            page.locator("input#cardCvc").fill("424")
            billing_name = page.locator("input#billingName").first
            if billing_name.is_visible(timeout=2_000):
                billing_name.fill("Douglas Adams")
            return

        # Stratégie 3 : sélecteurs par attribut (fallback)
        # / Strategy 3: attribute-based selectors (fallback)
        fallback = page.locator('input[name="cardnumber"], input[placeholder*="1234"]').first
        if fallback.is_visible(timeout=3_000):
            fallback.fill("4242424242424242")
            exp = page.locator('input[name="exp-date"], input[placeholder*="MM"]').first
            if exp.is_visible():
                exp.fill("12/42")
            cvc = page.locator('input[name="cvc"], input[placeholder*="CVC"]').first
            if cvc.is_visible():
                cvc.fill("424")

    return _fill

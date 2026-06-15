"""
Tests E2E : adhesion obligatoire sur le formulaire de reservation d'un event.
/ E2E tests: mandatory membership on the event booking form.

Conversion de tests/playwright/tests/38-event-adhesion-obligatoire-check.spec.ts

Flow :
1. API : cree produit adhesion + produit billet avec adhesion requise + event.
2. Login, va sur la page event -> verifie que "S'abonner pour acceder" est affiche.
3. API : cree une adhesion GRATUITE pour l'utilisateur.
4. Recharge la page event -> verifie que le compteur de reservation (bs-counter) est visible.
"""

import datetime
import os
import random
import shutil
import string

import pytest
import requests as http_requests


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Meme logique que tests/e2e/conftest.py : depuis le container on passe par
# le Docker gateway (Traefik) avec un header Host ; depuis l'hote, URL directe.
# / Same logic as tests/e2e/conftest.py: from container, go through the
# Docker gateway (Traefik) with a Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = (
    f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
)
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Genere un suffixe unique (DB dev partagee, pas de rollback).
    / Generates a unique suffix (shared dev DB, no rollback).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification API v2.
    / Builds API v2 authentication headers.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_product_with_membership_required(
    api_key, name, description, category, event_uuid,
    offer_name, offer_price, membership_required_product_uuid
):
    """Cree un produit billet avec adhesion obligatoire via POST /api/v2/products/.
    Le conftest create_product ne supporte pas membershipRequiredProduct, on
    fait donc un appel HTTP direct ici.
    / Creates a ticket product with mandatory membership via POST /api/v2/products/.
    The conftest create_product fixture doesn't support membershipRequiredProduct,
    so we make a direct HTTP call here.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "category": category,
        "isRelatedTo": {
            "@type": "Event",
            "identifier": event_uuid,
        },
        "offers": [
            {
                "@type": "Offer",
                "name": offer_name,
                "price": offer_price,
                "priceCurrency": "EUR",
                "membershipRequiredProduct": membership_required_product_uuid,
            }
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
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "uuid": data.get("identifier") if data else None,
        "offers": data.get("offers") if data else None,
        "data": data,
    }


def _create_membership_api(api_key, price_uuid, email, first_name="Test", last_name="Adherent", payment_mode="FREE"):
    """Cree une adhesion gratuite via POST /api/v2/memberships/.
    Equivalent de createMembershipApi dans tests/playwright/tests/utils/api.ts.
    / Creates a FREE membership via POST /api/v2/memberships/.
    Equivalent of createMembershipApi in tests/playwright/tests/utils/api.ts.
    """
    valid_until = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).isoformat()

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
        "validUntil": valid_until,
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "paymentMode",
                "value": payment_mode,
            },
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


class TestAdhesionObligatoireCheck:
    """Adhesion obligatoire sur event / Mandatory membership on event booking."""

    def test_block_booking_without_membership_then_allow_after_subscribing(
        self, page, api_key, create_event, create_product, login_as, django_shell
    ):
        """Verifie le blocage de reservation sans adhesion puis l'acces apres souscription.
        / Verifies booking is blocked without membership, then allowed after subscribing.

        Flow complet :
        1. Cree un produit adhesion (gratuit, subscriptionType=Y).
        2. Cree un event + produit billet avec adhesion obligatoire.
        3. Login user sans adhesion -> verifie alerte + compteur absent.
        4. Cree l'adhesion via API -> recharge la page -> verifie compteur visible.
        """
        random_id = _random_id()
        membership_product_name = f"Adhesion Event Test {random_id}"
        ticket_product_name = f"Billet Adh Required {random_id}"
        event_name = f"Event Adh Test {random_id}"
        user_email = f"testadh+{random_id}@pm.me"

        # --- Etape 1 : Creer le produit adhesion ---
        # subscriptionType=Y (annuelle), prix 0.00 (gratuit).
        # / Step 1: Create the membership product.
        # subscriptionType=Y (yearly), price 0.00 (free).
        membership_response = create_product(
            name=membership_product_name,
            description="Adhesion de test pour verifier le blocage sur event",
            category="Membership",
            offers=[
                {
                    "name": "Tarif adhesion gratuit",
                    "price": "0.00",
                    "subscriptionType": "Y",
                },
            ],
        )
        assert membership_response["ok"], (
            f"Creation produit adhesion echouee: {membership_response}"
        )
        membership_product_uuid = membership_response["uuid"]
        assert membership_product_uuid, (
            f"UUID produit adhesion manquant: {membership_response}"
        )

        membership_offers = membership_response.get("offers") or []
        assert membership_offers, (
            f"Aucune offre retournee pour le produit adhesion: {membership_response}"
        )
        membership_price_uuid = membership_offers[0].get("identifier") or ""
        assert membership_price_uuid, (
            f"UUID tarif adhesion manquant: {membership_offers}"
        )

        # --- Etape 2 : Creer l'event ---
        # Date de debut dans 7 jours.
        # / Step 2: Create the event. Start date in 7 days.
        start_date = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7)
        ).isoformat()

        event_response = create_event(name=event_name, start_date=start_date)
        assert event_response["ok"], f"Creation event echouee: {event_response}"
        event_slug = event_response["slug"]
        event_uuid = event_response["uuid"]
        assert event_slug, f"Slug event manquant: {event_response}"
        assert event_uuid, f"UUID event manquant: {event_response}"

        # --- Etape 3 : Creer le produit billet avec adhesion obligatoire ---
        # On passe directement membershipRequiredProduct dans l'offre via un
        # appel HTTP direct (le conftest create_product ne supporte pas ce champ).
        # / Step 3: Create the ticket product with mandatory membership.
        # We pass membershipRequiredProduct directly via HTTP call (conftest
        # create_product fixture doesn't support this field).
        ticket_response = _create_product_with_membership_required(
            api_key=api_key,
            name=ticket_product_name,
            description="Billet accessible uniquement aux adherents",
            category="Ticket booking",
            event_uuid=event_uuid,
            offer_name="Place adherent",
            offer_price="5.00",
            membership_required_product_uuid=membership_product_uuid,
        )
        assert ticket_response["ok"], (
            f"Creation produit billet avec adhesion requise echouee: {ticket_response}"
        )
        ticket_offers = ticket_response.get("offers") or []
        assert ticket_offers, (
            f"Aucune offre retournee pour le produit billet: {ticket_response}"
        )
        ticket_price_uuid = ticket_offers[0].get("identifier") or ""
        assert ticket_price_uuid, (
            f"UUID tarif billet manquant: {ticket_offers}"
        )

        # --- Etape 4 : Creer l'user en DB puis se connecter ---
        # force_login requiert un user existant et actif en DB.
        # On cree le user via le shell Django avant de l'utiliser dans login_as.
        # (Le spec TS utilisait loginAs qui creait l'user via le lien email TEST MODE.)
        # / Step 4: Create the user in DB then log in.
        # force_login requires an existing, active user in DB.
        # We create the user via Django shell before calling login_as.
        # (The TS spec used loginAs which created the user via the TEST MODE email link.)
        shell_output = django_shell(
            "from django.contrib.auth import get_user_model; "
            f"u, created = get_user_model().objects.get_or_create(email='{user_email}', "
            "defaults={'is_active': True, 'username': '" + user_email + "'}); "
            "u.is_active = True; u.save(); "
            "print('USER_READY')"
        )
        assert "USER_READY" in shell_output, (
            f"Creation/activation user echouee: {shell_output}"
        )
        login_as(page, user_email)

        # --- Etape 5 : Aller sur la page event et verifier le blocage ---
        # On cherche le bouton de reservation et on l'ouvre.
        # / Step 5: Go to event page and verify blocking.
        # We find the booking button and open the panel.
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")

        # Ouvrir le panneau de reservation (bouton "book" ou "reserver").
        # / Open the booking panel ("book" or "reserver" button).
        reserve_button = page.locator(
            'button:has-text("book"), button:has-text("Reserver"), '
            'button:has-text("réserver"), button:has-text("Reserver"), '
            'button:has-text("one or more seats")'
        ).first
        reserve_button.wait_for(state="visible", timeout=10000)
        reserve_button.click()

        # Attendre l'ouverture du panneau (offcanvas ou bookingPanel).
        # / Wait for the panel to open (offcanvas or bookingPanel).
        page.wait_for_selector(
            "#bookingPanel.show, .offcanvas.show",
            state="visible",
            timeout=10000,
        )

        # Verifier que l'alerte ".alert-info" contenant le nom du produit adhesion
        # est visible. Cette alerte indique a l'utilisateur qu'il doit s'abonner.
        # / Verify that the ".alert-info" alert containing the membership product
        # name is visible. This alert tells the user they must subscribe.
        subscribe_alert = page.locator(".alert-info").filter(has_text=membership_product_name)
        subscribe_alert.wait_for(state="visible", timeout=5000)

        # Verifier que le lien dans l'alerte pointe vers la page adhesions.
        # / Verify that the link in the alert points to the memberships page.
        membership_link = subscribe_alert.locator('a[href*="/memberships/"]')
        assert membership_link.count() > 0, (
            "Le lien vers /memberships/ est absent dans l'alerte"
        )
        link_text = membership_link.inner_text()
        assert membership_product_name in link_text, (
            f"Le lien d'adhesion devrait contenir '{membership_product_name}', "
            f"texte actuel : '{link_text}'"
        )

        # Verifier que le bs-counter n'est PAS present pour ce tarif.
        # (L'utilisateur ne peut pas reserver sans adhesion.)
        # / Verify the bs-counter is NOT present for this price.
        # (User cannot book without membership.)
        counter = page.locator(f'[data-testid="booking-amount-{ticket_price_uuid}"]')
        assert counter.count() == 0, (
            f"Le compteur de reservation devrait etre absent pour le tarif {ticket_price_uuid}"
        )

        # --- Etape 6 : Creer l'adhesion via API ---
        # On cree une adhesion gratuite pour l'utilisateur, puis on active son
        # compte si necessaire (force_login peut creer un user inactif).
        # / Step 6: Create the membership via API.
        # We create a free membership for the user, then activate the account
        # if needed (force_login may create an inactive user).
        membership_result = _create_membership_api(
            api_key=api_key,
            price_uuid=membership_price_uuid,
            email=user_email,
            first_name="Test",
            last_name="Adherent",
            payment_mode="FREE",
        )
        assert membership_result["ok"], (
            f"Creation adhesion gratuite echouee: {membership_result}"
        )

        # --- Etape 7 : Recharger la page et verifier l'acces ---
        # Apres l'adhesion, l'alerte doit disparaitre et le compteur doit
        # etre visible.
        # / Step 7: Reload the page and verify access.
        # After subscribing, the alert must disappear and the counter must
        # be visible.
        page.reload()
        page.wait_for_load_state("domcontentloaded")

        # Ré-ouvrir le panneau de reservation.
        # / Re-open the booking panel.
        reserve_button_after = page.locator(
            'button:has-text("book"), button:has-text("Reserver"), '
            'button:has-text("réserver"), button:has-text("Reserver"), '
            'button:has-text("one or more seats")'
        ).first
        reserve_button_after.wait_for(state="visible", timeout=10000)
        reserve_button_after.click()

        page.wait_for_selector(
            "#bookingPanel.show, .offcanvas.show",
            state="visible",
            timeout=10000,
        )

        # Verifier que l'alerte a disparu (plus d'adhesion obligatoire).
        # / Verify the alert is gone (no more mandatory membership message).
        subscribe_alert_after = page.locator(".alert-info").filter(
            has_text=membership_product_name
        )
        assert subscribe_alert_after.count() == 0, (
            "L'alerte d'adhesion obligatoire devrait avoir disparu apres souscription"
        )

        # Verifier que le bs-counter EST maintenant visible pour ce tarif.
        # / Verify the bs-counter IS now visible for this price.
        counter_after = page.locator(f'[data-testid="booking-amount-{ticket_price_uuid}"]')
        counter_after.wait_for(state="visible", timeout=5000)
        assert counter_after.count() > 0, (
            f"Le compteur de reservation devrait etre visible apres adhesion "
            f"pour le tarif {ticket_price_uuid}"
        )

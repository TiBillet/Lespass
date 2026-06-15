"""
Tests E2E : récapitulatif du compte utilisateur (adhésions et réservations).
/ E2E tests: user account summary (memberships and bookings).

Conversion de tests/playwright/tests/16-user-account-summary.spec.ts

Objectifs :
1. Créer une réservation et une adhésion pour un utilisateur (via API v2).
2. Se connecter en tant que cet utilisateur.
3. Vérifier que les deux apparaissent dans les pages "Mon compte".

/ Objectives:
1. Create a reservation and a membership for a user (via API v2).
2. Login as this user.
3. Verify both are listed in the account pages.
"""

import datetime
import os
import random
import string

import pytest
import requests as http_requests
import shutil


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Même logique que tests/e2e/conftest.py : depuis le container on passe par
# le Docker gateway (Traefik) avec un header Host ; depuis l'hôte, URL directe.
# / Same logic as tests/e2e/conftest.py: from container, go through the
# Docker gateway (Traefik) with a Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Génère un suffixe unique (DB dev partagée, pas de rollback).
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


def _create_reservation_api(api_key, event_uuid, email, price_uuid, qty=1, confirmed=True):
    """Crée une réservation via POST /api/v2/reservations/ (schema.org Reservation).
    Équivalent de createReservationApi dans tests/playwright/tests/utils/api.ts.
    / Creates a reservation via POST /api/v2/reservations/ (schema.org Reservation).
    Equivalent of createReservationApi in tests/playwright/tests/utils/api.ts.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {
            "@type": "Event",
            "identifier": event_uuid,
        },
        "underName": {
            "@type": "Person",
            "email": email,
        },
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": price_uuid,
                "ticketQuantity": qty,
            },
        ],
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "confirmed",
                "value": confirmed,
            },
        ],
    }
    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/reservations/",
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
    return {"ok": resp.ok, "status": resp.status_code, "data": data, "text": resp.text[:500]}


def _create_membership_api(api_key, price_uuid, email, valid_until, payment_mode="FREE"):
    """Crée une adhésion via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Équivalent de createMembershipApi dans tests/playwright/tests/utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Equivalent of createMembershipApi in tests/playwright/tests/utils/api.ts.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": "API",
            "familyName": "Member",
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
    return {"ok": resp.ok, "status": resp.status_code, "data": data, "text": resp.text[:500]}


class TestUserAccountSummary:
    """Récapitulatif compte utilisateur / User account summary."""

    def test_account_shows_all_memberships_and_bookings(
        self, page, api_key, create_event, create_product, login_as, django_shell
    ):
        """Le compte utilisateur affiche les réservations ET les adhésions.
        / The user account shows both bookings AND memberships.
        """
        random_id = _random_id()
        event_name = f"E2E Summary Event {random_id}"
        product_name = f"Billets Summary {random_id}"
        membership_product_name = f"Adhesion Summary {random_id}"
        membership_price_name = "Annuelle"
        user_email = f"jturbeaux+summary{random_id}@pm.me"

        # Date de début : demain (ISO 8601, UTC).
        # / Start date: tomorrow (ISO 8601, UTC).
        start_date = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=1)
        ).isoformat()

        # --- Étape 1 : Créer une réservation gratuite via API ---
        # Event + produit "Free booking" + réservation confirmée pour l'email.
        # / Step 1: Create a free booking via API.
        # Event + "Free booking" product + confirmed reservation for the email.
        event_response = create_event(name=event_name, start_date=start_date)
        assert event_response["ok"], f"Création event échouée: {event_response}"
        event_uuid = event_response["uuid"]
        assert event_uuid, f"UUID event manquant: {event_response}"

        product_response = create_product(
            name=product_name,
            description="Produit pour test compte utilisateur.",
            category="Free booking",
            event_uuid=event_uuid,
            offers=[
                {"name": "Tarif gratuit", "price": "0.00"},
            ],
        )
        assert product_response["ok"], f"Création produit échouée: {product_response}"
        offers = product_response.get("offers") or []
        assert offers, f"Aucune offre retournée par l'API: {product_response}"
        price_uuid = offers[0].get("identifier") or ""
        assert price_uuid != "", f"UUID du tarif manquant: {offers}"

        reservation_response = _create_reservation_api(
            api_key=api_key,
            event_uuid=event_uuid,
            email=user_email,
            price_uuid=price_uuid,
            qty=1,
            confirmed=True,
        )
        assert reservation_response["ok"], (
            f"Création réservation échouée: {reservation_response}"
        )

        # --- Étape 2 : Connexion en tant que cet utilisateur ---
        # L'API réservation crée le user avec is_active=False (contrairement à
        # l'API adhésion). Or force_login + ModelBackend rejette les users
        # inactifs sur les requêtes suivantes (cf. PIEGES.md 9.88). Le flow TS
        # `loginAs` passait par le lien email TEST MODE, qui activait le compte.
        # On reproduit cette activation en DB avant le login.
        # NB : pas de guillemets doubles dans le code shell (échappement conftest).
        # / Step 2: Login as this user.
        # The reservation API creates the user with is_active=False (unlike the
        # membership API). force_login + ModelBackend rejects inactive users on
        # subsequent requests (see PIEGES.md 9.88). The TS `loginAs` flow used
        # the TEST MODE email link, which activated the account. We replicate
        # that activation in DB before logging in.
        shell_output = django_shell(
            "from django.contrib.auth import get_user_model; "
            f"get_user_model().objects.filter(email__iexact='{user_email}')"
            ".update(is_active=True); "
            "print('USER_ACTIVATED')"
        )
        assert "USER_ACTIVATED" in shell_output, (
            f"Activation du user échouée: {shell_output}"
        )

        login_as(page, user_email)

        # --- Étape 3 : Vérifier la réservation dans le compte ---
        # On vérifie que le nom de l'event (suffixe unique) apparaît dans la
        # page "Mes réservations" — pas d'assertion sur des comptages globaux.
        # / Step 3: Verify the booking in the account page.
        # We check the event name (unique suffix) appears in "My bookings" —
        # no assertion on global counts.
        page.goto("/my_account/my_reservations/")
        page.wait_for_load_state("domcontentloaded")

        content = page.locator("body").inner_text()
        assert event_name in content, (
            f"Réservation '{event_name}' introuvable dans /my_account/my_reservations/"
        )

        # --- Étape 4 : Créer une adhésion via API (pendant la session) ---
        # / Step 4: Create a membership via API (while logged in).
        membership_product_response = create_product(
            name=membership_product_name,
            description="Produit adhesion pour test compte.",
            category="Membership",
            offers=[
                {"name": membership_price_name, "price": "10.00"},
            ],
        )
        assert membership_product_response["ok"], (
            f"Création produit adhésion échouée: {membership_product_response}"
        )

        # On cherche l'offre par son nom (comme le spec TS), au cas où le
        # produit aurait plusieurs tarifs.
        # / Find the offer by name (like the TS spec), in case the product
        # has several prices.
        membership_offers = membership_product_response.get("offers") or []
        membership_price_uuid = ""
        for offer in membership_offers:
            if offer.get("name") == membership_price_name:
                membership_price_uuid = offer.get("identifier") or ""
                break
        assert membership_price_uuid != "", (
            f"Tarif '{membership_price_name}' introuvable: {membership_offers}"
        )

        # Validité : dans 30 jours (ISO 8601, UTC).
        # / Validity: 30 days from now (ISO 8601, UTC).
        valid_until = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30)
        ).isoformat()

        membership_response = _create_membership_api(
            api_key=api_key,
            price_uuid=membership_price_uuid,
            email=user_email,
            valid_until=valid_until,
            payment_mode="FREE",
        )
        assert membership_response["ok"], (
            f"Création adhésion échouée: {membership_response}"
        )

        # --- Étape 5 : Vérifier l'adhésion dans le compte ---
        # Le nom du produit adhésion (suffixe unique) doit apparaître dans la
        # page "Mes adhésions".
        # / Step 5: Verify the membership in the account page.
        # The membership product name (unique suffix) must appear in
        # "My memberships".
        page.goto("/my_account/membership/")
        page.wait_for_load_state("domcontentloaded")

        content = page.locator("body").inner_text()
        assert membership_product_name in content, (
            f"Adhésion '{membership_product_name}' introuvable dans /my_account/membership/"
        )

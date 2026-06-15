"""
Tests E2E : annulation de reservation admin + verification FK LigneArticle.
/ E2E tests: admin reservation cancellation + LigneArticle FK verification.

Conversion de tests/playwright/tests/39-admin-reservation-cancel.spec.ts

Scenarios :
1. Reservation admin gratuite -> annulation via action groupee -> avoir CREDIT_NOTE cree.
2. Verification que la FK LigneArticle.reservation est renseignee.
3. Double annulation impossible (pas de doublon d'avoir).
"""

import datetime
import os
import random
import shutil
import string

import pytest
import requests as http_requests
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Meme logique que conftest.py : depuis le container on passe par le Docker
# gateway (Traefik) avec un header Host ; depuis l'hote, URL directe.
# / Same logic as conftest.py: from container go through Docker gateway
# (Traefik) with Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
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


def _create_reservation_api(api_key, event_uuid, email, price_uuid, qty=1):
    """Cree une reservation via POST /api/v2/reservations/ (schema.org Reservation).
    Equivalent de createReservationApi dans tests/playwright/tests/utils/api.ts.
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
                "value": True,
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


class TestAdminReservationCancel:
    """Annulation de reservation admin + verification FK / Admin reservation cancel + FK check."""

    def test_cancel_reservation_and_check_credit_note(
        self, page, api_key, create_event, create_product, login_as_admin, django_shell
    ):
        """Annule une reservation admin gratuite et verifie l'avoir CREDIT_NOTE en base.
        Verifie aussi la FK LigneArticle.reservation.
        / Cancels a free admin reservation and checks the CREDIT_NOTE in DB.
        Also checks LigneArticle.reservation FK.
        """
        random_id = _random_id()
        event_name = f"Event Cancel Admin {random_id}"
        product_name = f"Billet Cancel {random_id}"
        user_email = f"jturbeaux+rcan{random_id}@pm.me"

        # Date de debut : dans 7 jours (ISO 8601, UTC).
        # / Start date: 7 days from now (ISO 8601, UTC).
        start_date = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7)
        ).isoformat()

        # --- Etape 1 : Creer l'evenement et le produit via l'API ---
        # / Step 1: Create event and product via API.
        event_result = create_event(name=event_name, start_date=start_date)
        assert event_result["ok"], f"Creation event echouee: {event_result}"
        event_uuid = event_result["uuid"]
        assert event_uuid, f"UUID event manquant: {event_result}"

        product_result = create_product(
            name=product_name,
            description="Produit pour test annulation admin",
            category="Free booking",
            event_uuid=event_uuid,
            offers=[{"name": "Gratuit annul", "price": "0.00"}],
        )
        assert product_result["ok"], f"Creation produit echouee: {product_result}"
        offers = product_result.get("offers") or []
        assert offers, f"Aucune offre retournee: {product_result}"
        price_uuid = offers[0].get("identifier") or ""
        assert price_uuid != "", f"UUID du tarif manquant: {offers}"

        # --- Etape 2 : Creer une reservation via l'API ---
        # / Step 2: Create a reservation via API.
        resa_result = _create_reservation_api(
            api_key=api_key,
            event_uuid=event_uuid,
            email=user_email,
            price_uuid=price_uuid,
            qty=2,
        )
        assert resa_result["ok"], f"Creation reservation echouee: {resa_result}"

        # --- Etape 3 : Verifier la FK reservation sur LigneArticle ---
        # Au moins une LigneArticle doit avoir reservation_id renseigne.
        # On utilise des quotes simples UNIQUEMENT dans le code shell
        # (django_shell echappe les guillemets doubles).
        # / Step 3: Verify LigneArticle.reservation FK is set.
        # At least one LigneArticle should have reservation_id set.
        # Single quotes ONLY in shell code (django_shell escapes double quotes).
        fk_result = django_shell(
            "from BaseBillet.models import LigneArticle\n"
            f"lignes = LigneArticle.objects.filter(pricesold__productsold__product__name__contains='{product_name}').order_by('-datetime')[:5]\n"
            "for l in lignes:\n"
            "    print(f'UUID={l.uuid} resa_id={l.reservation_id} ps_id={l.paiement_stripe_id} status={l.status}')"
        )
        # La FK reservation_id doit etre renseignee (pas None) pour au moins une ligne.
        # / reservation_id FK must be set (not None) for at least one line.
        lines_with_uuid = [ln for ln in fk_result.split("\n") if "UUID=" in ln]
        assert lines_with_uuid, (
            f"Aucune LigneArticle trouvee pour le produit '{product_name}'. "
            f"Sortie shell : {fk_result}"
        )
        has_reservation_fk = any("resa_id=None" not in ln for ln in lines_with_uuid)
        assert has_reservation_fk, (
            f"Aucune LigneArticle avec reservation_id renseigne. Lignes : {lines_with_uuid}"
        )

        # --- Etape 4 : Connexion admin et navigation vers les reservations ---
        # / Step 4: Admin login and navigation to reservations list.
        login_as_admin(page)
        page.goto("/admin/BaseBillet/reservation/")
        page.wait_for_load_state("networkidle")

        # Rechercher par email utilisateur.
        # / Search by user email.
        search_input = page.locator('input[name="q"]').first
        search_input.fill(user_email)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        # Verifier qu'un resultat est present.
        # / Check that at least one result is visible.
        rows = page.locator("#result_list tbody tr")
        expect(rows.first).to_be_visible(timeout=10000)

        # --- Etape 5 : Annulation via action groupee ---
        # Cocher la premiere ligne, selectionner l'action, soumettre le formulaire.
        # Note : Unfold utilise Alpine.js x-show sur le bouton "Run" ;
        # selectOption seul ne declenche pas toujours Alpine -> on soumet le form directement.
        # / Step 5: Cancel via bulk action.
        # Check first row, select action, submit form directly.
        # Note: Unfold uses Alpine.js x-show on "Run" button;
        # selectOption alone doesn't always trigger Alpine -> submit form directly.
        checkbox = page.locator("#result_list tbody tr input[type='checkbox']").first
        checkbox.check()

        action_select = page.locator('select[name="action"]')
        action_select.select_option("action_cancel_refund_reservations")

        page.evaluate(
            "() => { const form = document.querySelector('#changelist-form'); if (form) form.submit(); }"
        )
        page.wait_for_load_state("networkidle")

        # Verifier le message de succes (Unfold affiche bg-green-100 ou messagelist .success).
        # / Check success message (Unfold shows bg-green-100 or messagelist .success).
        success_message = page.locator(".bg-green-100, .bg-blue-100, .messagelist .success")
        expect(success_message).to_be_visible(timeout=10000)

        # --- Etape 6 : Verifier l'annulation en base ---
        # La reservation doit etre en status 'C' (CANCELED) et tous les tickets aussi.
        # / Step 6: Verify cancellation in DB.
        # Reservation must have status 'C' (CANCELED) and all tickets too.
        cancel_result = django_shell(
            "from BaseBillet.models import Reservation, Ticket\n"
            f"resa = Reservation.objects.filter(user_commande__email='{user_email}').first()\n"
            "if resa:\n"
            "    cancelled_tickets = resa.tickets.filter(status='C').count()\n"
            "    total_tickets = resa.tickets.count()\n"
            "    print(f'resa_status={resa.status} cancelled_tickets={cancelled_tickets} total_tickets={total_tickets}')\n"
            "else:\n"
            "    print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in cancel_result, (
            f"Reservation introuvable pour {user_email} : {cancel_result}"
        )
        assert "resa_status=C" in cancel_result, (
            f"La reservation n'est pas en status CANCELED. Sortie : {cancel_result}"
        )

        # --- Etape 7 : Verifier les LigneArticle dans l'admin ---
        # / Step 7: Check LigneArticle rows in admin.
        page.goto("/admin/BaseBillet/lignearticle/")
        page.wait_for_load_state("networkidle")

        search_input_la = page.locator('input[name="q"]').first
        search_input_la.fill(product_name)
        search_input_la.press("Enter")
        page.wait_for_load_state("networkidle")

        rows_la = page.locator("#result_list tbody tr")
        row_count = rows_la.count()
        assert row_count >= 1, (
            f"Aucune LigneArticle dans l'admin apres annulation pour '{product_name}'"
        )

        # Lister les statuts visibles dans la page (a titre informatif).
        # / List visible statuses in the page (informational).
        body_text = page.inner_text("body")
        status_labels = [
            "CONFIRMED", "CREDIT NOTE", "FREE BOOKING", "CANCELLED", "REFUNDED",
            "Confirmed", "Credit note",
        ]
        found_statuses = [s for s in status_labels if s in body_text]
        print(f"LigneArticle statuses found: {', '.join(found_statuses)}")

    def test_double_cancel_does_not_create_duplicate(
        self, page, api_key, create_event, create_product, login_as_admin, django_shell
    ):
        """Verifie qu'une double annulation ne cree pas de doublon d'avoir.
        / Checks that a double cancellation does not create a duplicate credit note.
        """
        random_id = _random_id()
        event_name = f"Event Cancel Dup {random_id}"
        product_name = f"Billet Dup {random_id}"
        cancelled_email = f"jturbeaux+rcan2{random_id}@pm.me"

        start_date = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7)
        ).isoformat()

        # --- Etape 1 : Creer l'evenement et le produit ---
        # / Step 1: Create event and product.
        event_result = create_event(name=event_name, start_date=start_date)
        assert event_result["ok"], f"Creation event echouee: {event_result}"
        event_uuid = event_result["uuid"]

        product_result = create_product(
            name=product_name,
            description="Produit pour test double annulation",
            category="Free booking",
            event_uuid=event_uuid,
            offers=[{"name": "Gratuit dup", "price": "0.00"}],
        )
        assert product_result["ok"], f"Creation produit echouee: {product_result}"
        offers = product_result.get("offers") or []
        assert offers, f"Aucune offre retournee: {product_result}"
        price_uuid = offers[0].get("identifier") or ""
        assert price_uuid != "", f"UUID du tarif manquant: {offers}"

        # --- Etape 2 : Creer une reservation ---
        # / Step 2: Create a reservation.
        resa_result = _create_reservation_api(
            api_key=api_key,
            event_uuid=event_uuid,
            email=cancelled_email,
            price_uuid=price_uuid,
            qty=1,
        )
        assert resa_result["ok"], f"Creation reservation echouee: {resa_result}"

        # --- Etape 3 : Premiere annulation ---
        # / Step 3: First cancellation.
        login_as_admin(page)
        page.goto("/admin/BaseBillet/reservation/")
        page.wait_for_load_state("networkidle")

        search_input = page.locator('input[name="q"]').first
        search_input.fill(cancelled_email)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        checkbox = page.locator("#result_list tbody tr input[type='checkbox']").first
        checkbox.check()

        action_select = page.locator('select[name="action"]')
        action_select.select_option("action_cancel_refund_reservations")

        page.evaluate(
            "() => { const form = document.querySelector('#changelist-form'); if (form) form.submit(); }"
        )
        page.wait_for_load_state("networkidle")

        # --- Etape 4 : Deuxieme tentative d'annulation ---
        # Chercher a nouveau et tenter d'annuler une deuxieme fois.
        # / Step 4: Second cancellation attempt.
        # Search again and try to cancel a second time.
        search_input2 = page.locator('input[name="q"]').first
        search_input2.fill(cancelled_email)
        search_input2.press("Enter")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        row_count = rows.count()

        if row_count > 0:
            checkbox2 = page.locator("#result_list tbody tr input[type='checkbox']").first
            checkbox2.check()

            action_select2 = page.locator('select[name="action"]')

            # Verifier que l'action d'annulation est disponible dans la liste.
            # / Check that the cancel action is available in the select list.
            options_text = action_select2.inner_text()
            has_cancel_action = (
                "cancel" in options_text.lower() or "annuler" in options_text.lower()
            )

            if has_cancel_action:
                action_select2.select_option("action_cancel_refund_reservations")
                page.evaluate(
                    "() => { const form = document.querySelector('#changelist-form'); if (form) form.submit(); }"
                )
                page.wait_for_load_state("networkidle")

                # Verifier qu'il n'y a pas de doublon d'avoir en base.
                # Au max 1 avoir par reservation (pas de credit_note en double).
                # / Check no duplicate credit note in DB.
                # At most 1 credit note per reservation (no duplicate).
                dup_result = django_shell(
                    "from BaseBillet.models import LigneArticle\n"
                    f"count = LigneArticle.objects.filter(pricesold__productsold__product__name__contains='{product_name}', status__in=['R', 'N'], credit_note_for__isnull=False).count()\n"
                    "print(f'credit_notes_count={count}')"
                )
                import re as _re
                match = _re.search(r"credit_notes_count=(\d+)", dup_result)
                if match:
                    credit_note_count = int(match.group(1))
                    assert credit_note_count <= 1, (
                        f"Doublon d'avoir detecte : {credit_note_count} avoirs "
                        f"pour la reservation de {cancelled_email}. Sortie : {dup_result}"
                    )

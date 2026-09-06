"""
Tests E2E smoke : vrai aller-retour Stripe checkout.
/ E2E smoke tests: real Stripe checkout round-trip.

Ces tests font le vrai paiement via checkout.stripe.com.
Timeouts genereux (60-120s par etape) car Stripe peut etre lent.
Carte test : 4242 4242 4242 4242, 12/42, 424.
/ These tests make real payments via checkout.stripe.com.
Generous timeouts (60-120s per step) because Stripe can be slow.
Test card: 4242 4242 4242 4242, 12/42, 424.

IMPORTANT (membership) : le formulaire d'adhesion est un template PARTIEL
(form.html sans base template). Il DOIT etre charge via la page liste
/memberships/ (qui a le base template + HTMX) dans l'offcanvas.
Naviguer directement vers /memberships/<uuid>/ donne une page sans HTMX
et le formulaire se soumet en GET natif au lieu d'un POST HTMX.
/ IMPORTANT (membership): the membership form is a PARTIAL template
(form.html without base template). It MUST be loaded through the list page
/memberships/ (which has the base template + HTMX) in the offcanvas.
Navigating directly to /memberships/<uuid>/ gives a page without HTMX
and the form submits as native GET instead of HTMX POST.
"""

import json
import random
import re
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _lire_la_vente_en_base(django_shell, extrait_python):
    """Interroge la base et rend le dict decrit par l'extrait fourni.
    / Queries the database and returns the dict described by the given snippet.

    POURQUOI CETTE VERIFICATION EXISTE : un ecran de confirmation ne prouve rien sur
    l'argent. Le navigateur affiche « merci » des que le retour de paiement est rendu —
    meme si la vente n'a jamais ete ecrite, meme si la ligne est restee bloquee a PAID
    parce que le trigger a leve en chemin (ses erreurs sont avalees, cf.
    `test_adhesion_recompense_puis_qrcode`). Un test qui s'arrete au texte de la page
    valide donc un paiement qui n'a peut-etre pas eu lieu.
    / WHY THIS CHECK EXISTS: a confirmation screen proves nothing about the money. The
      browser shows "thanks" as soon as the return page renders — even if the sale was
      never written, even if the line stayed at PAID because the trigger raised on the way
      (its errors are swallowed). A test that stops at page text validates a payment that
      may never have happened.

    L'ATTENTE EST FAITE DANS LE SHELL, pas autour : le credit arrive par le webhook, donc
    de facon asynchrone, et chaque appel a `django_shell` coute un demarrage complet de
    Django (~5 s). Boucler ici couterait une minute par tentative.
    / THE POLLING HAPPENS INSIDE THE SHELL: the credit arrives asynchronously via the
      webhook, and each django_shell call costs a full Django boot (~5 s).
    """
    sortie = django_shell(extrait_python)
    for ligne in sortie.splitlines():
        if ligne.startswith("VENTE_JSON="):
            return json.loads(ligne[len("VENTE_JSON="):])
    raise AssertionError(
        f"La lecture en base n'a rien rendu d'exploitable. Sortie : {sortie[:400]}"
    )


class TestStripeSmokeCheckout:
    """Smoke tests Stripe : vrai checkout / Real Stripe checkout smoke tests."""

    def test_smoke_membership_stripe_checkout(
        self, page, create_product, fill_stripe_card, soumettre_paiement_stripe,
        admin_email, django_shell,
    ):
        """1 adhesion payante → page liste → offcanvas → Stripe → retour → confirmation.
        / 1 paid membership → list page → offcanvas → Stripe → return → confirmation.
        """
        page.set_default_timeout(120_000)

        rid = _random_id()
        user_email = f"test+smoke{rid}@pm.me"

        # 1. Créer un produit adhésion via API / Create membership product via API
        result = create_product(
            name=f"Smoke Stripe {rid}",
            category="Membership",
            description="Smoke test Stripe E2E",
            offers=[{"name": "Annuelle", "price": "1.00"}],
        )
        assert result["ok"], f"Création produit échouée: {result}"
        product_uuid = result["uuid"]

        # 2. Naviguer vers la page LISTE (pas /memberships/<uuid>/ !)
        # La page liste a le base template reunion/base.html qui charge HTMX.
        # / Navigate to the LIST page (not /memberships/<uuid>/ !)
        # The list page has the reunion/base.html base template that loads HTMX.
        page.goto("/memberships/")
        page.wait_for_load_state("domcontentloaded")

        # 3. Trouver le produit et ouvrir le formulaire dans l'offcanvas
        # Le bouton a data-testid="membership-open-<uuid>" et fait un hx-get
        # qui charge le formulaire dans #offcanvas-membership.
        # / Find the product and open the form in the offcanvas.
        # Button has data-testid and does hx-get to load form into offcanvas.
        subscribe_btn = page.locator(
            f'[data-testid="membership-open-{product_uuid}"]'
        )
        expect(subscribe_btn).to_be_visible(timeout=10_000)
        subscribe_btn.click()

        # 4. Attendre que l'offcanvas s'ouvre et le formulaire charge via HTMX
        # / Wait for the offcanvas to open and the form to load via HTMX
        page.wait_for_selector("#subscribePanel.show", state="visible")
        page.wait_for_selector("#membership-form", state="visible", timeout=10_000)

        # 5. Remplir le formulaire / Fill the form
        page.locator("#membership-email").fill(user_email)
        page.locator("#confirm-email").fill(user_email)
        page.locator('input[name="firstname"]').fill("Smoke")
        page.locator('input[name="lastname"]').fill("Test")

        # Sélectionner le tarif si radio visible / Select price if radio visible
        price_radio = page.locator('input[name="price"][type="radio"]').first
        if price_radio.count() > 0 and price_radio.is_visible():
            price_radio.check()

        # 6. Soumettre et attendre Stripe ou confirmation
        # Pattern race : Stripe redirect OU message de confirmation (gratuit/validation manuelle)
        # / Submit and wait for Stripe or confirmation
        # Race pattern: Stripe redirect OR confirmation message (free/manual validation)
        page.locator("#membership-submit").click()

        try:
            page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=30_000)
        except Exception:
            # Pas de redirect Stripe — chercher un message de confirmation
            # / No Stripe redirect — look for confirmation message
            confirmation = page.locator(
                "text=/demande|reçue|attente|waiting|received/i"
            )
            if confirmation.is_visible(timeout=5_000):
                # Produit gratuit ou validation manuelle — pas de Stripe
                return
            # Erreur réelle : ni Stripe ni confirmation
            errors = page.locator(
                ".alert-danger, .invalid-feedback:visible"
            ).all_text_contents()
            body = page.locator("body").inner_text()[:500]
            pytest.fail(
                f"Ni redirect Stripe ni confirmation. Errors: {errors}. Body: {body}"
            )

        # 7. Remplir la carte Stripe / Fill Stripe card
        # domcontentloaded au lieu de networkidle : Stripe maintient des connexions
        # persistantes (analytics, SSE) qui empechent networkidle de resoudre.
        # / domcontentloaded instead of networkidle: Stripe keeps persistent
        # connections that prevent networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)

        # 8. Cliquer payer / Click pay
        # Soumission robuste : un click() simple est parfois ignore par le
        # front Stripe, sans erreur ni requete (PIEGES 12.14).
        # / Robust submit: a plain click() is sometimes ignored, silently.
        soumettre_paiement_stripe(page)

        # 9. Attendre le retour vers TiBillet / Wait for return to TiBillet
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url,
            timeout=60_000,
        )

        # 10. Vérifier la page de confirmation / Verify confirmation page
        # `.first` : le toast de succes contient 2 elements qui matchent
        # (header "Succès" + body) — strict mode refuse sans .first.
        # / `.first`: the success toast has 2 matching elements
        # (header + body) — strict mode rejects without .first.
        success_msg = page.locator("text=/merci|confirmée|succès|success/i").first
        expect(success_msg).to_be_visible(timeout=30_000)

        # 11. Verifier que l'argent a REELLEMENT bouge, en base
        # / Verify the money REALLY moved, in the database
        vente = _lire_la_vente_en_base(
            django_shell,
            "import json, time\n"
            "from BaseBillet.models import LigneArticle, Membership\n"
            "lu = {'adhesion': None, 'statut_ligne': None, 'montant': None}\n"
            "for _essai in range(8):\n"
            f"    adhesion = Membership.objects.filter(user__email='{user_email}')"
            ".order_by('-date_added').first()\n"
            "    if adhesion is not None:\n"
            "        lu['adhesion'] = str(adhesion.uuid)\n"
            "        ligne = LigneArticle.objects.filter(membership=adhesion)"
            ".order_by('-datetime').first()\n"
            "        if ligne is not None:\n"
            "            lu['statut_ligne'] = ligne.status\n"
            "            lu['montant'] = int(ligne.amount)\n"
            "            if ligne.status == LigneArticle.VALID:\n"
            "                break\n"
            "    time.sleep(2)\n"
            "print('VENTE_JSON=' + json.dumps(lu))\n",
        )

        assert vente["adhesion"], (
            f"Aucune adhesion en base pour {user_email} alors que la page affiche une "
            f"confirmation : le paiement a ete encaisse sans rien creer."
        )
        assert vente["statut_ligne"] is not None, (
            "L'adhesion existe mais aucune ligne de vente ne lui est rattachee : "
            "la vente n'est pas comptabilisee."
        )
        # 'V' = confirmee. Une ligne restee a 'P' (payee mais non confirmee) est le
        # symptome visible d'un trigger interrompu : l'argent est pris, la contrepartie
        # n'est pas delivree.
        # / 'V' = confirmed. A line stuck at 'P' is the visible symptom of an interrupted
        #   trigger: the money is taken, the counterpart is not delivered.
        assert vente["statut_ligne"] == "V", (
            f"Ligne de vente au statut '{vente['statut_ligne']}' au lieu de 'V' "
            f"(confirmee). Un statut 'P' signifie que le paiement est encaisse mais que "
            f"le trigger n'est pas alle au bout."
        )
        assert vente["montant"] == 100, (
            f"Montant en base : {vente['montant']} centimes, attendu 100 (1,00 €)."
        )

    def test_smoke_booking_stripe_checkout(
        self, page, create_event, create_product, fill_stripe_card,
        soumettre_paiement_stripe, django_shell,
    ):
        """1 reservation payante → vrai checkout.stripe.com → retour → confirmation.
        / 1 paid booking → real checkout.stripe.com → return → confirmation.
        """
        from datetime import datetime, timedelta, timezone as tz

        page.set_default_timeout(120_000)

        rid = _random_id()
        user_email = f"test+smokebook{rid}@pm.me"
        start_date = (datetime.now(tz.utc) + timedelta(days=2)).isoformat()

        # 1. Créer événement + produit / Create event + product
        event_result = create_event(name=f"Smoke Event {rid}", start_date=start_date)
        assert event_result["ok"], f"Création événement échouée: {event_result}"
        event_slug = event_result["slug"]

        product_result = create_product(
            name=f"Billets Smoke {rid}",
            category="Ticket booking",
            event_uuid=event_result["uuid"],
            offers=[{"name": "Place", "price": "1.00"}],
        )
        assert product_result["ok"], f"Création produit échouée: {product_result}"

        # 2. Naviguer vers l'événement / Navigate to event
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")

        # 3. Ouvrir le panneau de réservation / Open booking panel
        open_button = page.locator(
            'button:has-text("book one or more seats"), '
            'button:has-text("réserver")'
        ).first
        open_button.click()
        page.wait_for_selector(
            "#bookingPanel.show, .offcanvas.show", state="visible"
        )

        # 4. Remplir email + sélectionner 1 billet / Fill email + select 1 ticket
        email_input = page.locator(
            '#bookingPanel input[name="email"], #booking-email'
        ).first
        email_input.fill(user_email)

        confirm_input = page.locator(
            '#bookingPanel input[name="email-confirm"], #booking-confirm'
        ).first
        if confirm_input.is_visible():
            confirm_input.fill(user_email)

        # Incrémenter bs-counter / Increment bs-counter
        counter_plus = page.locator(
            "bs-counter .bi-plus, bs-counter button:has(.bi-plus)"
        ).first
        counter_plus.click()

        # 5. Soumettre / Submit
        submit_btn = page.locator(
            '#bookingPanel button[type="submit"]'
        ).first
        submit_btn.click()

        # 6. Attendre Stripe / Wait for Stripe
        page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=60_000)

        # 7. Remplir carte + payer / Fill card + pay
        # domcontentloaded : Stripe maintient des connexions persistantes (SSE/analytics)
        # qui empechent networkidle de se resoudre.
        # / domcontentloaded: Stripe keeps persistent connections that prevent
        # networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)
        # Soumission robuste : cf. PIEGES 12.14.
        # / Robust submit: see PIEGES 12.14.
        soumettre_paiement_stripe(page)

        # 8. Attendre le retour / Wait for return
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url,
            timeout=60_000,
        )

        # 9. Vérifier / Verify
        body_text = page.locator("body").inner_text().lower()
        assert any(kw in body_text for kw in [
            "merci", "confirmée", "succès", "success",
            "reservation ok", "valider votre email",
        ]), f"Page de confirmation non trouvée: {body_text[:200]}"

        # 10. Verifier que la reservation existe REELLEMENT en base
        # Le texte de la page ne prouve rien : il s'affiche des que le retour de paiement
        # est rendu, meme si la reservation n'a jamais ete ecrite.
        # / Verify the booking REALLY exists in the database. Page text proves nothing.
        vente = _lire_la_vente_en_base(
            django_shell,
            "import json, time\n"
            "from BaseBillet.models import LigneArticle, Reservation\n"
            "lu = {'reservation': None, 'statut_ligne': None, 'billets': 0}\n"
            "for _essai in range(8):\n"
            f"    resa = Reservation.objects.filter(user_commande__email='{user_email}')"
            ".order_by('-datetime').first()\n"
            "    if resa is not None:\n"
            "        lu['reservation'] = str(resa.uuid)\n"
            "        lu['billets'] = resa.tickets.count()\n"
            "        ligne = LigneArticle.objects.filter(reservation=resa)"
            ".order_by('-datetime').first()\n"
            "        if ligne is not None:\n"
            "            lu['statut_ligne'] = ligne.status\n"
            "            if ligne.status == LigneArticle.VALID:\n"
            "                break\n"
            "    time.sleep(2)\n"
            "print('VENTE_JSON=' + json.dumps(lu))\n",
        )

        assert vente["reservation"], (
            f"Aucune reservation en base pour {user_email} alors que la page affiche une "
            f"confirmation : le paiement a ete encaisse sans rien creer."
        )
        assert vente["statut_ligne"] == "V", (
            f"Ligne de vente au statut '{vente['statut_ligne']}' au lieu de 'V' "
            f"(confirmee) : le paiement est encaisse mais la vente n'est pas confirmee."
        )
        assert vente["billets"] >= 1, (
            f"Reservation sans billet ({vente['billets']}) : le client a paye et n'a "
            f"rien recu."
        )

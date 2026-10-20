"""
Tests E2E : réservation de créneau à validation manuelle.
/ E2E tests: slot booking with manual validation.

LOCALISATION : tests/e2e/test_booking_validation_manuelle_stripe.py

Chaque test crée SA ressource (tarif payant à validation manuelle) et SA personne par
django_shell : aucune fixture partagée n'est touchée.
/ Each test creates ITS resource (paid price with manual validation) and ITS person.

Parcours vérifiés dans le vrai navigateur :
1. Demande → validation par l'admin → paiement Stripe réel → « Payé » dans le compte.
2. Demande → refus par l'admin avec un motif → créneau libéré, demande annulée.
/ Journeys checked in the real browser:
1. Request → admin validation → real Stripe payment → "Paid" in the account.
2. Request → admin refusal with a reason → slot freed, request cancelled.

Spécification : TECH_DOC/SESSIONS/BOOKING/SPEC.md (fiche E)
Lancer / Run : make e2e-visible validation_manuelle
"""

import json
import re
import time
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.validation_manuelle]


def creer_une_ressource_a_validation_manuelle(django_shell):
    """
    Crée une ressource ouverte tous les jours de 10 h à 18 h, avec un seul tarif :
    10 €, à validation manuelle. Rend un dict : pk de la ressource, uuid du tarif.
    / Creates a resource with one 10 € manual-validation price; returns their ids.
    """
    identifiant = uuid.uuid4().hex[:8]
    sortie = django_shell(
        "import datetime, json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from booking.models import Calendar, OpeningEntry, Resource, WeeklyOpening\n"
        f"calendrier = Calendar.objects.create(name='E2E demande {identifiant}')\n"
        f"ouverture = WeeklyOpening.objects.create(name='E2E demande {identifiant}')\n"
        "for jour in range(7):\n"
        "    OpeningEntry.objects.create(weekly_opening=ouverture, weekday=jour,\n"
        "        start_time=datetime.time(10, 0), slot_duration_minutes=60, slot_count=8)\n"
        f"produit = Product.objects.create(name='E2E salle demande {identifiant}',\n"
        "    categorie_article=Product.RESOURCE)\n"
        "tarif = Price.objects.create(product=produit, name='Sur demande',\n"
        "    prix=Decimal('10.00'), publish=True, manual_validation=True)\n"
        f"ressource = Resource.objects.create(name='E2E salle demande {identifiant}',\n"
        "    product=produit, calendar=calendrier, weekly_opening=ouverture, capacity=1)\n"
        "print(json.dumps({'ressource': ressource.pk, 'tarif': str(tarif.uuid)}))\n"
    )
    return json.loads(sortie.strip().splitlines()[-1])


def creer_une_personne(django_shell):
    """Crée une personne active à l'email unique, et rend cet email.
    / Creates an active person with a unique email, returns the email."""
    email = f"jturbeaux+e2edemande{uuid.uuid4().hex[:8]}@pm.me"
    django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"personne = get_or_create_user('{email}', send_mail=False)\n"
        "personne.is_active = True\n"
        "personne.save()\n"
    )
    return email


def le_booking_de_la_personne(django_shell, email, pk_de_la_ressource):
    """Le pk, le statut et le motif du refus du booking (None si absent).
    / The booking's pk, status and refusal reason (None if missing)."""
    sortie = django_shell(
        "import json\n"
        "from booking.models import Booking\n"
        f"booking = Booking.objects.filter(user__email='{email}',"
        f" resource_id={pk_de_la_ressource}).first()\n"
        "print(json.dumps(None if booking is None else {'pk': booking.pk,"
        " 'status': booking.status, 'motif_du_refus': booking.motif_du_refus}))\n"
    )
    return json.loads(sortie.strip().splitlines()[-1])


def lundi_prochain_au_lieu(django_shell):
    """
    Le lundi de la semaine prochaine, dans le fuseau du lieu (texte AAAA-MM-JJ).
    Un dimanche soir, la semaine en cours n'a plus aucun créneau libre.
    / Next week's Monday, in the venue's time zone. On a Sunday evening the current
    week has no free slot left.
    """
    return (
        django_shell(
            "import datetime\n"
            "from django.utils import timezone\n"
            "from BaseBillet.models import Configuration\n"
            "aujourd_hui = timezone.now().astimezone(Configuration.get_solo().get_tzinfo()).date()\n"
            "print(aujourd_hui - datetime.timedelta(days=aujourd_hui.weekday()) + datetime.timedelta(days=7))\n"
        )
        .strip()
        .splitlines()[-1]
    )


def envoyer_la_demande_du_premier_creneau(page, ressource, django_shell):
    """
    Ouvre la semaine prochaine de la ressource, clique le premier créneau libre, coche
    le tarif à validation manuelle et envoie la demande. Arrive sur « Mes réservations ».
    / Opens next week, clicks the first free slot, ticks the price, sends the request.
    """
    lundi_prochain = lundi_prochain_au_lieu(django_shell)
    page.goto(f"/booking/{ressource['ressource']}/resource/?semaine={lundi_prochain}")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="booking-calendar-slot-free"]').first.click()
    formulaire = page.locator('[data-testid="booking-confirm-form"]')
    expect(formulaire).to_be_visible(timeout=10_000)
    formulaire.locator(f'input[name="price"][value="{ressource["tarif"]}"]').check()
    formulaire.locator('input[name="firstname"]').fill("Ada")
    formulaire.locator('input[name="lastname"]').fill("Lovelace")

    # Le tarif à validation manuelle remplace les boutons « Réserver » et « Ajouter au
    # panier » par « Envoyer la demande ».
    # / The manual-validation price swaps the booking buttons for "Send the request".
    expect(page.locator('[data-testid="booking-request-block"]')).to_be_visible()
    page.locator('[data-testid="booking-send-request"]').click()
    page.wait_for_url(lambda url: "my_bookings" in url, timeout=15_000)
    page.wait_for_load_state("networkidle")


def ouvrir_la_fiche_admin(page, login_as_admin, pk_du_booking):
    """Connecte l'admin et ouvre la fiche du booking, panneau de décision visible.
    / Logs the admin in and opens the booking change form, decision panel visible."""
    login_as_admin(page)
    page.goto(f"/admin/booking/booking/{pk_du_booking}/change/")
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-testid="booking-actions-panel"]')).to_be_visible()


# Ce parcours ne s'achève qu'au retour du webhook Stripe : le booking ne passe en
# « payé » que lorsque Stripe rappelle. Sans `stripe listen`, l'attente échoue.
# / This journey only completes when the Stripe webhook returns.
@pytest.mark.stripe_listen
def test_demande_validee_par_l_admin_puis_payee_sur_stripe(
    page,
    login_as,
    login_as_admin,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
):
    """
    Demande → l'admin valide → la personne paie sur Stripe → « Payé » dans son compte.
    / Request → admin validates → the person pays on Stripe → "Paid" in the account.
    """
    page.set_default_timeout(120_000)
    ressource = creer_une_ressource_a_validation_manuelle(django_shell)
    email = creer_une_personne(django_shell)

    # 1) La personne envoie sa demande : badge « en attente » dans son compte.
    # / The person sends the request: "pending" badge in the account.
    login_as(page, email)
    envoyer_la_demande_du_premier_creneau(page, ressource, django_shell)
    booking = le_booking_de_la_personne(django_shell, email, ressource["ressource"])
    assert booking["status"] == "WA"
    expect(
        page.locator(f'[data-testid="booking-badge-request-{booking["pk"]}"]')
    ).to_be_visible()

    # 2) L'admin valide : la fiche se recharge avec les boutons de la demande validée.
    # / The admin validates: the page reloads with the validated-request buttons.
    ouvrir_la_fiche_admin(page, login_as_admin, booking["pk"])
    page.locator('[data-testid="booking-action-accept"]').click()
    expect(
        page.locator('[data-testid="booking-action-copy-payment-link"]')
    ).to_be_visible(timeout=15_000)
    assert (
        le_booking_de_la_personne(django_shell, email, ressource["ressource"])["status"]
        == "VA"
    )

    # 3) La personne paie depuis « Mes réservations ».
    # / The person pays from "My bookings".
    login_as(page, email)
    page.goto("/my_account/my_bookings/")
    page.wait_for_load_state("networkidle")
    page.locator(f'[data-testid="booking-pay-{booking["pk"]}"]').click()
    page.wait_for_url(lambda url: "checkout.stripe.com" in url, timeout=40_000)
    # domcontentloaded : Stripe garde des connexions ouvertes, networkidle n'arrive pas.
    # / domcontentloaded: Stripe keeps connections open, networkidle never comes.
    page.wait_for_load_state("domcontentloaded")
    fill_stripe_card(page, email)
    soumettre_paiement_stripe(page)
    page.wait_for_url(lambda url: "tibillet.localhost" in url, timeout=60_000)

    # 4) Le webhook est asynchrone : on interroge la base (15 tentatives, 2 s d'écart).
    # / The webhook is async: poll the DB (15 attempts, 2 s apart).
    statut = ""
    for tentative in range(15):
        statut = le_booking_de_la_personne(django_shell, email, ressource["ressource"])[
            "status"
        ]
        if statut == "PA":
            break
        time.sleep(2)
    assert statut == "PA", f"Statut attendu PA après paiement, obtenu : '{statut}'"

    # 5) Le compte montre la réservation payée, sans bouton « Payer ».
    # / The account shows the paid booking, without a "Pay" button.
    page.goto("/my_account/my_bookings/")
    page.wait_for_load_state("networkidle")
    expect(page.locator("body")).to_contain_text(
        re.compile(r"Payé par l'utilisateur|Paid by user")
    )
    expect(page.locator(f'[data-testid="booking-pay-{booking["pk"]}"]')).to_have_count(
        0
    )


def test_demande_refusee_par_l_admin_avec_un_motif(
    page, login_as, login_as_admin, django_shell
):
    """
    Demande → l'admin refuse avec un motif → la demande est annulée et garde le motif,
    le panneau de décision disparaît.
    / Request → the admin refuses with a reason → the request is cancelled and keeps the
    reason, the decision panel disappears.
    """
    ressource = creer_une_ressource_a_validation_manuelle(django_shell)
    email = creer_une_personne(django_shell)

    login_as(page, email)
    envoyer_la_demande_du_premier_creneau(page, ressource, django_shell)
    booking = le_booking_de_la_personne(django_shell, email, ressource["ressource"])
    assert booking["status"] == "WA"

    ouvrir_la_fiche_admin(page, login_as_admin, booking["pk"])
    page.locator('[data-testid="booking-action-refuse-details"] summary').click()
    page.locator('[data-testid="booking-action-refuse-motif"]').fill("Salle en travaux")
    # Le bouton demande une confirmation (hx-confirm) : on l'accepte.
    # / The button asks for a confirmation (hx-confirm): we accept it.
    page.once("dialog", lambda boite_de_dialogue: boite_de_dialogue.accept())
    page.locator('[data-testid="booking-action-refuse"]').click()

    # La fiche se recharge : une demande annulée n'a plus de panneau de décision.
    # / The page reloads: a cancelled request has no decision panel.
    expect(page.locator('[data-testid="booking-actions-panel"]')).to_have_count(
        0, timeout=15_000
    )
    booking_apres_le_refus = le_booking_de_la_personne(
        django_shell, email, ressource["ressource"]
    )
    assert booking_apres_le_refus["status"] == "CA"
    assert booking_apres_le_refus["motif_du_refus"] == "Salle en travaux"

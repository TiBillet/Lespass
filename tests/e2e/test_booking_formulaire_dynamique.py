"""
Tests E2E : réservation de ressource avec formulaire dynamique.
/ E2E tests: resource booking with a dynamic form.

LOCALISATION : tests/e2e/test_booking_formulaire_dynamique.py

Chaque test crée SA ressource (produit ressource, tarif gratuit, 3 questions) par
django_shell : aucun Stripe, et aucune fixture partagée n'est touchée.
/ Each test creates ITS resource (free price, 3 questions): no Stripe, no shared fixture.

Ce qui est vérifié dans le vrai navigateur :
- les questions s'affichent dans le panneau de réservation (partial champs_produit.html) ;
- le JS bloque l'envoi si une question à choix multiple obligatoire est vide ;
- les réponses arrivent sur le Booking, par la réservation directe ET par le panier ;
- elles s'affichent dans « Mes réservations » et dans la fiche admin.

Lancer / Run : make e2e-visible panier
"""

import json
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.panier]


def creer_une_ressource_avec_questions(django_shell):
    """
    Crée une ressource ouverte tous les jours de 10 h à 18 h, un tarif gratuit et trois
    questions : texte obligatoire, choix multiple obligatoire, texte facultatif.
    Rend un dict : pk de la ressource, uuid du tarif, noms techniques des questions.
    / Creates a resource, a free price and three questions; returns their ids.
    """
    identifiant = uuid.uuid4().hex[:8]
    sortie = django_shell(
        "import datetime, json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product, ProductFormField\n"
        "from booking.models import Calendar, OpeningEntry, Resource, WeeklyOpening\n"
        f"calendrier = Calendar.objects.create(name='E2E formulaire {identifiant}')\n"
        f"ouverture = WeeklyOpening.objects.create(name='E2E formulaire {identifiant}')\n"
        "for jour in range(7):\n"
        "    OpeningEntry.objects.create(weekly_opening=ouverture, weekday=jour,\n"
        "        start_time=datetime.time(10, 0), slot_duration_minutes=60, slot_count=8)\n"
        f"produit = Product.objects.create(name='E2E salle formulaire {identifiant}',\n"
        "    categorie_article=Product.RESOURCE)\n"
        "tarif = Price.objects.create(product=produit, name='Gratuit', prix=Decimal('0.00'),\n"
        "    publish=True)\n"
        f"ressource = Resource.objects.create(name='E2E salle formulaire {identifiant}',\n"
        "    product=produit, calendar=calendrier, weekly_opening=ouverture, capacity=5)\n"
        "groupe = ProductFormField.objects.create(product=produit, label='Nom du groupe',\n"
        "    field_type='ST', required=True, order=1)\n"
        "materiel = ProductFormField.objects.create(product=produit, label='Matériel',\n"
        "    field_type='MS', required=True, options=['Ampli', 'Micro'], order=2)\n"
        "remarque = ProductFormField.objects.create(product=produit, label='Remarque',\n"
        "    field_type='ST', required=False, order=3)\n"
        "print(json.dumps({'ressource': ressource.pk, 'tarif': str(tarif.uuid),\n"
        "    'groupe': groupe.name, 'materiel': materiel.name}))\n"
    )
    return json.loads(sortie.strip().splitlines()[-1])


def creer_un_acheteur(django_shell):
    """Crée un acheteur actif à l'email unique, et rend cet email.
    / Creates an active buyer with a unique email, returns the email."""
    email = f"test+e2eformulaire{uuid.uuid4().hex[:8]}@mock.test"
    django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"acheteur = get_or_create_user('{email}', send_mail=False)\n"
        "acheteur.is_active = True\n"
        "acheteur.save()\n"
    )
    return email


def reponses_du_booking(django_shell, email, pk_de_la_ressource):
    """Le custom_form du booking de l'acheteur sur cette ressource (None si absent).
    / The buyer's booking custom_form on this resource."""
    sortie = django_shell(
        "import json\n"
        "from booking.models import Booking\n"
        f"booking = Booking.objects.filter(user__email='{email}',"
        f" resource_id={pk_de_la_ressource}).first()\n"
        "print(json.dumps(booking.custom_form if booking else 'AUCUN_BOOKING'))\n"
    )
    return json.loads(sortie.strip().splitlines()[-1])


def ouvrir_le_formulaire_du_premier_creneau(page, ressource):
    """Ouvre la page de la ressource, clique le premier créneau libre, coche le tarif.
    / Opens the resource page, clicks the first free slot, ticks the price."""
    page.goto(f"/booking/{ressource['ressource']}/resource/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="booking-calendar-slot-free"]').first.click()
    formulaire = page.locator('[data-testid="booking-confirm-form"]')
    expect(formulaire).to_be_visible(timeout=10_000)
    formulaire.locator(f'input[name="price"][value="{ressource["tarif"]}"]').check()
    formulaire.locator('input[name="firstname"]').fill("Ada")
    formulaire.locator('input[name="lastname"]').fill("Lovelace")
    return formulaire


def test_reservation_directe_les_reponses_sont_enregistrees_et_visibles_dans_le_compte(
    page, login_as, django_shell
):
    """
    Réservation directe : le choix multiple obligatoire vide bloque l'envoi (JS), puis la
    réservation passe avec les réponses, visibles dans « Mes réservations ».
    / Direct booking: an empty required multi-select blocks the send, then the booking goes
    through and the answers show in "My bookings".
    """
    ressource = creer_une_ressource_avec_questions(django_shell)
    email = creer_un_acheteur(django_shell)
    login_as(page, email)

    formulaire = ouvrir_le_formulaire_du_premier_creneau(page, ressource)
    formulaire.locator(
        f'[data-testid="resource-booking-form-field-{ressource["groupe"]}"]'
    ).fill("Les Ours")

    # 1) Aucune case cochée : le JS bloque l'envoi et affiche le message.
    # / No box ticked: the JS blocks the send and shows the message.
    page.locator('[data-testid="resource-submit"]').click()
    expect(
        page.locator(f'[data-testid="resource-booking-form-error-{ressource["materiel"]}"]')
    ).to_be_visible()
    assert reponses_du_booking(django_shell, email, ressource["ressource"]) == "AUCUN_BOOKING"

    # 2) Une case cochée : la réservation passe, on arrive sur « Mes réservations ».
    # / One box ticked: the booking goes through, landing on "My bookings".
    formulaire.locator(
        f'[data-testid="resource-booking-form-field-{ressource["materiel"]}"][value="Micro"]'
    ).check()
    page.locator('[data-testid="resource-submit"]').click()
    page.wait_for_url(lambda url: "my_bookings" in url, timeout=15_000)

    assert reponses_du_booking(django_shell, email, ressource["ressource"]) == {
        "Nom du groupe": "Les Ours",
        "Matériel": ["Micro"],
    }
    page.wait_for_load_state("networkidle")
    accordeon = page.locator('[id^="booking"][id$="FormAccordion"]').first
    accordeon.locator("button.accordion-button").click()
    expect(accordeon).to_contain_text("Les Ours")


def test_panier_les_reponses_arrivent_sur_le_booking_et_dans_l_admin(
    page, login_as, login_as_admin, django_shell
):
    """
    Panier : les réponses partent avec « Ajouter au panier », arrivent sur le Booking au
    paiement (gratuit), et s'affichent dans la fiche admin.
    / Cart: answers go with "Add to cart", reach the Booking at (free) checkout, and show
    in the admin change view.
    """
    ressource = creer_une_ressource_avec_questions(django_shell)
    email = creer_un_acheteur(django_shell)
    login_as(page, email)

    formulaire = ouvrir_le_formulaire_du_premier_creneau(page, ressource)
    formulaire.locator(
        f'[data-testid="resource-booking-form-field-{ressource["groupe"]}"]'
    ).fill("Les Ours")
    formulaire.locator(
        f'[data-testid="resource-booking-form-field-{ressource["materiel"]}"][value="Ampli"]'
    ).check()
    page.locator('[data-testid="resource-add-to-cart"]').click()
    page.wait_for_load_state("networkidle")

    page.goto("/panier/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="panier-checkout"]').click()
    page.wait_for_load_state("networkidle")

    assert reponses_du_booking(django_shell, email, ressource["ressource"]) == {
        "Nom du groupe": "Les Ours",
        "Matériel": ["Ampli"],
    }

    pk_du_booking = django_shell(
        "from booking.models import Booking\n"
        f"print(Booking.objects.get(user__email='{email}',"
        f" resource_id={ressource['ressource']}).pk)\n"
    ).strip().splitlines()[-1]
    login_as_admin(page)
    page.goto(f"/admin/booking/booking/{pk_du_booking}/change/")
    page.wait_for_load_state("networkidle")
    reponses_dans_l_admin = page.locator('[data-testid="booking-custom-form-answers"]')
    expect(reponses_dans_l_admin).to_contain_text("Les Ours")
    expect(reponses_dans_l_admin).to_contain_text("Ampli")

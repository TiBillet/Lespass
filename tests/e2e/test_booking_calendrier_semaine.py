"""
Calendrier d'une ressource : une semaine à la fois, rechargée en htmx (navigateur).
/ Resource calendar: one week at a time, reloaded with htmx (browser).

LOCALISATION : tests/e2e/test_booking_calendrier_semaine.py

Vérifie ce que pytest ne peut pas voir (JavaScript, swap htmx) :
- « Semaine suivante » remplace la zone sans recharger la page, met ?semaine= dans
  l'adresse et pose le focus sur le titre ; le retour arrière ramène la semaine d'avant ;
- sur téléphone, les flèches de jour restent dans la semaine ;
- un créneau de la deuxième semaine ouvre le formulaire (clic délégué après le swap).

Code testé : booking/views.py (resource_page), booking/templates/booking/views/resource.html,
booking/templates/booking/partials/resource_semaine.html.

Lancer / Run : make e2e panier
"""
import json
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.panier]


def creer_une_salle_ouverte_tous_les_jours(django_shell):
    """
    Crée une ressource ouverte tous les jours de 10 h à 18 h (créneaux d'une heure),
    horizon de 28 jours, avec un tarif gratuit. Rend son pk.
    / Creates a resource open every day 10-18 with a free price; returns its pk.
    """
    identifiant = uuid.uuid4().hex[:8]
    sortie = django_shell(
        "import datetime, json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from booking.models import Calendar, OpeningEntry, Resource, WeeklyOpening\n"
        f"calendrier = Calendar.objects.create(name='E2E semaine {identifiant}')\n"
        f"ouverture = WeeklyOpening.objects.create(name='E2E semaine {identifiant}')\n"
        "for jour in range(7):\n"
        "    OpeningEntry.objects.create(weekly_opening=ouverture, weekday=jour,\n"
        "        start_time=datetime.time(10, 0), slot_duration_minutes=60, slot_count=8)\n"
        f"produit = Product.objects.create(name='E2E salle semaine {identifiant}',\n"
        "    categorie_article=Product.RESOURCE)\n"
        "Price.objects.create(product=produit, name='Gratuit', prix=Decimal('0.00'), publish=True)\n"
        f"ressource = Resource.objects.create(name='E2E salle semaine {identifiant}',\n"
        "    product=produit, calendar=calendrier, weekly_opening=ouverture, capacity=1)\n"
        "print(json.dumps({'ressource': ressource.pk}))\n"
    )
    return json.loads(sortie.strip().splitlines()[-1])["ressource"]


def creer_un_acheteur(django_shell):
    """Crée un acheteur actif à l'email unique, et rend cet email.
    / Creates an active buyer with a unique email, returns the email."""
    email = f"test+e2esemaine{uuid.uuid4().hex[:8]}@mock.test"
    django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"acheteur = get_or_create_user('{email}', send_mail=False)\n"
        "acheteur.is_active = True\n"
        "acheteur.save()\n"
    )
    return email


def poser_un_temoin_de_rechargement(page):
    """Un rechargement complet de la page efface ce témoin. / A full reload erases it."""
    page.evaluate("window.pas_de_rechargement = true")


def la_page_n_a_pas_ete_rechargee(page):
    return page.evaluate("window.pas_de_rechargement === true")


def test_semaine_suivante_sans_recharger_puis_retour_arriere(page, django_shell):
    pk_de_la_salle = creer_une_salle_ouverte_tous_les_jours(django_shell)
    page.goto(f"/booking/{pk_de_la_salle}/resource/")
    page.wait_for_load_state("networkidle")
    titre = page.locator('[data-testid="booking-calendar-week-label"]')
    titre_de_la_semaine_en_cours = titre.inner_text()
    expect(page.locator('[data-testid="booking-calendar-prev-week"]')).to_have_count(0)
    poser_un_temoin_de_rechargement(page)

    page.locator('[data-testid="booking-calendar-next-week"]').click()

    expect(titre).not_to_have_text(titre_de_la_semaine_en_cours)
    expect(page.locator('[data-testid="booking-calendar-prev-week"]')).to_be_visible()
    # Le focus va sur le titre de la nouvelle semaine (lecteur d'écran).
    # / Focus lands on the new week title (screen reader).
    expect(titre).to_be_focused()
    assert "?semaine=" in page.url
    assert la_page_n_a_pas_ete_rechargee(page)
    # La semaine suivante est entière : 7 jours × 8 créneaux libres.
    # / Next week is whole: 7 days × 8 free slots.
    expect(page.locator('[data-testid="booking-calendar-slot-free"]')).to_have_count(56)

    # Le retour arrière recharge la page (les skins règlent htmx sans cache d'historique) :
    # on ne vérifie pas le témoin, seulement la semaine affichée.
    # / Back reloads the page: only the displayed week is checked.
    page.go_back()

    expect(titre).to_have_text(titre_de_la_semaine_en_cours)
    assert "?semaine=" not in page.url


def test_sur_telephone_les_fleches_de_jour_restent_dans_la_semaine(page, django_shell):
    pk_de_la_salle = creer_une_salle_ouverte_tous_les_jours(django_shell)
    page.set_viewport_size({"width": 375, "height": 800})
    lundi_prochain = django_shell(
        "import datetime\n"
        "from django.utils import timezone\n"
        "from BaseBillet.models import Configuration\n"
        "aujourd_hui = timezone.now().astimezone(Configuration.get_solo().get_tzinfo()).date()\n"
        "print(aujourd_hui - datetime.timedelta(days=aujourd_hui.weekday()) + datetime.timedelta(days=7))\n"
    ).strip().splitlines()[-1]
    page.goto(f"/booking/{pk_de_la_salle}/resource/?semaine={lundi_prochain}")
    page.wait_for_load_state("networkidle")

    jour_precedent = page.locator('[data-testid="booking-mobile-prev-day"]')
    jour_suivant = page.locator('[data-testid="booking-mobile-next-day"]')
    jours_visibles = page.locator('[data-testid="booking-mobile-day"]:visible')
    expect(page.locator('[data-testid="booking-mobile-day-bar-item"]')).to_have_count(7)
    expect(jour_precedent).to_be_disabled()

    for _numero_du_clic in range(6):
        jour_suivant.click()

    # Dimanche : dernier jour de la semaine, la flèche « jour suivant » s'arrête.
    # / Sunday: last day of the week, the next-day arrow stops.
    expect(jour_suivant).to_be_disabled()
    expect(jours_visibles).to_have_count(1)
    expect(jours_visibles.locator('[data-testid="booking-mobile-day-header"]')).to_contain_text("dim")

    # Changer de semaine sur téléphone : la barre montre les 7 jours de la semaine suivante,
    # le premier est de nouveau affiché.
    # / Changing week on phone: the bar shows the next week's 7 days, back on the first.
    page.locator('[data-testid="booking-calendar-next-week"]').click()
    expect(jour_precedent).to_be_disabled()
    expect(page.locator('[data-testid="booking-mobile-day-bar-item"]')).to_have_count(7)

    largeur_de_la_page = page.evaluate("document.documentElement.scrollWidth")
    assert largeur_de_la_page <= 375


def test_un_creneau_de_la_deuxieme_semaine_ouvre_le_formulaire(page, login_as, django_shell):
    pk_de_la_salle = creer_une_salle_ouverte_tous_les_jours(django_shell)
    login_as(page, creer_un_acheteur(django_shell))
    page.goto(f"/booking/{pk_de_la_salle}/resource/")
    page.wait_for_load_state("networkidle")

    page.locator('[data-testid="booking-calendar-next-week"]').click()
    expect(page.locator('[data-testid="booking-calendar-prev-week"]')).to_be_visible()
    page.locator('[data-testid="booking-calendar-slot-free"]').first.click()

    expect(page.locator('[data-testid="booking-confirm-form"]')).to_be_visible(timeout=10_000)

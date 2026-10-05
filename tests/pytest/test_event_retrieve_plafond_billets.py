"""
Tests de bout en bout — la page evenement plafonne le compteur de billets.
/ End-to-end tests — the event page caps the ticket counter.

LOCALISATION : tests/pytest/test_event_retrieve_plafond_billets.py

Code teste / Tested code : EventMVT.retrieve (BaseBillet/views.py) et le gabarit
BaseBillet/templates/commun/formulaires/reservation.html.

`test_booking_counter_max.py` verifie le gabarit seul, avec un contexte fabrique a
la main. Ici, on passe par la VRAIE vue : `GET /event/<slug>/`. On verifie donc que
la vue calcule bien `max_billets` sur les tarifs que le gabarit parcourt, et qu'elle
transmet `places_restantes`.
/ `test_booking_counter_max.py` checks the template alone. Here we go through the
real view, so we check that the view sets `max_billets` on the prices the template
iterates, and passes `places_restantes`.

Chaque test est marque `django_db` : transaction annulee a la fin, rien ne reste en base.
/ Each test is `django_db`: rolled back at the end.

Lancer / Run :
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_event_retrieve_plafond_billets.py -q
"""

import re

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, creer_evenement_avec_tarif

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """Le lieu `lespass`, Stripe simule. / The `lespass` venue, Stripe faked."""
    with tenant_context(tenant):
        yield tenant


def _page_de_l_evenement(evenement):
    """HTML de la page publique de l'evenement. / Public event page HTML."""
    reponse = client_connecte().get(f"/event/{evenement.slug}/")
    assert reponse.status_code == 200
    return reponse.content.decode()


def _attribut_max_du_compteur(html, uuid_du_tarif):
    """
    Valeur de l'attribut `max` du compteur d'un tarif, ou None s'il est absent.
    / The counter's `max` attribute for a price, or None when absent.
    """
    balise = re.search(
        r'<bs-counter[^>]*name="' + str(uuid_du_tarif) + r'"[^>]*>', html, re.S
    )
    assert balise, "compteur du tarif introuvable / price counter not found"
    attribut = re.search(r'\bmax="([^"]*)"', balise.group(0))
    return attribut.group(1) if attribut else None


def test_le_compteur_est_plafonne_par_les_places_restantes(lieu):
    """
    Jauge de 2 places, tarif limite a 5 par personne : le compteur s'arrete a 2.
    / 2 seats left, price capped at 5 per person: the counter stops at 2.
    """
    concert = creer_evenement_avec_tarif(jauge_max=2, max_par_personne_tarif=5)

    html = _page_de_l_evenement(concert.evenement)

    assert _attribut_max_du_compteur(html, concert.tarif.uuid) == "2"


def test_le_compteur_est_plafonne_par_le_quota_du_tarif(lieu):
    """
    100 places libres, tarif limite a 4 par personne : le compteur s'arrete a 4.
    / 100 free seats, price capped at 4: the counter stops at 4.
    """
    concert = creer_evenement_avec_tarif(jauge_max=100, max_par_personne_tarif=4)

    html = _page_de_l_evenement(concert.evenement)

    assert _attribut_max_du_compteur(html, concert.tarif.uuid) == "4"


def test_la_page_n_ecrit_jamais_max_none(lieu):
    """
    Aucun quota par personne : le plafond vient des places restantes, et la chaine
    "None" n'apparait jamais dans un attribut `max`.
    / No per-person quota: the cap comes from the remaining seats, never "None".
    """
    concert = creer_evenement_avec_tarif(jauge_max=30)

    html = _page_de_l_evenement(concert.evenement)

    assert _attribut_max_du_compteur(html, concert.tarif.uuid) == "30"
    assert 'max="None"' not in html


def test_les_places_restantes_s_affichent_quand_il_en_reste_peu(lieu):
    """
    Jauge de 3 places, jauge non affichee : le message des places restantes est
    present, car il reste 10 places ou moins.
    / 3 seats, gauge hidden: the remaining-seats message shows (10 or less left).
    """
    concert = creer_evenement_avec_tarif(jauge_max=3)

    html = _page_de_l_evenement(concert.evenement)

    assert 'data-testid="booking-remaining-seats"' in html

"""
Fiche réservation de l'admin : les réponses au formulaire personnalisé s'affichent en
tableau, comme sur la fiche adhésion, et plus en JSON brut.
/ Admin reservation change view: custom form answers shown as a table, not raw JSON.

LOCALISATION : tests/pytest/test_admin_reservation_reponses_formulaire.py

Code testé / Tested code :
- Administration/admin_tenant.py : ReservationAdmin (exclude, change_form_after_template)
- Administration/templates/admin/reservation/custom_form.html

Lancer / Run : make test ARGS="tests/pytest/test_admin_reservation_reponses_formulaire.py"
"""

import pytest
from django.urls import reverse
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def creer_une_reservation(tenant, reponses):
    """Crée une réservation avec des réponses au formulaire personnalisé.
    / Creates a reservation with custom form answers."""
    from BaseBillet.models import Reservation

    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                concert = creer_evenement_avec_tarif(prix="10.00")
                return Reservation.objects.create(
                    user_commande=creer_utilisateur(),
                    event=concert.evenement,
                    custom_form=reponses,
                )


def afficher_la_fiche(admin_client, tenant, reservation):
    """GET de la fiche de la réservation dans l'admin. / GET of the admin change view."""
    with tenant_context(tenant):
        url = reverse("staff_admin:BaseBillet_reservation_change", args=[reservation.pk])
        return admin_client.get(url)


def test_la_fiche_affiche_les_reponses_en_tableau(admin_client, tenant):
    """Le bloc des réponses est présent, avec la réponse en clair.
    / The answers block is there, with the answer in plain text."""
    reservation = creer_une_reservation(tenant, {"allergies": "Arachides et noix"})

    reponse = afficher_la_fiche(admin_client, tenant, reservation)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="reservation-custom-form-answers"' in contenu
    assert "Arachides et noix" in contenu


def test_la_fiche_n_affiche_plus_le_json_brut(admin_client, tenant):
    """Le champ JSON custom_form n'est plus dans le formulaire.
    / The raw custom_form JSON field is no longer in the form."""
    reservation = creer_une_reservation(tenant, {"allergies": "Arachides et noix"})

    reponse = afficher_la_fiche(admin_client, tenant, reservation)

    contenu = reponse.content.decode()
    assert 'name="custom_form"' not in contenu


def test_la_fiche_sans_reponse_affiche_un_message(admin_client, tenant):
    """Sans réponse, un message le dit.
    / Without answers, a message says so."""
    reservation = creer_une_reservation(tenant, None)

    reponse = afficher_la_fiche(admin_client, tenant, reservation)

    contenu = reponse.content.decode()
    assert 'data-testid="reservation-custom-form-answers"' in contenu
    assert 'name="custom_form"' not in contenu

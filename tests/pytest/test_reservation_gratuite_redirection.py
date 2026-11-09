"""
Tests de la fin d'une réservation directe gratuite, et de l'option « Désactiver le panier ».
/ Tests for the end of a free direct booking, and for the "disable cart" option.

LOCALISATION : tests/pytest/test_reservation_gratuite_redirection.py

Code testé / Tested code :
- BaseBillet/views.py, EventMVT.reservation (redirection après une réservation gratuite)
- BaseBillet/templates/commun/formulaires/reservation.html (boutons selon la connexion
  et l'option panier)

Réserver exige d'être connecté : le cas « visiteur anonyme » est couvert par
tests/pytest/test_achat_reserve_aux_connectes.py.
/ Booking requires a login: the anonymous case lives in test_achat_reserve_aux_connectes.py.

Chaque test est marqué `django_db` : la transaction est annulée à la fin.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_reservation_gratuite_redirection.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


def reserver_un_billet_gratuit(client, concert, email):
    """
    Réserve un billet à 0 € par le formulaire de l'événement (parcours direct).
    / Books one 0 € ticket through the event form (direct flow).
    """
    return client.post(
        f"/event/{concert.evenement.slug}/reservation/",
        {
            "event": str(concert.evenement.uuid),
            "email": email,
            str(concert.tarif.uuid): "1",
        },
        **EN_TETE_HTMX,
    )


def test_visiteur_connecte_va_sur_mes_reservations(lieu):
    """
    Visiteur connecté (compte actif) : il va sur « Mes réservations », où sont ses billets.
    / Logged-in visitor: goes to "my bookings".
    """
    from django.urls import reverse

    compte_connecte = creer_utilisateur(actif=True)
    concert = creer_evenement_avec_tarif(prix="0.00")

    reponse = reserver_un_billet_gratuit(
        client_connecte(compte_connecte), concert, compte_connecte.email
    )

    assert reponse["HX-Redirect"] == reverse("my_account-my-reservations")


@pytest.mark.parametrize("panier_desactive", [False, True])
def test_le_formulaire_n_affiche_les_boutons_panier_que_si_le_panier_est_actif(
    lieu, panier_desactive
):
    """
    Panier désactivé sur l'événement : aucun bouton panier, même connecté. Le bouton de
    réservation directe reste toujours là.
    / Cart disabled on the event: no cart button, even logged in. Direct booking stays.
    """
    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.evenement.panier_desactive = panier_desactive
    concert.evenement.save(update_fields=["panier_desactive"])

    page = client_connecte(creer_utilisateur()).get(f"/event/{concert.evenement.slug}/")
    contenu = page.content.decode()

    assert page.status_code == 200
    assert 'data-testid="booking-submit"' in contenu
    assert ('data-testid="booking-add-to-cart"' in contenu) is (not panier_desactive)


def test_un_anonyme_sur_un_evenement_sans_panier_ne_voit_que_le_bouton_de_connexion(lieu):
    """
    Panier désactivé et visiteur anonyme : le seul bouton ouvre le panneau de connexion.
    Aucun bouton d'envoi direct : un POST anonyme serait refusé (403).
    / Cart disabled and anonymous visitor: only the login button, no direct submit.
    """
    concert = creer_evenement_avec_tarif(prix="0.00")
    concert.evenement.panier_desactive = True
    concert.evenement.save(update_fields=["panier_desactive"])

    page = client_connecte().get(f"/event/{concert.evenement.slug}/")
    contenu = page.content.decode()

    assert page.status_code == 200
    assert 'data-testid="booking-login"' in contenu
    assert 'data-testid="booking-submit"' not in contenu
    assert 'data-testid="booking-add-to-cart"' not in contenu

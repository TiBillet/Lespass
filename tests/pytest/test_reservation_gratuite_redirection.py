"""
Tests de la fin d'une réservation directe gratuite, et de l'option « Désactiver le panier ».
/ Tests for the end of a free direct booking, and for the "disable cart" option.

LOCALISATION : tests/pytest/test_reservation_gratuite_redirection.py

Code testé / Tested code :
- BaseBillet/views.py, EventMVT.reservation (redirection selon le compte et la connexion)
- BaseBillet/templates/commun/formulaires/reservation.html (boutons panier)

Chaque test est marqué `django_db` : la transaction est annulée à la fin.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_reservation_gratuite_redirection.py"
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


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


def textes_des_messages(reponse):
    """Les messages (toasts) ajoutés pendant la requête. / Messages queued during the request."""
    return [str(message) for message in get_messages(reponse.wsgi_request)]


def test_visiteur_anonyme_avec_un_email_deja_valide_revient_sur_l_evenement(lieu):
    """
    Visiteur NON connecté, e-mail d'un compte déjà validé : les billets partent par mail.
    Il revient sur la page de l'événement, pas sur « Mes réservations » (qui exige d'être
    connecté). Un seul toast, de succès.
    / Anonymous visitor with a validated email: back to the event page, one success toast.
    """
    compte_deja_valide = creer_utilisateur(actif=True)
    concert = creer_evenement_avec_tarif(prix="0.00")

    reponse = reserver_un_billet_gratuit(
        client_connecte(), concert, compte_deja_valide.email
    )

    assert reponse.status_code == 200
    assert reponse["HX-Redirect"] == f"/event/{concert.evenement.slug}/"
    assert textes_des_messages(reponse) == [
        "Réservation reçue ! Vos billets arrivent par e-mail."
    ]


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


def test_nouvel_email_affiche_la_demande_de_validation(lieu):
    """
    E-mail inconnu : le compte créé n'est pas actif. Pas de redirection : le panneau affiche
    le message qui demande de valider l'e-mail.
    / Unknown email: inactive account, the panel shows the email validation message.
    """
    concert = creer_evenement_avec_tarif(prix="0.00")
    email_inconnu = f"test+redirection{identifiant_unique()}@mock.test"

    reponse = reserver_un_billet_gratuit(client_connecte(), concert, email_inconnu)

    assert "HX-Redirect" not in reponse
    assert 'data-testid="reservation-ok-validation-email"' in reponse.content.decode()


def test_la_demande_de_validation_donne_l_adresse_de_l_expediteur(lieu):
    """
    Le message de validation donne l'adresse qui enverra le mail (DEFAULT_FROM_EMAIL),
    sans le nom affiché quand la variable a la forme « Nom <adresse> ».
    / The validation message shows the sender address, without the display name.
    """
    from unittest.mock import patch

    concert = creer_evenement_avec_tarif(prix="0.00")
    email_inconnu = f"test+expediteur{identifiant_unique()}@mock.test"

    with patch.dict("os.environ", {"DEFAULT_FROM_EMAIL": "Le Facteur <facteur@expediteur.test>"}):
        reponse = reserver_un_billet_gratuit(client_connecte(), concert, email_inconnu)

    contenu = reponse.content.decode()
    assert "facteur@expediteur.test" in contenu
    assert "Le Facteur" not in contenu


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

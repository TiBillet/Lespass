"""
Tests du réglage « Se connecter avant de réserver ».
/ Tests of the "log in before booking" setting.

LOCALISATION : tests/pytest/test_connexion_avant_de_reserver.py

LA RÈGLE TESTÉE
Quand `Configuration.connexion_obligatoire_pour_reserver` est coché, le bouton
« réserver » d'une personne non connectée ouvre le panneau de connexion, avec l'adresse
de l'événement (`?openbookingPanel=true`). La vue `connexion` signe cette adresse et la
met dans le lien du mail : au clic, `emailconfirmation` y ramène la personne. Une
adresse d'un autre site est ignorée.
/ With the setting on, an anonymous booking button opens the login panel; the login
link brings the person back to the event, booking form open. Off-site addresses are ignored.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core import signing
from django_tenants.utils import tenant_context

from fabriques_panier import (
    client_connecte,
    configuration_modifiee,
    creer_evenement_avec_tarif,
    creer_utilisateur,
)

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
    """Le lieu `lespass`, Stripe simulé. / The `lespass` venue, Stripe faked."""
    with tenant_context(tenant):
        yield tenant


def page_de_l_evenement(evenement, utilisateur=None):
    """HTML de la page publique de l'événement. / Public event page HTML."""
    reponse = client_connecte(utilisateur).get(f"/event/{evenement.slug}/")
    assert reponse.status_code == 200
    return reponse.content.decode()


# --------------------------------------------------------------------------
# Le bouton « réserver »
# / The booking button
# --------------------------------------------------------------------------


def test_reglage_coche_le_bouton_ouvre_la_connexion_pour_une_personne_non_connectee(
    lieu,
):
    """Réglage coché, personne non connectée : le bouton ouvre la connexion, avec l'adresse de retour.
    / Setting on, anonymous: the button opens the login panel with the return address."""
    concert = creer_evenement_avec_tarif()

    with configuration_modifiee(connexion_obligatoire_pour_reserver=True):
        page = page_de_l_evenement(concert.evenement)

    assert 'data-testid="booking-open-login"' in page
    assert 'data-testid="booking-open-panel"' not in page
    adresse_attendue = f"/event/{concert.evenement.slug}/?openbookingPanel=true"
    assert f'data-adresse-de-retour-apres-connexion="{adresse_attendue}"' in page


def test_reglage_coche_le_bouton_ouvre_le_formulaire_pour_une_personne_connectee(lieu):
    """Réglage coché, personne connectée : le bouton ouvre le formulaire, comme d'habitude.
    / Setting on, logged in: the button opens the booking form as usual."""
    concert = creer_evenement_avec_tarif()

    with configuration_modifiee(connexion_obligatoire_pour_reserver=True):
        page = page_de_l_evenement(concert.evenement, creer_utilisateur())

    assert 'data-testid="booking-open-panel"' in page
    assert 'data-testid="booking-open-login"' not in page


def test_reglage_decoche_le_bouton_ouvre_le_formulaire_pour_une_personne_non_connectee(
    lieu,
):
    """Réglage décoché (par défaut) : rien ne change pour une personne non connectée.
    / Setting off (default): nothing changes for an anonymous visitor."""
    concert = creer_evenement_avec_tarif()

    with configuration_modifiee(connexion_obligatoire_pour_reserver=False):
        page = page_de_l_evenement(concert.evenement)

    assert 'data-testid="booking-open-panel"' in page
    assert 'data-testid="booking-open-login"' not in page


# --------------------------------------------------------------------------
# La vue de connexion et le lien du mail
# / The login view and the login link
# --------------------------------------------------------------------------


def demander_la_connexion(adresse_de_retour):
    """
    Envoie le formulaire de connexion avec ce `next`. Le compte et le mail sont simulés.
    Rend le `next_url` donné à get_or_create_user.
    / Posts the login form with this `next`; returns the next_url given to get_or_create_user.
    """
    compte_simule = MagicMock()
    compte_simule.get_connect_token.return_value = "jeton"
    with patch(
        "BaseBillet.views.get_or_create_user", return_value=compte_simule
    ) as creer_le_compte:
        client_connecte().post(
            "/connexion/",
            {"email": "personne@exemple.fr", "next": adresse_de_retour},
            HTTP_HX_REQUEST="true",
        )
    return creer_le_compte.call_args.kwargs["next_url"]


def test_connexion_signe_une_adresse_de_retour_du_site(lieu):
    """Une adresse du site est signée et passée au mail de connexion.
    / A same-site address is signed and given to the login mail."""
    adresse_de_retour_signee = demander_la_connexion(
        "/event/concert/?openbookingPanel=true"
    )

    assert (
        signing.loads(adresse_de_retour_signee)
        == "/event/concert/?openbookingPanel=true"
    )


@pytest.mark.parametrize(
    "adresse_d_un_autre_site",
    ["https://ailleurs.example/piege/", "//ailleurs.example/piege/", "piege/"],
)
def test_connexion_ignore_une_adresse_d_un_autre_site(lieu, adresse_d_un_autre_site):
    """Une adresse d'un autre site (ou pas une adresse du site) est ignorée.
    / An off-site address is ignored."""
    assert demander_la_connexion(adresse_d_un_autre_site) is None


def test_connexion_sans_adresse_de_retour_ne_change_rien(lieu):
    """Le panneau ouvert par la barre de menu envoie un `next` vide : aucun retour prévu.
    / An empty `next` (menu login) gives no return address."""
    assert demander_la_connexion("") is None


def test_lien_du_mail_ramene_sur_l_evenement_formulaire_ouvert(lieu):
    """Le lien du mail connecte la personne et la ramène sur l'événement, formulaire ouvert.
    / The login link logs the person in and brings them back to the event, form open."""
    personne = creer_utilisateur()
    adresse_de_retour = "/event/concert/?openbookingPanel=true"

    reponse = client_connecte().get(
        f"/emailconfirmation/{personne.get_connect_token()}?next={signing.dumps(adresse_de_retour)}"
    )

    assert reponse.status_code == 302
    assert reponse["Location"] == adresse_de_retour

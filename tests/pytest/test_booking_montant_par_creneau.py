"""
Tests du montant payé pour une réservation de ressource, par créneau.
/ Tests of the amount paid for a resource booking, per slot.

LOCALISATION : tests/pytest/test_booking_montant_par_creneau.py

Spécification : booking/spec/main/booking-form.md, section « Tarifs », règles R1 à R3.
/ Specification: booking/spec/main/booking-form.md, section "Tarifs", rules R1 to R3.

Ces tests sont ici, et pas dans booking/tests/, parce qu'ils passent par le paiement :
ils ont besoin de `mock_stripe` (tests/pytest/conftest.py) et des simulations de
fabriques_panier.py. Chaque règle est testée sans panier et avec panier.
/ Here rather than in booking/tests/ because they go through payment and need
`mock_stripe` and the cart fakes. Each rule is tested with and without the cart.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_booking_montant_par_creneau.py -v
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

SANS_PANIER = "sans_panier"
AVEC_PANIER = "avec_panier"
LES_DEUX_PARCOURS = [SANS_PANIER, AVEC_PANIER]

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant, stripe=mock_stripe)


def reserver_des_creneaux(
    parcours, client, location, duree_du_creneau_en_minutes, nombre_de_creneaux,
    montant_libre=None,
):
    """
    Réserve `nombre_de_creneaux` créneaux consécutifs par le formulaire de réservation.
    `montant_libre` : le montant saisi dans le champ d'un tarif à prix libre.
    Sans panier : `POST /booking/<ressource>/book/`. Avec panier : ajout puis paiement.
    / Books consecutive slots through the booking form. `montant_libre`: the amount typed
    in an open price's field.
    """
    debut = location.debut_du_creneau
    fin = debut + timedelta(minutes=duree_du_creneau_en_minutes * nombre_de_creneaux)
    donnees_du_formulaire = {
        "resource": str(location.ressource.pk),
        "price_uuid": str(location.tarif.uuid),
        "start_datetime": debut.replace(tzinfo=None).isoformat(),
        "end_time": fin.replace(tzinfo=None).isoformat(),
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    if montant_libre is not None:
        donnees_du_formulaire[f"custom_amount_{location.tarif.uuid}"] = montant_libre

    if parcours == SANS_PANIER:
        return client.post(
            f"/booking/{location.ressource.pk}/book/",
            donnees_du_formulaire,
            **EN_TETE_HTMX,
        )

    reponse_de_l_ajout = client.post(
        "/panier/add/resource/", donnees_du_formulaire, **EN_TETE_HTMX
    )
    client.post("/panier/checkout/", **EN_TETE_HTMX)
    return reponse_de_l_ajout


def booking_de(acheteur, location):
    """Le booking de l'acheteur sur cette ressource, ou None.
    / The buyer's booking on this resource, or None."""
    from booking.models import Booking

    return Booking.objects.filter(user=acheteur, resource=location.ressource).first()


def montant_paye_en_centimes(acheteur, location):
    """
    Le montant de la ligne de vente du booking, en centimes : ce que Stripe facturera.
    / The booking's sale line amount, in cents: what Stripe will charge.
    """
    from BaseBillet.models import LigneArticle

    booking = booking_de(acheteur, location)
    assert booking is not None
    return LigneArticle.objects.get(booking=booking).amount


# --------------------------------------------------------------------------
# R1 : tarif fixe, N créneaux = N fois le montant affiché
# / R1: fixed price, N slots = N times the displayed amount
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r1_un_creneau_paye_le_montant_affiche(lieu, parcours):
    """
    R1 : 12 €/h pour un créneau de 90 minutes : affiché 18 €, payé 18 €.
    / R1: 12 €/h for a 90-minute slot: shown 18 €, paid 18 €.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(prix="12.00", duree_du_creneau_en_minutes=90)

    reserver_des_creneaux(parcours, client_connecte(acheteur), location, 90, 1)

    assert montant_paye_en_centimes(acheteur, location) == 1800


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r1_n_creneaux_payent_n_fois_le_montant_arrondi(lieu, parcours):
    """
    R1 : 1,03 €/h pour des créneaux de 50 minutes : 0,858… € par créneau, affiché 0,90 €.
    Pour 4 créneaux, on paie 4 × 0,90 = 3,60 €, et pas l'arrondi du total exact (3,40 €).
    / R1: 0.858… per slot, shown 0.90; 4 slots pay 4 × 0.90 = 3.60, not the rounded
    exact total (3.40).
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(prix="1.03", duree_du_creneau_en_minutes=50)

    reserver_des_creneaux(parcours, client_connecte(acheteur), location, 50, 4)

    assert montant_paye_en_centimes(acheteur, location) == 360


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "prix, duree_du_creneau_en_minutes, montant_en_centimes",
    [
        ("10.00", 40, 2010),
        ("10.00", 50, 2490),
        ("7.00", 45, 1590),
        ("3.33", 180, 3000),
    ],
)
def test_r1_tableau_des_montants_pour_3_creneaux(
    lieu, parcours, prix, duree_du_creneau_en_minutes, montant_en_centimes
):
    """
    R1 : la colonne « 3 créneaux » du tableau de la section « Tarifs ».
    / R1: the "3 créneaux" column of the table in the "Tarifs" section.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix=prix, duree_du_creneau_en_minutes=duree_du_creneau_en_minutes
    )

    reserver_des_creneaux(
        parcours, client_connecte(acheteur), location, duree_du_creneau_en_minutes, 3
    )

    assert montant_paye_en_centimes(acheteur, location) == montant_en_centimes


# --------------------------------------------------------------------------
# R2 : le minimum d'un prix libre, arrondi aux 10 centimes supérieurs
# / R2: the open-price minimum, rounded up to 10 cents
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r2_un_montant_egal_au_minimum_affiche_est_accepte(lieu, parcours):
    """
    R2 : 10 €/h minimum pour un créneau de 50 minutes : minimum affiché 8,40 €. Saisir
    8,40 est accepté, et on paie 8,40 €.
    / R2: minimum shown 8.40 for a 50-minute slot at 10 €/h: typing 8.40 is accepted.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix="10.00", prix_libre=True, duree_du_creneau_en_minutes=50
    )

    reserver_des_creneaux(
        parcours, client_connecte(acheteur), location, 50, 1, montant_libre="8.40"
    )

    assert montant_paye_en_centimes(acheteur, location) == 840


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r2_un_montant_sous_le_minimum_affiche_est_refuse(lieu, parcours):
    """
    R2 : même tarif, saisir 8,39 est refusé, bien que ce montant, ramené à l'heure,
    dépasse 10 € : aucun booking.
    / R2: same price, typing 8.39 is refused although its hourly value exceeds 10 €.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix="10.00", prix_libre=True, duree_du_creneau_en_minutes=50
    )

    reserver_des_creneaux(
        parcours, client_connecte(acheteur), location, 50, 1, montant_libre="8.39"
    )

    assert booking_de(acheteur, location) is None


# --------------------------------------------------------------------------
# R3 : le montant saisi d'un prix libre est par créneau
# / R3: an open price's typed amount is per slot
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r3_le_montant_saisi_est_par_creneau(lieu, parcours):
    """
    R3 : prix libre (minimum 6 €/h, soit 5 € par créneau de 50 minutes), 7 € saisis,
    2 créneaux : on paie 2 × 7 = 14 €.
    / R3: open price, 7 € typed, 2 slots of 50 minutes: paid 2 × 7 = 14 €.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix="6.00", prix_libre=True, duree_du_creneau_en_minutes=50
    )

    reserver_des_creneaux(
        parcours, client_connecte(acheteur), location, 50, 2, montant_libre="7.00"
    )

    assert montant_paye_en_centimes(acheteur, location) == 1400


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "montant_libre, duree_du_creneau_en_minutes, montant_en_centimes",
    [
        ("6.67", 40, 2001),
        ("0.76", 45, 228),
    ],
)
def test_r3_le_montant_saisi_n_est_pas_arrondi_aux_10_centimes(
    lieu, parcours, montant_libre, duree_du_creneau_en_minutes, montant_en_centimes
):
    """
    R3 : prix libre sans minimum, 3 créneaux : on paie 3 fois le montant saisi, au centime
    près, sans l'arrondi des tarifs fixes.
    / R3: open price, 3 slots: 3 times the typed amount, to the cent, without the rounding
    of fixed prices.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix="0.00", prix_libre=True, duree_du_creneau_en_minutes=duree_du_creneau_en_minutes
    )

    reserver_des_creneaux(
        parcours,
        client_connecte(acheteur),
        location,
        duree_du_creneau_en_minutes,
        3,
        montant_libre=montant_libre,
    )

    assert montant_paye_en_centimes(acheteur, location) == montant_en_centimes


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_r3_un_montant_qui_ne_tombe_pas_juste_en_heure(lieu, parcours):
    """
    R3 : 20 € saisis pour un créneau de 180 minutes (6,666… €/h) : on paie 20 € pile.
    / R3: 20 € typed for a 180-minute slot (6.666… €/h): exactly 20 € paid.
    """
    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(
        prix="5.00", prix_libre=True, duree_du_creneau_en_minutes=180
    )

    reserver_des_creneaux(
        parcours, client_connecte(acheteur), location, 180, 1, montant_libre="20.00"
    )

    assert montant_paye_en_centimes(acheteur, location) == 2000

"""
Tests du tarif « Ne peut pas être vendu seul » (exemple : un tarif enfant).
/ Tests of the accompanied-only price (e.g. a child price).

LOCALISATION : tests/pytest/test_tarif_vendu_seulement_accompagne.py

LA RÈGLE TESTÉE
Un tarif coché « Ne peut pas être vendu seul » (`Price.vendu_seulement_accompagne`) exige,
pour chaque événement, au moins un billet d'un tarif non coché dans le même achat. Un pass
compte sur chacun de ses événements. Contrôlé au paiement du panier et en réservation
directe ; ni en caisse, ni par l'API v2.
/ An accompanied-only price needs a non-accompanied ticket on the same event, same purchase.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.models import Price, Product, Reservation
from BaseBillet.services_commande import CommandeServiceError
from BaseBillet.services_panier import PanierSession
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    requete_avec_session,
    taches_celery_enregistrees,
)
from test_caracterisation_en_ligne import reserver_des_billets_sans_panier
from test_pass_multi_evenements import creer_un_pass_deux_jours, payer_le_panier

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
    """
    Le lieu `lespass`, avec Stripe (compte Connect compris) et Celery simulés, comme dans
    test_pass_multi_evenements.py.
    / The `lespass` venue, with Stripe (Connect included) and Celery faked.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with patch(
                "BaseBillet.models.Configuration.get_stripe_connect_account",
                return_value="acct_test_accompagne",
            ):
                with taches_celery_enregistrees() as taches_demandees:
                    yield SimpleNamespace(
                        tenant=tenant, taches_demandees=taches_demandees
                    )


MESSAGE_DEBUT = "ne peut pas être acheté seul"


def ajouter_un_tarif_enfant(produit, prix="5.00"):
    """Un tarif « Moins de 12 ans », coché « Ne peut pas être vendu seul ».
    / A "Under 12" price, accompanied-only."""
    return Price.objects.create(
        product=produit,
        name="Moins de 12 ans",
        prix=Decimal(prix),
        publish=True,
        vendu_seulement_accompagne=True,
    )


def un_panier():
    """Un panier vide, pour un nouvel acheteur. Rend (panier, acheteur).
    / An empty cart for a new buyer."""
    acheteur = creer_utilisateur()
    return PanierSession(requete_avec_session(acheteur)), acheteur


# --------------------------------------------------------------------------
# Le panier
# / The cart
# --------------------------------------------------------------------------


def test_panier_refuse_un_tarif_enfant_seul(lieu):
    """Un billet enfant seul au panier : le paiement est refusé, avec le nom du tarif.
    / A child ticket alone: checkout refused, naming the price."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_enfant = ajouter_un_tarif_enfant(concert.produit)
    panier, acheteur = un_panier()
    panier.add_ticket(concert.evenement.uuid, tarif_enfant.uuid, qty=1)

    with pytest.raises(CommandeServiceError) as refus:
        payer_le_panier(panier, acheteur)

    assert MESSAGE_DEBUT in str(refus.value)
    assert "Moins de 12 ans" in str(refus.value)


def test_panier_accepte_un_tarif_enfant_avec_un_adulte(lieu):
    """Un billet enfant et un billet plein tarif du même événement : accepté.
    / A child ticket with a full-price ticket on the same event: accepted."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_enfant = ajouter_un_tarif_enfant(concert.produit)
    panier, acheteur = un_panier()
    panier.add_ticket(concert.evenement.uuid, tarif_enfant.uuid, qty=2)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    commande = payer_le_panier(panier, acheteur)

    assert commande.reservations.get().tickets.count() == 3


def test_panier_refuse_un_adulte_sur_un_autre_evenement(lieu):
    """L'adulte est sur un autre événement que l'enfant : refusé (la règle vaut par événement).
    / The adult is on another event: refused (the rule is per event)."""
    samedi = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=10)
    dimanche = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=11)
    tarif_enfant_du_samedi = ajouter_un_tarif_enfant(samedi.produit)
    panier, acheteur = un_panier()
    panier.add_ticket(samedi.evenement.uuid, tarif_enfant_du_samedi.uuid, qty=1)
    panier.add_ticket(dimanche.evenement.uuid, dimanche.tarif.uuid, qty=1)

    with pytest.raises(CommandeServiceError):
        payer_le_panier(panier, acheteur)


def test_panier_accepte_un_tarif_enfant_accompagne_par_un_pass(lieu):
    """Un pass plein tarif accompagne un billet enfant sur l'un de ses événements.
    / A full-price pass accompanies a child ticket on one of its events."""
    le_pass = creer_un_pass_deux_jours()
    produit_du_samedi = le_pass.samedi.products.exclude(
        pk=le_pass.produit_pass.pk
    ).get()
    tarif_enfant = ajouter_un_tarif_enfant(produit_du_samedi)
    panier, acheteur = un_panier()
    panier.add_ticket(le_pass.samedi.uuid, tarif_enfant.uuid, qty=1)
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    commande = payer_le_panier(panier, acheteur)

    assert commande.reservations.count() == 2


def test_panier_refuse_un_pass_enfant_accompagne_sur_un_seul_jour(lieu):
    """
    Un pass coché « Ne peut pas être vendu seul » avec un billet adulte du samedi seulement :
    le dimanche n'a pas d'accompagnant, refusé.
    / An accompanied-only pass with an adult on Saturday only: Sunday has none, refused.
    """
    le_pass = creer_un_pass_deux_jours()
    Price.objects.filter(pk=le_pass.tarif_pass.pk).update(
        vendu_seulement_accompagne=True
    )
    produit_du_samedi = le_pass.samedi.products.exclude(
        pk=le_pass.produit_pass.pk
    ).get()
    panier, acheteur = un_panier()
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)
    panier.add_ticket(
        le_pass.samedi.uuid,
        produit_du_samedi.prices.get(name="Plein tarif").uuid,
        qty=1,
    )

    with pytest.raises(CommandeServiceError) as refus:
        payer_le_panier(panier, acheteur)

    assert le_pass.dimanche.name in str(refus.value)


# --------------------------------------------------------------------------
# La réservation directe
# / Direct booking
# --------------------------------------------------------------------------


def creer_un_evenement_gratuit_avec_tarif_enfant():
    """
    Un événement gratuit : « réservation gratuite » (son tarif à 0 € est créé tout seul) et
    un tarif enfant à 0 €. Gratuit, pour réserver sans Stripe.
    / A free event with its 0 € price and a 0 € child price (no Stripe).
    """
    concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
    tarif_enfant = ajouter_un_tarif_enfant(concert.produit, prix="0")
    return concert, tarif_enfant


def test_reservation_directe_refuse_un_tarif_enfant_seul(lieu):
    """Réserver un billet enfant seul par le formulaire de l'événement : refusé, rien n'est créé.
    / Booking a child ticket alone through the event form: refused, nothing created."""
    concert, tarif_enfant = creer_un_evenement_gratuit_avec_tarif_enfant()
    acheteur = creer_utilisateur()

    reponse = reserver_des_billets_sans_panier(
        client_connecte(acheteur), acheteur, concert.evenement, {tarif_enfant: 1}
    )

    assert MESSAGE_DEBUT in reponse.content.decode()
    assert not Reservation.objects.filter(user_commande=acheteur).exists()


def test_reservation_directe_accepte_un_tarif_enfant_avec_un_adulte(lieu):
    """Réserver un billet enfant et un billet adulte d'un coup : accepté.
    / Booking a child and an adult ticket together: accepted."""
    concert, tarif_enfant = creer_un_evenement_gratuit_avec_tarif_enfant()
    acheteur = creer_utilisateur()

    reserver_des_billets_sans_panier(
        client_connecte(acheteur),
        acheteur,
        concert.evenement,
        {tarif_enfant: 1, concert.tarif: 1},
    )

    assert Reservation.objects.get(user_commande=acheteur).tickets.count() == 2

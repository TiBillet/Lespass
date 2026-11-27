"""
Tests du tarif « Ne peut pas être vendu seul » (exemple : un tarif enfant).
/ Tests of the accompanied-only price (e.g. a child price).

LOCALISATION : tests/pytest/test_tarif_vendu_seulement_accompagne.py

LA RÈGLE TESTÉE
Un tarif coché « Ne peut pas être vendu seul » (`Price.vendu_seulement_accompagne`) exige,
pour chaque événement, au moins un billet d'un tarif non coché dans le même achat. Un pass
compte sur chacun de ses événements. Contrôlé au paiement du panier et en réservation
directe ; ni en caisse, ni par l'API v2.
À l'annulation, quand plus aucun billet non coché ne reste dans une réservation (l'achat sur
un événement), ses billets cochés sont annulés avec, en un seul remboursement Stripe. Refusé
si l'un d'eux est déjà scanné.
/ An accompanied-only price needs a non-accompanied ticket on the same event, same purchase.
Cancelling the last companion cancels the accompanied tickets too (one Stripe refund).
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    LigneArticle,
    Price,
    Product,
    Reservation,
    Ticket,
    reservations_concernees_par_l_annulation,
)
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


# --------------------------------------------------------------------------
# L'annulation en cascade
# / Cascade cancellation
# --------------------------------------------------------------------------


def payer_par_stripe(panier, acheteur, mock_stripe):
    """
    Paie le panier (vrai paiement Stripe simulé par mock_stripe), puis le valide, comme
    test_pass_multi_evenements.acheter_le_pass_par_stripe. Rend la commande.
    / Pays the cart, then simulates the validated Stripe payment.
    """
    from BaseBillet.models import Paiement_stripe, PaymentMethod
    from BaseBillet.services_vente import encaisser_vente_stripe
    from fabriques_panier import identifiant_unique

    from BaseBillet.services_commande import CommandeService

    commande, _succes = CommandeService.materialiser(
        panier, acheteur, first_name="Test", last_name="Accompagne", email=acheteur.email,
    )
    paiement = commande.paiement_stripe
    lignes_du_paiement = LigneArticle.objects.filter(paiement_stripe=paiement)
    montant_encaisse = 0
    for ligne in lignes_du_paiement:
        montant_encaisse += ligne.total_catalogue
    identifiant_du_paiement = f"pi_accompagne_{identifiant_unique()}"
    Paiement_stripe.objects.filter(pk=paiement.pk).update(
        status=Paiement_stripe.VALID,
        payment_intent_id=identifiant_du_paiement,
        montant_encaisse=montant_encaisse,
        moyen=PaymentMethod.STRIPE_NOFED,
    )
    lignes_du_paiement.update(status=LigneArticle.VALID)
    Ticket.objects.filter(reservation__commande=commande).update(status=Ticket.NOT_SCANNED)
    commande.reservations.update(status=Reservation.VALID)
    paiement.refresh_from_db()
    encaisser_vente_stripe(paiement)
    mock_stripe.session.payment_intent = identifiant_du_paiement
    return commande


def acheter_adultes_et_enfant_par_stripe(mock_stripe, adultes=1):
    """
    Concert à 10 €, tarif enfant à 5 € : achète `adultes` billets adulte et un billet enfant
    par Stripe. Rend (réservation, billets adulte, billet enfant).
    / Buys adult tickets and one child ticket by Stripe.
    """
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_enfant = ajouter_un_tarif_enfant(concert.produit)
    panier, acheteur = un_panier()
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=adultes)
    panier.add_ticket(concert.evenement.uuid, tarif_enfant.uuid, qty=1)
    reservation = payer_par_stripe(panier, acheteur, mock_stripe).reservations.get()
    billets_adulte = list(reservation.tickets.filter(pricesold__price=concert.tarif))
    billet_enfant = reservation.tickets.get(pricesold__price=tarif_enfant)
    return reservation, billets_adulte, billet_enfant


@pytest.mark.parametrize("par_l_admin", [False, True])
def test_annuler_le_seul_adulte_annule_l_enfant_en_un_remboursement(lieu, mock_stripe, par_l_admin):
    """Annuler le seul billet adulte annule le billet enfant : un remboursement Stripe de 15 €.
    / Cancelling the only adult cancels the child: one Stripe refund of 15."""
    from test_caracterisation_annulations import rembourser_comme_stripe

    reservation, (billet_adulte,), billet_enfant = acheter_adultes_et_enfant_par_stripe(mock_stripe)

    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe) as remboursement_stripe:
        reservation.cancel_and_refund_ticket(billet_adulte, annulation_par_l_admin=par_l_admin)

    assert remboursement_stripe.call_count == 1
    assert remboursement_stripe.call_args.kwargs["amount"] == 1500
    billet_enfant.refresh_from_db()
    assert billet_enfant.status == Ticket.CANCELED
    assert reservation.total_paid() == 0


def test_annuler_un_adulte_garde_l_enfant_s_il_reste_un_adulte(lieu, mock_stripe):
    """Deux adultes et un enfant : annuler un adulte ne touche pas l'enfant.
    / Two adults and a child: cancelling one adult keeps the child."""
    from test_caracterisation_annulations import rembourser_comme_stripe

    reservation, billets_adulte, billet_enfant = acheter_adultes_et_enfant_par_stripe(
        mock_stripe, adultes=2
    )

    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe) as remboursement_stripe:
        reservation.cancel_and_refund_ticket(billets_adulte[0])

    assert remboursement_stripe.call_args.kwargs["amount"] == 1000
    billet_enfant.refresh_from_db()
    assert billet_enfant.status == Ticket.NOT_SCANNED


def test_enfant_scanne_refuse_l_annulation_du_seul_adulte(lieu, mock_stripe):
    """
    Le billet enfant est scanné : annuler le seul adulte est refusé, avec le nom du tarif,
    sans rien rembourser ni annuler.
    / The child ticket is scanned: cancelling the only adult is refused, nothing changes.
    """
    reservation, (billet_adulte,), billet_enfant = acheter_adultes_et_enfant_par_stripe(mock_stripe)
    Ticket.objects.filter(pk=billet_enfant.pk).update(status=Ticket.SCANNED)

    with patch("stripe.Refund.create") as remboursement_stripe:
        with pytest.raises(Exception) as refus:
            reservation.cancel_and_refund_ticket(billet_adulte, annulation_par_l_admin=True)

    assert "Moins de 12 ans" in str(refus.value)
    assert remboursement_stripe.call_count == 0
    billet_adulte.refresh_from_db()
    assert billet_adulte.status == Ticket.NOT_SCANNED


def test_pass_enfant_annule_avec_le_seul_adulte_du_samedi(lieu, mock_stripe):
    """
    Un pass coché « Ne peut pas être vendu seul » et un adulte chaque jour. Annuler l'adulte
    du samedi annule le pass sur les deux jours ; l'adulte du dimanche reste.
    / An accompanied-only pass, an adult each day: cancelling Saturday's adult cancels the
    whole pass; Sunday's adult stays.
    """
    from test_caracterisation_annulations import rembourser_comme_stripe

    le_pass = creer_un_pass_deux_jours()
    Price.objects.filter(pk=le_pass.tarif_pass.pk).update(vendu_seulement_accompagne=True)
    panier, acheteur = un_panier()
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)
    for evenement in [le_pass.samedi, le_pass.dimanche]:
        produit_du_jour = evenement.products.exclude(pk=le_pass.produit_pass.pk).get()
        panier.add_ticket(evenement.uuid, produit_du_jour.prices.get(name="Plein tarif").uuid, qty=1)
    commande = payer_par_stripe(panier, acheteur, mock_stripe)
    reservation_du_samedi = commande.reservations.get(event=le_pass.samedi)
    reservation_du_dimanche = commande.reservations.get(event=le_pass.dimanche)
    adulte_du_samedi = reservation_du_samedi.tickets.get(pass_vendu__isnull=True)

    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe) as remboursement_stripe:
        reservation_du_samedi.cancel_and_refund_ticket(adulte_du_samedi)

    assert remboursement_stripe.call_count == 1
    assert not Ticket.objects.filter(pass_vendu__isnull=False, reservation__commande=commande).exclude(
        status=Ticket.CANCELED
    ).exists()
    assert reservation_du_dimanche.tickets.get(pass_vendu__isnull=True).status == Ticket.NOT_SCANNED


def test_annuler_la_reservation_du_samedi_annule_l_enfant_du_dimanche(lieu, mock_stripe):
    """
    Un pass plein tarif et un billet enfant le dimanche. Annuler la réservation du samedi
    annule le pass, donc l'enfant du dimanche reste seul : il est annulé aussi. Les deux
    réservations sont comptées pour le montant du mail.
    / Cancelling Saturday's reservation cancels the pass, so Sunday's child goes too.
    """
    from test_caracterisation_annulations import rembourser_comme_stripe

    le_pass = creer_un_pass_deux_jours()
    produit_du_dimanche = le_pass.dimanche.products.exclude(pk=le_pass.produit_pass.pk).get()
    tarif_enfant = ajouter_un_tarif_enfant(produit_du_dimanche)
    panier, acheteur = un_panier()
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)
    panier.add_ticket(le_pass.dimanche.uuid, tarif_enfant.uuid, qty=1)
    commande = payer_par_stripe(panier, acheteur, mock_stripe)
    reservation_du_samedi = commande.reservations.get(event=le_pass.samedi)
    reservation_du_dimanche = commande.reservations.get(event=le_pass.dimanche)

    reservations_touchees = reservations_concernees_par_l_annulation(reservation_du_samedi)
    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe) as remboursement_stripe:
        reservation_du_samedi.cancel_and_refund_resa()

    assert {r.pk for r in reservations_touchees} == {reservation_du_samedi.pk, reservation_du_dimanche.pk}
    assert remboursement_stripe.call_count == 1
    assert not reservation_du_dimanche.tickets.exclude(status=Ticket.CANCELED).exists()


def test_mail_du_client_compte_le_billet_enfant_annule_avec(lieu, mock_stripe):
    """Le client annule le seul adulte (10 €) : le mail annonce 15 €, enfant compris.
    / The customer cancels the only adult: the mail says 15, child included."""
    from test_caracterisation_annulations import client_de_mon_compte, rembourser_comme_stripe

    reservation, (billet_adulte,), _billet_enfant = acheter_adultes_et_enfant_par_stripe(mock_stripe)

    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe):
        client_de_mon_compte(lieu, reservation.user_commande).post(
            f"/my_account/{billet_adulte.uuid}/cancel_ticket/", HTTP_HX_REQUEST="true"
        )

    mails_de_billet = []
    for nom_de_la_tache, arguments in lieu.taches_demandees:
        if nom_de_la_tache == "send_ticket_cancellation_user":
            mails_de_billet.append(arguments)
    assert mails_de_billet == [(str(billet_adulte.uuid), 1500)]

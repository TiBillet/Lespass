"""
Tests du pass multi-événements, hors caisse (voir test_pass_multi_evenements_caisse.py).
/ Multi-event pass tests, register excluded.

LOCALISATION : tests/pytest/test_pass_multi_evenements.py

LES RÈGLES TESTÉES
Un pass (`Product.est_un_pass`) couvre au moins 2 événements, chacun avec son prix
(`EvenementDuPass.prix`) ; le prix du pass est leur somme.
- Vente : un billet par événement au prix de sa ligne, tous avec le même identifiant
  (`Ticket.pass_vendu`). Le stock compte des passes. En ligne, plus de vente une fois le
  premier événement commencé. Le pass s'achète par le panier, pas en réservation directe.
- Admin : un seul tarif sans prix libre, synchronisé avec les événements du pass.
- Annulation : le pass est indivisible, et refusé si un de ses billets est scanné.
/ Pass sale, admin and cancellation rules (online).
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework import serializers

from BaseBillet.models import (
    EvenementDuPass,
    LigneArticle,
    Price,
    Product,
    Reservation,
    SaleOrigin,
    Ticket,
)
from BaseBillet.models_vente import Vente
from BaseBillet.services_commande import CommandeService
from BaseBillet.services_panier import InvalidItemError, PanierSession
from BaseBillet.services_pass import deplier_le_pass
from BaseBillet.services_vente import ouvrir_vente
from BaseBillet.validators import TicketCreator
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    requete_avec_session,
    taches_celery_enregistrees,
)
from test_caracterisation_en_ligne import reserver_des_billets_sans_panier

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
    Le lieu `lespass`, avec Stripe (compte Connect compris) et Celery simulés. Sans compte
    Connect simulé, le premier prix Stripe appellerait le vrai Stripe.
    / The `lespass` venue, with Stripe (Connect included) and Celery faked.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with patch(
                "BaseBillet.models.Configuration.get_stripe_connect_account",
                return_value="acct_test_pass",
            ):
                with taches_celery_enregistrees():
                    yield tenant


def creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00", stock_de_passes=None):
    """
    Un pass samedi + dimanche, avec un tarif à la somme des deux lignes.
    Rend `samedi`, `dimanche`, `produit_pass`, `tarif_pass`.
    / A Saturday + Sunday pass with one price (the sum).
    """
    samedi = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    dimanche = creer_evenement_avec_tarif(jours_avant_l_evenement=11).evenement

    produit_pass = Product.objects.create(
        name=f"TEST_pass {identifiant_unique()}",
        categorie_article=Product.BILLET,
        est_un_pass=True,
    )
    EvenementDuPass.objects.create(produit=produit_pass, evenement=samedi, prix=Decimal(prix_samedi))
    EvenementDuPass.objects.create(produit=produit_pass, evenement=dimanche, prix=Decimal(prix_dimanche))
    samedi.products.add(produit_pass)
    dimanche.products.add(produit_pass)

    tarif_pass = Price.objects.create(
        product=produit_pass,
        name="Pass 2 jours",
        prix=produit_pass.prix_total_du_pass(),
        publish=True,
        stock=stock_de_passes,
    )
    return SimpleNamespace(
        samedi=samedi,
        dimanche=dimanche,
        produit_pass=produit_pass,
        tarif_pass=tarif_pass,
    )


def acheter_le_pass(le_pass, acheteur, quantite=1):
    """
    Achète des passes comme le panier : une réservation par événement, une vente, les
    mêmes identifiants. Rend les réservations.
    / Buys passes like the cart does; returns the reservations.
    """
    pass_deplie = deplier_le_pass(le_pass.produit_pass, quantite)
    identifiants_des_passes = {le_pass.tarif_pass.uuid: pass_deplie["identifiants_des_passes"]}

    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)
    reservations = []
    for ligne_du_pass in pass_deplie["lignes_du_pass"]:
        reservation = Reservation.objects.create(user_commande=acheteur, event=ligne_du_pass.evenement)
        TicketCreator(
            reservation=reservation,
            products_dict={le_pass.produit_pass: {le_pass.tarif_pass: quantite}},
            create_checkout=False,
            vente=vente,
            identifiants_des_passes=identifiants_des_passes,
        )
        reservations.append(reservation)
    return reservations


# --------------------------------------------------------------------------
# Le modèle : prix et disponibilité
# / The model: price and availability
# --------------------------------------------------------------------------


def test_prix_du_pass_est_la_somme_des_prix_par_evenement(lieu):
    """12 € le samedi + 13 € le dimanche = 25 € le pass.
    / 12 € + 13 € = 25 € for the pass."""
    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")

    assert le_pass.produit_pass.prix_total_du_pass() == Decimal("25.00")


def test_pass_vendable_quand_les_deux_jours_ont_des_places(lieu):
    """Deux événements à venir, avec des places : le pass est vendable.
    / Two upcoming events with seats: the pass can be sold."""
    le_pass = creer_un_pass_deux_jours()

    assert le_pass.produit_pass.pass_est_vendable() is True


def test_pass_plus_vendable_quand_le_premier_jour_a_commence(lieu):
    """Le samedi a commencé : le pass n'est plus vendable, même si le dimanche est à venir.
    / Saturday has started: the pass can no longer be sold."""
    le_pass = creer_un_pass_deux_jours()
    le_pass.samedi.datetime = timezone.now() - timedelta(hours=1)
    le_pass.samedi.save()

    assert le_pass.produit_pass.pass_est_vendable() is False


def test_pass_vendable_au_comptoir_apres_le_debut_du_premier_jour(lieu):
    """Au comptoir, le pass se vend encore une fois le samedi commencé (pas terminé).
    / At the register, the pass still sells once Saturday has started (not ended)."""
    le_pass = creer_un_pass_deux_jours()
    le_pass.samedi.datetime = timezone.now() - timedelta(hours=1)
    le_pass.samedi.end_datetime = timezone.now() + timedelta(hours=5)
    le_pass.samedi.save()

    assert le_pass.produit_pass.pass_est_vendable(vente_au_comptoir=True) is True
    assert le_pass.produit_pass.pass_est_vendable() is False


def test_pass_plus_vendable_au_comptoir_quand_un_jour_est_termine(lieu):
    """Au comptoir, le pass ne se vend plus une fois le samedi terminé.
    / At the register, the pass no longer sells once Saturday is over."""
    le_pass = creer_un_pass_deux_jours()
    le_pass.samedi.datetime = timezone.now() - timedelta(hours=30)
    le_pass.samedi.end_datetime = timezone.now() - timedelta(hours=20)
    le_pass.samedi.save()

    assert le_pass.produit_pass.pass_est_vendable(vente_au_comptoir=True) is False


def test_pass_plus_vendable_quand_un_jour_n_a_plus_assez_de_places(lieu):
    """Le dimanche n'a qu'une place : on peut vendre 1 pass, pas 2.
    / Sunday has one seat left: 1 pass can be sold, not 2."""
    le_pass = creer_un_pass_deux_jours()
    le_pass.dimanche.jauge_max = 1
    le_pass.dimanche.save()

    assert le_pass.produit_pass.pass_est_vendable(quantite_demandee=1) is True
    assert le_pass.produit_pass.pass_est_vendable(quantite_demandee=2) is False


def test_pass_sans_evenement_n_est_pas_vendable(lieu):
    """Un pass qui ne couvre aucun événement ne se vend pas.
    / A pass covering no event cannot be sold."""
    produit_pass_vide = Product.objects.create(
        name=f"TEST_pass vide {identifiant_unique()}",
        categorie_article=Product.BILLET,
        est_un_pass=True,
    )

    assert produit_pass_vide.pass_est_vendable() is False


# --------------------------------------------------------------------------
# Le stock : des passes, pas des billets
# / Stock: passes, not tickets
# --------------------------------------------------------------------------


def test_stock_du_pass_compte_les_passes_et_pas_les_billets(lieu):
    """
    Stock de 2 passes. Un pass acheté fait 2 billets (un par jour), mais compte pour 1.
    Il reste donc 1 pass : on peut en demander 1, pas 2.
    / Stock of 2 passes. One pass bought = 2 tickets but counts as 1.
    """
    le_pass = creer_un_pass_deux_jours(stock_de_passes=2)
    acheter_le_pass(le_pass, creer_utilisateur(), quantite=1)

    assert le_pass.tarif_pass.out_of_stock(quantite_demandee=1) is False
    assert le_pass.tarif_pass.out_of_stock(quantite_demandee=2) is True


# --------------------------------------------------------------------------
# La création des billets
# / Ticket creation
# --------------------------------------------------------------------------


def test_achat_d_un_pass_cree_un_billet_par_evenement_avec_le_meme_identifiant(lieu):
    """Un pass acheté : un billet le samedi, un le dimanche, même identifiant de pass.
    / One pass bought: one ticket per day, same pass id."""
    le_pass = creer_un_pass_deux_jours()
    acheteur = creer_utilisateur()

    acheter_le_pass(le_pass, acheteur, quantite=1)

    billet_du_samedi = Ticket.objects.get(reservation__event=le_pass.samedi, reservation__user_commande=acheteur)
    billet_du_dimanche = Ticket.objects.get(reservation__event=le_pass.dimanche, reservation__user_commande=acheteur)
    assert billet_du_samedi.pass_vendu is not None
    assert billet_du_samedi.pass_vendu == billet_du_dimanche.pass_vendu


def test_deux_passes_achetes_font_deux_identifiants_differents(lieu):
    """Deux passes achetés : 2 billets par jour, et 2 identifiants de pass différents.
    / Two passes bought: 2 tickets per day, 2 different pass ids."""
    le_pass = creer_un_pass_deux_jours()
    acheteur = creer_utilisateur()

    acheter_le_pass(le_pass, acheteur, quantite=2)

    identifiants_du_samedi = set()
    for billet in Ticket.objects.filter(reservation__event=le_pass.samedi, reservation__user_commande=acheteur):
        identifiants_du_samedi.add(billet.pass_vendu)
    identifiants_du_dimanche = set()
    for billet in Ticket.objects.filter(reservation__event=le_pass.dimanche, reservation__user_commande=acheteur):
        identifiants_du_dimanche.add(billet.pass_vendu)
    assert len(identifiants_du_samedi) == 2
    assert identifiants_du_samedi == identifiants_du_dimanche


def test_chaque_billet_du_pass_est_vendu_au_prix_de_sa_ligne(lieu):
    """
    Pass à 12 € + 13 €. Le billet du samedi vaut 12 €, celui du dimanche 13 €.
    Chaque événement a sa ligne de vente, à sa part, dans la même vente.
    / Each pass ticket is sold at its line price, one sale line per event, one sale.
    """
    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    acheteur = creer_utilisateur()

    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass(le_pass, acheteur)

    ligne_du_samedi = LigneArticle.objects.get(reservation=reservation_du_samedi)
    ligne_du_dimanche = LigneArticle.objects.get(reservation=reservation_du_dimanche)
    assert ligne_du_samedi.amount == 1200
    assert ligne_du_dimanche.amount == 1300
    assert ligne_du_samedi.vente_id == ligne_du_dimanche.vente_id

    billet_du_samedi = reservation_du_samedi.tickets.get()
    billet_du_dimanche = reservation_du_dimanche.tickets.get()
    assert billet_du_samedi.pricesold.prix == Decimal("12.00")
    assert billet_du_dimanche.pricesold.prix == Decimal("13.00")


def test_billet_normal_n_a_pas_d_identifiant_de_pass(lieu):
    """Un billet acheté sur un tarif normal ne porte aucun identifiant de pass.
    / A normal ticket has no pass id."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    acheteur = creer_utilisateur()
    reservation = Reservation.objects.create(user_commande=acheteur, event=concert.evenement)
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)

    TicketCreator(
        reservation=reservation,
        products_dict={concert.produit: {concert.tarif: 1}},
        create_checkout=False,
        vente=vente,
    )

    assert reservation.tickets.get().pass_vendu is None


def test_pass_vendu_sans_ses_identifiants_est_refuse(lieu):
    """
    Un pass passé à TicketCreator sans ses identifiants fabriquerait un seul billet sur
    deux. La vente est refusée.
    / A pass without its ids would make one ticket out of two: refused.
    """
    le_pass = creer_un_pass_deux_jours()
    acheteur = creer_utilisateur()
    reservation = Reservation.objects.create(user_commande=acheteur, event=le_pass.samedi)
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)

    with pytest.raises(serializers.ValidationError):
        TicketCreator(
            reservation=reservation,
            products_dict={le_pass.produit_pass: {le_pass.tarif_pass: 1}},
            create_checkout=False,
            vente=vente,
        )


def test_pass_refuse_sur_un_evenement_qu_il_ne_couvre_pas(lieu):
    """Un billet de pass ne peut pas être créé sur un événement hors du pass.
    / A pass ticket cannot be created on an event outside the pass."""
    le_pass = creer_un_pass_deux_jours()
    autre_evenement = creer_evenement_avec_tarif().evenement
    acheteur = creer_utilisateur()
    reservation = Reservation.objects.create(user_commande=acheteur, event=autre_evenement)
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)

    with pytest.raises(serializers.ValidationError):
        TicketCreator(
            reservation=reservation,
            products_dict={le_pass.produit_pass: {le_pass.tarif_pass: 1}},
            create_checkout=False,
            vente=vente,
            identifiants_des_passes={le_pass.tarif_pass.uuid: [uuid.uuid4()]},
        )


# --------------------------------------------------------------------------
# Le panier : ajout d'un pass
# / The cart: adding a pass
# --------------------------------------------------------------------------


def test_pass_ajoute_au_panier_compte_la_somme_des_prix(lieu):
    """Un pass 12 € + 13 € ajouté au panier : le total du panier vaut 2500 centimes.
    / A 12 € + 13 € pass in the cart: the cart total is 2500 cents."""
    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    assert panier.calcul_total_centimes() == 2500


def test_pass_refuse_au_panier_quand_un_autre_jour_est_complet(lieu):
    """
    Le dimanche est complet. On ajoute le pass depuis la page du samedi : refusé, car le
    pass ferait aussi un billet le dimanche.
    / Sunday is full: adding the pass from Saturday's page is refused.
    """
    le_pass = creer_un_pass_deux_jours()
    le_pass.dimanche.jauge_max = 0
    le_pass.dimanche.save()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)


def test_pass_au_panier_occupe_une_place_sur_chaque_jour(lieu):
    """
    Le dimanche n'a qu'une place. Le pass ajouté depuis le samedi la prend : un billet
    dimanche seul ajouté ensuite au panier est refusé.
    / Sunday has one seat; the pass in the cart takes it, a Sunday ticket is then refused.
    """
    le_pass = creer_un_pass_deux_jours()
    le_pass.dimanche.jauge_max = 1
    le_pass.dimanche.save()
    tarif_dimanche_seul = le_pass.dimanche.products.exclude(pk=le_pass.produit_pass.pk).get().prices.get()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(le_pass.dimanche.uuid, tarif_dimanche_seul.uuid, qty=1)


def test_stock_du_pass_est_commun_aux_pages_des_deux_jours(lieu):
    """
    Stock de 1 pass. Ajouté depuis la page du samedi, il n'en reste plus : l'ajout depuis
    la page du dimanche est refusé.
    / Stock of 1 pass shared by both event pages.
    """
    le_pass = creer_un_pass_deux_jours(stock_de_passes=1)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(le_pass.dimanche.uuid, le_pass.tarif_pass.uuid, qty=1)


def test_pass_refuse_au_panier_sur_un_evenement_hors_du_pass(lieu):
    """Le produit pass est rattaché à un 3e événement qui n'est pas dans le pass : refusé.
    / Pass product attached to an event outside the pass: refused."""
    le_pass = creer_un_pass_deux_jours()
    autre_evenement = creer_evenement_avec_tarif(jours_avant_l_evenement=12).evenement
    autre_evenement.products.add(le_pass.produit_pass)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(autre_evenement.uuid, le_pass.tarif_pass.uuid, qty=1)


# --------------------------------------------------------------------------
# Le panier : paiement
# / The cart: checkout
# --------------------------------------------------------------------------


def payer_le_panier(panier, acheteur):
    """
    Matérialise le panier comme sa vue. Le paiement Stripe est neutralisé : ces tests
    lisent ce qui est écrit avant lui, sans dépendre de la clé Stripe du lieu.
    / Materializes the cart; the Stripe payment is neutralised (not under test here).
    """
    with patch.object(CommandeService, "_creer_paiement_stripe"):
        commande, _succes = CommandeService.materialiser(
            panier,
            acheteur,
            first_name=acheteur.first_name,
            last_name=acheteur.last_name,
            email=acheteur.email,
        )
    commande.refresh_from_db()
    return commande


def test_paiement_du_panier_cree_une_reservation_par_jour_dans_la_commande(lieu):
    """
    Un pass au panier, payé : une réservation le samedi, une le dimanche, dans la même
    commande. Chacune a un billet au prix de sa ligne, avec le même identifiant de pass.
    / A paid pass: one reservation per day in one order, same pass id, line prices.
    """
    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    acheteur = creer_utilisateur()
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    commande = payer_le_panier(panier, acheteur)

    reservation_du_samedi = commande.reservations.get(event=le_pass.samedi)
    reservation_du_dimanche = commande.reservations.get(event=le_pass.dimanche)
    billet_du_samedi = reservation_du_samedi.tickets.get()
    billet_du_dimanche = reservation_du_dimanche.tickets.get()
    assert billet_du_samedi.pass_vendu is not None
    assert billet_du_samedi.pass_vendu == billet_du_dimanche.pass_vendu
    assert LigneArticle.objects.get(reservation=reservation_du_samedi).amount == 1200
    assert LigneArticle.objects.get(reservation=reservation_du_dimanche).amount == 1300


def test_pass_et_billet_seul_du_meme_jour_partagent_la_reservation_du_jour(lieu):
    """
    Un pass et un billet « samedi seul » au panier : le samedi a UNE réservation avec
    deux billets (un de pass, un normal). Le dimanche a la réservation du pass.
    / A pass plus a Saturday-only ticket: one Saturday reservation holding both tickets.
    """
    le_pass = creer_un_pass_deux_jours()
    tarif_samedi_seul = le_pass.samedi.products.exclude(pk=le_pass.produit_pass.pk).get().prices.get()
    acheteur = creer_utilisateur()
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)
    panier.add_ticket(le_pass.samedi.uuid, tarif_samedi_seul.uuid, qty=1)

    commande = payer_le_panier(panier, acheteur)

    reservation_du_samedi = commande.reservations.get(event=le_pass.samedi)
    assert reservation_du_samedi.tickets.count() == 2
    assert reservation_du_samedi.tickets.filter(pass_vendu__isnull=False).count() == 1
    assert commande.reservations.get(event=le_pass.dimanche).tickets.count() == 1


# --------------------------------------------------------------------------
# La réservation directe : le pass passe par le panier
# / Direct booking: the pass goes through the cart
# --------------------------------------------------------------------------


def test_reservation_directe_d_un_pass_est_refusee_sans_rien_creer(lieu):
    """
    « Payer maintenant » avec un pass : refusé, avec un message qui renvoie au panier.
    Aucune réservation n'est créée.
    / "Pay now" with a pass: refused, pointing to the cart. No reservation created.
    """
    le_pass = creer_un_pass_deux_jours()
    acheteur = creer_utilisateur()

    reponse = reserver_des_billets_sans_panier(
        client_connecte(acheteur), acheteur, le_pass.samedi, {le_pass.tarif_pass: 1}
    )

    assert "par le panier" in reponse.content.decode()
    assert not Reservation.objects.filter(user_commande=acheteur).exists()


def test_panier_affiche_les_evenements_du_pass_et_son_prix_total(lieu):
    """
    Le panier affiche un pass avec ses deux événements et son prix total (25 €).
    / The cart shows a pass with its two events and its total price.
    """
    from BaseBillet.context_processors import _build_items_with_details

    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(le_pass.samedi.uuid, le_pass.tarif_pass.uuid, qty=1)

    detail_du_pass = _build_items_with_details(panier)[0]

    assert detail_du_pass['evenements_du_pass'] == [le_pass.samedi, le_pass.dimanche]
    assert detail_du_pass['prix_du_pass'] == Decimal("25.00")


# --------------------------------------------------------------------------
# L'admin : création et réglage d'un pass
# / Admin: creating and setting up a pass
# --------------------------------------------------------------------------


def test_synchronisation_met_le_prix_du_tarif_a_la_somme_des_lignes(lieu):
    """Le tarif du pass prend la somme des prix par événement, sans prix libre.
    / The pass price takes the sum of the per-event prices, never a free price."""
    from Administration.admin.products import synchroniser_le_produit_pass

    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    Price.objects.filter(pk=le_pass.tarif_pass.pk).update(prix=Decimal("99.00"), free_price=True)

    synchroniser_le_produit_pass(le_pass.produit_pass)

    le_pass.tarif_pass.refresh_from_db()
    assert le_pass.tarif_pass.prix == Decimal("25.00")
    assert le_pass.tarif_pass.free_price is False


def test_synchronisation_rattache_le_pass_a_ses_evenements_seulement(lieu):
    """
    Le pass est rattaché au samedi et au dimanche, et retiré d'un 3e événement qui n'est
    pas dans le pass.
    / The pass is attached to its events, and removed from an event outside the pass.
    """
    from Administration.admin.products import synchroniser_le_produit_pass

    le_pass = creer_un_pass_deux_jours()
    le_pass.dimanche.products.remove(le_pass.produit_pass)
    evenement_hors_du_pass = creer_evenement_avec_tarif().evenement
    evenement_hors_du_pass.products.add(le_pass.produit_pass)

    resultat = synchroniser_le_produit_pass(le_pass.produit_pass)

    assert le_pass.dimanche.products.filter(pk=le_pass.produit_pass.pk).exists()
    assert not evenement_hors_du_pass.products.filter(pk=le_pass.produit_pass.pk).exists()
    assert resultat["evenements_ajoutes"] == [le_pass.dimanche]
    assert resultat["evenements_retires"] == [evenement_hors_du_pass]


def test_liste_des_evenements_du_pass_presente_sur_tout_produit_billet(lieu):
    """
    L'inline des événements du pass est toujours dans la fiche d'un produit billet : la
    case « Ceci est un pass » l'affiche ou le masque côté navigateur, sans enregistrer.
    / The pass events inline is always on a ticket product page (shown by the checkbox).
    """
    from Administration.admin.products import EvenementDuPassInline, TicketProductAdmin
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import TicketProduct

    admin_des_billets = TicketProductAdmin(TicketProduct, staff_admin_site)
    produit_normal = creer_evenement_avec_tarif().produit

    assert EvenementDuPassInline in admin_des_billets.get_inlines(None, produit_normal)
    assert EvenementDuPassInline in admin_des_billets.get_inlines(None, None)


def test_page_admin_d_un_produit_normal_contient_la_case_et_son_emplacement(lieu, admin_client):
    """
    La fiche d'un produit billet normal contient la liste des événements du pass et
    l'emplacement où le script déplace la case.
    / A normal ticket product page holds the pass events list and the checkbox slot.
    """
    produit_normal = creer_evenement_avec_tarif().produit

    reponse = admin_client.get(f"/admin/BaseBillet/ticketproduct/{produit_normal.pk}/change/")

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert "evenements_du_pass-TOTAL_FORMS" in contenu
    assert 'id="emplacement-case-pass"' in contenu
    assert 'id="id_est_un_pass"' in contenu


def test_un_seul_enregistrement_suffit_pour_creer_un_pass(lieu, admin_client):
    """
    Cocher « Ceci est un pass » et ajouter deux événements dans le même envoi suffit.
    / Checking the box and adding events in ONE submit creates the pass.
    """
    samedi = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    dimanche = creer_evenement_avec_tarif(jours_avant_l_evenement=11).evenement
    produit = Product.objects.create(
        name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES
    )
    tarif_gratuit = produit.prices.get()

    reponse = admin_client.post(
        f"/admin/BaseBillet/ticketproduct/{produit.pk}/change/",
        data={
            "name": produit.name,
            "categorie_article": Product.FREERES,
            "poids": "0",
            "publish": "on",
            "est_un_pass": "on",
            "prices-TOTAL_FORMS": "1",
            "prices-INITIAL_FORMS": "1",
            "prices-0-uuid": str(tarif_gratuit.uuid),
            "prices-0-product": str(produit.pk),
            "prices-0-name": tarif_gratuit.name,
            "prices-0-prix": "0",
            "prices-0-publish": "on",
            "prices-0-order": "100",
            "evenements_du_pass-TOTAL_FORMS": "2",
            "evenements_du_pass-INITIAL_FORMS": "0",
            "evenements_du_pass-0-evenement": str(samedi.uuid),
            "evenements_du_pass-0-prix": "0",
            "evenements_du_pass-1-evenement": str(dimanche.uuid),
            "evenements_du_pass-1-prix": "0",
            "form_fields-TOTAL_FORMS": "0",
            "form_fields-INITIAL_FORMS": "0",
            "_save": "Enregistrer",
        },
    )

    erreurs = None
    if reponse.status_code == 200:
        erreurs = (
            reponse.context["adminform"].form.errors,
            [formset.errors for formset in reponse.context["inline_admin_formsets"]],
        )
    assert reponse.status_code == 302, erreurs
    produit.refresh_from_db()
    assert produit.est_un_pass is True
    assert produit.evenements_du_pass.count() == 2
    assert samedi.products.filter(pk=produit.pk).exists()
    assert dimanche.products.filter(pk=produit.pk).exists()


def test_page_admin_d_un_pass_affiche_ses_evenements(lieu, admin_client):
    """La page admin d'un pass s'affiche et contient la liste de ses événements.
    / The admin page of a pass renders and lists its events."""
    le_pass = creer_un_pass_deux_jours()

    reponse = admin_client.get(f"/admin/BaseBillet/ticketproduct/{le_pass.produit_pass.pk}/change/")

    assert reponse.status_code == 200
    assert "evenements_du_pass-TOTAL_FORMS" in reponse.content.decode()


def donnees_du_formulaire_de_produit_gratuit(produit, est_un_pass=True, tarifs=None, lignes_du_pass=None):
    """
    Données POST minimales du formulaire admin d'un produit gratuit (pas de contrôle Stripe).
    `tarifs` : [{"name", "free_price"}] ; `lignes_du_pass` : [{"evenement", "prix", "supprimer"}].
    / Minimal POST data of a free product admin form.
    """
    from django.http import QueryDict

    donnees = QueryDict(mutable=True)
    donnees.update({
        "name": produit.name,
        "categorie_article": Product.FREERES,
        "poids": "0",
        "publish": "on",
        "prices-TOTAL_FORMS": str(len(tarifs or [])),
        "prices-INITIAL_FORMS": "0",
    })
    if est_un_pass:
        donnees["est_un_pass"] = "on"
    for numero_du_tarif, tarif in enumerate(tarifs or []):
        donnees[f"prices-{numero_du_tarif}-name"] = tarif["name"]
        if tarif.get("free_price"):
            donnees[f"prices-{numero_du_tarif}-free_price"] = "on"
    donnees["evenements_du_pass-TOTAL_FORMS"] = str(len(lignes_du_pass or []))
    for numero_de_la_ligne, ligne in enumerate(lignes_du_pass or []):
        donnees[f"evenements_du_pass-{numero_de_la_ligne}-evenement"] = ligne["evenement"]
        donnees[f"evenements_du_pass-{numero_de_la_ligne}-prix"] = ligne["prix"]
        if ligne.get("supprimer"):
            donnees[f"evenements_du_pass-{numero_de_la_ligne}-DELETE"] = "on"
    return donnees


def deux_lignes_de_pass():
    """Deux événements à venir, chacun avec un prix : le minimum d'un pass.
    / Two upcoming events with a price each: a pass minimum."""
    samedi = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    dimanche = creer_evenement_avec_tarif(jours_avant_l_evenement=11).evenement
    return [
        {"evenement": str(samedi.uuid), "prix": "0"},
        {"evenement": str(dimanche.uuid), "prix": "0"},
    ]


def test_formulaire_refuse_un_pass_a_deux_tarifs(lieu):
    """Un pass n'a qu'un seul tarif : deux tarifs dans le formulaire sont refusés.
    / A pass has one price only: two prices are refused."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass"}, {"name": "Pass réduit"}]
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert not formulaire.is_valid()


def test_formulaire_refuse_un_pass_a_prix_libre(lieu):
    """Un pass ne peut pas être à prix libre.
    / A pass cannot be a free price."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass", "free_price": True}]
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert not formulaire.is_valid()


def test_formulaire_refuse_de_transformer_un_produit_vendu_en_pass(lieu):
    """Un produit dont un billet a été vendu ne peut plus devenir un pass.
    / A product with a sold ticket cannot become a pass."""
    from Administration.admin.products import TicketProductForm

    concert = creer_evenement_avec_tarif(prix="10.00")
    acheteur = creer_utilisateur()
    reservation = Reservation.objects.create(user_commande=acheteur, event=concert.evenement)
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)
    TicketCreator(
        reservation=reservation,
        products_dict={concert.produit: {concert.tarif: 1}},
        create_checkout=False,
        vente=vente,
    )
    Product.objects.filter(pk=concert.produit.pk).update(categorie_article=Product.FREERES)
    concert.produit.refresh_from_db()
    donnees = donnees_du_formulaire_de_produit_gratuit(concert.produit, tarifs=[{"name": "Pass"}])

    formulaire = TicketProductForm(data=donnees, instance=concert.produit)

    assert not formulaire.is_valid()


def test_formulaire_accepte_un_pass_a_un_tarif(lieu):
    """Un pass gratuit avec un seul tarif fixe est accepté.
    / A free pass with one fixed price is accepted."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass"}], lignes_du_pass=deux_lignes_de_pass()
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert formulaire.is_valid(), formulaire.errors


def test_formulaire_refuse_un_pass_a_un_seul_evenement(lieu):
    """Un pass qui ne couvre qu'un événement est refusé : il en faut au moins 2.
    / A pass covering a single event is refused: at least 2 are needed."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    une_seule_ligne = deux_lignes_de_pass()[:1]
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass"}], lignes_du_pass=une_seule_ligne
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert not formulaire.is_valid()


def test_formulaire_refuse_un_pass_dont_une_ligne_n_a_pas_de_prix(lieu):
    """Deux événements, mais l'un sans prix : il ne compte pas, le pass est refusé.
    / Two events but one without a price: refused."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    lignes = deux_lignes_de_pass()
    lignes[1]["prix"] = ""
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass"}], lignes_du_pass=lignes
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert not formulaire.is_valid()


def test_formulaire_refuse_un_pass_dont_une_ligne_est_supprimee(lieu):
    """Deux événements, mais l'un coché « supprimer » : il en reste 1, le pass est refusé.
    / Two events but one marked for deletion: refused."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_pass {identifiant_unique()}", categorie_article=Product.FREERES)
    lignes = deux_lignes_de_pass()
    lignes[1]["supprimer"] = True
    donnees = donnees_du_formulaire_de_produit_gratuit(
        produit, tarifs=[{"name": "Pass"}], lignes_du_pass=lignes
    )

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert not formulaire.is_valid()


def test_formulaire_accepte_un_produit_normal_sans_evenement_de_pass(lieu):
    """La règle des 2 événements ne touche pas un produit billet normal.
    / The 2-event rule does not apply to a normal ticket product."""
    from Administration.admin.products import TicketProductForm

    produit = Product.objects.create(name=f"TEST_billet {identifiant_unique()}", categorie_article=Product.FREERES)
    donnees = donnees_du_formulaire_de_produit_gratuit(produit, est_un_pass=False, tarifs=[{"name": "Gratuit"}])

    formulaire = TicketProductForm(data=donnees, instance=produit)

    assert formulaire.is_valid(), formulaire.errors


def test_code_promo_ne_propose_pas_les_passes(lieu):
    """Le choix du produit d'un code promo ne propose pas les passes.
    / The promo code product choice does not offer passes."""
    from Administration.admin.prices import PromotionalCodeAdmin
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import PromotionalCode

    le_pass = creer_un_pass_deux_jours()
    concert = creer_evenement_avec_tarif()
    admin_des_codes_promo = PromotionalCodeAdmin(PromotionalCode, staff_admin_site)
    champ_produit = PromotionalCode._meta.get_field("product")

    champ_du_formulaire = admin_des_codes_promo.formfield_for_foreignkey(champ_produit, None)

    assert not champ_du_formulaire.queryset.filter(pk=le_pass.produit_pass.pk).exists()
    assert champ_du_formulaire.queryset.filter(pk=concert.produit.pk).exists()


# --------------------------------------------------------------------------
# L'annulation : un pass est indivisible
# / Cancellation: a pass is indivisible
# --------------------------------------------------------------------------


def acheter_le_pass_billets_valides(le_pass, acheteur):
    """
    Achète un pass, puis rend ses billets valides (prêts à être scannés), comme après un
    paiement. Rend (réservation du samedi, réservation du dimanche).
    / Buys a pass and makes its tickets valid, like after a payment.
    """
    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass(le_pass, acheteur)
    Ticket.objects.filter(reservation__in=[reservation_du_samedi, reservation_du_dimanche]).update(
        status=Ticket.NOT_SCANNED
    )
    return reservation_du_samedi, reservation_du_dimanche


def test_annuler_le_billet_du_dimanche_annule_tout_le_pass(lieu):
    """La personne annule son billet du dimanche : le billet du samedi est annulé aussi.
    / Cancelling the Sunday ticket cancels the Saturday ticket too."""
    le_pass = creer_un_pass_deux_jours()
    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    billet_du_dimanche = reservation_du_dimanche.tickets.get()

    reservation_du_dimanche.cancel_and_refund_ticket(billet_du_dimanche)

    assert reservation_du_samedi.tickets.get().status == Ticket.CANCELED
    assert reservation_du_dimanche.tickets.get().status == Ticket.CANCELED
    reservation_du_samedi.refresh_from_db()
    assert reservation_du_samedi.status == Reservation.CANCELED


def test_pass_dont_un_jour_est_scanne_ne_peut_plus_etre_annule(lieu):
    """
    Le billet du samedi a été scanné. Annuler le billet du dimanche est refusé, et rien
    n'est annulé.
    / Saturday was scanned: cancelling Sunday is refused, nothing is cancelled.
    """
    le_pass = creer_un_pass_deux_jours()
    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    reservation_du_samedi.tickets.update(status=Ticket.SCANNED)
    billet_du_dimanche = reservation_du_dimanche.tickets.get()

    with pytest.raises(Exception):
        reservation_du_dimanche.cancel_and_refund_ticket(billet_du_dimanche)

    assert reservation_du_dimanche.tickets.get().status == Ticket.NOT_SCANNED


def test_annuler_la_reservation_du_samedi_annule_le_billet_de_pass_du_dimanche(lieu):
    """
    La réservation du samedi contient un billet de pass et un billet « samedi seul ».
    L'annuler annule les deux, et le billet du pass sur le dimanche.
    / Cancelling Saturday's reservation also cancels the Sunday pass ticket.
    """
    le_pass = creer_un_pass_deux_jours()
    acheteur = creer_utilisateur()
    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(le_pass, acheteur)
    produit_samedi_seul = le_pass.samedi.products.exclude(pk=le_pass.produit_pass.pk).get()
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)
    TicketCreator(
        reservation=reservation_du_samedi,
        products_dict={produit_samedi_seul: {produit_samedi_seul.prices.get(): 1}},
        create_checkout=False,
        vente=vente,
    )
    reservation_du_samedi.tickets.update(status=Ticket.NOT_SCANNED)

    reservation_du_samedi.cancel_and_refund_resa()

    assert not reservation_du_samedi.tickets.exclude(status=Ticket.CANCELED).exists()
    assert reservation_du_dimanche.tickets.get().status == Ticket.CANCELED


def test_annuler_un_billet_normal_n_annule_que_lui(lieu):
    """Un billet hors pass s'annule seul : l'autre billet de la réservation reste valide.
    / A non-pass ticket is cancelled alone."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    acheteur = creer_utilisateur()
    reservation = Reservation.objects.create(user_commande=acheteur, event=concert.evenement)
    vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur)
    TicketCreator(
        reservation=reservation,
        products_dict={concert.produit: {concert.tarif: 2}},
        create_checkout=False,
        vente=vente,
    )
    reservation.tickets.update(status=Ticket.NOT_SCANNED)
    premier_billet, second_billet = list(reservation.tickets.order_by("uuid"))

    reservation.cancel_and_refund_ticket(premier_billet)

    second_billet.refresh_from_db()
    assert second_billet.status == Ticket.NOT_SCANNED


def test_annulation_admin_d_un_pass_paye_en_especes_rembourse_chaque_jour(lieu):
    """
    Pass 12 € + 13 € payé en espèces, annulé par l'admin : chaque jour reçoit son avoir.
    / Cash-paid pass cancelled by the admin: each day gets its credit note.
    """
    from BaseBillet.models import PaymentMethod
    from BaseBillet.services_vente import ajouter_reglement, encaisser_vente

    le_pass = creer_un_pass_deux_jours(prix_samedi="12.00", prix_dimanche="13.00")
    acheteur = creer_utilisateur()
    pass_deplie = deplier_le_pass(le_pass.produit_pass, 1)
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE, client=acheteur)
    reservations = []
    for ligne_du_pass in pass_deplie["lignes_du_pass"]:
        reservation = Reservation.objects.create(user_commande=acheteur, event=ligne_du_pass.evenement)
        TicketCreator(
            reservation=reservation,
            products_dict={le_pass.produit_pass: {le_pass.tarif_pass: 1}},
            sale_origin=SaleOrigin.LABOUTIK,
            paid_externally=True,
            external_payment_method=PaymentMethod.CASH,
            vente=vente,
            identifiants_des_passes={le_pass.tarif_pass.uuid: pass_deplie["identifiants_des_passes"]},
        )
        reservations.append(reservation)
    ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=2500)
    encaisser_vente(vente)
    reservation_du_samedi, reservation_du_dimanche = reservations
    # total_paid() rend des euros (Decimal). / total_paid() returns euros.
    assert reservation_du_samedi.total_paid() == Decimal("12.00")
    assert reservation_du_dimanche.total_paid() == Decimal("13.00")

    reservation_du_samedi.cancel_and_refund_ticket(
        reservation_du_samedi.tickets.get(),
        annulation_par_l_admin=True,
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reservation_du_samedi.total_paid() == 0
    assert reservation_du_dimanche.total_paid() == 0
    assert reservation_du_dimanche.tickets.get().status == Ticket.CANCELED


def test_reservation_sait_si_elle_contient_un_pass(lieu):
    """
    Méthode lue par « Mes réservations » (la page appelle Fedow, injoignable en test).
    / Method read by the account page (the page itself calls Fedow).
    """
    le_pass = creer_un_pass_deux_jours()
    reservation_du_samedi, _reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    concert = creer_evenement_avec_tarif(prix="10.00")
    acheteur_du_concert = creer_utilisateur()
    reservation_du_concert = Reservation.objects.create(user_commande=acheteur_du_concert, event=concert.evenement)
    TicketCreator(
        reservation=reservation_du_concert,
        products_dict={concert.produit: {concert.tarif: 1}},
        create_checkout=False,
        vente=ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur_du_concert),
    )

    assert reservation_du_samedi.contient_des_billets_de_pass() is True
    assert reservation_du_concert.contient_des_billets_de_pass() is False


def test_choix_d_un_evenement_du_pass_propose_les_memes_evenements_que_la_liste(lieu, admin_client):
    """
    L'autocomplétion du champ « Événement » d'un pass propose les événements de la liste
    admin par défaut : l'événement à venir, ni l'archivé, ni le passé.
    / The pass event autocomplete offers the default admin list events only.
    """
    import json

    mot_commun = f"Choixpass{identifiant_unique()}"
    evenement_a_venir = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    evenement_archive = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    evenement_passe = creer_evenement_avec_tarif(jours_avant_l_evenement=-10).evenement
    for evenement, suffixe in [(evenement_a_venir, "a venir"), (evenement_archive, "archive"), (evenement_passe, "passe")]:
        evenement.name = f"{mot_commun} {suffixe}"
        evenement.save()
    from BaseBillet.models import Event
    Event.objects.filter(pk=evenement_archive.pk).update(archived=True)

    reponse = admin_client.get(
        "/admin/autocomplete/",
        {
            "app_label": "BaseBillet",
            "model_name": "evenementdupass",
            "field_name": "evenement",
            "term": mot_commun,
        },
    )

    assert reponse.status_code == 200
    identifiants_proposes = set()
    for resultat in json.loads(reponse.content)["results"]:
        identifiants_proposes.add(resultat["id"])
    assert identifiants_proposes == {str(evenement_a_venir.pk)}


def test_choix_d_un_evenement_du_pass_retire_les_evenements_deja_choisis(lieu, admin_client):
    """
    Le navigateur envoie les événements déjà choisis dans les autres lignes du pass
    (`deja_choisis`) : ils ne sont plus proposés. Un identifiant illisible est ignoré.
    / Events already chosen in other pass lines are no longer offered.
    """
    import json

    mot_commun = f"Dejachoisi{identifiant_unique()}"
    samedi = creer_evenement_avec_tarif(jours_avant_l_evenement=10).evenement
    dimanche = creer_evenement_avec_tarif(jours_avant_l_evenement=11).evenement
    lundi = creer_evenement_avec_tarif(jours_avant_l_evenement=12).evenement
    for evenement, suffixe in [(samedi, "samedi"), (dimanche, "dimanche"), (lundi, "lundi")]:
        evenement.name = f"{mot_commun} {suffixe}"
        evenement.save()

    reponse = admin_client.get(
        "/admin/autocomplete/",
        {
            "app_label": "BaseBillet",
            "model_name": "evenementdupass",
            "field_name": "evenement",
            "term": mot_commun,
            "deja_choisis": f"{samedi.pk},pas-un-uuid,{dimanche.pk}",
        },
    )

    assert reponse.status_code == 200
    identifiants_proposes = set()
    for resultat in json.loads(reponse.content)["results"]:
        identifiants_proposes.add(resultat["id"])
    assert identifiants_proposes == {str(lundi.pk)}

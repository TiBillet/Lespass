"""
Tests de la matérialisation d'un panier en Commande, et du paiement de cette Commande.
/ Tests of cart materialization into an Order, and of that Order's payment.

LOCALISATION : tests/pytest/test_commande_service.py

Code testé / Tested code :
- BaseBillet/services_commande.py — CommandeService.materialiser() et ses phases ;
- BaseBillet/signals.py — machine à états, signal commande_mark_paid_when_paiement_valid ;
- BaseBillet/triggers.py — actions après paiement (adhésion, billet, ressource) ;
- BaseBillet/views.py — EventMVT.stripe_return (retour de paiement du panier).

FLUX TESTÉ :
1. PanierSession.add_*() remplit le panier en session ;
2. CommandeService.materialiser() crée la Commande, les adhésions, les réservations, les
   bookings et leurs lignes de vente, puis un seul paiement Stripe (ou finalise en gratuit) ;
3. le retour de paiement (`/event/<paiement>/stripe_return/`) relit la session Stripe
   (simulée par `mock_stripe`) et déclenche la chaîne : lignes payées, triggers, Commande payée.

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
Stripe (session et catalogue) et Celery sont simulés : aucun appel réseau, aucune tâche
envoyée au worker. Les tâches demandées sont enregistrées et vérifiées.
/ Rolled-back transaction per test. Stripe and Celery are faked; requested tasks are recorded.

Lancer / Run : make test ARGS="tests/pytest/test_commande_service.py"
"""

import time
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    noms_des_taches,
    requete_avec_session,
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


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session + catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe (session + catalogue) and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


def materialiser(panier, acheteur):
    """Appelle CommandeService.materialiser() comme le fait la vue PanierMVT.checkout.
    / Calls materialiser() the way the PanierMVT.checkout view does."""
    from BaseBillet.services_commande import CommandeService

    return CommandeService.materialiser(
        panier,
        acheteur,
        first_name=acheteur.first_name,
        last_name=acheteur.last_name,
        email=acheteur.email,
    )


def revenir_de_stripe(acheteur, paiement):
    """
    Joue le retour navigateur depuis Stripe, par la vraie vue du panier.
    / Plays the browser return from Stripe, through the real cart return view.

    La session Stripe relue est celle de `mock_stripe` : `payment_status="paid"` par défaut.
    / The Stripe session read back is `mock_stripe`'s: paid by default.
    """
    client = client_connecte(acheteur)
    reponse = client.get(f"/event/{paiement.uuid}/stripe_return/")
    return reponse


# --------------------------------------------------------------------------
# Matérialisation : les phases
# / Materialization: the phases
# --------------------------------------------------------------------------


def test_materialiser_un_panier_vide_leve_une_erreur(lieu):
    """Un panier vide ne crée aucune Commande.
    / An empty cart creates no Order."""
    from BaseBillet.models import Commande
    from BaseBillet.services_commande import CommandeServiceError
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    panier = PanierSession(requete_avec_session(acheteur))

    with pytest.raises(CommandeServiceError):
        materialiser(panier, acheteur)

    assert not Commande.objects.filter(user=acheteur).exists()


def test_materialiser_une_adhesion_payante_la_cree_en_attente_de_paiement(lieu):
    """
    Phase 1 : l'adhésion est créée en attente de paiement, rattachée à la Commande, avec le
    prénom et le nom saisis dans le formulaire (prioritaires sur ceux du compte).
    / Phase 1: the membership is created waiting for payment, with the form's names.
    """
    from BaseBillet.models import Commande, LigneArticle, Membership
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur(prenom="", nom="")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid, firstname="Ada", lastname="Lovelace")

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    assert commande.status == Commande.PENDING
    adhesion_creee = commande.memberships_commande.get()
    assert adhesion_creee.status == Membership.WAITING_PAYMENT
    assert adhesion_creee.first_name == "Ada"
    assert adhesion_creee.last_name == "Lovelace"
    assert adhesion_creee.contribution_value == Decimal("15.00")
    ligne_de_l_adhesion = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne_de_l_adhesion.amount == 1500
    assert commande.first_name == "Ada"


def test_materialiser_cree_une_reservation_par_evenement(lieu):
    """
    Phase 2 : deux tarifs du même événement vont dans UNE réservation ; un autre événement
    a sa propre réservation.
    / Phase 2: two prices of the same event share ONE reservation; another event has its own.
    """
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    tarif_reduit_du_concert = ajouter_un_tarif(concert.produit, prix="5.00")
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(concert.evenement.uuid, tarif_reduit_du_concert.uuid, qty=1)
    panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    assert commande.reservations.count() == 2
    reservation_du_concert = commande.reservations.get(event=concert.evenement)
    assert reservation_du_concert.tickets.count() == 3
    reservation_du_spectacle = commande.reservations.get(event=spectacle.evenement)
    assert reservation_du_spectacle.tickets.count() == 1


def test_materialiser_propage_options_et_formulaire_sur_la_reservation(lieu):
    """Les options et le formulaire personnalisé de l'item vont sur la réservation.
    / The item's options and custom form are copied onto the reservation."""
    from BaseBillet.models import OptionGenerale
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    option_vegetarienne = OptionGenerale.objects.create(name="TEST_panier végétarien")
    concert.evenement.options_radio.add(option_vegetarienne)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid,
        concert.tarif.uuid,
        qty=1,
        options=[str(option_vegetarienne.uuid)],
        custom_form={"allergies": "arachides"},
    )

    commande, _succes = materialiser(panier, acheteur)

    reservation = commande.reservations.get()
    assert reservation.custom_form == {"allergies": "arachides"}
    assert option_vegetarienne in reservation.options.all()


def test_materialiser_une_ressource_cree_un_booking_rattache_a_la_commande(lieu):
    """Phase 3 : le créneau devient un booking en attente de paiement, avec sa ligne de vente.
    / Phase 3: the slot becomes a booking waiting for payment, with its sale line."""
    from BaseBillet.models import LigneArticle
    from BaseBillet.services_panier import PanierSession
    from booking.models import Booking

    acheteur = creer_utilisateur()
    location = creer_ressource_avec_tarif(prix="12.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=2,
    )

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    booking = commande.bookings.get()
    assert booking.resource == location.ressource
    assert booking.status == Booking.WAITING_PAYMENT
    assert booking.slot_count == 2
    ligne_du_booking = LigneArticle.objects.get(booking=booking)
    assert ligne_du_booking.amount == 2400


def test_materialiser_un_panier_payant_cree_un_seul_paiement_porte_par_la_commande(
    lieu,
):
    """
    Adhésion + billets de deux événements + ressource : UN seul paiement Stripe, porté par la
    Commande (ni réservation ni booking sur le paiement), lignes non payées, Commande en attente.
    / One single Stripe payment carried by the Order, unpaid lines, pending Order.
    """
    from BaseBillet.models import Commande, LigneArticle
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    location = creer_ressource_avec_tarif(prix="12.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    assert commande.status == Commande.PENDING
    paiement = commande.paiement_stripe
    assert paiement is not None
    assert paiement.reservation is None
    assert paiement.booking is None
    assert lieu.stripe.mock_create.call_count == 1
    lignes_du_paiement = LigneArticle.objects.filter(paiement_stripe=paiement)
    assert lignes_du_paiement.count() == 4
    for ligne in lignes_du_paiement:
        assert ligne.status == LigneArticle.UNPAID
    montant_total = 0
    for ligne in lignes_du_paiement:
        montant_total += int(ligne.amount * ligne.qty)
    assert montant_total == 1500 + 2000 + 800 + 1200


def test_materialiser_une_adhesion_seule_propose_le_prelevement_sepa(lieu):
    """Adhésion seule : Stripe propose la carte ET le SEPA (si le lieu l'accepte).
    / Membership only: Stripe offers card AND SEPA (when the venue accepts it)."""
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)

    with configuration_modifiee(stripe_accept_sepa=True):
        materialiser(panier, acheteur)

    moyens_proposes = lieu.stripe.mock_create.call_args.kwargs["payment_method_types"]
    assert "sepa_debit" in moyens_proposes


def test_materialiser_un_panier_avec_billet_refuse_le_prelevement_sepa(lieu):
    """Un billet dans le panier : pas de SEPA (le débit peut prendre des jours).
    / A ticket in the cart: no SEPA (the debit can take days)."""
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    with configuration_modifiee(stripe_accept_sepa=True):
        materialiser(panier, acheteur)

    moyens_proposes = lieu.stripe.mock_create.call_args.kwargs["payment_method_types"]
    assert moyens_proposes == ["card"]


def test_materialiser_un_panier_avec_reservation_gratuite_refuse_le_prelevement_sepa(
    lieu,
):
    """
    Adhésion payante + « réservation gratuite » (sans ligne de vente) : pas de SEPA non plus.
    Les billets gratuits attendent le paiement de la Commande, et un prélèvement peut prendre
    des jours.
    / Paid membership + free booking (no sale line): no SEPA either, the free tickets wait for
    the Order's payment.
    """
    from BaseBillet.models import Product
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    entree_libre = creer_evenement_avec_tarif(categorie=Product.FREERES)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(entree_libre.evenement.uuid, entree_libre.tarif.uuid, qty=1)

    with configuration_modifiee(stripe_accept_sepa=True):
        materialiser(panier, acheteur)

    moyens_proposes = lieu.stripe.mock_create.call_args.kwargs["payment_method_types"]
    assert moyens_proposes == ["card"]


def test_materialiser_un_panier_gratuit_valide_tout_sans_stripe(lieu):
    """
    Deux réservations gratuites (`FREERES`) : Commande payée tout de suite, réservations
    gratuites confirmées, aucun paiement ni appel Stripe.
    / Two free reservations: Order paid at once, reservations confirmed, no Stripe at all.
    """
    from BaseBillet.models import Commande, Product, Reservation
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    atelier = creer_evenement_avec_tarif(
        categorie=Product.FREERES, jours_avant_l_evenement=7
    )
    visite = creer_evenement_avec_tarif(
        categorie=Product.FREERES, jours_avant_l_evenement=9
    )
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(atelier.evenement.uuid, atelier.tarif.uuid, qty=2)
    panier.add_ticket(visite.evenement.uuid, visite.tarif.uuid, qty=1)

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None
    assert commande.paiement_stripe is None
    for reservation in commande.reservations.all():
        assert reservation.status == Reservation.FREERES_USERACTIV
    assert not lieu.stripe.mock_create.called
    assert not lieu.catalogue_stripe.price_create.called


def test_materialiser_annule_tout_si_une_erreur_survient(lieu):
    """Une exception en cours de matérialisation n'écrit rien : pas de Commande à moitié faite.
    / An exception during materialization writes nothing: no half-made Order."""
    from unittest.mock import patch
    from BaseBillet.models import Commande, Product
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(atelier.evenement.uuid, atelier.tarif.uuid, qty=1)

    with patch(
        "BaseBillet.services_commande.CommandeService._finaliser_gratuit",
        side_effect=RuntimeError("panne simulée"),
    ):
        with pytest.raises(RuntimeError):
            materialiser(panier, acheteur)

    assert not Commande.objects.filter(user=acheteur).exists()


# --------------------------------------------------------------------------
# Paiement d'une Commande : retour de Stripe
# / Paying an Order: return from Stripe
# --------------------------------------------------------------------------


def preparer_une_commande_mixte(lieu):
    """
    Panier « adhésion + 2 billets d'un concert + 1 billet d'un spectacle + 1 h de ressource »,
    matérialisé. Rend l'acheteur et la Commande.
    / Materialized mixed cart. Returns the buyer and the Order.
    """
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    location = creer_ressource_avec_tarif(prix="12.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )
    commande, _succes = materialiser(panier, acheteur)
    return acheteur, commande


def test_le_retour_de_paiement_valide_toute_la_commande_mixte(lieu):
    """
    Après le retour de Stripe (payé) : paiement validé, toutes les lignes validées, billets
    actifs, réservations payées, adhésion active avec échéance, booking payé, Commande payée.
    / After the (paid) Stripe return, the whole mixed Order is paid and activated.

    Les réservations restent « payées » (`P`) : elles ne passent « validées » (`V`) que
    lorsque la tâche d'envoi des billets par mail tourne, et elle est seulement demandée ici.
    / Reservations stay `P`: they only become `V` when the (recorded, not run) mail task runs.
    """
    from BaseBillet.models import Commande, LigneArticle, Membership, Paiement_stripe
    from BaseBillet.models import Reservation, Ticket
    from booking.models import Booking

    acheteur, commande = preparer_une_commande_mixte(lieu)
    paiement = commande.paiement_stripe

    revenir_de_stripe(acheteur, paiement)

    paiement.refresh_from_db()
    commande.refresh_from_db()
    assert paiement.status == Paiement_stripe.VALID
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None
    for ligne in LigneArticle.objects.filter(paiement_stripe=paiement):
        assert ligne.status == LigneArticle.VALID
    for reservation in commande.reservations.all():
        assert reservation.status == Reservation.PAID
        for billet in reservation.tickets.all():
            assert billet.status == Ticket.NOT_SCANNED
    adhesion_payee = commande.memberships_commande.get()
    assert adhesion_payee.status == Membership.ONCE
    assert adhesion_payee.deadline is not None
    assert commande.bookings.get().status == Booking.PAID_BY_USER

    taches = noms_des_taches(lieu.taches_demandees)
    assert "send_membership_invoice_to_email" in taches
    assert taches.count("ticket_celery_mailer") == 2


def test_revenir_deux_fois_de_stripe_ne_duplique_rien(lieu):
    """
    Retour puis rechargement de la page de retour : rien n'est créé ni envoyé deux fois, et
    la date de paiement de la Commande ne bouge pas (tests/PIEGES.md, 11.7).
    / Return then reload: nothing is created or sent twice, the Order's paid date is unchanged.
    """
    from BaseBillet.models import LigneArticle, Ticket

    acheteur, commande = preparer_une_commande_mixte(lieu)
    paiement = commande.paiement_stripe
    revenir_de_stripe(acheteur, paiement)
    commande.refresh_from_db()
    date_de_paiement_apres_le_premier_retour = commande.paid_at
    nombre_de_taches_apres_le_premier_retour = len(lieu.taches_demandees)

    revenir_de_stripe(acheteur, paiement)

    commande.refresh_from_db()
    assert commande.paid_at == date_de_paiement_apres_le_premier_retour
    assert len(lieu.taches_demandees) == nombre_de_taches_apres_le_premier_retour
    assert LigneArticle.objects.filter(paiement_stripe=paiement).count() == 4
    assert Ticket.objects.filter(reservation__commande=commande).count() == 3


@pytest.mark.parametrize("session_expiree", [False, True])
def test_revenir_de_stripe_sans_payer_laisse_la_commande_en_attente(
    lieu, session_expiree
):
    """
    Comportement actuel, figé (décision du mainteneur, SPEC §2.2 point 4) : au retour sans
    paiement, la Commande reste en attente et l'adhésion en attente de paiement. Le paiement
    passe « en attente », ou « expiré » si la session Stripe a expiré.
    La décision produit attend le panier en base (TECH_DOC/SESSIONS/TODO/).
    / Current behaviour, frozen: the Order stays pending after an unpaid return.
    """
    from BaseBillet.models import Commande, Membership, Paiement_stripe

    acheteur, commande = preparer_une_commande_mixte(lieu)
    paiement = commande.paiement_stripe
    lieu.stripe.session.payment_status = "unpaid"
    lieu.stripe.session.status = "open"
    if session_expiree:
        lieu.stripe.session.expires_at = time.time() - 60
    else:
        lieu.stripe.session.expires_at = time.time() + 3600

    revenir_de_stripe(acheteur, paiement)

    paiement.refresh_from_db()
    commande.refresh_from_db()
    if session_expiree:
        assert paiement.status == Paiement_stripe.EXPIRE
    else:
        assert paiement.status == Paiement_stripe.PENDING
    assert commande.status == Commande.PENDING
    assert commande.memberships_commande.get().status == Membership.WAITING_PAYMENT


# --------------------------------------------------------------------------
# Signal : un paiement validé passe la Commande en payée
# / Signal: a validated payment marks the Order as paid
# --------------------------------------------------------------------------


def creer_commande_et_paiement(statut_du_paiement, statut_de_la_commande, paid_at=None):
    """Commande liée à un paiement Stripe, aux statuts demandés.
    / Order linked to a Stripe payment, with the requested statuses."""
    from BaseBillet.models import Commande, Paiement_stripe

    acheteur = creer_utilisateur()
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=statut_du_paiement,
    )
    commande = Commande.objects.create(
        user=acheteur,
        email_acheteur=acheteur.email,
        first_name="Ada",
        last_name="Lovelace",
        status=statut_de_la_commande,
        paiement_stripe=paiement,
        paid_at=paid_at,
    )
    return commande, paiement


def test_un_paiement_valide_passe_la_commande_en_payee(lieu):
    """Paiement « validé » → Commande « payée », avec sa date.
    / Payment VALID → Order PAID, with its date."""
    from BaseBillet.models import Commande, Paiement_stripe

    commande, paiement = creer_commande_et_paiement(
        Paiement_stripe.PAID, Commande.PENDING
    )

    paiement.status = Paiement_stripe.VALID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None


def test_un_paiement_valide_sans_commande_ne_plante_pas(lieu):
    """Parcours direct : un paiement sans Commande passe « validé » sans erreur.
    / Direct flow: a payment without an Order becomes VALID without error."""
    from BaseBillet.models import Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=creer_utilisateur(),
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PAID,
    )

    paiement.status = Paiement_stripe.VALID
    paiement.save()

    paiement.refresh_from_db()
    assert paiement.status == Paiement_stripe.VALID


def test_un_paiement_seulement_paye_ne_passe_pas_la_commande_en_payee(lieu):
    """Tant que le paiement n'est pas « validé », la Commande reste en attente.
    / Until the payment is VALID, the Order stays pending."""
    from BaseBillet.models import Commande, Paiement_stripe

    commande, paiement = creer_commande_et_paiement(
        Paiement_stripe.PENDING, Commande.PENDING
    )

    paiement.status = Paiement_stripe.PAID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PENDING
    assert commande.paid_at is None


def test_resauver_un_paiement_valide_ne_change_pas_la_date_de_paiement(lieu):
    """Une Commande déjà payée garde sa date de paiement.
    / An already paid Order keeps its paid date."""
    from BaseBillet.models import Commande, Paiement_stripe

    date_de_paiement_initiale = timezone.now() - timedelta(hours=1)
    commande, paiement = creer_commande_et_paiement(
        Paiement_stripe.VALID, Commande.PAID, paid_at=date_de_paiement_initiale
    )

    paiement.save()

    commande.refresh_from_db()
    assert commande.paid_at == date_de_paiement_initiale


# --------------------------------------------------------------------------
# Modèle Commande : les choix qui protègent l'historique
# / Commande model: the choices that protect history
# --------------------------------------------------------------------------


def test_un_utilisateur_avec_une_commande_ne_peut_pas_etre_supprime(lieu):
    """L'acheteur est protégé : l'historique des commandes ne disparaît pas.
    / The buyer is protected: order history never disappears."""
    from django.db.models.deletion import ProtectedError
    from BaseBillet.models import Commande

    acheteur = creer_utilisateur()
    Commande.objects.create(
        user=acheteur, email_acheteur=acheteur.email, first_name="A", last_name="B"
    )

    with pytest.raises(ProtectedError):
        acheteur.delete()


def test_un_paiement_stripe_ne_porte_qu_une_seule_commande(lieu):
    """Un paiement = une Commande : une deuxième Commande sur le même paiement est refusée.
    / One payment = one Order: a second Order on the same payment is refused."""
    from BaseBillet.models import Commande, Paiement_stripe

    commande, paiement = creer_commande_et_paiement(
        Paiement_stripe.PENDING, Commande.PENDING
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Commande.objects.create(
                user=commande.user,
                email_acheteur=commande.email_acheteur,
                first_name="A",
                last_name="B",
                paiement_stripe=paiement,
            )


def test_supprimer_un_code_promo_garde_la_commande(lieu):
    """Le code promo supprimé est retiré de la Commande, qui reste.
    / A deleted promo code is cleared from the Order, which remains."""
    from BaseBillet.models import Commande, PromotionalCode

    concert = creer_evenement_avec_tarif(prix="10.00")
    code_promo = PromotionalCode.objects.create(
        name="TEST_panier_promo_supprime",
        discount_rate=Decimal("10.00"),
        product=concert.produit,
    )
    acheteur = creer_utilisateur()
    commande = Commande.objects.create(
        user=acheteur,
        email_acheteur=acheteur.email,
        first_name="A",
        last_name="B",
        promo_code=code_promo,
    )

    code_promo.delete()

    commande.refresh_from_db()
    assert commande.promo_code is None


# --------------------------------------------------------------------------
# Montants et actions après paiement : ce que le panier doit garantir
# / Amounts and post-payment actions: what the cart must guarantee
# --------------------------------------------------------------------------


def test_un_code_promo_ne_remise_que_le_produit_auquel_il_est_lie(lieu):
    """
    Événement à deux produits billet, code promo -50 % lié au produit A : le billet A est
    remisé, le billet B reste plein tarif.
    / Two ticket products, a -50 % code linked to product A: only A is discounted.
    """
    from BaseBillet.models import LigneArticle, Product, PromotionalCode
    from BaseBillet.services_panier import PanierSession
    from fabriques_panier import identifiant_unique

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_b = Product.objects.create(
        name=f"TEST_panier billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_b)
    tarif_b = ajouter_un_tarif(produit_b, prix="10.00", nom="Plein tarif B")
    code_promo = PromotionalCode.objects.create(
        name=f"TEST_panier_moitie_{identifiant_unique()}",
        discount_rate=Decimal("50.00"),
        product=concert.produit,
    )
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid,
        concert.tarif.uuid,
        qty=1,
        promotional_code_name=code_promo.name,
    )
    panier.add_ticket(concert.evenement.uuid, tarif_b.uuid, qty=1)

    commande, _succes = materialiser(panier, acheteur)

    reservation = commande.reservations.get()
    ligne_du_billet_a = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=concert.tarif
    )
    ligne_du_billet_b = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=tarif_b
    )
    assert ligne_du_billet_a.amount == 500
    assert ligne_du_billet_b.amount == 1000
    assert ligne_du_billet_b.promotional_code is None


def test_deux_codes_promo_sur_deux_produits_du_meme_evenement_remisent_chacun_le_sien(
    lieu,
):
    """
    Deux ajouts successifs sur le même événement : billet A avec le code -50 % du produit A,
    billet B avec le code -20 % du produit B. Chaque billet est facturé avec SA remise, comme
    le panier l'a affiché.
    / Two adds on the same event, each with its own product's code: each ticket is billed
    with its own discount, as the cart displayed.
    """
    from BaseBillet.models import LigneArticle, Product, PromotionalCode
    from BaseBillet.services_panier import PanierSession
    from fabriques_panier import identifiant_unique

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_b = Product.objects.create(
        name=f"TEST_panier billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_b)
    tarif_b = ajouter_un_tarif(produit_b, prix="10.00", nom="Plein tarif B")
    code_du_produit_a = PromotionalCode.objects.create(
        name=f"TEST_panier_moitie_{identifiant_unique()}",
        discount_rate=Decimal("50.00"),
        product=concert.produit,
    )
    code_du_produit_b = PromotionalCode.objects.create(
        name=f"TEST_panier_vingt_{identifiant_unique()}",
        discount_rate=Decimal("20.00"),
        product=produit_b,
    )
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid,
        concert.tarif.uuid,
        qty=1,
        promotional_code_name=code_du_produit_a.name,
    )
    panier.add_ticket(
        concert.evenement.uuid,
        tarif_b.uuid,
        qty=1,
        promotional_code_name=code_du_produit_b.name,
    )

    commande, _succes = materialiser(panier, acheteur)

    reservation = commande.reservations.get()
    ligne_du_billet_a = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=concert.tarif
    )
    ligne_du_billet_b = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=tarif_b
    )
    assert ligne_du_billet_a.amount == 500
    assert ligne_du_billet_b.amount == 800
    assert ligne_du_billet_b.promotional_code == code_du_produit_b


def test_un_prix_libre_redevenu_prix_fixe_avant_le_paiement_facture_le_prix_fixe(lieu):
    """
    Billet à prix libre ajouté avec 6 € saisis, puis le lieu passe ce tarif en prix fixe à
    20 € avant le paiement : le montant saisi ne vaut plus, le billet est facturé 20 €.
    / Free-price ticket added at 6 €, then the price becomes fixed at 20 € before checkout:
    the ticket is billed 20 €.
    """
    from BaseBillet.models import LigneArticle
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid, concert.tarif.uuid, qty=1, custom_amount="6.00"
    )
    concert.tarif.free_price = False
    concert.tarif.prix = Decimal("20.00")
    concert.tarif.save(update_fields=["free_price", "prix"])

    commande, _succes = materialiser(panier, acheteur)

    ligne = LigneArticle.objects.get(reservation__commande=commande)
    assert ligne.amount == 2000


def test_un_prix_libre_ajoute_deux_fois_facture_chacun_de_ses_montants(lieu):
    """
    Même tarif à prix libre ajouté deux fois (10 € puis 20 €) : 30 € facturés, comme le total
    affiché par le panier — pas deux fois le dernier montant.
    / Same free price added twice (10 € then 20 €): 30 € charged, as the cart displays.
    """
    from BaseBillet.models import LigneArticle
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid, concert.tarif.uuid, qty=1, custom_amount="10.00"
    )
    panier.add_ticket(
        concert.evenement.uuid, concert.tarif.uuid, qty=1, custom_amount="20.00"
    )
    total_affiche_par_le_panier = panier.calcul_total_centimes()

    commande, _succes = materialiser(panier, acheteur)

    montant_facture = 0
    for ligne in LigneArticle.objects.filter(paiement_stripe=commande.paiement_stripe):
        montant_facture += int(ligne.amount * ligne.qty)
    assert total_affiche_par_le_panier == 3000
    assert montant_facture == 3000
    assert commande.reservations.get().tickets.count() == 2


def test_la_recompense_et_l_envoi_a_laboutik_partent_apres_la_validation_en_base(
    lieu, django_capture_on_commit_callbacks
):
    """
    Adhésion à 0 € par le panier (matérialisée dans une transaction) : la tâche de récompense
    monnaie et l'envoi de la vente à LaBoutik ne partent qu'après la validation en base. Le
    worker Celery relit la ligne avec sa propre connexion : lancée avant, la tâche pourrait ne
    pas la trouver et échouer sans nouvel essai.
    / Free membership through the cart: the reward task and the LaBoutik sale are sent only
    once the transaction is committed.
    """
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion_gratuite = creer_adhesion(prix="0.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion_gratuite.tarif.uuid)

    with django_capture_on_commit_callbacks(execute=False) as rappels_apres_validation:
        materialiser(panier, acheteur)

    taches_avant_la_validation = noms_des_taches(lieu.taches_demandees)
    assert (
        "refill_from_lespass_to_user_wallet_from_price_solded"
        not in taches_avant_la_validation
    )
    assert "send_sale_to_laboutik" not in taches_avant_la_validation

    for rappel in rappels_apres_validation:
        rappel()

    taches_apres_la_validation = noms_des_taches(lieu.taches_demandees)
    assert (
        taches_apres_la_validation.count(
            "refill_from_lespass_to_user_wallet_from_price_solded"
        )
        == 1
    )
    assert taches_apres_la_validation.count("send_sale_to_laboutik") == 1


def test_la_vente_d_un_billet_a_zero_euro_part_a_laboutik_apres_la_validation_en_base(
    lieu, django_capture_on_commit_callbacks
):
    """
    Billet « payant » à 0 € par le panier (matérialisé dans une transaction) : sa vente part à
    LaBoutik, mais seulement après la validation en base (trigger_B, comme trigger_A).
    / 0 € paid-category ticket through the cart: its sale is sent to LaBoutik only after the
    commit.
    """
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="0.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    with django_capture_on_commit_callbacks(execute=False) as rappels_apres_validation:
        materialiser(panier, acheteur)

    assert "send_sale_to_laboutik" not in noms_des_taches(lieu.taches_demandees)

    for rappel in rappels_apres_validation:
        rappel()

    assert noms_des_taches(lieu.taches_demandees).count("send_sale_to_laboutik") == 1


def test_une_adhesion_gratuite_prise_par_le_panier_declenche_les_actions_d_adhesion(
    lieu, django_capture_on_commit_callbacks
):
    """
    Adhésion à 0 € par le panier : comme par le parcours direct, le mail de confirmation et
    la récompense monnaie sont demandés, et l'adhérent est rattaché au lieu (visible dans
    l'admin).
    / Free membership through the cart: confirmation mail and reward requested, member linked
    to the venue — as in the direct flow.
    """
    from BaseBillet.models import LigneArticle, Membership
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion_gratuite = creer_adhesion(prix="0.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion_gratuite.tarif.uuid)

    # La récompense part après la validation en base : on exécute ces rappels.
    # / The reward is sent after the commit: run those callbacks.
    with django_capture_on_commit_callbacks(execute=True):
        commande, _succes = materialiser(panier, acheteur)

    adhesion_creee = commande.memberships_commande.get()
    assert adhesion_creee.status == Membership.ONCE
    assert adhesion_creee.deadline is not None
    assert (
        LigneArticle.objects.get(membership=adhesion_creee).status == LigneArticle.VALID
    )
    taches = noms_des_taches(lieu.taches_demandees)
    assert "send_membership_invoice_to_email" in taches
    assert "refill_from_lespass_to_user_wallet_from_price_solded" in taches
    assert acheteur.client_achat.filter(pk=lieu.tenant.pk).exists()


def test_un_billet_gratuit_pris_par_le_panier_n_envoie_qu_un_seul_mail(lieu):
    """
    Réservation gratuite (`FREERES`) par le panier : les billets sont envoyés une seule fois.
    / Free reservation through the cart: tickets are mailed only once.
    """
    from BaseBillet.models import Product
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(atelier.evenement.uuid, atelier.tarif.uuid, qty=1)

    materialiser(panier, acheteur)

    taches = noms_des_taches(lieu.taches_demandees)
    assert taches.count("ticket_celery_mailer") == 1


def test_un_tarif_adherent_paye_avec_son_adhesion_dans_le_meme_panier(lieu):
    """
    La raison d'être du panier : l'adhésion et le billet au tarif adhérent payés ensemble.
    Après le retour de Stripe, l'adhésion est active et le billet actif.
    / The cart's purpose: membership and members-only ticket paid together.
    """
    from BaseBillet.models import Commande, Membership, Ticket
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="5.00")
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
    commande, succes = materialiser(panier, acheteur)
    assert succes is True

    revenir_de_stripe(acheteur, commande.paiement_stripe)

    commande.refresh_from_db()
    assert commande.status == Commande.PAID
    assert commande.memberships_commande.get().status == Membership.ONCE
    billet = Ticket.objects.get(reservation__commande=commande)
    assert billet.status == Ticket.NOT_SCANNED


@pytest.mark.parametrize("paiement_abouti", [True, False])
def test_une_reservation_gratuite_reservee_aux_adherents_attend_le_paiement_de_l_adhesion(
    lieu, paiement_abouti
):
    """
    Panier : adhésion payante + « réservation gratuite » réservée aux adhérents. Le billet
    gratuit n'est accepté que grâce à l'adhésion du panier : il n'est actif (et envoyé)
    qu'une fois la Commande payée. Paiement abandonné : aucun billet actif, aucun envoi.
    / Cart: paid membership + members-only free booking. The free ticket is active (and
    mailed) only once the Order is paid; abandoned payment: nothing active, nothing mailed.
    """
    from BaseBillet.models import Product, Ticket
    from BaseBillet.services_panier import PanierSession
    from fabriques_panier import noms_des_taches

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    entree_libre = creer_evenement_avec_tarif(categorie=Product.FREERES)
    entree_libre.tarif.adhesions_obligatoires.add(adhesion.produit)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(entree_libre.evenement.uuid, entree_libre.tarif.uuid, qty=1)
    commande, succes = materialiser(panier, acheteur)
    assert succes is True
    if not paiement_abouti:
        lieu.stripe.session.payment_status = "unpaid"
        lieu.stripe.session.status = "open"
        lieu.stripe.session.expires_at = time.time() + 3600

    revenir_de_stripe(acheteur, commande.paiement_stripe)

    billet = Ticket.objects.get(reservation__commande=commande)
    envois_de_billets = noms_des_taches(lieu.taches_demandees).count(
        "ticket_celery_mailer"
    )
    if paiement_abouti:
        assert billet.status == Ticket.NOT_SCANNED
        assert envois_de_billets == 1
    else:
        assert billet.status == Ticket.NOT_ACTIV
        assert envois_de_billets == 0


def test_une_ressource_a_tarif_adherent_passe_avec_l_adhesion_dans_le_meme_panier(lieu):
    """
    Créneau au tarif adhérent + adhésion dans le même panier : au paiement, l'adhésion n'est
    pas encore active, mais elle fait partie de la même Commande. Le booking est créé.
    / Members-only slot + membership in the same cart: the membership belongs to the same
    Order, so the booking is created.
    """
    from BaseBillet.services_panier import PanierSession

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    location = creer_ressource_avec_tarif(prix="3.00")
    location.tarif.adhesions_obligatoires.add(adhesion.produit)
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )

    commande, succes = materialiser(panier, acheteur)

    assert succes is True
    assert commande.bookings.get().resource == location.ressource

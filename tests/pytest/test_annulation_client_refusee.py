"""
Tests de l'option « Refuser l'annulation par le client » d'un événement.
/ Tests of the event option "Refuse cancellation by the customer".

LOCALISATION : tests/pytest/test_annulation_client_refusee.py

LA RÈGLE TESTÉE
`Event.annulation_par_le_client_desactivee` :
- le client ne peut annuler ni sa réservation ni un billet, et ne voit plus les boutons ;
- l'administration peut toujours annuler ;
- un pass est indivisible : un seul de ses événements qui refuse bloque tout le pass ;
- la mention est affichée dans le formulaire, le panier et le mail de confirmation.
/ The customer cannot cancel, the admin still can, one refusing event blocks the whole
pass, and the notice is shown before and after the purchase.

Ces tests ne laissent rien en base de dev : chaque test est annulé à la fin (`django_db`).
/ These tests leave nothing in the dev database.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django_tenants.utils import tenant_context

from BaseBillet.context_processors import _build_items_with_details
from BaseBillet.models import Reservation, SaleOrigin, Ticket
from BaseBillet.models_vente import Vente
from BaseBillet.services_panier import PanierSession
from BaseBillet.services_vente import ouvrir_vente
from BaseBillet.validators import TicketCreator
from pages.services import gabarit_skin
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    requete_avec_session,
    taches_celery_enregistrees,
)
from test_caracterisation_annulations import (
    annuler_un_billet_depuis_mon_compte,
    annuler_une_reservation_depuis_mon_compte,
    client_de_mon_compte,
)
from test_pass_multi_evenements import (
    acheter_le_pass_billets_valides,
    creer_un_pass_deux_jours,
)

pytestmark = pytest.mark.django_db

SKINS_AVEC_PAGE_DE_COMPTE = ["classic", "V2"]


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture(autouse=True, scope="session")
def _inject_cli_env():
    """Remplace la fixture du conftest, qui crée en base une clé API et un superutilisateur.
    / Overrides the conftest fixture, which creates an API key and a superuser."""


@pytest.fixture
def lieu(tenant, mock_stripe):
    """Le lieu `lespass`, avec Stripe (compte Connect compris) et Celery simulés.
    / The `lespass` venue, with Stripe (Connect included) and Celery faked."""
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with patch(
                "BaseBillet.models.Configuration.get_stripe_connect_account",
                return_value="acct_test_annulation",
            ):
                with taches_celery_enregistrees():
                    yield SimpleNamespace(tenant=tenant)


def refuser_l_annulation(evenement):
    """Coche l'option sur l'événement. / Ticks the option on the event."""
    evenement.annulation_par_le_client_desactivee = True
    evenement.save(update_fields=["annulation_par_le_client_desactivee"])


def reserver_deux_billets_gratuits(refuse_l_annulation):
    """
    Une réservation de deux billets à 0 €, valides. Gratuits : l'annulation n'a rien à
    rembourser, seule la règle testée peut la refuser.
    / A booking of two valid 0 € tickets: only the tested rule can refuse cancellation.
    """
    concert = creer_evenement_avec_tarif(prix="0.00")
    if refuse_l_annulation:
        refuser_l_annulation(concert.evenement)
    acheteur = creer_utilisateur(actif=True)
    reservation = Reservation.objects.create(
        user_commande=acheteur, event=concert.evenement
    )
    TicketCreator(
        reservation=reservation,
        products_dict={concert.produit: {concert.tarif: 2}},
        create_checkout=False,
        vente=ouvrir_vente(
            origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
        ),
    )
    reservation.tickets.update(status=Ticket.NOT_SCANNED)
    Reservation.objects.filter(pk=reservation.pk).update(status=Reservation.VALID)
    return Reservation.objects.get(pk=reservation.pk)


def nombre_de_billets_annules(reservation):
    """Compte relu en base. / Count read from the database."""
    return Ticket.objects.filter(
        reservation=reservation, status=Ticket.CANCELED
    ).count()


# --------------------------------------------------------------------------
# Le refus côté serveur
# / Server-side refusal
# --------------------------------------------------------------------------


@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_annuler_sa_reservation_depuis_mon_compte(lieu, refuse_l_annulation):
    """La réservation n'est annulée que si l'événement l'accepte.
    / The booking is cancelled only if the event allows it."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation)
    client = client_de_mon_compte(lieu, reservation.user_commande)

    annuler_une_reservation_depuis_mon_compte(client, reservation)

    reservation.refresh_from_db()
    assert (reservation.status == Reservation.CANCELED) is (not refuse_l_annulation)
    assert nombre_de_billets_annules(reservation) == (0 if refuse_l_annulation else 2)


@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_annuler_un_billet_depuis_mon_compte(lieu, refuse_l_annulation):
    """Le billet n'est annulé que si l'événement l'accepte.
    / The ticket is cancelled only if the event allows it."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation)
    client = client_de_mon_compte(lieu, reservation.user_commande)

    annuler_un_billet_depuis_mon_compte(client, reservation.tickets.first())

    assert nombre_de_billets_annules(reservation) == (0 if refuse_l_annulation else 1)


def test_l_admin_annule_une_reservation_refusee_au_client(lieu):
    """L'administration annule toute la réservation malgré l'option.
    / The admin cancels the whole booking despite the option."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation=True)

    reservation.cancel_and_refund_resa(annulation_par_l_admin=True)

    assert nombre_de_billets_annules(reservation) == 2


def test_l_admin_annule_un_billet_refuse_au_client(lieu):
    """L'administration annule un billet malgré l'option.
    / The admin cancels one ticket despite the option."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation=True)

    reservation.cancel_and_refund_ticket(
        reservation.tickets.first(), annulation_par_l_admin=True
    )

    assert nombre_de_billets_annules(reservation) == 1


# --------------------------------------------------------------------------
# Le pass est indivisible
# / The pass is indivisible
# --------------------------------------------------------------------------


def test_un_seul_jour_qui_refuse_bloque_le_billet_de_l_autre_jour(lieu):
    """Le samedi refuse : le billet de pass du dimanche ne s'annule pas.
    / Saturday refuses: Sunday's pass ticket cannot be cancelled."""
    le_pass = creer_un_pass_deux_jours()
    _samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    refuser_l_annulation(le_pass.samedi)

    with (
        translation.override("fr"),
        pytest.raises(Exception, match="Annulation en ligne impossible"),
    ):
        reservation_du_dimanche.cancel_and_refund_ticket(
            reservation_du_dimanche.tickets.get()
        )

    assert nombre_de_billets_annules(reservation_du_dimanche) == 0


def test_un_seul_jour_qui_refuse_bloque_la_reservation_de_l_autre_jour(lieu):
    """Le samedi refuse : la réservation du dimanche, qui porte le pass, ne s'annule pas.
    / Saturday refuses: Sunday's booking, holding the pass, cannot be cancelled."""
    le_pass = creer_un_pass_deux_jours()
    _samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    refuser_l_annulation(le_pass.samedi)

    with (
        translation.override("fr"),
        pytest.raises(Exception, match="Annulation en ligne impossible"),
    ):
        reservation_du_dimanche.cancel_and_refund_resa()

    assert nombre_de_billets_annules(reservation_du_dimanche) == 0


def test_l_admin_annule_un_pass_refuse_au_client(lieu):
    """L'administration annule tout le pass malgré l'option.
    / The admin cancels the whole pass despite the option."""
    le_pass = creer_un_pass_deux_jours()
    reservation_du_samedi, reservation_du_dimanche = acheter_le_pass_billets_valides(
        le_pass, creer_utilisateur()
    )
    refuser_l_annulation(le_pass.samedi)

    reservation_du_dimanche.cancel_and_refund_ticket(
        reservation_du_dimanche.tickets.get(), annulation_par_l_admin=True
    )

    assert nombre_de_billets_annules(reservation_du_samedi) == 1
    assert nombre_de_billets_annules(reservation_du_dimanche) == 1


# --------------------------------------------------------------------------
# L'affichage
# / Display
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skin", SKINS_AVEC_PAGE_DE_COMPTE)
@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_mes_reservations_montre_le_bouton_ou_le_refus(lieu, skin, refuse_l_annulation):
    """Les boutons d'annulation laissent la place au message de refus.
    / The cancel buttons are replaced by the refusal message."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation)
    client = client_de_mon_compte(lieu, reservation.user_commande)

    def gabarit_du_skin_teste(nom_du_gabarit, skin_preview=None):
        return gabarit_skin(nom_du_gabarit, skin)

    with patch("pages.services.gabarit_skin", side_effect=gabarit_du_skin_teste):
        page = client.get("/my_account/my_reservations/").content.decode()

    billet = reservation.tickets.first()
    assert (f'data-testid="reservation-cancel-{reservation.uuid}"' in page) is (
        not refuse_l_annulation
    )
    assert (f'data-testid="ticket-cancel-{billet.uuid}"' in page) is (
        not refuse_l_annulation
    )
    assert (
        f'data-testid="reservation-cancel-refused-{reservation.uuid}"' in page
    ) is refuse_l_annulation
    assert (
        f'data-testid="ticket-cancel-refused-{billet.uuid}"' in page
    ) is refuse_l_annulation


@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_le_formulaire_de_reservation_affiche_la_mention(lieu, refuse_l_annulation):
    """La mention est dans le formulaire seulement si l'événement refuse l'annulation.
    / The notice is in the form only if the event refuses cancellation."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    if refuse_l_annulation:
        refuser_l_annulation(concert.evenement)

    page = client_connecte().get(f"/event/{concert.evenement.slug}/").content.decode()

    assert 'data-testid="booking-submit"' in page
    assert ('data-testid="booking-no-cancellation"' in page) is refuse_l_annulation


@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_le_panier_affiche_la_mention_pour_un_pass(lieu, refuse_l_annulation):
    """Pass ajouté depuis le dimanche : la mention s'affiche si le samedi refuse.
    / Pass added from Sunday: the notice shows if Saturday refuses."""
    le_pass = creer_un_pass_deux_jours()
    if refuse_l_annulation:
        refuser_l_annulation(le_pass.samedi)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(le_pass.dimanche.uuid, le_pass.tarif_pass.uuid, 1)

    detail = _build_items_with_details(panier)[0]
    html = render_to_string("htmx/components/panier_item.html", {"detail": detail})

    assert ('data-testid="panier-item-no-cancellation"' in html) is refuse_l_annulation


@pytest.mark.parametrize("refuse_l_annulation", [True, False])
def test_le_mail_de_confirmation_affiche_la_mention(lieu, refuse_l_annulation):
    """La mention est dans le mail seulement si la réservation ne peut pas être annulée.
    / The notice is in the email only if the booking cannot be cancelled."""
    reservation = reserver_deux_billets_gratuits(refuse_l_annulation)

    with translation.override("fr"):
        html = render_to_string(
            "emails/buy_confirmation.html",
            {
                "reservation": reservation,
                "event": reservation.event,
                "date_de_l_evenement": timezone.localtime(reservation.event.datetime),
            },
        )

    assert ("non échangeable et non remboursable" in html) is refuse_l_annulation

"""
Test : le mail d'annulation d'un Booking annonce le montant de la vente remboursée.
/ Test: the Booking cancellation mail shows the refunded sale amount.

LOCALISATION : tests/pytest/test_mail_annulation_booking.py
Code testé / Tested code : booking/tasks.py (send_booking_cancellation_user)

Le mail part APRÈS l'annulation. À ce moment, la ligne de remboursement est rattachée au
booking : total_paid() vaut 0. Le mail doit donc lire la vente d'origine.
/ The mail is sent AFTER cancellation: the refund line is linked to the booking and
total_paid() is 0. The mail must read the original sale.

Le booking est payé et remboursé par les vrais gestes : réservation du créneau par son
formulaire, retour de Stripe, puis annulation par la personne
(`Booking.cancel_and_refund_booking`). La vente et son remboursement sont donc écrits par
le service de vente, avec leurs montants entiers.
/ The booking is paid and refunded through the real gestures: the sale and its refund are
written by the sale service, with their whole-cent amounts.

SIMULATIONS
Le test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1), rien n'est supprimé à la main. Stripe (session, catalogue, remboursement) et
Celery sont simulés ; l'envoi du mail aussi (`CeleryMailerClass`).
/ Rolled-back transaction; Stripe, Celery and the mail sending are faked.

Lancer / Run :
    make test ARGS="tests/pytest/test_mail_annulation_booking.py"
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from BaseBillet.models import Paiement_stripe
from booking.models import Booking
from booking.tasks import send_booking_cancellation_user
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from test_caracterisation_admin_api import reserver_une_ressource_sans_panier
from test_caracterisation_annulations import rembourser_comme_stripe
from test_caracterisation_en_ligne import revenir_de_stripe_billetterie

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux et les tâches activent la langue du lieu sans la remettre
    (tests/PIEGES.md, 10.5).
    / Signals and tasks activate the venue language without resetting it."""
    yield
    translation.deactivate()


def test_mail_d_annulation_annonce_le_montant_de_la_vente_et_pas_zero(
    tenant, mock_stripe
):
    """Booking payé 15 € puis remboursé : le mail annonce 15 €, pas 0 €.
    / Booking paid 15 € then refunded: the mail shows 15 €, not 0 €.

    Le créneau est dans deux jours : la date limite d'annulation (24 h avant) n'est
    pas passée, le mail annonce donc un remboursement.
    / The slot is in two days: the cancellation deadline has not passed.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                acheteur = creer_utilisateur()
                client_de_l_acheteur = client_connecte(acheteur)
                location = creer_ressource_avec_tarif(prix="15.00")
                reserver_une_ressource_sans_panier(client_de_l_acheteur, location)
                booking = Booking.objects.get(
                    user=acheteur, resource=location.ressource
                )
                paiement = Paiement_stripe.objects.get(booking=booking)
                revenir_de_stripe_billetterie(client_de_l_acheteur, paiement)

                with patch(
                    "stripe.Refund.create", side_effect=rembourser_comme_stripe
                ):
                    booking.cancel_and_refund_booking()

                # Précondition : total_paid() compte le remboursement.
                # / Precondition: total_paid() counts the refund.
                assert booking.total_paid() == Decimal("0.00")

                with patch("booking.tasks.CeleryMailerClass") as faux_mailer:
                    send_booking_cancellation_user(str(booking.pk))

    contexte_du_mail = faux_mailer.call_args.kwargs["context"]
    assert contexte_du_mail["refund_amount"] == Decimal("15.00"), (
        f"Le mail doit annoncer 15 €, obtenu {contexte_du_mail['refund_amount']}"
    )

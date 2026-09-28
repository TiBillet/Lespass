"""
Tests des boutons d'envoi de billets dans l'admin Reservation.
/ Tests for the ticket sending buttons in the Reservation admin.

LOCALISATION : tests/pytest/test_reservation_admin_envoi_mail.py

Contexte (Sentry BILLETTERIE-COOP-TG / TH) : sur une réservation gratuite en
attente de validation du mail (F), « Send tickets through email again »
passait la résa en VALID sans activer les billets. L'admin repassait ensuite
le statut à la main (régression V -> FA), et le PDF des billets plantait.
/ Context: on a free booking waiting for email validation (F), the resend
button set VALID without activating the tickets.

Couvre :
- le statut est en lecture seule sur le formulaire de modification ;
- résa F : seul le bouton « Valider et envoyer par mail » est proposé ;
- ce bouton passe par F -> FA : billets activés + mail demandé ;
- l'ancien bouton est refusé (403) sur une résa F.
"""

import uuid
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context


@pytest.fixture
def reservation_en_attente_du_mail(tenant):
    """Réservation gratuite F avec un billet NOT_ACTIV, sur un event existant.
    / Free F booking with one NOT_ACTIV ticket, on an existing event."""
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Event, Reservation, Ticket

    with tenant_context(tenant):
        suffix = uuid.uuid4().hex[:8]
        user = TibilletUser.objects.create(
            email=f"test_resa_f_{suffix}@example.com",
            username=f"test_resa_f_{suffix}",
            is_active=False,
        )
        event = Event.objects.first()
        assert event, "Pre-requis : au moins un Event existe dans le tenant lespass."
        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.FREERES,
        )
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_ACTIV)

    yield reservation

    with tenant_context(tenant):
        reservation.delete()  # CASCADE sur les billets / cascades to tickets
        user.delete()


def _url_change(reservation):
    return f"/admin/BaseBillet/reservation/{reservation.pk}/change/"


def test_statut_en_lecture_seule(admin_client, reservation_en_attente_du_mail):
    reponse = admin_client.get(_url_change(reservation_en_attente_du_mail))
    assert reponse.status_code == 200
    assert 'name="status"' not in reponse.content.decode()


def test_resa_f_affiche_seulement_valider_et_envoyer(admin_client, reservation_en_attente_du_mail):
    reponse = admin_client.get(_url_change(reservation_en_attente_du_mail))
    contenu = reponse.content.decode()
    assert "validate_and_send_ticket_to_mail" in contenu
    assert "/send_ticket_to_mail/" not in contenu


def test_valider_et_envoyer_active_les_billets(admin_client, tenant, reservation_en_attente_du_mail):
    from BaseBillet.models import Reservation, Ticket

    reservation = reservation_en_attente_du_mail
    url = f"/admin/BaseBillet/reservation/{reservation.pk}/validate_and_send_ticket_to_mail/"

    with patch("BaseBillet.signals.ticket_celery_mailer.delay") as mailer_delay, \
            patch("BaseBillet.signals.webhook_reservation.delay"):
        reponse = admin_client.get(url, HTTP_REFERER=_url_change(reservation))

    assert reponse.status_code == 302
    mailer_delay.assert_called_once_with(reservation.pk)
    with tenant_context(tenant):
        reservation.refresh_from_db()
        assert reservation.status == Reservation.FREERES_USERACTIV
        statuts_billets = list(reservation.tickets.values_list("status", flat=True))
        assert statuts_billets == [Ticket.NOT_SCANNED]


def test_ancien_bouton_refuse_sur_resa_f(admin_client, reservation_en_attente_du_mail):
    reservation = reservation_en_attente_du_mail
    url = f"/admin/BaseBillet/reservation/{reservation.pk}/send_ticket_to_mail/"

    with patch("Administration.admin_tenant.ticket_celery_mailer.delay") as mailer_delay:
        reponse = admin_client.get(url, HTTP_REFERER=_url_change(reservation))

    assert reponse.status_code == 403
    mailer_delay.assert_not_called()

"""
Tests des boutons d'envoi de billets (admin Reservation) et du PDF de billet (admin Ticket).
/ Tests for the ticket sending buttons (Reservation admin) and the ticket PDF (Ticket admin).

LOCALISATION : tests/pytest/test_reservation_admin_envoi_mail.py

Code testé : Administration/admin_tenant.py
- ReservationAdmin.get_readonly_fields
- ReservationAdmin.send_ticket_to_mail / validate_and_send_ticket_to_mail
- TicketAdmin.get_pdf

Règle métier : une réservation gratuite en attente de validation du mail (FREERES)
a des billets inactifs (NOT_ACTIV). Ils ne deviennent valides qu'avec la transition
FREERES -> FREERES_USERACTIV (BaseBillet/signals.py, reservation_paid).
/ Business rule: a free booking waiting for email validation has inactive tickets.
They become valid only through the FREERES -> FREERES_USERACTIV transition.

Couvre :
- le statut est en lecture seule sur la page de modification ;
- résa FREERES : seul le bouton « Valider et envoyer par mail » est affiché ;
- ce bouton active les billets et demande l'envoi du mail ;
- un second clic sur « Valider et envoyer par mail » est refusé (403) ;
- le bouton « renvoyer les billets » est refusé (403) sur une résa FREERES ;
- résa confirmée : seul le bouton « renvoyer les billets » est affiché ;
- résa annulée : aucun bouton d'envoi ;
- le PDF d'un billet inactif renvoie un message d'erreur et une redirection.

Les tâches Celery (mail, webhook) sont remplacées par des mocks : aucun mail ne part.
/ Celery tasks are mocked: no email is sent.
"""

import uuid
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django_tenants.utils import tenant_context


def _creer_reservation_de_test(tenant, statut_de_la_reservation, statut_du_billet):
    """
    Crée une réservation avec un billet, sur un évènement existant.
    Renvoie (reservation, utilisateur) : les deux sont à supprimer après le test.
    / Creates a booking with one ticket, on an existing event. Returns (booking, user).
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Event, Reservation, Ticket

    with tenant_context(tenant):
        suffixe_unique = uuid.uuid4().hex[:8]
        utilisateur = TibilletUser.objects.create(
            email=f"test_resa_admin_{suffixe_unique}@example.com",
            username=f"test_resa_admin_{suffixe_unique}",
            is_active=False,
        )

        # On réutilise un évènement de la base de dev.
        # Supprimer un Event en test est piégeux (receivers stdimage post_delete).
        # / Reuse a dev DB event: deleting an Event in tests is tricky.
        evenement_existant = Event.objects.first()
        assert evenement_existant, (
            "Pre-requis : au moins un Event existe dans le tenant lespass."
        )

        reservation = Reservation.objects.create(
            user_commande=utilisateur,
            event=evenement_existant,
            status=statut_de_la_reservation,
        )
        Ticket.objects.create(reservation=reservation, status=statut_du_billet)

    return reservation, utilisateur


def _supprimer_reservation_de_test(tenant, reservation, utilisateur):
    # La suppression de la réservation supprime aussi ses billets (CASCADE).
    # / Deleting the booking also deletes its tickets (CASCADE).
    with tenant_context(tenant):
        reservation.delete()
        utilisateur.delete()


@pytest.fixture
def reservation_en_attente_du_mail(tenant):
    """Réservation gratuite FREERES avec un billet NOT_ACTIV.
    / Free FREERES booking with one NOT_ACTIV ticket."""
    from BaseBillet.models import Reservation, Ticket

    reservation, utilisateur = _creer_reservation_de_test(
        tenant, Reservation.FREERES, Ticket.NOT_ACTIV
    )
    yield reservation
    _supprimer_reservation_de_test(tenant, reservation, utilisateur)


@pytest.fixture
def reservation_confirmee(tenant):
    """Réservation VALID avec un billet NOT_SCANNED.
    / VALID booking with one NOT_SCANNED ticket."""
    from BaseBillet.models import Reservation, Ticket

    reservation, utilisateur = _creer_reservation_de_test(
        tenant, Reservation.VALID, Ticket.NOT_SCANNED
    )
    yield reservation
    _supprimer_reservation_de_test(tenant, reservation, utilisateur)


@pytest.fixture
def reservation_annulee(tenant):
    """Réservation CANCELED avec un billet CANCELED.
    / CANCELED booking with one CANCELED ticket."""
    from BaseBillet.models import Reservation, Ticket

    reservation, utilisateur = _creer_reservation_de_test(
        tenant, Reservation.CANCELED, Ticket.CANCELED
    )
    yield reservation
    _supprimer_reservation_de_test(tenant, reservation, utilisateur)


def _url_page_modification(reservation):
    return f"/admin/BaseBillet/reservation/{reservation.pk}/change/"


def test_statut_en_lecture_seule_sur_la_page_de_modification(
    admin_client, reservation_en_attente_du_mail
):
    # Le formulaire ne contient pas de champ "status" modifiable.
    # / The form has no editable "status" field.
    reponse = admin_client.get(_url_page_modification(reservation_en_attente_du_mail))

    assert reponse.status_code == 200
    assert 'name="status"' not in reponse.content.decode()


def test_resa_en_attente_du_mail_affiche_seulement_valider_et_envoyer(
    admin_client, reservation_en_attente_du_mail
):
    # Seul le bouton « Valider et envoyer par mail » est présent.
    # / Only the "Validate and send by email" button is shown.
    reponse = admin_client.get(_url_page_modification(reservation_en_attente_du_mail))
    contenu_html = reponse.content.decode()

    assert "/validate_and_send_ticket_to_mail/" in contenu_html
    assert "/send_ticket_to_mail/" not in contenu_html


def test_valider_et_envoyer_active_les_billets_et_demande_le_mail(
    admin_client, tenant, reservation_en_attente_du_mail
):
    # Le bouton passe la résa en FREERES_USERACTIV : billets activés + mail demandé.
    # / The button moves the booking to FREERES_USERACTIV: tickets activated + email queued.
    from BaseBillet.models import Reservation, Ticket

    reservation = reservation_en_attente_du_mail
    url_valider_et_envoyer = f"/admin/BaseBillet/reservation/{reservation.pk}/validate_and_send_ticket_to_mail/"

    with (
        patch("BaseBillet.signals.ticket_celery_mailer.delay") as envoi_du_mail_mocke,
        patch("BaseBillet.signals.webhook_reservation.delay"),
    ):
        reponse = admin_client.get(
            url_valider_et_envoyer,
            HTTP_REFERER=_url_page_modification(reservation),
        )

    assert reponse.status_code == 302
    envoi_du_mail_mocke.assert_called_once_with(reservation.pk)

    with tenant_context(tenant):
        reservation.refresh_from_db()
        assert reservation.status == Reservation.FREERES_USERACTIV

        statuts_des_billets = list(reservation.tickets.values_list("status", flat=True))
        assert statuts_des_billets == [Ticket.NOT_SCANNED]


def test_renvoyer_les_billets_refuse_sur_resa_en_attente_du_mail(
    admin_client, reservation_en_attente_du_mail
):
    # Appel direct de l'URL du bouton caché : refus 403, aucun mail demandé.
    # / Direct call to the hidden button URL: 403, no email queued.
    reservation = reservation_en_attente_du_mail
    url_renvoyer_les_billets = (
        f"/admin/BaseBillet/reservation/{reservation.pk}/send_ticket_to_mail/"
    )

    with patch(
        "Administration.admin_tenant.ticket_celery_mailer.delay"
    ) as envoi_du_mail_mocke:
        reponse = admin_client.get(
            url_renvoyer_les_billets,
            HTTP_REFERER=_url_page_modification(reservation),
        )

    assert reponse.status_code == 403
    envoi_du_mail_mocke.assert_not_called()


def test_pdf_billet_inactif_redirige_avec_message_erreur(
    admin_client, tenant, reservation_en_attente_du_mail
):
    # Un billet NOT_ACTIV n'a pas de PDF : message d'erreur + retour à la page précédente.
    # / A NOT_ACTIV ticket has no PDF: error message + back to the previous page.
    with tenant_context(tenant):
        billet_inactif = reservation_en_attente_du_mail.tickets.first()

    page_precedente = "/admin/BaseBillet/ticket/"
    url_pdf_du_billet = f"/admin/BaseBillet/ticket/{billet_inactif.pk}/ticket_pdf/"

    reponse = admin_client.get(url_pdf_du_billet, HTTP_REFERER=page_precedente)

    assert reponse.status_code == 302
    assert reponse.url == page_precedente

    # admin_client est partagé par toute la session pytest : des messages d'autres tests
    # peuvent être encore en attente. On ne compte que les messages d'erreur.
    # / admin_client is session-scoped: only error messages are counted.
    messages_d_erreur = []
    for message in get_messages(reponse.wsgi_request):
        if message.level_tag == "error":
            messages_d_erreur.append(message)
    assert len(messages_d_erreur) == 1


def test_second_clic_sur_valider_et_envoyer_refuse(
    admin_client, reservation_en_attente_du_mail
):
    # Après la validation, la résa n'est plus FREERES : un second appel est refusé.
    # / Once validated, the booking is no longer FREERES: a second call is refused.
    reservation = reservation_en_attente_du_mail
    url_valider_et_envoyer = f"/admin/BaseBillet/reservation/{reservation.pk}/validate_and_send_ticket_to_mail/"

    with (
        patch("BaseBillet.signals.ticket_celery_mailer.delay") as envoi_du_mail_mocke,
        patch("BaseBillet.signals.webhook_reservation.delay"),
    ):
        premiere_reponse = admin_client.get(
            url_valider_et_envoyer, HTTP_REFERER=_url_page_modification(reservation)
        )
        seconde_reponse = admin_client.get(
            url_valider_et_envoyer, HTTP_REFERER=_url_page_modification(reservation)
        )

    assert premiere_reponse.status_code == 302
    assert seconde_reponse.status_code == 403
    envoi_du_mail_mocke.assert_called_once()


def test_resa_confirmee_affiche_seulement_renvoyer_les_billets(
    admin_client, reservation_confirmee
):
    # Résa VALID avec un billet valide : seul « renvoyer les billets » est présent.
    # / VALID booking with a valid ticket: only "resend tickets" is shown.
    reponse = admin_client.get(_url_page_modification(reservation_confirmee))
    contenu_html = reponse.content.decode()

    assert "/send_ticket_to_mail/" in contenu_html
    assert "/validate_and_send_ticket_to_mail/" not in contenu_html


def test_resa_annulee_n_affiche_aucun_bouton_d_envoi(admin_client, reservation_annulee):
    # Résa annulée (billets annulés) : aucun bouton d'envoi.
    # / Cancelled booking (cancelled tickets): no sending button.
    reponse = admin_client.get(_url_page_modification(reservation_annulee))
    contenu_html = reponse.content.decode()

    assert "/send_ticket_to_mail/" not in contenu_html
    assert "/validate_and_send_ticket_to_mail/" not in contenu_html

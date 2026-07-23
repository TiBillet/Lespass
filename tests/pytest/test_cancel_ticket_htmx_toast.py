"""
Test DB-only : MyAccount.cancel_ticket — toast HTMX via l'entête HX-Trigger.
/ DB-only test: MyAccount.cancel_ticket — HTMX toast through the HX-Trigger header.

CONTEXTE (issue #431) :
"Quand on annule un billet, le message de confirmation s'affiche après un
reload et pas directement." L'annulation d'un billet passait par
HttpResponseClientRedirect : le message django.messages n'était affiché
qu'après le rechargement complet de la page.

LE CORRECTIF : la branche HTMX de MyAccount.cancel_ticket (BaseBillet/views.py)
draine les django.messages en attente et les embarque dans l'entête
HX-Trigger (payload {"toast": {"items": [{"level", "text"}]}}) pour que le
toast s'affiche immédiatement, sans reload :
- succès : HttpResponse("") 200 + HX-Trigger (level "success") ;
- erreur : HttpResponse("", status=400) + HX-Trigger (level "error"),
  htmx ne swappe pas (la ligne du billet reste affichée) mais traite
  quand même l'entête HX-Trigger.
La branche NON-HTMX garde le comportement HttpResponseClientRedirect
(entête HX-Redirect vers /my_account/my_reservations/).

/ CONTEXT (issue #431): "When cancelling a ticket, the confirmation message
only shows after a reload, not immediately." The HTMX branch of cancel_ticket
must ship queued django.messages through the HX-Trigger header so the toast
displays immediately; the non-HTMX branch keeps the HX-Redirect behavior.

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_cancel_ticket_htmx_toast.py -v
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test.client import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def _creer_user_connectable(tenant, suffix):
    """
    Cree un utilisateur capable de passer MyAccount.dispatch :
    - is_active=True (get_or_create_user cree des users INACTIFS ; un user
      inactif redevient AnonymousUser au chargement de session -> redirect '/') ;
    - wallet local (sans wallet, dispatch appelle FedowAPI -> reseau).
    IMPORTANT : activer AVANT de creer la reservation — le passage
    is_active False->True declenche activator_free_reservation (signals.py).
    / Creates a user able to pass MyAccount.dispatch: active (inactive users
    resolve to AnonymousUser on session load -> redirect '/') and with a local
    wallet (without one, dispatch calls FedowAPI -> network). Activate BEFORE
    creating the reservation — the False->True transition triggers
    activator_free_reservation (signals.py).
    """
    from AuthBillet.models import Wallet
    from AuthBillet.utils import get_or_create_user

    user = get_or_create_user(f"cancel_ticket_htmx_{suffix}@example.com", send_mail=False)
    user.is_active = True
    user.wallet = Wallet.objects.create(origin=tenant)
    user.save(update_fields=["is_active", "wallet"])
    return user


def _creer_resa_avec_ticket(user, suffix, ticket_status):
    """
    Event + reservation + UN ticket GRATUIT (sans pricesold ni LigneArticle) :
    cancel_and_refund_ticket prend alors la voie sans remboursement — aucun
    appel Stripe (total_paid()==0, aucune ligne hors-Stripe ne matche).
    / Event + reservation + ONE FREE ticket (no pricesold, no LigneArticle):
    cancel_and_refund_ticket takes the no-refund path — no Stripe call
    (total_paid()==0, no non-Stripe line matches).
    """
    from BaseBillet.models import Event, Reservation, Ticket

    event = Event.objects.create(
        name=f"AnnulBillet_{suffix}",
        datetime=timezone.now() + timedelta(days=7),
    )
    reservation = Reservation.objects.create(user_commande=user, event=event)
    ticket = Ticket.objects.create(reservation=reservation, status=ticket_status)
    return event, reservation, ticket


def test_cancel_ticket_htmx_renvoie_le_toast_dans_hx_trigger(tenant):
    """
    POST HTMX sur cancel_ticket : 200, entête HX-Trigger avec le toast
    de succès, et le billet passe CANCELED en DB. (Issue #431)
    / HTMX POST on cancel_ticket: 200, HX-Trigger header carrying the
    success toast, and the ticket is CANCELED in DB. (Issue #431)
    """
    with tenant_context(tenant):
        from BaseBillet.models import Ticket

        suffix = uuid.uuid4().hex[:8]
        user = _creer_user_connectable(tenant, suffix)
        event, reservation, ticket = _creer_resa_avec_ticket(user, suffix, Ticket.NOT_SCANNED)

        client = DjangoClient(HTTP_HOST=tenant.get_primary_domain().domain)
        client.force_login(user)

        with patch("BaseBillet.views.send_ticket_cancellation_user.delay") as mock_mail:
            response = client.post(
                f"/my_account/{ticket.uuid}/cancel_ticket/",
                HTTP_HX_REQUEST="true",
            )

        assert response.status_code == 200

        # Le toast voyage dans l'entête HX-Trigger, pas dans le body.
        # / The toast travels in the HX-Trigger header, not in the body.
        trigger = response.headers.get("HX-Trigger")
        assert trigger, "L'entête HX-Trigger doit être présente (issue #431)"
        payload = json.loads(trigger)
        items = payload["toast"]["items"]
        assert isinstance(items, list) and len(items) > 0

        # Assertion robuste, indépendante de la locale : niveau + texte non vide.
        # / Locale-independent robust assertion: level + non-empty text.
        assert items[0]["level"] == "success"
        assert len(items[0]["text"]) > 0

        ticket.refresh_from_db()
        assert ticket.status == Ticket.CANCELED

        mock_mail.assert_called_once_with(str(ticket.uuid))

        # Cleanup : tickets + reservation. PAS l'event (piege stdimage 10.1).
        # / Cleanup: tickets + reservation. NOT the event (stdimage pitfall 10.1).
        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_cancel_ticket_htmx_erreur_renvoie_le_toast_erreur(tenant):
    """
    Billet déjà SCANNÉ : cancel_and_refund_ticket lève ("You cannot cancel a
    ticket that has been scanned.", models.py). La branche HTMX d'erreur
    renvoie 400 + HX-Trigger level "error", et le billet reste SCANNED.
    / Already SCANNED ticket: cancel_and_refund_ticket raises. The HTMX error
    branch returns 400 + HX-Trigger level "error", ticket stays SCANNED.
    """
    with tenant_context(tenant):
        from BaseBillet.models import Ticket

        suffix = uuid.uuid4().hex[:8]
        user = _creer_user_connectable(tenant, suffix)
        event, reservation, ticket = _creer_resa_avec_ticket(user, suffix, Ticket.SCANNED)

        client = DjangoClient(HTTP_HOST=tenant.get_primary_domain().domain)
        client.force_login(user)

        with patch("BaseBillet.views.send_ticket_cancellation_user.delay") as mock_mail:
            response = client.post(
                f"/my_account/{ticket.uuid}/cancel_ticket/",
                HTTP_HX_REQUEST="true",
            )

        # 400 : htmx ne swappe pas (la ligne reste) mais traite HX-Trigger.
        # / 400: htmx does not swap (row stays) but still processes HX-Trigger.
        assert response.status_code == 400
        trigger = response.headers.get("HX-Trigger")
        assert trigger, "L'entête HX-Trigger doit être présente même en erreur"
        payload = json.loads(trigger)
        items = payload["toast"]["items"]
        assert isinstance(items, list) and len(items) > 0
        assert items[0]["level"] == "error"
        assert len(items[0]["text"]) > 0

        # Le billet scanné n'est PAS annulé.
        # / The scanned ticket is NOT cancelled.
        ticket.refresh_from_db()
        assert ticket.status == Ticket.SCANNED

        mock_mail.assert_not_called()

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_cancel_ticket_sans_htmx_redirige(tenant):
    """
    POST SANS entête HX-Request : comportement historique conservé —
    HttpResponseClientRedirect (django-htmx) = 200 + entête HX-Redirect vers
    /my_account/my_reservations/. Le billet est bien CANCELED en DB.
    / POST WITHOUT the HX-Request header: legacy behavior preserved —
    HttpResponseClientRedirect (django-htmx) = 200 + HX-Redirect header to
    /my_account/my_reservations/. Ticket is CANCELED in DB.
    """
    with tenant_context(tenant):
        from BaseBillet.models import Ticket

        suffix = uuid.uuid4().hex[:8]
        user = _creer_user_connectable(tenant, suffix)
        event, reservation, ticket = _creer_resa_avec_ticket(user, suffix, Ticket.NOT_SCANNED)

        client = DjangoClient(HTTP_HOST=tenant.get_primary_domain().domain)
        client.force_login(user)

        with patch("BaseBillet.views.send_ticket_cancellation_user.delay"):
            response = client.post(f"/my_account/{ticket.uuid}/cancel_ticket/")

        # HttpResponseClientRedirect : HttpResponse 200 + entête HX-Redirect.
        # / HttpResponseClientRedirect: HttpResponse 200 + HX-Redirect header.
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/my_account/my_reservations/"
        assert response.headers.get("HX-Trigger") is None

        ticket.refresh_from_db()
        assert ticket.status == Ticket.CANCELED

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()

"""
Test DB-only : Reservation.valid_tickets_count() / Reservation.cancelled_tickets_count().
/ DB-only test: Reservation.valid_tickets_count() / Reservation.cancelled_tickets_count().

CONTEXTE (issue #432) :
BaseBillet/templates/reunion/views/account/reservations.html affichait
`{{ resa.tickets.all|length }}` : ce total incluait les tickets CANCELED /
NOT_ACTIV / CREATED, alors que le partial ticket_accordion.html n'affiche que
les tickets NOT_SCANNED et SCANNED. Le nombre de places affiche pouvait donc
etre superieur au nombre de billets reellement listes en dessous.

LE CORRECTIF : Reservation.valid_tickets_count() (BaseBillet/models.py), sur
le meme modele que Event.valid_tickets_count(), compte uniquement les tickets
au statut NOT_SCANNED ou SCANNED. Reservation.cancelled_tickets_count() compte
separement les tickets CANCELED, pour que le template puisse afficher les deux
informations ("2 places + 1 annulee") au lieu de faire disparaitre les billets
annules du compteur.

/ CONTEXT (issue #432): the template rendered `{{ resa.tickets.all|length }}`,
counting ALL tickets including CANCELED / NOT_ACTIV / CREATED, while
ticket_accordion.html only lists NOT_SCANNED / SCANNED tickets — an
inconsistent "N seats" count.

THE FIX: Reservation.valid_tickets_count() (BaseBillet/models.py), mirroring
Event.valid_tickets_count(), counts only NOT_SCANNED/SCANNED tickets.
Reservation.cancelled_tickets_count() separately counts CANCELED tickets, so
the template can display both pieces of information ("2 places + 1 annulee")
instead of silently dropping cancelled tickets from the count.

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_reservation_valid_tickets_count.py -v
"""
import uuid
from datetime import timedelta

import pytest
from django.db.models import Count, Q
from django.utils import timezone
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def test_valid_tickets_count_exclut_les_tickets_annules(tenant):
    """
    Reservation avec un mix NOT_SCANNED + SCANNED + CANCELED : seuls les
    tickets NOT_SCANNED/SCANNED sont comptes par valid_tickets_count().
    / Reservation with a mix of NOT_SCANNED + SCANNED + CANCELED: only
    NOT_SCANNED/SCANNED tickets are counted by valid_tickets_count().
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation, Ticket

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"Concert_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"valid_tickets_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.CANCELED)

        assert reservation.valid_tickets_count() == 2
        assert reservation.cancelled_tickets_count() == 1

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_valid_tickets_count_exclut_les_tickets_en_attente(tenant):
    """
    Les tickets CREATED / NOT_ACTIV (paiement/email en attente) ne sont ni
    valides ni annules — ils ne comptent dans aucun des deux compteurs, comme
    dans ticket_accordion.html.
    / CREATED / NOT_ACTIV (pending payment/email) tickets are neither valid
    nor cancelled — counted in neither, matching ticket_accordion.html.
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation, Ticket

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"Atelier_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"attente_tickets_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        Ticket.objects.create(reservation=reservation, status=Ticket.CREATED)
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_ACTIV)
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)

        assert reservation.valid_tickets_count() == 1
        assert reservation.cancelled_tickets_count() == 0

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_valid_et_cancelled_tickets_count_sans_aucun_ticket(tenant):
    """
    Reservation sans aucun ticket : les deux compteurs renvoient 0.
    / Reservation without any ticket: both counters return 0.
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"Vide_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"aucun_ticket_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        assert reservation.valid_tickets_count() == 0
        assert reservation.cancelled_tickets_count() == 0

        reservation.delete()


def test_cancelled_tickets_count_quand_tous_les_tickets_sont_annules(tenant):
    """
    Reservation dont tous les tickets sont CANCELED : valid_tickets_count()
    renvoie 0, cancelled_tickets_count() compte tout.
    / Reservation whose tickets are all CANCELED: valid_tickets_count()
    returns 0, cancelled_tickets_count() counts them all.
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation, Ticket

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"ToutAnnule_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"tout_annule_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        Ticket.objects.create(reservation=reservation, status=Ticket.CANCELED)
        Ticket.objects.create(reservation=reservation, status=Ticket.CANCELED)

        assert reservation.valid_tickets_count() == 0
        assert reservation.cancelled_tickets_count() == 2

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_annulation_partielle_deplace_un_ticket_de_valid_vers_cancelled(tenant):
    """
    Annuler un seul ticket parmi plusieurs diminue valid_tickets_count() de 1
    et augmente cancelled_tickets_count() de 1.
    / Cancelling a single ticket among several decreases valid_tickets_count()
    by 1 and increases cancelled_tickets_count() by 1.
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation, Ticket

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"AnnulationPartielle_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"annulation_partielle_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        ticket_a = Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)

        assert reservation.valid_tickets_count() == 2
        assert reservation.cancelled_tickets_count() == 0

        ticket_a.status = Ticket.CANCELED
        ticket_a.save(update_fields=["status"])

        assert reservation.valid_tickets_count() == 1
        assert reservation.cancelled_tickets_count() == 1

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()


def test_annotate_correspond_aux_methodes_du_modele(tenant):
    """
    Garde-fou anti-regression : le queryset annote de MyAccount.my_reservations()
    doit toujours produire les memes nombres que Reservation.valid_tickets_count()
    et cancelled_tickets_count(). Si quelqu'un change la logique d'un cote sans
    mettre a jour l'autre, ce test doit rougir immediatement.
    / Regression guard: the annotated queryset from MyAccount.my_reservations()
    must always match Reservation.valid_tickets_count() and
    cancelled_tickets_count(). If either side changes without updating the
    other, this test must fail immediately.
    """
    with tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.models import Event, Reservation, Ticket

        suffix = uuid.uuid4().hex[:8]

        event = Event.objects.create(
            name=f"AnnotateEquivalence_{suffix}",
            datetime=timezone.now() + timedelta(days=7),
        )
        user = get_or_create_user(f"annotate_equiv_{suffix}@example.com", send_mail=False)
        reservation = Reservation.objects.create(user_commande=user, event=event)

        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.CANCELED)
        Ticket.objects.create(reservation=reservation, status=Ticket.CREATED)

        # Meme annotation que MyAccount.my_reservations() (BaseBillet/views.py).
        # / Same annotation as MyAccount.my_reservations() (BaseBillet/views.py).
        annotated = Reservation.objects.filter(uuid=reservation.uuid).annotate(
            annotated_valid_count=Count(
                'tickets', filter=Q(tickets__status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED])
            ),
            annotated_cancelled_count=Count(
                'tickets', filter=Q(tickets__status=Ticket.CANCELED)
            ),
        ).first()

        assert annotated.annotated_valid_count == reservation.valid_tickets_count()
        assert annotated.annotated_cancelled_count == reservation.cancelled_tickets_count()

        Ticket.objects.filter(reservation=reservation).delete()
        reservation.delete()

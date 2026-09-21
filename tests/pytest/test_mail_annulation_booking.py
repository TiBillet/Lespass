"""
Test : le mail d'annulation d'un Booking annonce le montant de la vente remboursée.
/ Test: the Booking cancellation mail shows the refunded sale amount.

LOCALISATION : tests/pytest/test_mail_annulation_booking.py
Code testé / Tested code : booking/tasks.py (send_booking_cancellation_user)

Le mail part APRÈS l'annulation. À ce moment, la ligne de remboursement est rattachée au
booking : total_paid() vaut 0. Le mail doit donc lire la vente d'origine.
/ The mail is sent AFTER cancellation: the refund line is linked to the booking and
total_paid() is 0. The mail must read the original sale.

Lancer / Run :
    docker exec lespass_django poetry run pytest tests/pytest/test_mail_annulation_booking.py -q
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


def test_mail_d_annulation_annonce_le_montant_de_la_vente_et_pas_zero(tenant):
    """Booking payé 15 € puis remboursé : le mail annonce 15 €, pas 0 €.
    / Booking paid 15 € then refunded: the mail shows 15 €, not 0 €.
    """
    from AuthBillet.utils import get_or_create_user
    from BaseBillet.models import LigneArticle, PaymentMethod, PriceSold, SaleOrigin
    from booking.models import Booking, Resource
    from booking.tasks import send_booking_cancellation_user

    with tenant_context(tenant):
        # Une ressource existante du lieu : seul le créneau compte ici.
        # / An existing resource of the place: only the slot matters here.
        ressource = Resource.objects.first()
        if ressource is None:
            pytest.fail(
                "Aucune ressource de réservation dans le tenant : lancer les données de démo."
            )

        # N'importe quel tarif vendu du lieu : seul le montant compte ici.
        # / Any sold price of the place: only the amount matters here.
        tarif_vendu = PriceSold.objects.first()
        client = get_or_create_user(
            f"test+booking{uuid.uuid4().hex[:8]}@mock.test", send_mail=False
        )

        # Créneau loin dans le futur : la date limite d'annulation n'est pas passée.
        # / Slot far in the future: the cancellation deadline has not passed.
        booking = Booking.objects.create(
            resource=ressource,
            user=client,
            start_datetime=timezone.now() + timedelta(days=60),
            slot_duration_minutes=60,
            slot_count=1,
        )

        try:
            # La vente, puis la ligne négative que crée partial_refund_payment() au remboursement.
            # / The sale, then the negative line partial_refund_payment() creates on refund.
            LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=1,
                amount=1500,
                booking=booking,
                payment_method=PaymentMethod.STRIPE_NOFED,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.LESPASS,
            )
            LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=-1,
                amount=1500,
                booking=booking,
                payment_method=PaymentMethod.STRIPE_NOFED,
                status=LigneArticle.REFUNDED,
                sale_origin=SaleOrigin.LESPASS,
            )
            # Précondition : total_paid() compte le remboursement.
            # / Precondition: total_paid() counts the refund.
            assert booking.total_paid() == Decimal("0.00")

            with patch("booking.tasks.CeleryMailerClass") as faux_mailer:
                send_booking_cancellation_user(str(booking.pk))

            contexte_du_mail = faux_mailer.call_args.kwargs["context"]
            assert contexte_du_mail["refund_amount"] == Decimal("15.00"), (
                f"Le mail doit annoncer 15 €, obtenu {contexte_du_mail['refund_amount']}"
            )
        finally:
            LigneArticle.objects.filter(booking=booking).delete()
            booking.delete()

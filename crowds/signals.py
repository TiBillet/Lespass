from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import connection

from .models import Participation, Contribution
from .tasks import email_participation_requested_admin, email_contribution_paid_admin

logger = logging.getLogger(__name__)


# --- Participation: notify admins when a new request is created ---
@receiver(post_save, sender=Participation)
def participation_created_notify(sender, instance: Participation, created: bool, **kwargs):
    if not created:
        return
    try:
        schema_name = connection.schema_name
    except Exception:
        schema_name = 'public'
    try:
        email_participation_requested_admin.delay(
            schema_name=schema_name,
            initiative_uuid=str(instance.initiative_id),
            participation_uuid=str(instance.pk),
        )
    except Exception as e:
        logger.error(f"crowds.signals participation_created_notify: {e}")


# --- Contribution: detect payment status transitions ---
@receiver(pre_save, sender=Contribution)
def contribution_store_old_status(sender, instance: Contribution, **kwargs):
    """Store old payment_status on the instance to compare post_save."""
    try:
        if not instance.pk:
            instance._old_payment_status = None
            return
        old = Contribution.objects.filter(pk=instance.pk).only("payment_status").first()
        instance._old_payment_status = old.payment_status if old else None
    except Exception:
        instance._old_payment_status = None


@receiver(post_save, sender=Contribution)
def contribution_paid_notify(sender, instance: Contribution, created: bool, **kwargs):
    # Only when transitioning to a paid status
    try:
        new_status = instance.payment_status

        ### Au cas ou on veut suivre le status, mini machine a état :
        # old_status = getattr(instance, "_old_payment_status", None)
        # paid_values = {Contribution.PaymentStatus.PAID, Contribution.PaymentStatus.PAID_ADMIN}
        # if new_status in paid_values and new_status != old_status:

        if new_status == Contribution.PaymentStatus.PENDING:
            try:
                schema_name = connection.schema_name
            except Exception:
                schema_name = 'public'
            email_contribution_paid_admin.delay(
                schema_name=schema_name,
                initiative_uuid=str(instance.initiative_id),
                contribution_uuid=str(instance.pk),
            )
    except Exception as e:
        logger.error(f"crowds.signals contribution_paid_notify: {e}")

from __future__ import annotations

import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db import connection
from django.core.cache import cache

from .models import Participation, Contribution, Initiative, BudgetItem, Vote, GlobalFunding
from .tasks import email_participation_requested_admin, email_contribution_paid_admin

logger = logging.getLogger(__name__)


# --- Cache invalidation for Crowds data ---
def invalidate_crowds_cache():
    """
    FR: Invalide les caches globaux de l'application Crowds pour le tenant actuel.
        Ceci inclut le résumé de la liste et les données du diagramme de Sankey.
    EN: Invalidate global Crowds application caches for the current tenant.
        This includes the list summary and the Sankey diagram data.
    """
    try:
        tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
        if tenant_id:
            # Invalide le résumé de la liste (utilisé dans InitiativeViewSet._summary_context)
            cache.delete(f"crowds:list:summary:{tenant_id}")
            # Invalide les données du Sankey (utilisé dans InitiativeViewSet.sankey)
            cache.delete(f"crowds:sankey:data:{tenant_id}")
            logger.info(f"crowds.signals: Cache invalidated for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"crowds.signals invalidate_crowds_cache error: {e}")

@receiver(post_save, sender=Initiative)
@receiver(post_delete, sender=Initiative)
@receiver(post_save, sender=Contribution)
@receiver(post_delete, sender=Contribution)
@receiver(post_save, sender=Participation)
@receiver(post_delete, sender=Participation)
@receiver(post_save, sender=BudgetItem)
@receiver(post_delete, sender=BudgetItem)
@receiver(post_save, sender=Vote)
@receiver(post_delete, sender=Vote)
@receiver(post_save, sender=GlobalFunding)
@receiver(post_delete, sender=GlobalFunding)
def on_crowds_data_change(sender, **kwargs):
    """
    FR: Déclenché à chaque modification d'une initiative, contribution ou participation.
    EN: Triggered on every modification of an initiative, contribution or participation.
    """
    invalidate_crowds_cache()


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

        if new_status == Contribution.PaymentStatus.PENDING and not settings.TEST:
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

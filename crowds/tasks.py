from __future__ import annotations

import logging
from typing import Iterable, List

from celery import shared_task
from django.utils.translation import gettext_lazy as _, activate
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context

from BaseBillet.tasks import CeleryMailerClass
from BaseBillet.models import Configuration
from .models import Initiative, Participation, Contribution

logger = logging.getLogger(__name__)
User = get_user_model()


def _admin_recipients() -> List[str]:
    """Return unique list of admin/staff recipient emails for the current tenant.
    Priority: Configuration.email then all staff/superusers.
    """
    emails: List[str] = []
    try:
        config = Configuration.get_solo()
        if getattr(config, "email", None):
            emails.append(config.email)
    except Exception:
        pass
    try:
        for u in User.objects.filter(is_active=True).filter(is_staff=True).only("email"):
            if u.email:
                emails.append(u.email)
    except Exception:
        pass
    # dedupe while preserving order
    seen = set()
    uniq: List[str] = []
    for e in emails:
        if e and e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def _currency(initiative: Initiative) -> str:
    try:
        return initiative.asset.currency_code
    except Exception:
        return "EUR"


@shared_task
def email_participation_requested_admin(schema_name: str, initiative_uuid: str, participation_uuid: str) -> bool:
    """Notify the place admins that a participation has been requested (state requested).
    Uses tenant schema switching to render with the correct Configuration and URLs.
    """
    try:
        with schema_context(schema_name):
            config = Configuration.get_solo()
            activate(config.language)

            part = Participation.objects.select_related("initiative", "participant").get(pk=participation_uuid)
            init = part.initiative

            recipients = _admin_recipients() or ([config.email] if getattr(config, "email", None) else [])
            if not recipients:
                logger.warning("crowds.email_participation_requested_admin: no recipients found")
                return False

            subject = f"{config.organisation} — " + _("Nouvelle participation demandée")
            context = {
                "title": subject,
                "organisation": config.organisation,
                "now": timezone.now(),
                "initiative": init,
                "participation": part,
                "participant_email": getattr(part.participant, "email", ""),
                "participant_name": getattr(part.participant, "get_full_name", lambda: "")() or getattr(part.participant, "first_name", "") or getattr(part.participant, "email", ""),
                "requested_amount_eur": (part.requested_amount_cents or 0) / 100,
                "currency": _currency(init),
            }
            sent_any = False
            for to in recipients:
                try:
                    mail = CeleryMailerClass(
                        to,
                        subject,
                        template="crowds/email/participation_requested_admin.html",
                        context=context,
                    )
                    mail.send()
                    sent_any = sent_any or bool(mail.sended)
                except Exception as e:
                    logger.error(f"crowds.email_participation_requested_admin: error sending to {to}: {e}")
            return sent_any
    except Exception as e:
        logger.exception(f"crowds.email_participation_requested_admin failed: {e}")
        return False


@shared_task
def email_contribution_paid_admin(schema_name: str, initiative_uuid: str, contribution_uuid: str) -> bool:
    """Notify the place admins that a financial contribution has been marked as paid.
    Triggered when a Contribution transitions to paid/admin_paid.
    """
    try:
        with schema_context(schema_name):
            config = Configuration.get_solo()
            activate(config.language)

            contrib = Contribution.objects.select_related("initiative", "contributor").get(pk=contribution_uuid)
            init = contrib.initiative

            recipients = _admin_recipients() or ([config.email] if getattr(config, "email", None) else [])
            if not recipients:
                logger.warning("crowds.email_contribution_paid_admin: no recipients found")
                return False

            subject = f"{config.organisation} — " + _("Contribution payée")
            context = {
                "title": subject,
                "organisation": config.organisation,
                "now": timezone.now(),
                "initiative": init,
                "contribution": contrib,
                "contributor_name": contrib.contributor_name or getattr(contrib.contributor, "email", ""),
                "contributor_email": getattr(contrib.contributor, "email", ""),
                "amount_eur": (contrib.amount or 0) / 100,
                "currency": _currency(init),
                "paid_at": contrib.paid_at or timezone.now(),
                "payment_status": contrib.payment_status,
            }
            sent_any = False
            for to in recipients:
                try:
                    mail = CeleryMailerClass(
                        to,
                        subject,
                        template="crowds/email/contribution_paid_admin.html",
                        context=context,
                    )
                    mail.send()
                    sent_any = sent_any or bool(mail.sended)
                except Exception as e:
                    logger.error(f"crowds.email_contribution_paid_admin: error sending to {to}: {e}")
            return sent_any
    except Exception as e:
        logger.exception(f"crowds.email_contribution_paid_admin failed: {e}")
        return False

# laboutik/tasks.py
# Taches Celery pour l'app LaBoutik.
# Celery tasks for the LaBoutik app.
#
# Pattern : crowds/tasks.py (schema_context multi-tenant)
# Pattern: crowds/tasks.py (multi-tenant schema_context)
#
# Import des taches d'impression pour que Celery autodiscover les trouve.
# Les taches sont definies dans laboutik/printing/tasks.py mais Celery
# ne scanne que laboutik/tasks.py (pas les sous-modules).
# / Import printing tasks so Celery autodiscover finds them.
# Tasks are defined in laboutik/printing/tasks.py but Celery
# only scans laboutik/tasks.py (not submodules).
from laboutik.printing.tasks import imprimer_async, imprimer_commande  # noqa: F401

import logging
import os

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.template.loader import render_to_string
from django.utils.translation import activate, gettext as _
from django_tenants.utils import schema_context

from BaseBillet.models import Configuration

logger = logging.getLogger(__name__)


@shared_task
def envoyer_rapport_cloture(schema_name, cloture_uuid, email_destinataire=None):
    """
    Envoie le rapport de cloture par email avec PDF + CSV en pieces jointes.
    Sends the closure report by email with PDF + CSV attachments.

    LOCALISATION : laboutik/tasks.py

    :param schema_name: nom du schema tenant (pour schema_context)
    :param cloture_uuid: UUID de la ClotureCaisse (str)
    :param email_destinataire: email du destinataire (optionnel, sinon config.email)
    """
    try:
        with schema_context(schema_name):
            from laboutik.models import ClotureCaisse
            from laboutik.pdf import generer_pdf_cloture
            from laboutik.csv_export import generer_csv_cloture

            config = Configuration.get_solo()
            activate(config.language)

            # Charger la cloture / Load the closure
            cloture = ClotureCaisse.objects.select_related(
                'point_de_vente', 'responsable',
            ).get(uuid=cloture_uuid)

            # Generer PDF et CSV / Generate PDF and CSV
            pdf_bytes = generer_pdf_cloture(cloture)
            csv_string = generer_csv_cloture(cloture)

            # Destinataire : email fourni ou email de la config
            # Recipient: provided email or config email
            destinataire = email_destinataire or config.email
            if not destinataire:
                logger.warning(f"Pas de destinataire pour cloture {cloture_uuid}")
                return False

            # Nom du fichier base sur le PV et la date
            # Filename based on POS and date
            date_str = cloture.datetime_cloture.strftime("%Y%m%d_%H%M")
            nom_base = f"cloture_{date_str}"

            # Construire le corps HTML de l'email
            # Build the HTML email body
            context_email = {
                "config": config,
                "cloture": cloture,
                "point_de_vente": cloture.point_de_vente,
                "total_general_euros": cloture.total_general / 100,
                "nombre_transactions": cloture.nombre_transactions,
            }
            html_body = render_to_string(
                "laboutik/email/cloture_rapport_email.html",
                context_email,
            )
            text_body = _(
                "Rapport de clôture — %(pv)s — Total : %(total).2f EUR"
            ) % {
                "pv": cloture.point_de_vente.name,
                "total": cloture.total_general / 100,
            }

            # Expediteur : meme logique que CeleryMailerClass
            # Sender: same logic as CeleryMailerClass
            from_email = os.environ.get('DEFAULT_FROM_EMAIL', os.environ.get('EMAIL_HOST_USER'))

            # Construire et envoyer l'email / Build and send the email
            sujet = _("Rapport de clôture — %(pv)s") % {
                "pv": cloture.point_de_vente.name,
            }
            mail = EmailMultiAlternatives(
                subject=sujet,
                body=text_body,
                from_email=from_email,
                to=[destinataire],
            )
            mail.attach_alternative(html_body, "text/html")
            mail.attach(f"{nom_base}.pdf", pdf_bytes, "application/pdf")
            mail.attach(f"{nom_base}.csv", csv_string.encode("utf-8"), "text/csv")
            mail.send(fail_silently=False)

            logger.info(
                f"Rapport cloture envoye: {cloture_uuid} → {destinataire}"
            )
            return True

    except Exception as e:
        logger.exception(f"Erreur envoi rapport cloture {cloture_uuid}: {e}")
        return False

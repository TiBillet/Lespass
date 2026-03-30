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


@shared_task
def generer_cloture_mensuelle():
    """
    Generee le 1er de chaque mois pour le mois precedent.
    Itere sur les tenants actifs avec module_caisse.
    / Generated on the 1st of each month for the previous month.
    Iterates over active tenants with module_caisse.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from Customers.models import Client

    aujourd_hui = date.today()
    premier_jour_mois_courant = aujourd_hui.replace(day=1)
    premier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(months=1)
    dernier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(days=1)

    logger.info(
        f"Cloture mensuelle: {premier_jour_mois_precedent} → {dernier_jour_mois_precedent}"
    )

    tenants = Client.objects.exclude(schema_name='public')
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                _generer_cloture_agregee(
                    niveau='M',
                    niveau_source='J',
                    date_debut=premier_jour_mois_precedent,
                    date_fin=dernier_jour_mois_precedent,
                )
        except Exception as e:
            logger.exception(
                f"Erreur cloture mensuelle tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_annuelle():
    """
    Generee le 1er janvier pour l'annee precedente.
    / Generated on January 1st for the previous year.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import date
    from Customers.models import Client

    annee_precedente = date.today().year - 1
    date_debut = date(annee_precedente, 1, 1)
    date_fin = date(annee_precedente, 12, 31)

    logger.info(f"Cloture annuelle: {date_debut} → {date_fin}")

    tenants = Client.objects.exclude(schema_name='public')
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                _generer_cloture_agregee(
                    niveau='A',
                    niveau_source='M',
                    date_debut=date_debut,
                    date_fin=date_fin,
                )
        except Exception as e:
            logger.exception(
                f"Erreur cloture annuelle tenant {tenant.schema_name}: {e}"
            )


def _generer_cloture_agregee(niveau, niveau_source, date_debut, date_fin):
    """
    Agrege les clotures d'un niveau inferieur pour creer une cloture de niveau superieur, par PV.
    / Aggregates lower-level closures to create a higher-level closure, per POS.

    LOCALISATION : laboutik/tasks.py

    :param niveau: 'M' ou 'A' — le niveau de la cloture a creer
    :param niveau_source: 'J' ou 'M' — le niveau des clotures a agreger
    :param date_debut: date de debut (date, pas datetime)
    :param date_fin: date de fin (date, pas datetime)
    """
    import datetime as dt_module
    from django.db import transaction
    from django.db.models import Sum, Min, Max
    from django.utils import timezone as tz

    from BaseBillet.models import Configuration
    from laboutik.models import ClotureCaisse, PointDeVente, LaboutikConfiguration

    # Verifier que le module caisse est actif / Check module_caisse is active
    config_base = Configuration.get_solo()
    if not config_base.module_caisse:
        return

    # Convertir dates en datetime aware / Convert dates to aware datetimes
    dt_debut = tz.make_aware(dt_module.datetime.combine(date_debut, dt_module.time.min))
    dt_fin = tz.make_aware(dt_module.datetime.combine(date_fin, dt_module.time.max))

    # Pour chaque PV qui a des clotures source dans la periode
    # / For each POS with source closures in the period
    pvs_avec_clotures = ClotureCaisse.objects.filter(
        niveau=niveau_source,
        datetime_cloture__gte=dt_debut,
        datetime_cloture__lte=dt_fin,
    ).values_list('point_de_vente', flat=True).distinct()

    for pv_uuid in pvs_avec_clotures:
        point_de_vente = PointDeVente.objects.get(uuid=pv_uuid)

        clotures_source = ClotureCaisse.objects.filter(
            point_de_vente=point_de_vente,
            niveau=niveau_source,
            datetime_cloture__gte=dt_debut,
            datetime_cloture__lte=dt_fin,
        )

        if not clotures_source.exists():
            continue

        # Garde anti-doublon : si Celery Beat relance la tache (retry, restart),
        # ne pas creer de doublon pour la meme periode et le meme PV.
        # / Anti-duplicate guard: if Celery Beat retries, don't create duplicates.
        deja_existante = ClotureCaisse.objects.filter(
            point_de_vente=point_de_vente,
            niveau=niveau,
            datetime_cloture__gte=dt_debut,
            datetime_cloture__lte=dt_fin,
        ).exists()
        if deja_existante:
            logger.info(
                f"Cloture {niveau} deja existante pour PV={point_de_vente.name}, "
                f"periode {date_debut} → {date_fin} — skip"
            )
            continue

        aggregats = clotures_source.aggregate(
            total_especes=Sum('total_especes'),
            total_carte_bancaire=Sum('total_carte_bancaire'),
            total_cashless=Sum('total_cashless'),
            total_general=Sum('total_general'),
            nombre_transactions=Sum('nombre_transactions'),
            premiere_ouverture=Min('datetime_ouverture'),
            derniere_cloture=Max('datetime_cloture'),
        )

        with transaction.atomic():
            # Numero sequentiel global par niveau (pas par PV)
            # / Global sequential number per level (not per POS)
            dernier = ClotureCaisse.objects.select_for_update().filter(
                niveau=niveau,
            ).order_by('-numero_sequentiel').first()
            dernier_num = dernier.numero_sequentiel if dernier else 0

            config = LaboutikConfiguration.get_solo()

            ClotureCaisse.objects.create(
                point_de_vente=point_de_vente,
                responsable=None,
                datetime_ouverture=aggregats['premiere_ouverture'],
                datetime_cloture=aggregats['derniere_cloture'],
                niveau=niveau,
                numero_sequentiel=dernier_num + 1,
                total_especes=aggregats['total_especes'] or 0,
                total_carte_bancaire=aggregats['total_carte_bancaire'] or 0,
                total_cashless=aggregats['total_cashless'] or 0,
                total_general=aggregats['total_general'] or 0,
                nombre_transactions=aggregats['nombre_transactions'] or 0,
                rapport_json={
                    "type": f"cloture_{niveau}",
                    "periode": f"{date_debut} → {date_fin}",
                    "nb_clotures_source": clotures_source.count(),
                },
                hash_lignes='',
                total_perpetuel=config.total_perpetuel,
            )

        logger.info(
            f"Cloture {niveau} creee: PV={point_de_vente.name}, "
            f"seq={dernier_num + 1}, total={aggregats['total_general']}cts"
        )

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
            from laboutik.excel_export import generer_excel_cloture

            config = Configuration.get_solo()
            activate(config.language)

            # Charger la cloture / Load the closure
            cloture = ClotureCaisse.objects.select_related(
                'point_de_vente', 'responsable',
            ).get(uuid=cloture_uuid)

            # Generer PDF, CSV et Excel / Generate PDF, CSV and Excel
            pdf_bytes = generer_pdf_cloture(cloture)
            csv_string = generer_csv_cloture(cloture)
            excel_bytes = generer_excel_cloture(cloture)

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
            mail.attach(
                f"{nom_base}.xlsx", excel_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            mail.send(fail_silently=False)

            logger.info(
                f"Rapport cloture envoye: {cloture_uuid} → {destinataire}"
            )
            return True

    except Exception as e:
        logger.exception(f"Erreur envoi rapport cloture {cloture_uuid}: {e}")
        return False


@shared_task
def envoyer_rapports_clotures_recentes():
    """
    Envoie un seul email recapitulatif par tenant avec les rapports des
    clotures generees dans les 24 dernieres heures.
    Lancee toutes les heures par Celery Beat. Ne traite que les tenants
    dont l'heure locale est 7h (1h apres les clotures auto de 6h).
    Chaque cloture a ses 3 fichiers (PDF, CSV, Excel) en pieces jointes.
    Le corps du mail liste chaque cloture avec ses in/out et noms de fichiers.
    / Sends a single recap email per tenant with reports of closures
    generated in the last 24 hours.
    Runs every hour via Celery Beat. Only processes tenants
    where local time is 7am (1h after the 6am auto closures).
    Each closure has its 3 files (PDF, CSV, Excel) as attachments.
    The email body lists each closure with its in/out and filenames.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import timedelta
    from django.utils import timezone as dj_timezone
    from Customers.models import Client

    tenants = Client.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                config = Configuration.get_solo()
                if not config.module_caisse:
                    continue

                # Verifier l'heure locale du tenant (7h = 1h apres les clotures)
                # / Check tenant's local time (7am = 1h after closures)
                tz_tenant = config.get_tzinfo()
                heure_locale = dj_timezone.now().astimezone(tz_tenant).hour
                if heure_locale != 7:
                    continue

                # Destinataire / Recipient
                destinataire = config.email
                if not destinataire:
                    continue

                # Chercher les clotures des 24 dernieres heures
                # / Find closures from the last 24 hours
                from laboutik.models import ClotureCaisse
                from laboutik.pdf import generer_pdf_cloture
                from laboutik.csv_export import generer_csv_cloture
                from laboutik.excel_export import generer_excel_cloture

                activate(config.language)

                seuil = dj_timezone.now() - timedelta(hours=24)
                clotures = ClotureCaisse.objects.filter(
                    datetime_cloture__gte=seuil,
                ).select_related(
                    'point_de_vente',
                ).order_by('datetime_cloture')

                if not clotures.exists():
                    continue

                # Construire le corps HTML et les pieces jointes
                # / Build the HTML body and attachments
                pieces_jointes = []
                lignes_recap = []
                niveaux_labels = {
                    'J': _("Journalière"),
                    'H': _("Hebdomadaire"),
                    'M': _("Mensuelle"),
                    'A': _("Annuelle"),
                }

                for cloture in clotures:
                    date_str = cloture.datetime_cloture.strftime("%Y%m%d_%H%M")
                    niveau_label = niveaux_labels.get(cloture.niveau, cloture.niveau)
                    nom_base = f"cloture_{cloture.niveau}_{date_str}"

                    # Noms des fichiers / Filenames
                    nom_pdf = f"{nom_base}.pdf"
                    nom_csv = f"{nom_base}.csv"
                    nom_xlsx = f"{nom_base}.xlsx"

                    # Generer les 3 formats / Generate all 3 formats
                    pdf_bytes = generer_pdf_cloture(cloture)
                    csv_string = generer_csv_cloture(cloture)
                    excel_bytes = generer_excel_cloture(cloture)

                    pieces_jointes.append((nom_pdf, pdf_bytes, "application/pdf"))
                    pieces_jointes.append((nom_csv, csv_string.encode("utf-8"), "text/csv"))
                    pieces_jointes.append((
                        nom_xlsx, excel_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ))

                    # Reconstruire les in/out depuis le rapport_json
                    # / Rebuild in/out from rapport_json
                    rapport = cloture.rapport_json or {}
                    totaux = rapport.get("totaux_par_moyen", {})
                    solde = rapport.get("solde_caisse", {})

                    entrees_especes = totaux.get("especes", 0) / 100
                    entrees_cb = totaux.get("carte_bancaire", 0) / 100
                    entrees_cashless = totaux.get("cashless", 0) / 100
                    total_in = totaux.get("total", 0) / 100
                    sorties = solde.get("sorties_especes", 0) / 100

                    pv_name = cloture.point_de_vente.name if cloture.point_de_vente else "—"

                    lignes_recap.append({
                        "niveau_label": niveau_label,
                        "numero": cloture.numero_sequentiel,
                        "pv_name": pv_name,
                        "nb_transactions": cloture.nombre_transactions,
                        "entrees_especes": f"{entrees_especes:.2f}",
                        "entrees_cb": f"{entrees_cb:.2f}",
                        "entrees_cashless": f"{entrees_cashless:.2f}",
                        "total_in": f"{total_in:.2f}",
                        "sorties": f"{sorties:.2f}",
                        "nom_pdf": nom_pdf,
                        "nom_csv": nom_csv,
                        "nom_xlsx": nom_xlsx,
                    })

                # Construire le HTML du mail / Build the email HTML
                html_parts = [
                    '<!DOCTYPE html><html><head><meta charset="utf-8"></head>',
                    '<body style="font-family:sans-serif;font-size:14px;color:#333;max-width:700px;margin:0 auto;">',
                    f'<h2 style="color:#17a2b8;">{_("Rapports de clôture — récapitulatif quotidien")}</h2>',
                ]

                if config.organisation:
                    html_parts.append(f'<p><strong>{config.organisation}</strong></p>')

                html_parts.append(
                    f'<p>{_("Date")} : {dj_timezone.now().astimezone(tz_tenant).strftime("%d/%m/%Y")}</p>'
                )

                for ligne in lignes_recap:
                    html_parts.append(
                        f'<div style="margin:1em 0;padding:0.8em;border:1px solid #ddd;border-radius:6px;">'
                        f'<h3 style="margin:0 0 0.5em 0;color:#333;">'
                        f'{ligne["niveau_label"]} #{ligne["numero"]} — {ligne["pv_name"]}'
                        f'</h3>'
                        f'<table style="border-collapse:collapse;width:100%;">'
                        f'<tr style="background:#f8f9fa;">'
                        f'<td style="padding:4px 8px;border:1px solid #eee;"><strong>{_("Entrées")}</strong></td>'
                        f'<td style="padding:4px 8px;border:1px solid #eee;">'
                        f'{_("Espèces")} : {ligne["entrees_especes"]} € · '
                        f'{_("CB")} : {ligne["entrees_cb"]} € · '
                        f'{_("Cashless")} : {ligne["entrees_cashless"]} €'
                        f'</td></tr>'
                        f'<tr><td style="padding:4px 8px;border:1px solid #eee;"><strong>{_("Total IN")}</strong></td>'
                        f'<td style="padding:4px 8px;border:1px solid #eee;">{ligne["total_in"]} € '
                        f'({ligne["nb_transactions"]} {_("transactions")})</td></tr>'
                    )
                    if float(ligne["sorties"]) > 0:
                        html_parts.append(
                            f'<tr style="color:#c62828;">'
                            f'<td style="padding:4px 8px;border:1px solid #eee;"><strong>{_("Sorties espèces")}</strong></td>'
                            f'<td style="padding:4px 8px;border:1px solid #eee;">- {ligne["sorties"]} €</td></tr>'
                        )
                    html_parts.append(
                        f'<tr style="background:#f0f0f0;">'
                        f'<td style="padding:4px 8px;border:1px solid #eee;"><strong>{_("Fichiers joints")}</strong></td>'
                        f'<td style="padding:4px 8px;border:1px solid #eee;font-size:12px;">'
                        f'📄 {ligne["nom_pdf"]} · 📊 {ligne["nom_csv"]} · 📈 {ligne["nom_xlsx"]}'
                        f'</td></tr>'
                        f'</table></div>'
                    )

                html_parts.append(
                    f'<hr style="border:none;border-top:1px solid #ccc;margin:1em 0;">'
                    f'<p style="font-size:12px;color:#999;">{_("Généré par TiBillet")}</p>'
                    f'</body></html>'
                )
                html_body = '\n'.join(html_parts)

                # Texte brut de fallback / Plain text fallback
                text_body = _("Rapports de clôture — %(nb)s clôture(s) — %(date)s") % {
                    "nb": len(lignes_recap),
                    "date": dj_timezone.now().astimezone(tz_tenant).strftime("%d/%m/%Y"),
                }

                # Envoyer l'email / Send the email
                from_email = os.environ.get('DEFAULT_FROM_EMAIL', os.environ.get('EMAIL_HOST_USER'))
                sujet = _("Rapports de clôture — %(org)s — %(date)s") % {
                    "org": config.organisation or tenant.schema_name,
                    "date": dj_timezone.now().astimezone(tz_tenant).strftime("%d/%m/%Y"),
                }

                mail = EmailMultiAlternatives(
                    subject=sujet,
                    body=text_body,
                    from_email=from_email,
                    to=[destinataire],
                )
                mail.attach_alternative(html_body, "text/html")

                for nom_fichier, contenu, content_type in pieces_jointes:
                    mail.attach(nom_fichier, contenu, content_type)

                mail.send(fail_silently=False)

                logger.info(
                    f"[{tenant.schema_name}] Email recapitulatif envoye: "
                    f"{len(lignes_recap)} cloture(s) → {destinataire}"
                )

        except Exception as e:
            logger.exception(
                f"Erreur envoi rapports tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_journaliere_auto():
    """
    Cloture journaliere automatique.
    Lancee toutes les heures par Celery Beat. Ne traite que les tenants
    dont l'heure locale est 6h (entre 6:00 et 6:59).
    Si aucune vente depuis la derniere cloture J, la tache ne fait rien.
    / Automatic daily closure.
    Runs every hour via Celery Beat. Only processes tenants
    where local time is 6am (between 6:00 and 6:59).
    If no sales since the last J closure, the task does nothing.

    LOCALISATION : laboutik/tasks.py
    """
    from django.db import transaction
    from django.db.models import F
    from django.utils import timezone as dj_timezone
    from Customers.models import Client
    from BaseBillet.models import LigneArticle, SaleOrigin

    tenants = Client.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                from laboutik.models import (
                    ClotureCaisse, LaboutikConfiguration, PointDeVente,
                )
                from laboutik.reports import RapportComptableService

                # Verifier que le module caisse est actif / Check module_caisse is active
                config_base = Configuration.get_solo()
                if not config_base.module_caisse:
                    continue

                # Verifier l'heure locale du tenant (ne traiter que si 6h)
                # / Check tenant's local time (only process if 6am)
                tz_tenant = config_base.get_tzinfo()
                heure_locale = dj_timezone.now().astimezone(tz_tenant).hour
                if heure_locale != 6:
                    continue

                # Trouver la derniere cloture journaliere
                # / Find the last daily closure
                derniere_cloture = ClotureCaisse.objects.filter(
                    niveau=ClotureCaisse.JOURNALIERE,
                ).order_by('-datetime_cloture').first()

                # Trouver la premiere vente apres la derniere cloture
                # / Find the first sale after the last closure
                filtre_ventes = {
                    'sale_origin': SaleOrigin.LABOUTIK,
                    'status': LigneArticle.VALID,
                }
                if derniere_cloture:
                    filtre_ventes['datetime__gt'] = derniere_cloture.datetime_cloture

                premiere_vente = LigneArticle.objects.filter(
                    **filtre_ventes,
                ).order_by('datetime').first()

                if not premiere_vente:
                    # Aucune vente depuis la derniere cloture — rien a faire
                    # / No sales since last closure — nothing to do
                    continue

                datetime_ouverture = premiere_vente.datetime
                datetime_cloture = dj_timezone.now()

                # Calculer le rapport complet via le service
                # / Compute the full report via the service
                service = RapportComptableService(None, datetime_ouverture, datetime_cloture)
                rapport = service.generer_rapport_complet()
                totaux = rapport['totaux_par_moyen']
                hash_lignes = service.calculer_hash_lignes()
                nb_transactions = service.lignes.count()

                if nb_transactions == 0:
                    continue

                # Creer la cloture dans un bloc atomique
                # / Create the closure in an atomic block
                with transaction.atomic():
                    dernier_seq = ClotureCaisse.objects.select_for_update().filter(
                        niveau=ClotureCaisse.JOURNALIERE,
                    ).order_by('-numero_sequentiel').first()
                    numero_sequentiel = (dernier_seq.numero_sequentiel + 1) if dernier_seq else 1

                    config = LaboutikConfiguration.get_solo()
                    LaboutikConfiguration.objects.filter(pk=config.pk).update(
                        total_perpetuel=F('total_perpetuel') + totaux['total']
                    )
                    config.refresh_from_db()

                    # Le PV est informatif — on prend le premier PV actif
                    # / POS is informational — take the first active POS
                    pv = PointDeVente.objects.filter(hidden=False).first()

                    ClotureCaisse.objects.create(
                        point_de_vente=pv,
                        responsable=None,
                        datetime_ouverture=datetime_ouverture,
                        datetime_cloture=datetime_cloture,
                        niveau=ClotureCaisse.JOURNALIERE,
                        numero_sequentiel=numero_sequentiel,
                        total_especes=totaux['especes'],
                        total_carte_bancaire=totaux['carte_bancaire'],
                        total_cashless=totaux['cashless'],
                        total_general=totaux['total'],
                        nombre_transactions=nb_transactions,
                        rapport_json=rapport,
                        hash_lignes=hash_lignes,
                        total_perpetuel=config.total_perpetuel,
                    )

                logger.info(
                    f"[{tenant.schema_name}] Cloture J auto: "
                    f"seq={numero_sequentiel}, total={totaux['total']}cts, "
                    f"tx={nb_transactions}"
                )

        except Exception as e:
            logger.exception(
                f"Erreur cloture J auto tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_hebdomadaire():
    """
    Cloture hebdomadaire automatique, lancee tous les lundis.
    Agrege les clotures J de la semaine precedente (lundi a dimanche).
    Ne traite que les tenants dont l'heure locale est 6h.
    / Automatic weekly closure, runs every Monday.
    Aggregates J closures from the previous week (Monday to Sunday).
    Only processes tenants where local time is 6am.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import timedelta
    from django.utils import timezone as dj_timezone
    from Customers.models import Client

    tenants = Client.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                config_base = Configuration.get_solo()
                if not config_base.module_caisse:
                    continue

                # Verifier l'heure locale du tenant / Check tenant's local time
                tz_tenant = config_base.get_tzinfo()
                heure_locale = dj_timezone.now().astimezone(tz_tenant).hour
                if heure_locale != 6:
                    continue

                # Semaine precedente : lundi a dimanche
                # / Previous week: Monday to Sunday
                aujourd_hui = dj_timezone.now().astimezone(tz_tenant).date()
                lundi_cette_semaine = aujourd_hui - timedelta(days=aujourd_hui.weekday())
                lundi_semaine_derniere = lundi_cette_semaine - timedelta(weeks=1)
                dimanche_semaine_derniere = lundi_cette_semaine - timedelta(days=1)

                _generer_cloture_agregee(
                    niveau='H',
                    niveau_source='J',
                    date_debut=lundi_semaine_derniere,
                    date_fin=dimanche_semaine_derniere,
                )

        except Exception as e:
            logger.exception(
                f"Erreur cloture H tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_mensuelle():
    """
    Cloture mensuelle automatique. Lancee le 1er de chaque mois, toutes les heures.
    Ne traite que les tenants dont l'heure locale est 6h.
    Agrege les clotures J du mois precedent.
    / Automatic monthly closure. Runs on the 1st of each month, every hour.
    Only processes tenants where local time is 6am.
    Aggregates J closures from the previous month.

    LOCALISATION : laboutik/tasks.py
    """
    from dateutil.relativedelta import relativedelta
    from django.utils import timezone as dj_timezone
    from Customers.models import Client

    tenants = Client.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                config_base = Configuration.get_solo()
                if not config_base.module_caisse:
                    continue

                # Verifier l'heure locale du tenant / Check tenant's local time
                tz_tenant = config_base.get_tzinfo()
                heure_locale = dj_timezone.now().astimezone(tz_tenant).hour
                if heure_locale != 6:
                    continue

                # Mois precedent / Previous month
                aujourd_hui = dj_timezone.now().astimezone(tz_tenant).date()
                premier_jour_mois_courant = aujourd_hui.replace(day=1)
                premier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(months=1)
                dernier_jour_mois_precedent = premier_jour_mois_courant - relativedelta(days=1)

                _generer_cloture_agregee(
                    niveau='M',
                    niveau_source='J',
                    date_debut=premier_jour_mois_precedent,
                    date_fin=dernier_jour_mois_precedent,
                )

        except Exception as e:
            logger.exception(
                f"Erreur cloture M tenant {tenant.schema_name}: {e}"
            )


@shared_task
def generer_cloture_annuelle():
    """
    Cloture annuelle automatique. Lancee le 1er janvier, toutes les heures.
    Ne traite que les tenants dont l'heure locale est 6h.
    Agrege les clotures M de l'annee precedente.
    / Automatic annual closure. Runs on January 1st, every hour.
    Only processes tenants where local time is 6am.
    Aggregates M closures from the previous year.

    LOCALISATION : laboutik/tasks.py
    """
    from datetime import date
    from django.utils import timezone as dj_timezone
    from Customers.models import Client

    tenants = Client.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                config_base = Configuration.get_solo()
                if not config_base.module_caisse:
                    continue

                # Verifier l'heure locale du tenant / Check tenant's local time
                tz_tenant = config_base.get_tzinfo()
                heure_locale = dj_timezone.now().astimezone(tz_tenant).hour
                if heure_locale != 6:
                    continue

                # Annee precedente / Previous year
                annee_precedente = dj_timezone.now().astimezone(tz_tenant).date().year - 1
                date_debut = date(annee_precedente, 1, 1)
                date_fin = date(annee_precedente, 12, 31)

                _generer_cloture_agregee(
                    niveau='A',
                    niveau_source='M',
                    date_debut=date_debut,
                    date_fin=date_fin,
                )

        except Exception as e:
            logger.exception(
                f"Erreur cloture A tenant {tenant.schema_name}: {e}"
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

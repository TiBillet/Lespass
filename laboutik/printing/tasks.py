"""
Taches Celery pour l'impression asynchrone.
Fire-and-forget avec retry exponentiel.
/ Celery tasks for asynchronous printing.
Fire-and-forget with exponential retry.

LOCALISATION : laboutik/printing/tasks.py

FLUX :
1. La vue Django appelle imprimer_async.delay(printer_pk, ticket_data, schema_name)
2. Celery execute la tache dans un worker
3. schema_context() isole les requetes dans le bon tenant
4. imprimer() dispatch vers le bon backend (Cloud, LAN, Inner)
5. En cas d'echec recoverable (imprimante injoignable), retry exponentiel
6. En cas d'erreur permanente (imprimante supprimee), abandon sans retry

DEPENDENCIES :
- laboutik.printing.imprimer (dispatch vers le backend)
- laboutik.printing.formatters (formatter_ticket_commande)
- laboutik.models (Printer, CommandeSauvegarde)
"""
import logging

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=10)
def imprimer_async(self, printer_pk, ticket_data, schema_name):
    """
    Imprime un ticket de maniere asynchrone via Celery.
    Cree un ImpressionLog pour la tracabilite (LNE exigence 9).
    Retry exponentiel en cas d'echec recoverable (imprimante injoignable).
    Abandon immediat si l'imprimante n'existe plus en DB (erreur permanente).
    / Prints a ticket asynchronously via Celery.
    Creates an ImpressionLog for tracking (LNE requirement 9).
    Exponential retry on recoverable failure (printer unreachable).
    Immediate abort if printer no longer exists in DB (permanent error).

    LOCALISATION : laboutik/printing/tasks.py

    :param printer_pk: UUID (str) de l'imprimante
    :param ticket_data: dict avec header, articles, total, qrcode, footer + impression_meta optionnel
    :param schema_name: nom du schema tenant (pour schema_context)
    """
    try:
        with schema_context(schema_name):
            from laboutik.models import Printer, ImpressionLog
            from laboutik.printing import imprimer

            # Erreur permanente : l'imprimante n'existe plus → pas de retry
            # / Permanent error: printer no longer exists → no retry
            try:
                printer = Printer.objects.get(pk=printer_pk)
            except (ObjectDoesNotExist, ValueError):
                logger.error(
                    f"[PRINT TASK] Imprimante {printer_pk} introuvable — "
                    f"abandon (pas de retry)"
                )
                return

            # --- Tracabilite : creer ImpressionLog (LNE exigence 9) ---
            # Le dict ticket_data peut contenir une cle "impression_meta"
            # avec les infos necessaires a la tracabilite.
            # / Tracking: create ImpressionLog (LNE requirement 9)
            # ticket_data may contain an "impression_meta" key
            # with information needed for tracking.
            impression_meta = ticket_data.pop("impression_meta", None)
            if impression_meta:
                uuid_transaction = impression_meta.get("uuid_transaction")
                cloture_uuid = impression_meta.get("cloture_uuid")
                type_justificatif = impression_meta.get("type_justificatif", "VENTE")
                operateur_pk_str = impression_meta.get("operateur_pk")
                format_emission = impression_meta.get("format_emission", "P")

                # Detecter duplicata : une impression precedente existe-t-elle ?
                # Sans uuid_transaction ni cloture_uuid, impossible de determiner
                # le duplicata — on considere que c'est un original.
                # / Detect duplicate: does a previous print exist?
                # Without uuid_transaction or cloture_uuid, we can't determine
                # duplicate status — treat as original.
                est_duplicata = False
                if uuid_transaction:
                    nb_precedentes = ImpressionLog.objects.filter(
                        uuid_transaction=uuid_transaction,
                        type_justificatif=type_justificatif,
                    ).count()
                    est_duplicata = nb_precedentes > 0
                elif cloture_uuid:
                    nb_precedentes = ImpressionLog.objects.filter(
                        cloture__uuid=cloture_uuid,
                        type_justificatif=type_justificatif,
                    ).count()
                    est_duplicata = nb_precedentes > 0

                # Injecter is_duplicata dans ticket_data pour le builder ESC/POS
                # / Inject is_duplicata into ticket_data for the ESC/POS builder
                ticket_data["is_duplicata"] = est_duplicata

                # Operateur (peut etre None si tache Celery sans user)
                # / Operator (may be None if Celery task without user)
                operateur = None
                if operateur_pk_str:
                    from AuthBillet.models import TibilletUser
                    try:
                        operateur = TibilletUser.objects.get(pk=operateur_pk_str)
                    except TibilletUser.DoesNotExist:
                        pass

                # Cloture (pour les tickets Z)
                # / Closure (for Z-tickets)
                cloture_obj = None
                if cloture_uuid:
                    from laboutik.models import ClotureCaisse
                    try:
                        cloture_obj = ClotureCaisse.objects.get(uuid=cloture_uuid)
                    except ClotureCaisse.DoesNotExist:
                        pass

                ImpressionLog.objects.create(
                    uuid_transaction=uuid_transaction,
                    cloture=cloture_obj,
                    operateur=operateur,
                    printer=printer,
                    type_justificatif=type_justificatif,
                    is_duplicata=est_duplicata,
                    format_emission=format_emission,
                )

                logger.info(
                    f"[PRINT TASK] ImpressionLog cree — "
                    f"type={type_justificatif} duplicata={est_duplicata}"
                )

            result = imprimer(printer, ticket_data)

            if not result["ok"]:
                error_message = result.get("error", "Erreur inconnue")
                logger.warning(
                    f"[PRINT TASK] Echec impression — "
                    f"printer={printer.name} erreur={error_message} "
                    f"retry={self.request.retries}/{self.max_retries}"
                )
                # Erreur recoverable → retry exponentiel
                # / Recoverable error → exponential retry
                delai_retry = min(5 * (2 ** self.request.retries), 300)
                raise self.retry(
                    exc=Exception(error_message),
                    countdown=delai_retry,
                )

            logger.info(
                f"[PRINT TASK] OK — printer={printer.name}"
            )

    except self.MaxRetriesExceededError:
        logger.error(
            f"[PRINT TASK] Abandon apres {self.max_retries} retries — "
            f"printer_pk={printer_pk}"
        )


@shared_task(bind=True, max_retries=10)
def imprimer_commande(self, commande_pk, schema_name):
    """
    Imprime une commande restaurant en la splitant par imprimante de categorie.
    Chaque categorie de produit peut avoir une imprimante differente
    (ex: cuisine, bar, patisserie).
    Abandon immediat si la commande n'existe plus en DB.
    / Prints a restaurant order by splitting it per category printer.
    Each product category can have a different printer
    (e.g. kitchen, bar, pastry).
    Immediate abort if order no longer exists in DB.

    LOCALISATION : laboutik/printing/tasks.py

    :param commande_pk: UUID (str) de la CommandeSauvegarde
    :param schema_name: nom du schema tenant (pour schema_context)
    """
    try:
        with schema_context(schema_name):
            from laboutik.models import CommandeSauvegarde
            from laboutik.printing import imprimer
            from laboutik.printing.formatters import formatter_ticket_commande

            # Erreur permanente : la commande n'existe plus → pas de retry
            # / Permanent error: order no longer exists → no retry
            try:
                commande = CommandeSauvegarde.objects.get(pk=commande_pk)
            except (ObjectDoesNotExist, ValueError):
                logger.error(
                    f"[PRINT COMMANDE] Commande {commande_pk} introuvable — "
                    f"abandon (pas de retry)"
                )
                return

            articles = commande.articles.select_related(
                'product__categorie_pos',
            ).all()

            # Grouper les articles par imprimante de categorie.
            # Si la categorie n'a pas d'imprimante, l'article est ignore.
            # Ce comportement est voulu : les articles sans imprimante
            # ne generent pas de ticket (ex: boissons sur un PV sans imprimante bar).
            # / Group articles by category printer.
            # If the category has no printer, the article is skipped.
            # This is intentional: articles without a printer
            # don't generate a ticket.
            articles_par_imprimante = {}
            for article in articles:
                categorie = article.product.categorie_pos if article.product else None
                if not categorie:
                    continue

                printer = categorie.printer
                if not printer or not printer.active:
                    continue

                printer_pk_str = str(printer.pk)
                if printer_pk_str not in articles_par_imprimante:
                    articles_par_imprimante[printer_pk_str] = {
                        "printer": printer,
                        "articles": [],
                    }
                articles_par_imprimante[printer_pk_str]["articles"].append(article)

            # Imprimer un ticket par imprimante.
            # Si une imprimante echoue, on continue avec les autres
            # (on ne bloque pas la cuisine parce que le bar est en panne).
            # / Print one ticket per printer.
            # If one printer fails, continue with the others.
            for printer_pk_str, groupe in articles_par_imprimante.items():
                printer = groupe["printer"]
                articles_groupe = groupe["articles"]

                ticket_data = formatter_ticket_commande(
                    commande, articles_groupe, printer
                )
                result = imprimer(printer, ticket_data)

                if not result["ok"]:
                    logger.warning(
                        f"[PRINT COMMANDE] Echec — "
                        f"printer={printer.name} "
                        f"erreur={result.get('error', '')}"
                    )

            logger.info(
                f"[PRINT COMMANDE] OK — commande={commande.uuid} "
                f"imprimantes={len(articles_par_imprimante)}"
            )

    except self.MaxRetriesExceededError:
        logger.error(
            f"[PRINT COMMANDE] Abandon apres {self.max_retries} retries — "
            f"commande_pk={commande_pk}"
        )

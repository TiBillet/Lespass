"""
Taches Celery + helpers de calcul pour la generation de clotures.
/ Celery tasks + calculation helpers for closure generation.

LOCALISATION : comptabilite/tasks.py

S2 livre :
- generer_cloture_pour_tenant (shared_task) : genere 1 cloture pour 1 tenant
- helpers : _bornes_pour_niveau, _prochain_numero_sequentiel, _calculer_total_perpetuel

S5 ajoutera les wrappers @app.task dans TiBillet/celery.py + add_periodic_task
pour les declenchements J/H/M/A automatiques.
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

logger = logging.getLogger(__name__)


def _bornes_pour_niveau(niveau, datetime_debut_iso=None, datetime_fin_iso=None):
    """
    Calcule (datetime_debut, datetime_fin) pour le niveau J/H/M/A.
    Override possible via les parametres ISO (datetime_debut_iso, datetime_fin_iso).
    / Computes (start, end) for J/H/M/A. Optional override via ISO strings.

    J : [hier 00:00 local, aujourd'hui 00:00 local)
    H : [lundi semaine derniere 00:00, lundi semaine courante 00:00)
    M : [1er du mois precedent 00:00, 1er du mois courant 00:00)
    A : [1er janvier annee precedente 00:00, 1er janvier courante 00:00)
    """
    if datetime_debut_iso and datetime_fin_iso:
        return (
            datetime.fromisoformat(datetime_debut_iso),
            datetime.fromisoformat(datetime_fin_iso),
        )

    now_local = timezone.localtime()
    today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    if niveau == "J":
        return (today_midnight - timedelta(days=1), today_midnight)

    if niveau == "H":
        lundi_courant = today_midnight - timedelta(days=today_midnight.weekday())
        return (lundi_courant - timedelta(days=7), lundi_courant)

    if niveau == "M":
        premier_courant = today_midnight.replace(day=1)
        if premier_courant.month == 1:
            premier_precedent = premier_courant.replace(
                year=premier_courant.year - 1, month=12,
            )
        else:
            premier_precedent = premier_courant.replace(
                month=premier_courant.month - 1,
            )
        return (premier_precedent, premier_courant)

    if niveau == "A":
        premier_janvier_courant = today_midnight.replace(month=1, day=1)
        premier_janvier_precedent = premier_janvier_courant.replace(
            year=premier_janvier_courant.year - 1,
        )
        return (premier_janvier_precedent, premier_janvier_courant)

    raise ValueError(f"Niveau inconnu : {niveau}")


def _prochain_numero_sequentiel():
    """
    Lit le dernier numero sequentiel du tenant courant + 1, avec verrou.
    A appeler DANS transaction.atomic() — sinon select_for_update echoue.
    / Reads last sequential number + 1 with lock. Call inside transaction.atomic().
    """
    from comptabilite.models import ClotureCaisse
    derniere = (
        ClotureCaisse.objects
        .select_for_update()
        .order_by("-numero_sequentiel")
        .first()
    )
    return (derniere.numero_sequentiel + 1) if derniere else 1


def _calculer_total_perpetuel(niveau, total_general):
    """
    Total cumule depuis la creation du tenant (clotures journalieres uniquement).
    Pour J : derniere_journaliere.total_perpetuel + total_general.
    Pour H/M/A : derniere_journaliere.total_perpetuel (pas d'addition).
    / Cumulative total since tenant creation (daily closures only).
    """
    from comptabilite.models import ClotureCaisse
    derniere_journaliere = (
        ClotureCaisse.objects
        .filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        .order_by("-datetime_fin")
        .first()
    )
    base = derniere_journaliere.total_perpetuel if derniere_journaliere else 0
    if niveau == ClotureCaisse.NIVEAU_JOURNALIER:
        return base + total_general
    return base


@shared_task
def generer_cloture_pour_tenant(
    schema_name,
    niveau,
    datetime_debut_iso=None,
    datetime_fin_iso=None,
):
    """
    Genere 1 cloture pour 1 tenant donne. Idempotent : si la cloture
    existe deja pour (niveau, debut, fin), retourne son UUID sans recreer.
    / Generate 1 closure for 1 tenant. Idempotent.

    Retourne l'UUID (str) de la cloture creee ou existante, None si modules
    inactifs (module_billetterie ET module_adhesion desactives).
    / Returns UUID string of created/existing closure, or None if both modules off.
    """
    from Customers.models import Client
    tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        from comptabilite.services import RapportComptableService
        from BaseBillet.models import Configuration

        config = Configuration.get_solo()
        if not (config.module_billetterie or config.module_adhesion):
            logger.info(
                f"[{schema_name}] Modules billetterie/adhesion desactives, skip."
            )
            return None

        datetime_debut, datetime_fin = _bornes_pour_niveau(
            niveau, datetime_debut_iso, datetime_fin_iso,
        )

        # Idempotence : si cloture existante pour cette periode + niveau → retour direct
        existante = ClotureCaisse.objects.filter(
            niveau=niveau,
            datetime_debut=datetime_debut,
            datetime_fin=datetime_fin,
        ).first()
        if existante:
            logger.info(
                f"[{schema_name}] Cloture {niveau} {datetime_debut} deja existante "
                f"(#{existante.numero_sequentiel}), skip."
            )
            return str(existante.uuid)

        # Calcul du rapport (hors transaction pour eviter de tenir le verrou trop longtemps)
        service = RapportComptableService(datetime_debut, datetime_fin)
        rapport = service.generer_rapport_complet()
        hash_lignes = service.calculer_hash_lignes()
        total_general = rapport["totaux_par_moyen"]["total"]
        nombre_transactions = service.queryset.count()

        # Total HT / TVA depuis la section tva du rapport
        total_ht = sum(t["total_ht"] for t in rapport["tva"].values())
        total_tva = sum(t["total_tva"] for t in rapport["tva"].values())

        with transaction.atomic():
            numero = _prochain_numero_sequentiel()
            perpetuel = _calculer_total_perpetuel(niveau, total_general)
            cloture = ClotureCaisse.objects.create(
                niveau=niveau,
                numero_sequentiel=numero,
                datetime_debut=datetime_debut,
                datetime_fin=datetime_fin,
                total_general=total_general,
                total_ht=total_ht,
                total_tva=total_tva,
                nombre_transactions=nombre_transactions,
                total_perpetuel=perpetuel,
                hash_lignes=hash_lignes,
                rapport_json=rapport,
            )

        logger.info(
            f"[{schema_name}] Cloture {niveau} #{numero} creee "
            f"(total={total_general}c, {nombre_transactions} txns)."
        )
        return str(cloture.uuid)

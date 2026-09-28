"""
Signaux Django pour le module tireuse connectee (controlvanne).
/ Django signals for the connected tap module (controlvanne).

LOCALISATION : controlvanne/signals.py

Ce fichier est charge dans controlvanne/apps.py via ready().
/ This file is loaded in controlvanne/apps.py via ready().

DEPENDANCES :
- controlvanne.TireuseBec : modele tireuse physique
- controlvanne.RfidSession : session NFC en cours
- inventaire.models.Stock : stock du produit (centilitres)
- controlvanne.groupes_ws : groupes WebSocket par lieu et envoi (pousser_aux_kiosks)
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext

from .groupes_ws import pousser_aux_kiosks, uuid_du_lieu_courant
from .models import TireuseBec

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helper : rechargement des écrans kiosk
# / Helper: kiosk screens reload
# ──────────────────────────────────────────────────────────────────────


def demander_rechargement_des_kiosks(tireuse):
    """
    Demande aux écrans kiosk de cette tireuse de recharger leur page.
    / Asks this tap's kiosk screens to reload their page.

    LOCALISATION : controlvanne/signals.py

    POURQUOI : la fiche de la bière (nom, description, étiquette, tags, prix,
    couleur d'accent) est rendue UNE FOIS par le serveur (kiosk_detail.html).
    Les messages WebSocket ne mettent à jour que l'état (carte posée, volume,
    solde). Quand le fût change, il faut donc recharger la page entière.
    / The beer sheet is server-rendered once; WS messages only update the
    state. When the keg changes, the whole page must be reloaded.

    Le message {"kiosk_reload": true} est lu par ecran_tireuse.js.
    Il part à la fin de la transaction (on_commit) : l'admin enregistre le fût,
    ses tags et ses tarifs dans la même transaction, et la page rechargée doit
    voir la version finale.
    / Sent on commit so the reloaded page sees the final keg, tags and prices.

    :param tireuse: TireuseBec
    """
    payload = {
        "tireuse_bec_uuid": str(tireuse.uuid),
        "kiosk_reload": True,
    }
    # Le lieu est fixé maintenant, au moment de l'événement (groupes par lieu)
    # / The venue is fixed now, when the event happens (per-venue groups)
    uuid_du_lieu = uuid_du_lieu_courant()

    def envoyer_apres_commit():
        # Écran de cette tireuse + liste des tireuses du lieu
        # / This tap's screen + the venue's tap list
        pousser_aux_kiosks(tireuse.uuid, payload, uuid_du_lieu)

    transaction.on_commit(envoyer_apres_commit)


# ──────────────────────────────────────────────────────────────────────
# Helper : snapshot WebSocket
# ──────────────────────────────────────────────────────────────────────


def _snapshot_for_bec(tb):
    """Construit le payload WebSocket pour une tireuse.
    / Builds the WebSocket payload for a tap."""
    if not tb.enabled:
        return {
            "tireuse_bec": tb.nom_tireuse,
            "tireuse_bec_uuid": str(tb.uuid),
            "maintenance": True,
            "present": False,
            "authorized": False,
            "vanne_ouverte": False,
            "message": gettext("En maintenance"),
        }

    from .models import RfidSession

    # Session NFC ouverte la plus recente (ended_at=null = carte posee)
    # / Most recent open NFC session (ended_at=null = card present)
    open_session = (
        RfidSession.objects.filter(tireuse_bec=tb, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )

    return {
        "tireuse_bec": tb.nom_tireuse,
        "tireuse_bec_uuid": str(tb.uuid),
        "liquid_label": tb.liquid_label,
        "present": bool(open_session and open_session.uid),
        "authorized": bool(open_session.authorized) if open_session else False,
        "vanne_ouverte": False,
        "volume_ml": float(open_session.volume_end_ml if open_session else 0.0),
        "debit_cl_min": 0.0,
        "reservoir_ml": float(tb.reservoir_ml),
        "reservoir_max_ml": tb.reservoir_max_ml,
        "prix_litre": str(tb.prix_litre),
        "message": "",
        "uid": open_session.uid if open_session else None,
    }


# ──────────────────────────────────────────────────────────────────────
# Signal 1 : pre_save — init reservoir_ml quand fut_actif change
# ──────────────────────────────────────────────────────────────────────


@receiver(pre_save, sender=TireuseBec)
def tireusebec_pre_save(sender, instance, **kwargs):
    """Memorise l'etat precedent pour detecter le changement de fut.
    Si le fut change, initialise reservoir_ml depuis le Stock inventaire.
    / Memorize previous state to detect keg change.
    If keg changes, init reservoir_ml from inventory Stock."""

    # Valeur par defaut : pas de changement detecte
    # / Default: no change detected
    instance._old_fut_id = None

    # Nouvel objet non encore persiste : rien a comparer
    # / New unsaved object: nothing to compare
    if not instance.pk:
        return

    try:
        old = TireuseBec.objects.get(pk=instance.pk)
        instance._old_fut_id = old.fut_actif_id
    except TireuseBec.DoesNotExist:
        return

    # Si le fut actif change, initialiser reservoir_ml depuis le Stock inventaire
    # / If the active keg changes, init reservoir_ml from the inventory Stock
    if (
        instance.fut_actif_id != instance._old_fut_id
        and instance.fut_actif_id is not None
    ):
        try:
            from inventaire.models import Stock

            stock = Stock.objects.filter(product_id=instance.fut_actif_id).first()
            if stock and stock.quantite > 0:
                # Stock en centilitres → ml (×10)
                # / Stock in centiliters → ml (×10)
                instance.reservoir_ml = Decimal(str(stock.quantite)) * 10
            else:
                # Fût neuf SANS Stock inventaire : remettre le réservoir à 0
                # plutôt que de garder la valeur de l'ancien fût (jauge fausse,
                # « fût vide » prématuré). Pas d'info = pas de réserve connue ;
                # l'opérateur crée un Stock ou passe en réservoir illimité.
                # (fix review 2026-07-06, finding I2)
                # / Fresh keg WITHOUT inventory Stock: reset the reservoir to 0
                # rather than keeping the old keg's value (wrong gauge). No
                # info = no known reserve; the operator creates a Stock or
                # switches to unlimited reservoir.
                instance.reservoir_ml = Decimal("0")
        except Exception:
            # On ne bloque pas l'enregistrement de la tireuse, mais on garde une trace
            # / Do not block the tap save, but keep a trace
            logger.warning(
                f"Réservoir non initialisé pour la tireuse {instance.pk} (fût changé)",
                exc_info=True,
            )


# ──────────────────────────────────────────────────────────────────────
# Signal 2 : post_save — push WebSocket apres modification
# ──────────────────────────────────────────────────────────────────────


@receiver(post_save, sender=TireuseBec)
def tireusebec_post_save(sender, instance, created, **kwargs):
    """Push WebSocket apres modification d'une tireuse.
    A la creation, genere automatiquement un PointDeVente de type TIREUSE.
    / Push WebSocket after tap modification.
    On creation, auto-generates a PointDeVente of type TIREUSE.

    TENANT-SAFE : ce signal est déclenché par un save() en contexte HTTP
    (tenant déjà résolu par TenantMainMiddleware). Le payload est construit
    en synchrone par _snapshot_for_bec() AVANT l'envoi async.
    Le consumer state_update() ne fait aucune requête DB — il transmet le JSON.
    / TENANT-SAFE: this signal is triggered by a save() in HTTP context
    (tenant already resolved by TenantMainMiddleware). The payload is built
    synchronously by _snapshot_for_bec() BEFORE the async send.
    The consumer state_update() does no DB queries — it forwards the JSON.
    """

    # A la creation d'une tireuse, on lui fabrique automatiquement :
    # 1. son point de vente (type TIREUSE, meme nom) ;
    # 2. son Terminal — le Raspberry Pi qui la pilotera — et le code PIN qui permettra
    #    d'appairer ce Pi.
    #
    # Le gestionnaire n'a donc qu'un objet a creer : la tireuse. Le reste suit.
    # / On tap creation, auto-create its point of sale, its Terminal (the Raspberry Pi that
    # will drive it) and the PIN to pair that Pi.
    if created:
        champs_a_mettre_a_jour = {}

        # --- Le point de vente ---
        # nom_tireuse est unique (contrainte DB), donc le nom du POS l'est aussi.
        # / nom_tireuse is unique (DB constraint), so the POS name is too.
        if instance.point_de_vente is None:
            from laboutik.models import PointDeVente

            point_de_vente_cree = PointDeVente.objects.create(
                name=instance.nom_tireuse,
                comportement=PointDeVente.TIREUSE,
            )
            champs_a_mettre_a_jour["point_de_vente"] = point_de_vente_cree
            instance.point_de_vente = point_de_vente_cree

        # --- Le Terminal (le Raspberry Pi) et son code PIN ---
        #
        # LA TIREUSE ET SON PI SONT DEUX CHOSES DIFFERENTES, et c'est voulu.
        # La tireuse est l'objet METIER : elle porte le fut, le debitmetre, le prix, et tout
        # l'historique des services. Le Terminal est le MATERIEL : il est jetable. Quand un
        # Pi grille, on en appaire un autre sur le meme terminal — la tireuse, elle, garde
        # sa configuration et son historique.
        #
        # Le role TI est INDISPENSABLE : c'est lui qui decide que le claim delivrera une
        # TireuseAPIKey. Avec une cle de caisse, le Pi ne pourrait pas piloter la vanne.
        # / The tap is the BUSINESS object (keg, price, history). The Terminal is the
        # HARDWARE, and it is disposable. Role TI decides which API key class is issued.
        if instance.terminal is None:
            from AuthBillet.models import TibilletUser
            from discovery.services import fabriquer_le_code_pin_d_appairage
            from laboutik.models import Terminal

            terminal_cree = Terminal.objects.create(
                name=instance.nom_tireuse,
                terminal_role=TibilletUser.ROLE_TIREUSE,
            )
            fabriquer_le_code_pin_d_appairage(terminal_cree)

            champs_a_mettre_a_jour["terminal"] = terminal_cree
            instance.terminal = terminal_cree

        # On lie les objets a la tireuse sans re-declencher le signal post_save.
        # update() ne passe pas par save(), donc pas de recursion.
        # / Link objects to tap without re-triggering post_save signal.
        if champs_a_mettre_a_jour:
            TireuseBec.objects.filter(pk=instance.pk).update(**champs_a_mettre_a_jour)

    # Le fût branché a changé (admin, liste modifiable ou fiche de la tireuse) :
    # la fiche bière affichée est périmée, les kiosks rechargent leur page.
    # Le rechargement redonne aussi l'état à jour : pas besoin du snapshot.
    # _old_fut_id est posé par tireusebec_pre_save.
    # / The keg on tap changed: kiosks reload (fresh state too, no snapshot needed).
    ancien_fut_id = getattr(instance, "_old_fut_id", None)
    le_fut_a_change = (not created) and ancien_fut_id != instance.fut_actif_id
    if le_fut_a_change:
        demander_rechargement_des_kiosks(instance)
        return

    # Push differe a la fin de la transaction en cours : le save() du
    # reservoir se fait desormais DANS l'atomic de facturation (fix C1) —
    # pousser immediatement enverrait un etat pas encore committe (et un
    # faux etat en cas de rollback). Hors transaction, on_commit s'execute
    # immediatement : comportement inchange. Piege projet documente
    # (broadcast dans atomic → on_commit).
    # / Push deferred to the end of the current transaction: the reservoir
    # save() now happens INSIDE the billing atomic (C1 fix) — pushing
    # immediately would send a not-yet-committed state (and a wrong state
    # on rollback). Outside a transaction, on_commit runs immediately:
    # unchanged behavior. Documented project trap (broadcast inside atomic).
    # Le lieu est fixé maintenant, au moment de l'événement (groupes par lieu)
    # / The venue is fixed now, when the event happens (per-venue groups)
    uuid_du_lieu = uuid_du_lieu_courant()

    def pousser_snapshot_apres_commit():
        payload = _snapshot_for_bec(instance)
        # Écran de cette tireuse + liste des tireuses du lieu
        # / This tap's screen + the venue's tap list
        pousser_aux_kiosks(instance.uuid, payload, uuid_du_lieu)

    transaction.on_commit(pousser_snapshot_apres_commit)


# ──────────────────────────────────────────────────────────────────────
# Signal 3 : post_save du fût — recharger les kiosks qui l'affichent
# / Signal 3: keg post_save — reload the kiosks showing it
# ──────────────────────────────────────────────────────────────────────


def recharger_les_kiosks_du_fut(sender, instance, created, **kwargs):
    """
    Un fût modifié (nom, couleur, description, étiquette, tags, tarifs) :
    les kiosks des tireuses qui le servent rechargent leur page.
    / A modified keg: kiosks of the taps serving it reload their page.

    LOCALISATION : controlvanne/signals.py

    Branché sur Product ET FutProduct : l'admin des fûts enregistre un
    FutProduct (modèle proxy), et Django envoie alors le signal avec
    sender=FutProduct, pas Product.
    Les produits qui ne sont pas des fûts sont ignorés tout de suite, sans
    requête (le signal Product se déclenche pour tous les produits).
    / Connected to Product AND FutProduct (proxy: sender is FutProduct).
    Non-keg products are skipped without any query.
    """
    from BaseBillet.models import Product

    if created or instance.categorie_article != Product.FUT:
        return

    tireuses_qui_servent_ce_fut = TireuseBec.objects.filter(fut_actif_id=instance.pk)
    for tireuse in tireuses_qui_servent_ce_fut:
        demander_rechargement_des_kiosks(tireuse)


def brancher_les_signaux_du_fut():
    """
    Branche recharger_les_kiosks_du_fut sur Product et FutProduct.
    Appelée à l'import de ce module (chargé par apps.py ready()).
    / Connects recharger_les_kiosks_du_fut to Product and FutProduct.
    """
    from BaseBillet.models import FutProduct, Product

    post_save.connect(
        recharger_les_kiosks_du_fut,
        sender=Product,
        dispatch_uid="controlvanne_recharger_kiosks_product",
    )
    post_save.connect(
        recharger_les_kiosks_du_fut,
        sender=FutProduct,
        dispatch_uid="controlvanne_recharger_kiosks_futproduct",
    )


brancher_les_signaux_du_fut()

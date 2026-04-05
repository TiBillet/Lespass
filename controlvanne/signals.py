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
- channels.layers.get_channel_layer : WebSocket
- asgiref.sync.async_to_sync : bridge sync/async
"""

from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import TireuseBec


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
            "message": "En Maintenance",
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
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# Signal 2 : post_save — push WebSocket apres modification
# ──────────────────────────────────────────────────────────────────────


@receiver(post_save, sender=TireuseBec)
def tireusebec_post_save(sender, instance, created, **kwargs):
    """Push WebSocket apres modification d'une tireuse.
    / Push WebSocket after tap modification."""

    payload = _snapshot_for_bec(instance)

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    # Canal specifique a cette tireuse (kiosk individuel)
    # / Channel specific to this tap (individual kiosk)
    async_to_sync(channel_layer.group_send)(
        f"rfid_state.{instance.uuid}",
        {"type": "state_update", "payload": payload},
    )

    # Canal global (tous les kiosks)
    # / Global channel (all kiosks)
    async_to_sync(channel_layer.group_send)(
        "rfid_state.all",
        {"type": "state_update", "payload": payload},
    )

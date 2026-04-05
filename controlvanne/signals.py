#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models import F
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Fut, HistoriqueFut, TireuseBec, RfidSession


def _safe(name: str) -> str:
    return (name or "").strip().lower()[:80] or "all"


def snapshot_for_bec(tb: TireuseBec):
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
    open_s = (
        RfidSession.objects.filter(tireuse_bec=tb, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    return {
        "tireuse_bec": tb.nom_tireuse,
        "tireuse_bec_uuid": str(tb.uuid),
        "liquid_label": tb.liquid_label,
        "present": bool(open_s and open_s.uid),
        "authorized": bool(open_s.authorized) if open_s else False,
        "vanne_ouverte": False,
        "volume_ml": float(open_s.volume_end_ml if open_s else 0.0),
        "debit_cl_min": 0.0,
        "reservoir_ml": float(tb.reservoir_ml),
        "reservoir_max_ml": tb.reservoir_max_ml,
        "prix_litre": str(tb.prix_litre),
        "monnaie": tb.monnaie,
        "message": "",
        "uid": open_s.uid if open_s else None,
    }


@receiver(pre_save, sender=TireuseBec)
def _tireusebec_pre_save(sender, instance: TireuseBec, **kwargs):
    """Mémorise l'état précédent et applique les changements de fût avant la sauvegarde."""
    instance._old_name = None
    instance._old_fut_id = None
    instance._old_reservoir_ml = Decimal("0.00")

    if not instance.pk:
        return
    try:
        old = TireuseBec.objects.get(pk=instance.pk)
        instance._old_name = old.nom_tireuse
        instance._old_fut_id = old.fut_actif_id
        instance._old_reservoir_ml = old.reservoir_ml
    except TireuseBec.DoesNotExist:
        return

    # Si le fût actif change, mettre à jour reservoir_ml sur l'instance
    if instance.fut_actif_id != instance._old_fut_id and instance.fut_actif_id is not None:
        try:
            fut = Fut.objects.get(pk=instance.fut_actif_id)
            instance.reservoir_ml = fut.volume_fut_l * 1000
        except Fut.DoesNotExist:
            pass


@receiver(post_save, sender=TireuseBec)
def on_tireusebec_changed(sender, instance: TireuseBec, created, **kwargs):
    old_fut_id = getattr(instance, "_old_fut_id", None)

    # --- Gestion historique fûts ---
    if instance.fut_actif_id != old_fut_id:
        # Fermer l'entrée d'historique précédente
        if old_fut_id is not None:
            old_reservoir = getattr(instance, "_old_reservoir_ml", Decimal("0.00"))
            HistoriqueFut.objects.filter(
                tireuse_bec=instance, retire_le__isnull=True
            ).update(retire_le=timezone.now(), volume_final_ml=old_reservoir)

        # Créer nouvelle entrée et décrémenter stock
        if instance.fut_actif:
            HistoriqueFut.objects.create(
                tireuse_bec=instance,
                fut=instance.fut_actif,
                volume_initial_ml=instance.reservoir_ml,
            )
            Fut.objects.filter(
                pk=instance.fut_actif_id, quantite_stock__gt=0
            ).update(quantite_stock=F("quantite_stock") - 1)

    # --- Push WebSocket ---
    payload = snapshot_for_bec(instance)
    ch = get_channel_layer()

    async_to_sync(ch.group_send)(
        f"rfid_state.{instance.uuid}", {"type": "state_update", "payload": payload}
    )
    async_to_sync(ch.group_send)(
        "rfid_state.all", {"type": "state_update", "payload": payload}
    )

    # Si renommage : notifier les écrans abonnés à l'ancien nom
    old_name = getattr(instance, "_old_name", None)
    if old_name and old_name != instance.nom_tireuse:
        async_to_sync(ch.group_send)(
            f"rfid_state.{instance.uuid}",
            {"type": "state_update", "payload": {"redirect_to": instance.nom_tireuse}},
        )

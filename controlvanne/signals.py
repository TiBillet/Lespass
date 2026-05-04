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

    # A la creation d'une tireuse, on cree automatiquement :
    # 1. Un PointDeVente de type TIREUSE avec le meme nom
    # 2. Un PairingDevice avec un PIN 6 chiffres pour l'appairage du Pi
    # Ca evite a l'admin de devoir creer ces objets manuellement.
    # / On tap creation, auto-create:
    # 1. A TIREUSE-type PointDeVente with the same name
    # 2. A PairingDevice with a 6-digit PIN for Pi pairing
    if created:
        from django.db import connection

        champs_a_mettre_a_jour = {}

        # --- Auto-creation du PointDeVente ---
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

        # --- Auto-creation du PairingDevice avec PIN ---
        # On verifie que connection.tenant est un vrai Client (pas un FakeTenant).
        # En contexte de test (schema_context), Django met un FakeTenant
        # qui n'est pas une instance de Client — le PairingDevice FK crasherait.
        # / Check connection.tenant is a real Client (not FakeTenant from tests).
        if instance.pairing_device is None:
            from Customers.models import Client

            tenant_courant = connection.tenant
            tenant_est_un_vrai_client = isinstance(tenant_courant, Client)

            if tenant_est_un_vrai_client:
                from discovery.models import PairingDevice

                pin_genere = PairingDevice.generate_unique_pin()
                pairing_device_cree = PairingDevice.objects.create(
                    name=instance.nom_tireuse,
                    tenant=tenant_courant,
                    pin_code=pin_genere,
                )
                champs_a_mettre_a_jour["pairing_device"] = pairing_device_cree
                instance.pairing_device = pairing_device_cree

        # On lie les objets a la tireuse sans re-declencher le signal post_save.
        # update() ne passe pas par save(), donc pas de recursion.
        # / Link objects to tap without re-triggering post_save signal.
        if champs_a_mettre_a_jour:
            TireuseBec.objects.filter(pk=instance.pk).update(**champs_a_mettre_a_jour)

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

"""
Helper pour envoyer du HTML aux caisses connectees via WebSocket
/ Helper to send HTML to connected POS terminals via WebSocket

LOCALISATION : wsocket/broadcast.py

Deux fonctions :
1. broadcast_html() — generique, envoie un template rendu a un group
2. broadcast_jauge_event() — specifique, recalcule et broadcast la jauge d'un event

Le message_type correspond a la methode du consumer qui recevra le message.
Par exemple "jauge_update" appelle LaboutikConsumer.jauge_update().
Le point "." dans le type est converti en "_" par Channels.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def broadcast_html(group_name, template_name, context, message_type="notification"):
    """
    Rend un template HTML et l'envoie a toutes les caisses du group.
    / Renders an HTML template and sends it to all POS terminals in the group.

    :param group_name: Nom du group Redis (ex: "laboutik-pv-{uuid}")
    :param template_name: Chemin du template Django
    :param context: Dictionnaire de contexte pour le template
    :param message_type: Type de message (correspond a la methode du consumer)
    """
    # Rendre le template en HTML cote serveur
    # / Render the template to HTML server-side
    html_rendu = render_to_string(template_name, context)

    # Envoyer au group Redis (toutes les caisses connectees)
    # / Send to Redis group (all connected POS terminals)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": message_type,
            "html": html_rendu,
        },
    )


def broadcast_jauge_event(event):
    """
    Recalcule et broadcast la jauge d'un event a toutes les caisses du tenant.
    / Recalculates and broadcasts an event's gauge to all POS terminals in the tenant.

    LOCALISATION : wsocket/broadcast.py

    Appele via transaction.on_commit() depuis le signal post_save Ticket.
    Envoie a toutes les caisses du tenant (group laboutik-jauges-{schema}).
    Les PV qui n'affichent pas cet event ignorent le OOB swap (pas d'ID cible).

    Chaque tuile billet a sa propre jauge :
    - Si Price.stock est defini → jauge par tarif (tickets vendus pour cette Price)
    - Sinon → jauge globale de l'event (Event.jauge_max)

    FLUX :
    1. Recalcule la jauge globale de l'event (pour la sidebar)
    2. Pour chaque Price publiee EUR de l'event, recalcule la jauge par tuile
    3. Rend le template hx_jauge_billet.html (N blocs OOB tuiles + 1 sidebar)
    4. Envoie via broadcast_html() au group tenant-scoped

    :param event: Instance Event (rechargee depuis la DB)
    """
    from django.db import connection
    from BaseBillet.models import Price, Ticket

    # --- Jauge globale de l'event (pour la sidebar) ---
    # / Global event gauge (for the sidebar)
    places_vendues_event = event.valid_tickets_count()
    jauge_max_event = event.jauge_max or 0
    pourcentage_event = (
        int(round(places_vendues_event / jauge_max_event * 100))
        if jauge_max_event
        else 0
    )
    est_complet_event = event.complet()

    event_data = {
        "uuid": str(event.uuid),
        "jauge_max": jauge_max_event,
        "places_vendues": places_vendues_event,
        "pourcentage": pourcentage_event,
        "complet": est_complet_event,
    }

    # --- Jauge par tuile (1 tuile = 1 Price) ---
    # Reproduit la logique de _construire_donnees_articles() lignes 393-418
    # / Per-tile gauge (1 tile = 1 Price)
    # Replicates the logic from _construire_donnees_articles() lines 393-418
    # Event.products est un M2M vers Product
    # On cherche les Prices EUR publiees de ces Products
    # / Event.products is a M2M to Product
    # We look for published EUR Prices of those Products
    produits_de_levent = event.products.all()
    prix_euros = Price.objects.filter(
        product__in=produits_de_levent,
        publish=True,
        asset__isnull=True,
    ).select_related("product")

    tuiles = []
    for price in prix_euros:
        if price.stock is not None and price.stock > 0:
            # Jauge par tarif — compter les tickets vendus pour cette Price
            # / Per-rate gauge — count tickets sold for this Price
            places_vendues_tuile = Ticket.objects.filter(
                reservation__event__pk=event.pk,
                pricesold__price__pk=price.pk,
                status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
            ).count()
            jauge_max_tuile = price.stock
            est_complet_tuile = places_vendues_tuile >= price.stock
        else:
            # Jauge globale de l'event
            # / Global event gauge
            places_vendues_tuile = places_vendues_event
            jauge_max_tuile = jauge_max_event
            est_complet_tuile = est_complet_event

        pourcentage_tuile = (
            int(round(places_vendues_tuile / jauge_max_tuile * 100))
            if jauge_max_tuile
            else 0
        )

        tuiles.append(
            {
                # ID composite event__price — meme format que article.id dans la tuile
                # / Composite event__price ID — same format as article.id in the tile
                "id": f"{event.uuid}__{price.uuid}",
                "jauge_max": jauge_max_tuile,
                "places_vendues": places_vendues_tuile,
                "pourcentage": pourcentage_tuile,
                "complet": est_complet_tuile,
            }
        )

    # Group tenant-scoped : toutes les caisses du tenant recoivent le broadcast
    # / Tenant-scoped group: all POS terminals in the tenant receive the broadcast
    group_name = f"laboutik-jauges-{connection.schema_name}"

    logger.info(
        f"[WS] Broadcast jauge event {event.name} "
        f"({places_vendues_event}/{jauge_max_event}, {len(tuiles)} tuiles) "
        f"→ {group_name}"
    )

    broadcast_html(
        group_name=group_name,
        template_name="laboutik/partial/hx_jauge_billet.html",
        context={"event": event_data, "tuiles": tuiles},
        message_type="jauge_update",
    )


def broadcast_stock_update(produits_stock_data):
    """
    Broadcast la mise à jour des badges stock à toutes les caisses du tenant.
    / Broadcasts stock badge updates to all POS terminals in the tenant.

    LOCALISATION : wsocket/broadcast.py

    Appelé via transaction.on_commit() depuis _creer_lignes_articles()
    après chaque décrémentation de stock.

    Le group laboutik-jauges-{schema} est déjà rejoint par tous les consumers
    (voir LaboutikConsumer.connect()).

    :param produits_stock_data: liste de dicts avec les données stock mises à jour.
        Chaque dict : {product_uuid, quantite, unite, en_alerte, en_rupture, bloquant, quantite_lisible}
    """
    from django.db import connection

    if not produits_stock_data:
        return

    group_name = f"laboutik-jauges-{connection.schema_name}"

    logger.info(
        f"[WS] Broadcast stock update : {len(produits_stock_data)} produit(s) "
        f"→ {group_name}"
    )

    broadcast_html(
        group_name=group_name,
        template_name="laboutik/partial/hx_stock_badge.html",
        context={"produits_stock": produits_stock_data},
        message_type="stock_update",
    )

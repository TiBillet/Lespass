"""
Backend d'impression Sunmi Inner (WebSocket vers la tablette Sunmi).
Envoie des commandes JSON au PrinterConsumer via le channel layer Redis.
L'app Android sur la tablette Sunmi interprete les commandes et imprime.
/ Sunmi Inner printing backend (WebSocket to Sunmi tablet).
Sends JSON commands to PrinterConsumer via the Redis channel layer.
The Android app on the Sunmi tablet interprets commands and prints.

LOCALISATION : laboutik/printing/sunmi_inner.py

FLUX :
1. can_print() verifie que l'imprimante est active
2. print_ticket() convertit le ticket_data en liste de commandes JSON
3. Envoie les commandes au group Redis `printer-{printer.uuid}`
4. Le PrinterConsumer (wsocket/consumers.py) recoit et transmet au navigateur/app

DEPENDENCIES :
- Django Channels (channel layer Redis)
- PrinterConsumer dans wsocket/consumers.py
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection
from django.utils import timezone

from laboutik.printing.base import PrinterBackend, nom_du_groupe_websocket

logger = logging.getLogger(__name__)


def ticket_data_to_json_commands(ticket_data):
    """
    Convertit un dict ticket_data en liste de commandes JSON
    pour l'app Sunmi Inner.
    / Converts a ticket_data dict to a list of JSON commands
    for the Sunmi Inner app.

    LOCALISATION : laboutik/printing/sunmi_inner.py

    :param ticket_data: dict avec header, articles, total, qrcode, footer
    :return: list de dicts (commandes JSON)
    """
    commands = []

    # Unite des montants : "EUR" (defaut), ou le nom de la monnaie d'un ticket en
    # points ou en temps. « EUR » reste colle au nombre (« 5.00EUR ») ; un nom de
    # monnaie en est separe (« 300.00 Points fidélité »).
    # / Amount unit: "EUR" (default) or a points/time currency name.
    unite_du_ticket = ticket_data.get("unite", "EUR")
    suffixe_de_l_unite = unite_du_ticket if unite_du_ticket == "EUR" else f" {unite_du_ticket}"

    # --- En-tete ---
    # / Header
    header = ticket_data.get("header", {})
    title = header.get("title", "")
    subtitle = header.get("subtitle", "")
    date_text = header.get("date", "")

    if title:
        commands.append({
            "type": "text",
            "value": title,
            "bold": True,
            "size": 2,
            "align": "center",
        })
    if subtitle:
        commands.append({
            "type": "text",
            "value": subtitle,
            "align": "center",
        })
    if date_text:
        commands.append({
            "type": "text",
            "value": date_text,
            "align": "center",
        })
    if title or subtitle or date_text:
        commands.append({
            "type": "text",
            "value": "--------------------------------",
            "align": "left",
        })

    # --- Articles ---
    # / Articles
    articles = ticket_data.get("articles", [])
    for article in articles:
        article_name = article.get("name", "")

        # Ligne de texte seul (titre de partie, ligne sans argent d'un reçu) : le nom
        # seul, sans quantité ni prix. Même règle que escpos_builder.
        # / Text-only line: the name only. Same rule as escpos_builder.
        if article.get("texte_seul"):
            commands.append({
                "type": "text",
                "value": article_name,
                "align": "left",
            })
            continue

        article_qty = article.get("qty", 1)
        article_price = article.get("price", 0)
        article_total = article.get("total", 0)

        # Meme logique que escpos_builder : price > 0 = format vente, sinon cuisine
        # / Same logic as escpos_builder: price > 0 = sale format, otherwise kitchen
        article_a_un_prix = (article_price is not None and article_price > 0)

        if article_a_un_prix:
            total_euros = f"{article_total / 100:.2f}"
            line = f"{article_name} x{article_qty}  {total_euros}{suffixe_de_l_unite}"
        else:
            line = f"{article_qty} x {article_name}"

        commands.append({
            "type": "text",
            "value": line,
            "align": "left",
        })

    if articles:
        commands.append({
            "type": "text",
            "value": "--------------------------------",
            "align": "left",
        })

    # --- Total ---
    # / Total
    total_data = ticket_data.get("total", {})
    total_amount = total_data.get("amount", 0)
    total_label = total_data.get("label", "")

    if total_amount:
        total_euros = f"{total_amount / 100:.2f}"
        commands.append({
            "type": "text",
            "value": f"TOTAL: {total_euros} {unite_du_ticket}",
            "bold": True,
            "align": "left",
        })

    if total_label:
        commands.append({
            "type": "text",
            "value": total_label,
            "align": "left",
        })

    # --- Detail des moyens de paiement ---
    # Meme regle que escpos_builder : seulement si au moins deux moyens ont servi.
    # / Same rule as escpos_builder: only when two methods or more were used.
    cascade_detail = ticket_data.get("cascade_detail", [])
    if len(cascade_detail) >= 2:
        for moyen in cascade_detail:
            montant_euros = f"{moyen.get('total', 0) / 100:.2f}"
            commands.append({
                "type": "text",
                "value": f"{moyen.get('name', '')}  {montant_euros}{suffixe_de_l_unite}",
                "align": "left",
            })

    # --- QR code ---
    qrcode_text = ticket_data.get("qrcode")
    if qrcode_text:
        commands.append({
            "type": "qrcode",
            "value": qrcode_text,
            "size": 5,
        })

    # --- Pied de page ---
    # / Footer
    footer_lines = ticket_data.get("footer", [])
    for footer_line in footer_lines:
        commands.append({
            "type": "text",
            "value": footer_line,
            "align": "center",
        })

    # --- Coupe papier ---
    # / Paper cut
    commands.append({"type": "cut"})

    return commands


class SunmiInnerBackend(PrinterBackend):
    """
    Backend pour les imprimantes Sunmi integrees dans la tablette (type SI).
    Envoie des commandes JSON via le channel layer Redis au PrinterConsumer.
    / Backend for printers built into the Sunmi tablet (type SI).
    Sends JSON commands via the Redis channel layer to PrinterConsumer.

    LOCALISATION : laboutik/printing/sunmi_inner.py
    """

    def can_print(self, printer):
        """
        L'imprimante Inner est toujours joignable si elle est active.
        La tablette Sunmi heberge a la fois le navigateur et l'imprimante.
        / The Inner printer is always reachable if active.
        The Sunmi tablet hosts both the browser and the printer.
        """
        if not printer.active:
            return (False, "Imprimante desactivee.")
        return (True, None)

    def print_ticket(self, printer, ticket_data):
        """
        Convertit le ticket_data en commandes JSON et les envoie
        au PrinterConsumer via le channel layer Redis.
        / Converts ticket_data to JSON commands and sends them
        to PrinterConsumer via the Redis channel layer.
        """
        # Convertir le ticket_data en commandes JSON
        # / Convert ticket_data to JSON commands
        commands = ticket_data_to_json_commands(ticket_data)

        # Envoyer les commandes au canal Redis de l'imprimante.
        #
        # Le canal porte le nom du lieu (le schema du tenant). Redis est partage par tous
        # les lieux : sans ce cloisonnement, un abonne d'un autre lieu recevrait ce ticket.
        # La tache Celery qui nous appelle tourne dans un schema_context, donc
        # connection.schema_name est bien celui du lieu qui imprime.
        # / Send commands to the printer's Redis channel. The channel carries the venue name
        # (tenant schema): Redis is shared across venues.
        group_name = nom_du_groupe_websocket(connection.schema_name, printer.uuid)
        channel_layer = get_channel_layer()

        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "print.ticket",
                    "commands": commands,
                },
            )
            logger.info(
                f"[PRINT] Inner OK — printer={printer.name} "
                f"group={group_name} commands={len(commands)}"
            )
            return {"ok": True}
        except Exception as exc:
            error_message = f"Erreur channel layer : {exc}"
            logger.error(f"[PRINT] Inner erreur — {error_message}")
            return {"ok": False, "error": error_message}

    def print_test(self, printer):
        """
        Envoie un ticket de test via WebSocket.
        / Sends a test ticket via WebSocket.
        """
        now = timezone.now()
        ticket_data = {
            "header": {
                "title": "TEST IMPRESSION INNER",
                "subtitle": printer.name,
                "date": now.strftime("%d/%m/%Y %H:%M"),
            },
            "articles": [],
            "total": {},
            "qrcode": None,
            "footer": ["Impression de test OK"],
        }
        return self.print_ticket(printer, ticket_data)

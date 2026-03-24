"""
Construit des donnees ESC/POS a partir d'un dict ticket_data.
Utilise la bibliotheque SunmiCloudPrinter pour generer les octets binaires.
Factorise entre les backends Cloud et LAN (memes commandes ESC/POS, transport different).
/ Builds ESC/POS data from a ticket_data dict.
Uses the SunmiCloudPrinter library to generate binary bytes.
Shared between Cloud and LAN backends (same ESC/POS commands, different transport).

LOCALISATION : laboutik/printing/escpos_builder.py

FLUX :
1. Recoit un dict ticket_data (header, articles, total, qrcode, footer)
2. Cree un SunmiCloudPrinter (utilise comme builder ESC/POS pur, pas d'envoi)
3. Active UTF-8 (obligatoire pour accents francais et symbole €)
4. Construit le ticket section par section
5. Retourne les octets ESC/POS bruts (bytes)
"""
import logging

from laboutik.printing.sunmi_cloud_printer import (
    SunmiCloudPrinter,
    ALIGN_LEFT,
    ALIGN_CENTER,
)

logger = logging.getLogger(__name__)


def build_escpos_from_ticket_data(dots_per_line, ticket_data):
    """
    Construit les donnees ESC/POS a partir d'un dict ticket_data.
    Retourne les octets binaires prets a etre envoyes a l'imprimante.
    / Builds ESC/POS data from a ticket_data dict.
    Returns raw binary bytes ready to send to the printer.

    LOCALISATION : laboutik/printing/escpos_builder.py

    Le SunmiCloudPrinter est utilise ici comme un builder ESC/POS pur.
    Il n'envoie rien — on recupere juste les octets via .orderData.
    L'envoi est gere par le backend (Cloud, LAN, Inner).
    / SunmiCloudPrinter is used here as a pure ESC/POS builder.
    It doesn't send anything — we just get the bytes via .orderData.
    Sending is handled by the backend (Cloud, LAN, Inner).

    :param dots_per_line: Nombre de dots par ligne (576, 384, 240)
    :param ticket_data: dict avec header, articles, total, qrcode, footer
    :return: bytes ESC/POS
    """
    # On passe des valeurs bidon pour app_id/app_key/sn car on n'utilise
    # pas httpPost — on veut juste le builder ESC/POS.
    # / We pass dummy values for app_id/app_key/sn because we don't use
    # httpPost — we just want the ESC/POS builder.
    builder = SunmiCloudPrinter(
        dots_per_line=dots_per_line,
        app_id="builder_only",
        app_key="builder_only",
        printer_sn="builder_only",
    )

    # Activer UTF-8 — obligatoire pour les accents francais et le symbole €.
    # Sans ca, "Bière" s'imprime comme "Bi?re".
    # / Enable UTF-8 — mandatory for French accents and € symbol.
    builder.setUtf8Mode(1)
    builder.restoreDefaultSettings()

    # --- En-tete du ticket ---
    # / Ticket header
    header = ticket_data.get("header", {})
    title = header.get("title", "")
    subtitle = header.get("subtitle", "")
    date_text = header.get("date", "")

    if title:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=False)
        builder.appendText(title + "\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)

    if subtitle:
        builder.setAlignment(ALIGN_CENTER)
        builder.appendText(subtitle + "\n")

    if date_text:
        builder.setAlignment(ALIGN_CENTER)
        builder.appendText(date_text + "\n")

    if title or subtitle or date_text:
        builder.appendText("--------------------------------\n")

    # --- Articles ---
    # / Articles
    articles = ticket_data.get("articles", [])
    if articles:
        builder.setAlignment(ALIGN_LEFT)
        for article in articles:
            article_name = article.get("name", "")
            article_qty = article.get("qty", 1)
            article_price = article.get("price", 0)
            article_total = article.get("total", 0)

            # Distinguer ticket vente (avec prix) et ticket commande cuisine (sans prix).
            # Un article offert a un prix unitaire (price > 0) mais total = 0.
            # Un article cuisine a price = 0 et total = 0.
            # On utilise "price" pour decider si on affiche le format vente ou cuisine.
            # / Distinguish sale ticket (with price) from kitchen order (no price).
            # A free article has a unit price (price > 0) but total = 0.
            # A kitchen article has price = 0 and total = 0.
            # We use "price" to decide between sale and kitchen format.
            article_a_un_prix = (article_price is not None and article_price > 0)

            if article_a_un_prix:
                total_euros = f"{article_total / 100:.2f}"
                line = f"{article_name} x{article_qty}  {total_euros}EUR\n"
            else:
                # Ticket commande cuisine : juste qty x nom, pas de prix
                # / Kitchen order ticket: just qty x name, no price
                line = f"{article_qty} x {article_name}\n"

            builder.appendText(line)

        builder.appendText("--------------------------------\n")

    # --- Total ---
    # / Total
    total_data = ticket_data.get("total", {})
    total_amount = total_data.get("amount", 0)
    total_label = total_data.get("label", "")

    # Afficher le total meme si 0 (retour de consigne, articles offerts).
    # Ne pas afficher si "amount" est absent du dict total (ticket cuisine sans total).
    # / Display total even if 0 (deposit return, free articles).
    # Don't display if "amount" is missing from total dict (kitchen ticket without total).
    total_est_present = "amount" in total_data and total_amount is not None
    if total_est_present:
        builder.setAlignment(ALIGN_LEFT)
        builder.setPrintModes(bold=True, double_h=False, double_w=False)
        total_euros = f"{total_amount / 100:.2f}"
        builder.appendText(f"TOTAL: {total_euros} EUR\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)

    if total_label:
        builder.appendText(f"{total_label}\n")

    # --- QR code ---
    # QR code agrandi (module_size=8, ec_level=2) pour les billets.
    # Plus gros = plus facile a scanner au portail d'entree.
    # / Enlarged QR code (module_size=8, ec_level=2) for tickets.
    # Bigger = easier to scan at the entry gate.
    qrcode_text = ticket_data.get("qrcode")
    if qrcode_text:
        builder.lineFeed(1)
        builder.setAlignment(ALIGN_CENTER)
        builder.appendQRcode(module_size=8, ec_level=2, text=qrcode_text)
        builder.lineFeed(1)

    # --- Pied de page ---
    # / Footer
    footer_lines = ticket_data.get("footer", [])
    if footer_lines:
        builder.setAlignment(ALIGN_CENTER)
        for footer_line in footer_lines:
            builder.appendText(footer_line + "\n")

    # --- Avance papier et coupe ---
    # / Paper feed and cut
    builder.lineFeed(3)
    builder.cutPaper(full_cut=False)

    return builder.orderData

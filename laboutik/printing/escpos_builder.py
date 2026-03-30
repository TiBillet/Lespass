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
    Supporte les mentions legales, ventilation TVA et mention DUPLICATA (LNE exigences 3 et 9).
    / Builds ESC/POS data from a ticket_data dict.
    Returns raw binary bytes ready to send to the printer.
    Supports legal mentions, VAT breakdown and DUPLICATE marking (LNE requirements 3 and 9).

    LOCALISATION : laboutik/printing/escpos_builder.py

    :param dots_per_line: Nombre de dots par ligne (576, 384, 240)
    :param ticket_data: dict avec header, articles, total, qrcode, footer + legal, tva_breakdown, is_duplicata
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

    # --- Mentions legales (raison sociale, SIRET, TVA) ---
    # / Legal mentions (business name, SIRET, VAT)
    legal = ticket_data.get("legal")
    if legal:
        builder.setAlignment(ALIGN_CENTER)
        business_name = legal.get("business_name", "")
        if business_name:
            builder.setPrintModes(bold=True, double_h=False, double_w=False)
            builder.appendText(business_name + "\n")
            builder.setPrintModes(bold=False, double_h=False, double_w=False)

        address = legal.get("address", "")
        if address:
            builder.appendText(address + "\n")

        siret = legal.get("siret", "")
        if siret:
            builder.appendText(f"SIRET: {siret}\n")

        tva_number = legal.get("tva_number", "")
        if tva_number:
            builder.appendText(f"TVA: {tva_number}\n")

        receipt_number = legal.get("receipt_number", "")
        if receipt_number:
            builder.appendText(f"Ticket: {receipt_number}\n")

    if title or subtitle or date_text or legal:
        builder.appendText("--------------------------------\n")

    # --- Mention DUPLICATA (en haut, bien visible) ---
    # / DUPLICATE mention (at the top, clearly visible)
    is_duplicata = ticket_data.get("is_duplicata", False)
    if is_duplicata:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=True)
        builder.appendText("*** DUPLICATA ***\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)
        builder.appendText("--------------------------------\n")

    # --- Mention SIMULATION (mode ecole, LNE exigence 5) ---
    # / SIMULATION label (training mode, LNE req. 5)
    is_simulation = ticket_data.get("is_simulation", False)
    if is_simulation:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=True)
        builder.appendText("*** SIMULATION ***\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)
        builder.appendText("\n")

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
            # / Distinguish sale ticket (with price) from kitchen order (no price).
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
    # / Display total even if 0 (deposit return, free articles).
    total_est_present = "amount" in total_data and total_amount is not None
    if total_est_present:
        builder.setAlignment(ALIGN_LEFT)
        builder.setPrintModes(bold=True, double_h=False, double_w=False)
        total_euros = f"{total_amount / 100:.2f}"
        builder.appendText(f"TOTAL: {total_euros} EUR\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)

    if total_label:
        builder.appendText(f"{total_label}\n")

    # --- Ventilation TVA par taux ---
    # / VAT breakdown by rate
    tva_breakdown = ticket_data.get("tva_breakdown", [])
    if tva_breakdown:
        builder.appendText("--------------------------------\n")
        builder.setAlignment(ALIGN_LEFT)

        # En-tete du tableau TVA
        # / VAT table header
        builder.appendText("TVA%     HT       TVA      TTC\n")

        for tva_ligne in tva_breakdown:
            taux = tva_ligne.get("rate", "0.00")
            ht = tva_ligne.get("ht", 0)
            tva_montant = tva_ligne.get("tva", 0)
            ttc = tva_ligne.get("ttc", 0)

            ht_euros = f"{ht / 100:.2f}"
            tva_euros = f"{tva_montant / 100:.2f}"
            ttc_euros = f"{ttc / 100:.2f}"

            builder.appendText(
                f"{taux:>5}% {ht_euros:>7} {tva_euros:>7} {ttc_euros:>7}\n"
            )

        # Totaux HT et TVA globaux
        # / Global HT and VAT totals
        total_ht = ticket_data.get("total_ht", 0)
        total_tva = ticket_data.get("total_tva", 0)

        if total_ht or total_tva:
            builder.appendText("--------------------------------\n")
            builder.appendText(f"Total HT:  {total_ht / 100:.2f} EUR\n")
            builder.appendText(f"Total TVA: {total_tva / 100:.2f} EUR\n")

    # --- QR code ---
    # QR code agrandi (module_size=8, ec_level=2) pour les billets.
    # / Enlarged QR code (module_size=8, ec_level=2) for tickets.
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

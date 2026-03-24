"""
Formatters de tickets d'impression.
Transforment des objets Django en dicts ticket_data independants du backend.
/ Ticket formatting functions.
Transform Django objects into ticket_data dicts independent of the backend.

LOCALISATION : laboutik/printing/formatters.py

Chaque formatter retourne un dict avec la structure suivante :
{
    "header": {"title": str, "subtitle": str, "date": str},
    "articles": [{"name": str, "qty": int, "price": int, "total": int}],
    "total": {"amount": int, "label": str},
    "qrcode": str or None,
    "footer": [str, ...],
}

Les montants sont en centimes (int). Le builder ESC/POS les convertit en euros.
"""
from django.utils import timezone
from django.utils.translation import gettext as _


def formatter_ticket_vente(lignes_articles, pv, operateur, moyen_paiement):
    """
    Formate un ticket de vente client (apres paiement).
    / Formats a customer sale ticket (after payment).

    LOCALISATION : laboutik/printing/formatters.py

    :param lignes_articles: QuerySet ou list de LigneArticle
    :param pv: PointDeVente
    :param operateur: TibilletUser (caissier)
    :param moyen_paiement: str (ex: "Especes", "CB", "NFC")
    :return: dict ticket_data
    """
    now = timezone.localtime(timezone.now())

    # Construire la liste des articles
    # / Build the articles list
    articles = []
    total_centimes = 0
    for ligne in lignes_articles:
        # LigneArticle.amount est en centimes, qty est un Decimal
        # / LigneArticle.amount is in cents, qty is a Decimal
        qty = int(ligne.qty)
        amount_centimes = ligne.amount
        article_total = amount_centimes * qty
        total_centimes += article_total

        # Nom du produit via PriceSold → ProductSold
        # / Product name via PriceSold → ProductSold
        product_name = str(ligne.pricesold) if ligne.pricesold else _("Article")

        articles.append({
            "name": product_name,
            "qty": qty,
            "price": amount_centimes,
            "total": article_total,
        })

    # Nom de l'operateur
    # / Operator name
    operateur_name = ""
    if operateur:
        operateur_name = operateur.email if operateur.email else str(operateur)

    return {
        "header": {
            "title": pv.name if pv else "",
            "subtitle": operateur_name,
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "articles": articles,
        "total": {
            "amount": total_centimes,
            "label": moyen_paiement,
        },
        "qrcode": None,
        "footer": [_("Merci de votre visite !")],
    }


def formatter_ticket_billet(ticket, reservation, event):
    """
    Formate un billet d'entree (evenement).
    / Formats an entry ticket (event).

    LOCALISATION : laboutik/printing/formatters.py

    :param ticket: BaseBillet.Ticket
    :param reservation: BaseBillet.Reservation
    :param event: BaseBillet.Event
    :return: dict ticket_data
    """
    # Date de l'evenement
    # / Event date
    event_date = ""
    if event.datetime:
        event_date = timezone.localtime(event.datetime).strftime("%d/%m/%Y %H:%M")

    # Nom du tarif (via le ticket ou la reservation)
    # / Price name (via the ticket or the reservation)
    tarif_name = ""
    if hasattr(ticket, 'pricesold') and ticket.pricesold:
        tarif_name = str(ticket.pricesold)

    # Nom du client
    # / Customer name
    client_name = ""
    if reservation and reservation.user_commande:
        user = reservation.user_commande
        client_name = user.email if user.email else str(user)

    # QR code : meme contenu que le PDF (UUID signe avec la cle RSA de l'event)
    # Si la cle RSA n'est pas configuree, on utilise l'UUID brut en fallback.
    # / QR code: same content as PDF (UUID signed with event's RSA key)
    # If RSA key is not configured, we fall back to raw UUID.
    qrcode_data = None
    if ticket:
        try:
            qrcode_data = ticket.qrcode()
        except Exception:
            qrcode_data = str(ticket.uuid)

    return {
        "header": {
            "title": event.name if event else "",
            "subtitle": tarif_name,
            "date": event_date,
        },
        "articles": [],
        "total": {},
        "qrcode": qrcode_data,
        "footer": [
            client_name,
            _("Presentez ce QR code a l'entree"),
        ],
    }


def formatter_ticket_commande(commande, articles_groupe, printer):
    """
    Formate un ticket de commande cuisine/bar (pour l'imprimante de la categorie).
    / Formats a kitchen/bar order ticket (for the category's printer).

    LOCALISATION : laboutik/printing/formatters.py

    :param commande: laboutik.CommandeSauvegarde
    :param articles_groupe: list de ArticleCommandeSauvegarde (meme categorie)
    :param printer: laboutik.Printer
    :return: dict ticket_data
    """
    now = timezone.localtime(timezone.now())

    # Nom de la table si disponible
    # / Table name if available
    table_name = ""
    if commande.table:
        table_name = commande.table.name

    # Construire la liste des articles (pas de prix pour la cuisine)
    # / Build articles list (no price for kitchen)
    articles = []
    for article in articles_groupe:
        articles.append({
            "name": article.product.name if article.product else _("Article"),
            "qty": article.qty,
            "price": 0,
            "total": 0,
        })

    # Titre = nom de l'imprimante (ex: "CUISINE", "BAR")
    # / Title = printer name (e.g. "KITCHEN", "BAR")
    title = printer.name if printer else _("Commande")

    return {
        "header": {
            "title": title,
            "subtitle": f"Table: {table_name}" if table_name else "",
            "date": now.strftime("%H:%M"),
        },
        "articles": articles,
        "total": {},
        "qrcode": None,
        "footer": [f"#{str(commande.uuid)[:8]}"],
    }


def formatter_ticket_cloture(cloture):
    """
    Formate un ticket de cloture de caisse (Z-ticket).
    / Formats a cash register closure ticket (Z-ticket).

    LOCALISATION : laboutik/printing/formatters.py

    :param cloture: laboutik.ClotureCaisse
    :return: dict ticket_data
    """
    # Dates du service
    # / Service dates
    date_ouverture = ""
    if cloture.datetime_ouverture:
        date_ouverture = timezone.localtime(
            cloture.datetime_ouverture
        ).strftime("%d/%m/%Y %H:%M")

    date_cloture = ""
    if cloture.datetime_cloture:
        date_cloture = timezone.localtime(
            cloture.datetime_cloture
        ).strftime("%d/%m/%Y %H:%M")

    # Totaux par moyen de paiement (en centimes → articles pour affichage)
    # / Totals by payment method (in cents → articles for display)
    articles = []
    if cloture.total_especes:
        articles.append({
            "name": _("Especes"),
            "qty": 1,
            "price": cloture.total_especes,
            "total": cloture.total_especes,
        })
    if cloture.total_carte_bancaire:
        articles.append({
            "name": _("Carte bancaire"),
            "qty": 1,
            "price": cloture.total_carte_bancaire,
            "total": cloture.total_carte_bancaire,
        })
    if cloture.total_cashless:
        articles.append({
            "name": _("Cashless"),
            "qty": 1,
            "price": cloture.total_cashless,
            "total": cloture.total_cashless,
        })

    pv_name = cloture.point_de_vente.name if cloture.point_de_vente else ""

    return {
        "header": {
            "title": _("CLOTURE CAISSE"),
            "subtitle": pv_name,
            "date": date_cloture,
        },
        "articles": articles,
        "total": {
            "amount": cloture.total_general,
            "label": f"{cloture.nombre_transactions} {_('transactions')}",
        },
        "qrcode": None,
        "footer": [
            f"{_('Ouverture')}: {date_ouverture}",
            f"{_('Fermeture')}: {date_cloture}",
        ],
    }

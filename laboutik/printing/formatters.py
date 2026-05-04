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
    Inclut les mentions legales (raison sociale, SIRET, TVA) conformement LNE exigence 3.
    / Formats a customer sale ticket (after payment).
    Includes legal mentions (business name, SIRET, VAT) per LNE requirement 3.

    LOCALISATION : laboutik/printing/formatters.py

    :param lignes_articles: QuerySet ou list de LigneArticle
    :param pv: PointDeVente
    :param operateur: TibilletUser (caissier)
    :param moyen_paiement: str (ex: "Especes", "CB", "NFC")
    :return: dict ticket_data
    """
    from BaseBillet.models import Configuration
    from laboutik.models import LaboutikConfiguration
    from django.db.models import F

    now = timezone.localtime(timezone.now())

    # --- Infos legales depuis Configuration (singleton du tenant) ---
    # / Legal info from Configuration (tenant singleton)
    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    # Adresse complete
    # / Full address
    parties_adresse = []
    if config.adress:
        parties_adresse.append(config.adress)
    if config.postal_code:
        parties_adresse.append(str(config.postal_code))
    if config.city:
        parties_adresse.append(config.city)
    adresse_complete = " ".join(parties_adresse)

    # TVA : numero ou mention d'exoneration
    # / VAT: number or exemption notice
    tva_display = (
        config.tva_number
        if config.tva_number
        else _("TVA non applicable, art. 293 B du CGI")
    )

    # Numero sequentiel du ticket (incremente atomiquement avec verrou)
    # Le select_for_update() garantit qu'aucun autre worker ne lit
    # la meme valeur entre l'UPDATE et le refresh_from_db().
    # / Sequential receipt number (atomically incremented with lock)
    from django.db import transaction

    with transaction.atomic():
        LaboutikConfiguration.objects.select_for_update().filter(
            pk=laboutik_config.pk,
        ).update(compteur_tickets=F("compteur_tickets") + 1)
        laboutik_config.refresh_from_db()
    numero_ticket = laboutik_config.compteur_tickets

    legal = {
        "business_name": config.organisation or "",
        "address": adresse_complete,
        "siret": config.siren or "",
        "tva_number": tva_display,
        "receipt_number": f"T-{numero_ticket:06d}",
        "terminal_id": pv.name if pv else "",
    }

    # --- Construire la liste des articles avec taux TVA ---
    # / Build the articles list with VAT rate
    articles = []
    total_centimes = 0
    tva_par_taux = {}

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

        # Taux TVA de la ligne
        # / VAT rate of the line
        taux_tva = float(ligne.vat or 0)

        article_dict = {
            "name": product_name,
            "qty": qty,
            "price": amount_centimes,
            "total": article_total,
            "vat_rate": f"{taux_tva:.2f}",
        }

        # Si c'est une vente au poids/volume, ajouter une sous-ligne avec le détail
        # / If weight/volume sale, add a sub-line with details
        if ligne.weight_quantity:
            try:
                price_obj = ligne.pricesold.price if ligne.pricesold else None
                if price_obj and price_obj.poids_mesure:
                    # Accéder à l'unité de stock
                    # / Access stock unit
                    stock = price_obj.product.stock_inventaire
                    unite = stock.unite if stock else "GR"

                    # Déterminer le symbole d'unité et le prix de référence
                    # / Determine unit symbol and reference price
                    if unite == "GR":
                        unite_display = "g"
                        prix_reference = price_obj.prix
                        sous_ligne = f"  {ligne.weight_quantity}{unite_display} x {prix_reference}E/kg"
                    elif unite == "CL":
                        unite_display = "cl"
                        prix_reference = price_obj.prix
                        sous_ligne = f"  {ligne.weight_quantity}{unite_display} x {prix_reference}E/L"
                    else:
                        # Unité par défaut (pièces) - ne pas afficher de sous-ligne
                        sous_ligne = None

                    if sous_ligne:
                        # Ajouter la sous-ligne au dictionnaire article
                        # / Add sub-line to article dict
                        article_dict["weight_detail"] = sous_ligne
            except (AttributeError, TypeError):
                # Si on ne peut pas accéder au stock, on ignore la sous-ligne
                # / If we can't access stock, ignore sub-line
                pass

        articles.append(article_dict)

        # Accumuler la TVA par taux
        # / Accumulate VAT by rate
        cle_tva = f"{taux_tva:.2f}"
        if cle_tva not in tva_par_taux:
            tva_par_taux[cle_tva] = {"rate": cle_tva, "ttc": 0}
        tva_par_taux[cle_tva]["ttc"] += article_total

    # Calculer HT et TVA pour chaque taux
    # / Compute HT and VAT for each rate
    tva_breakdown = []
    total_ht_global = 0
    total_tva_global = 0

    for cle_tva, donnees_tva in tva_par_taux.items():
        taux = float(cle_tva)
        ttc = donnees_tva["ttc"]

        if taux > 0:
            ht = int(round(ttc / (1 + taux / 100)))
            tva_montant = ttc - ht
        else:
            ht = ttc
            tva_montant = 0

        total_ht_global += ht
        total_tva_global += tva_montant

        tva_breakdown.append(
            {
                "rate": cle_tva,
                "ht": ht,
                "tva": tva_montant,
                "ttc": ttc,
            }
        )

    # Nom de l'operateur
    # / Operator name
    operateur_name = ""
    if operateur:
        operateur_name = operateur.email if operateur.email else str(operateur)

    # Pied de ticket personnalise
    # / Custom receipt footer
    pied_ticket = laboutik_config.pied_ticket or ""

    footer_lines = []
    if pied_ticket:
        footer_lines.append(pied_ticket)
    footer_lines.append(_("Merci de votre visite !"))

    # Mode ecole : les tickets portent la mention "SIMULATION" (LNE exigence 5)
    # / Training mode: receipts carry "SIMULATION" label (LNE req. 5)
    is_simulation = laboutik_config.mode_ecole

    # Detail cascade NFC (si paiement multi-asset)
    # / NFC cascade detail (if multi-asset payment)
    # Cherche le uuid_transaction commun a toutes les lignes de ce paiement.
    # / Find the uuid_transaction shared by all lines of this payment.
    cascade_detail = []
    uuid_tx = None
    for ligne in lignes_articles:
        if hasattr(ligne, "uuid_transaction") and ligne.uuid_transaction:
            uuid_tx = ligne.uuid_transaction
            break

    if uuid_tx:
        from django.db.models import Sum as _Sum

        from BaseBillet.models import LigneArticle
        from fedow_core.models import Asset as FedowAsset

        # Agreger les montants par asset UUID pour ce paiement
        # / Aggregate amounts by asset UUID for this payment
        lignes_par_asset = (
            LigneArticle.objects.filter(
                uuid_transaction=uuid_tx,
                asset__isnull=False,
            )
            .values("asset")
            .annotate(total=_Sum("amount"))
        )

        # Prefetch les assets pour eviter N+1
        # / Prefetch assets to avoid N+1
        asset_uuids = [e["asset"] for e in lignes_par_asset]
        assets_par_uuid = {
            a.uuid: a for a in FedowAsset.objects.filter(uuid__in=asset_uuids)
        }

        for entry in lignes_par_asset:
            asset_obj = assets_par_uuid.get(entry["asset"])
            if asset_obj:
                cascade_detail.append(
                    {
                        "name": asset_obj.name,
                        "total": entry["total"],
                    }
                )

    return {
        "header": {
            "title": pv.name if pv else "",
            "subtitle": operateur_name,
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "legal": legal,
        "articles": articles,
        "total": {
            "amount": total_centimes,
            "label": moyen_paiement,
        },
        "tva_breakdown": tva_breakdown,
        "total_ht": total_ht_global,
        "total_tva": total_tva_global,
        "cascade_detail": cascade_detail,
        "is_duplicata": False,
        "is_simulation": is_simulation,
        "pied_ticket": pied_ticket,
        "qrcode": None,
        "footer": footer_lines,
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
    if hasattr(ticket, "pricesold") and ticket.pricesold:
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
        articles.append(
            {
                "name": article.product.name if article.product else _("Article"),
                "qty": article.qty,
                "price": 0,
                "total": 0,
            }
        )

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


def formatter_ticket_x(
    totaux_par_moyen, solde_caisse, datetime_ouverture, nb_transactions
):
    """
    Formate un Ticket X temporaire (consultation du service en cours, pas de cloture).
    Le Ticket X est un instantane : il n'est pas persiste en base.
    / Formats a temporary X-ticket (current shift consultation, no closure).
    The X-ticket is a snapshot: it is not persisted in the database.

    LOCALISATION : laboutik/printing/formatters.py

    :param totaux_par_moyen: dict avec especes, carte_bancaire, cashless, cheque, total (centimes)
    :param solde_caisse: dict avec fond_de_caisse, entrees_especes, sorties_especes, solde (centimes)
    :param datetime_ouverture: datetime de la 1ere vente apres derniere cloture
    :param nb_transactions: nombre de transactions dans la periode
    :return: dict ticket_data
    """
    now = timezone.localtime(timezone.now())
    date_ouverture = ""
    if datetime_ouverture:
        date_ouverture = timezone.localtime(datetime_ouverture).strftime(
            "%d/%m/%Y %H:%M"
        )

    # Lignes par moyen de paiement / Lines by payment method
    articles = []
    if totaux_par_moyen.get("especes"):
        articles.append(
            {
                "name": _("Especes"),
                "qty": 1,
                "price": totaux_par_moyen["especes"],
                "total": totaux_par_moyen["especes"],
            }
        )
    if totaux_par_moyen.get("carte_bancaire"):
        articles.append(
            {
                "name": _("Carte bancaire"),
                "qty": 1,
                "price": totaux_par_moyen["carte_bancaire"],
                "total": totaux_par_moyen["carte_bancaire"],
            }
        )
    if totaux_par_moyen.get("cashless"):
        articles.append(
            {
                "name": _("Cashless"),
                "qty": 1,
                "price": totaux_par_moyen["cashless"],
                "total": totaux_par_moyen["cashless"],
            }
        )
    if totaux_par_moyen.get("cheque"):
        articles.append(
            {
                "name": _("Cheque"),
                "qty": 1,
                "price": totaux_par_moyen["cheque"],
                "total": totaux_par_moyen["cheque"],
            }
        )

    # Lignes solde caisse / Cash drawer balance lines
    footer = [
        f"{_('Ouverture')}: {date_ouverture}",
        f"{_('Impression')}: {now.strftime('%d/%m/%Y %H:%M')}",
        "",
    ]
    if solde_caisse:
        fond = solde_caisse.get("fond_de_caisse", 0)
        entrees = solde_caisse.get("entrees_especes", 0)
        sorties = solde_caisse.get("sorties_especes", 0)
        solde = solde_caisse.get("solde", 0)
        footer.append(f"{_('Fond de caisse')}: {fond / 100:.2f} EUR")
        footer.append(f"{_('Entrees especes')}: {entrees / 100:.2f} EUR")
        if sorties:
            footer.append(f"{_('Sorties especes')}: -{sorties / 100:.2f} EUR")
        footer.append(f"{_('Solde caisse')}: {solde / 100:.2f} EUR")

    return {
        "header": {
            "title": _("TICKET X"),
            "subtitle": _("Consultation en cours"),
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "articles": articles,
        "total": {
            "amount": totaux_par_moyen.get("total", 0),
            "label": f"{nb_transactions} {_('transactions')}",
        },
        "qrcode": None,
        "footer": footer,
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
        date_ouverture = timezone.localtime(cloture.datetime_ouverture).strftime(
            "%d/%m/%Y %H:%M"
        )

    date_cloture = ""
    if cloture.datetime_cloture:
        date_cloture = timezone.localtime(cloture.datetime_cloture).strftime(
            "%d/%m/%Y %H:%M"
        )

    # Totaux par moyen de paiement (en centimes → articles pour affichage)
    # / Totals by payment method (in cents → articles for display)
    articles = []
    if cloture.total_especes:
        articles.append(
            {
                "name": _("Especes"),
                "qty": 1,
                "price": cloture.total_especes,
                "total": cloture.total_especes,
            }
        )
    if cloture.total_carte_bancaire:
        articles.append(
            {
                "name": _("Carte bancaire"),
                "qty": 1,
                "price": cloture.total_carte_bancaire,
                "total": cloture.total_carte_bancaire,
            }
        )
    if cloture.total_cashless:
        articles.append(
            {
                "name": _("Cashless"),
                "qty": 1,
                "price": cloture.total_cashless,
                "total": cloture.total_cashless,
            }
        )

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


def formatter_recu_vider_carte(transactions):
    """
    Formate un recu client pour un vider carte (remboursement especes).
    Inclut les mentions legales + detail par asset + reference Transaction.
    / Formats a customer receipt for a card refund (cash refund).
    Includes legal mentions + detail per asset + Transaction reference.

    LOCALISATION : laboutik/printing/formatters.py

    :param transactions: liste de Transaction REFUND (1 par asset)
    :return: dict ticket_data compatible avec imprimer_async
    """
    from BaseBillet.models import Configuration
    from laboutik.models import LaboutikConfiguration

    now = timezone.localtime(timezone.now())

    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    # Mentions legales basiques (adresse + SIRET si dispo).
    # / Basic legal mentions.
    parties_adresse = []
    if config.adress:
        parties_adresse.append(config.adress)
    if config.postal_code:
        parties_adresse.append(str(config.postal_code))
    if config.city:
        parties_adresse.append(config.city)
    adresse_complete = " ".join(parties_adresse)

    legal = {
        "organisation": config.organisation or "",
        "adresse": adresse_complete,
        "siret": getattr(laboutik_config, "siret", "") or "",
    }

    # Calcul du total et detail par asset.
    # / Compute total and per-asset detail.
    total_centimes = 0
    articles = []
    for tx in transactions:
        total_centimes += tx.amount
        articles.append({
            "name": f"{tx.asset.name} ({tx.get_action_display()})",
            "qty": 1,
            "prix_centimes": tx.amount,
            "total_centimes": tx.amount,
        })

    return {
        "header": {
            "title": str(_("REMBOURSEMENT CARTE")),
            "subtitle": "",
            "date": now.strftime("%d/%m/%Y %H:%M"),
        },
        "legal": legal,
        "articles": articles,
        "total": {
            "amount": total_centimes,
            "label": str(_("Especes")),
        },
        "is_duplicata": False,
        "is_simulation": False,
        "pied_ticket": str(_("Merci de votre visite.")),
        "qrcode": None,
        "footer": [],
    }

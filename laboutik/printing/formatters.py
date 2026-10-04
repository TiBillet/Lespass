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

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from BaseBillet.models import PaymentMethod
from comptabilite.presentation import (
    codes_des_moyens_dans_l_ordre,
    fuseau_d_affichage_du_rapport,
    lignes_du_tiroir,
)
from comptabilite.rapport import CLE_PLUSIEURS_MOYENS, nom_du_moyen_de_paiement


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
    from BaseBillet.models import Configuration, PaymentMethod
    from fedow_core.models import Asset as FedowAsset
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

    # --- Regrouper les parts d'un meme article ---
    # Un article paye avec plusieurs monnaies donne une ligne par monnaie : meme
    # tarif vendu, meme prix unitaire (amount), meme TVA, et une quantite
    # partielle chacune (total = amount x qty). On les regroupe : le client lit
    # « Vin x3 15,00 », pas « Vin x1,2 » puis « Vin x1,8 ».
    # / Parts of one item paid with several currencies are grouped back.
    articles_regroupes = {}
    for ligne in lignes_articles:
        cle_article = (ligne.pricesold_id, ligne.amount, float(ligne.vat or 0))
        if cle_article not in articles_regroupes:
            articles_regroupes[cle_article] = {"ligne": ligne, "qty": Decimal("0")}
        articles_regroupes[cle_article]["qty"] += Decimal(ligne.qty)

    # --- Construire la liste des articles avec taux TVA ---
    # / Build the articles list with VAT rate
    articles = []
    total_centimes = 0
    tva_par_taux = {}

    for article_regroupe in articles_regroupes.values():
        # La 1re ligne du groupe porte le nom, la TVA et le detail au poids,
        # identiques sur toutes les parts.
        # / The group's 1st line carries name, VAT and weight detail.
        ligne = article_regroupe["ligne"]
        quantite_totale = article_regroupe["qty"]

        # Montant = prix unitaire x quantite, arrondi au centime comme les
        # rapports (0,5 -> 1). LigneArticle.amount est en centimes.
        # / Amount = unit price x qty, rounded like the reports. amount is in cents.
        amount_centimes = ligne.amount
        article_total = int(
            (Decimal(amount_centimes) * quantite_totale).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        total_centimes += article_total

        # Quantite lisible sur le papier : un entier quand elle est entiere
        # (cas normal), sinon deux decimales. Jamais un Decimal : les
        # imprimantes l'ecrivent telle quelle et le ticket part en JSON (Celery).
        # / Readable quantity: an int when whole, else two decimals. Never a Decimal.
        if quantite_totale == quantite_totale.to_integral_value():
            qty = int(quantite_totale)
        else:
            qty = f"{quantite_totale:.2f}"

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

    # --- Unite des montants du ticket ---
    # Un panier ne contient qu'une monnaie. S'il est paye en points ou en temps
    # (moyen NON_MONETAIRE), les montants sont dans cette monnaie (centiemes) et le
    # ticket n'a pas de TVA : ce n'est pas une vente en argent.
    # / One currency per cart. A points/time ticket shows that currency, no VAT.
    unite_du_ticket = "EUR"
    premiere_ligne_du_ticket = next(iter(lignes_articles), None)
    ticket_en_points = (
        premiere_ligne_du_ticket is not None
        and premiere_ligne_du_ticket.payment_method == PaymentMethod.NON_MONETAIRE
    )
    if ticket_en_points:
        # Monnaie introuvable : « Points ou temps », jamais « EUR »
        # / Currency not found: "Points or time", never "EUR"
        unite_du_ticket = str(_("Points ou temps"))
        monnaie_du_ticket = FedowAsset.objects.filter(
            uuid=premiere_ligne_du_ticket.asset
        ).first()
        if monnaie_du_ticket is not None:
            unite_du_ticket = monnaie_du_ticket.name
        tva_breakdown = []
        total_ht_global = 0
        total_tva_global = 0

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

    # Detail des moyens de paiement de ce paiement : une entree par monnaie de
    # carte (par nom d'asset) et une par autre moyen (especes, CB, cheque). Les
    # montants portent sur amount x qty. Les imprimantes ne l'impriment que si au
    # moins deux moyens ont servi.
    # / Payment methods detail: one entry per card currency and one per other
    #   method, amounts on amount x qty. Printed only with two methods or more.
    cascade_detail = []
    uuid_tx = None
    for ligne in lignes_articles:
        if hasattr(ligne, "uuid_transaction") and ligne.uuid_transaction:
            uuid_tx = ligne.uuid_transaction
            break

    if uuid_tx:
        from BaseBillet.models import LigneArticle
        from laboutik.reports import montant_ttc_centimes
        from laboutik.views import LABELS_MOYENS_PAIEMENT_DB

        # Toutes les lignes du paiement, complement en especes ou CB compris
        # (il partage le uuid_transaction). list() : une seule requete.
        # / All lines of the payment, cash/card complement included.
        montants_par_moyen = list(
            LigneArticle.objects.filter(uuid_transaction=uuid_tx)
            .values("asset", "payment_method")
            .annotate(total=montant_ttc_centimes())
            .order_by("payment_method")
        )

        # Les assets en une requete (evite N+1).
        # / Assets in one query (avoids N+1).
        asset_uuids = [
            entree["asset"] for entree in montants_par_moyen if entree["asset"]
        ]
        assets_par_uuid = {
            a.uuid: a for a in FedowAsset.objects.filter(uuid__in=asset_uuids)
        }
        libelles_des_moyens = dict(PaymentMethod.choices)
        libelles_des_moyens.update(LABELS_MOYENS_PAIEMENT_DB)

        # Les monnaies de carte d'abord, dans l'ordre ou la cascade les debite
        # (cadeau, puis locale, puis federee), puis les autres moyens (especes,
        # CB...). Chaque montant est arrondi au centime par moyen : la somme du
        # detail peut donc differer d'un centime du TOTAL, arrondi par article.
        # / Card currencies first, in cascade order (gift, local, federated),
        #   then other methods. Per-method rounding: the detail sum may differ
        #   by one cent from the TOTAL.
        rang_dans_la_cascade = {
            PaymentMethod.LOCAL_GIFT: 0,
            PaymentMethod.LOCAL_EURO: 1,
            PaymentMethod.STRIPE_FED: 2,
        }
        montants_par_moyen.sort(
            key=lambda entree: rang_dans_la_cascade.get(entree["payment_method"], 3)
        )

        detail_monnaies_de_carte = []
        detail_autres_moyens = []
        for entree in montants_par_moyen:
            asset_obj = assets_par_uuid.get(entree["asset"])
            if asset_obj is not None:
                detail_monnaies_de_carte.append(
                    {"name": asset_obj.name, "total": entree["total"]}
                )
            else:
                code_du_moyen = entree["payment_method"]
                nom_du_moyen = str(libelles_des_moyens.get(code_du_moyen, code_du_moyen))
                detail_autres_moyens.append(
                    {"name": nom_du_moyen, "total": entree["total"]}
                )
        cascade_detail = detail_monnaies_de_carte + detail_autres_moyens

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
        # Unite des montants : "EUR", ou le nom de la monnaie de points / temps
        # / Amount unit: "EUR", or the points/time currency name
        "unite": unite_du_ticket,
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


# La largeur d'une ligne de ticket (papier 58 mm, police normale).
# / The width of a ticket line (58 mm paper, normal font).
LARGEUR_D_UNE_LIGNE_DE_TICKET = 32

# La date des lignes de pied des tickets X et Z : année sur deux chiffres, pour que
# « Début de période: 10/03/26 10:00 » tienne en 32 caractères.
# / The date of the X and Z ticket footer lines: two-digit year, to fit 32 chars.
FORMAT_DE_DATE_DU_PIED = "%d/%m/%y %H:%M"


def _ligne_de_montant_du_pied(libelle, montant_en_centimes):
    """
    Une ligne de pied « Libellé: 12.34 EUR », montant signé. Si elle dépasse la
    largeur du ticket, « EUR » est retiré (les autres lignes disent la monnaie) :
    l'imprimante ne coupe pas la ligne au milieu d'un mot.
    / A footer line "Label: 12.34 EUR", signed; " EUR" is dropped when the line is
    wider than the ticket.
    """
    ligne = f"{libelle}: {montant_en_centimes / 100:.2f} EUR"
    if len(ligne) > LARGEUR_D_UNE_LIGNE_DE_TICKET:
        ligne = f"{libelle}: {montant_en_centimes / 100:.2f}"
    return ligne


def _lignes_du_tiroir_du_rapport(section_caisse_especes):
    """
    Les lignes de pied du tiroir de la caisse, écrites par la présentation partagée
    (`comptabilite/presentation.py` `lignes_du_tiroir`) : mêmes libellés et mêmes
    signes qu'à l'écran. Fond, espèces reçues, espèces rendues, corrections, sorties
    de caisse, solde théorique. Une ligne nulle n'est pas imprimée (le fond et le
    solde le sont toujours). L'argent qui sort est négatif : les lignes au-dessus du
    solde s'additionnent en solde.
    / The cash drawer footer lines, written by the shared presentation (same labels
    and signs as the screen). A zero line is not printed, except float and balance.

    :param section_caisse_especes: `rapport["caisse_especes"]` (ou None)
    :return: liste de textes (vide sans section)
    """
    lignes = []
    if not section_caisse_especes:
        return lignes

    lignes_signees_du_tiroir = lignes_du_tiroir(section_caisse_especes)
    for ligne_du_tiroir in lignes_signees_du_tiroir:
        montant = ligne_du_tiroir["montant_en_centimes"]
        if not montant and not ligne_du_tiroir["toujours_imprimee"]:
            continue
        lignes.append(_ligne_de_montant_du_pied(ligne_du_tiroir["libelle"], montant))
    return lignes


def formatter_ticket_x(rapport_du_service, datetime_ouverture):
    """
    Formate le ticket X : la consultation du service en cours, jamais stockee. Lu
    dans le rapport X du rapport des ventes unique (`RapportDesVentes.rapport_x()`),
    de la fin de la derniere cloture journaliere jusqu'a maintenant. Meme forme et
    memes lignes que le ticket Z.
    / Formats the X ticket from the single sales report (never stored). Same shape and
    lines as the Z ticket.

    LOCALISATION : laboutik/printing/formatters.py

    CONTENU :
    - au-dessus du total : le chiffre d'affaires par moyen (comme le ticket Z) ;
    - total : le chiffre d'affaires TTC, et le nombre d'operations numerotees ;
    - les heures dans le fuseau fige dans l'en-tete du rapport ;
    - pied : les lignes a part (recharges, cartes videes, ecarts, si non nulles),
      ouverture, impression, puis le tiroir (fond, especes recues, rendues,
      corrections, sorties, solde ; une ligne nulle n'est pas imprimee), les offerts
      et les points (hors argent, jamais dans le total).
    / Lines per method, total = revenue incl. tax, footer with the drawer, gifts and
      points.

    APPELE PAR : laboutik/views.py, `CaisseViewSet.imprimer_ticket_x`.

    :param rapport_du_service: dict de `RapportDesVentes(debut, maintenant).rapport_x()`
    :param datetime_ouverture: debut du service (fin de la derniere J)
    :return: dict ticket_data
    """
    # Les heures s'écrivent dans le fuseau figé dans l'en-tête du rapport.
    # / Hours are written in the time zone frozen in the report header.
    fuseau_du_rapport = fuseau_d_affichage_du_rapport(rapport_du_service)
    maintenant = timezone.localtime(timezone.now(), fuseau_du_rapport)
    date_ouverture = ""
    if datetime_ouverture:
        date_ouverture = timezone.localtime(
            datetime_ouverture, fuseau_du_rapport
        ).strftime(FORMAT_DE_DATE_DU_PIED)

    articles = _lignes_des_moyens_du_rapport(
        rapport_du_service.get("chiffre_affaires", {})
    )

    chiffre_affaires_ttc = rapport_du_service.get("chiffre_affaires", {}).get(
        "total_ttc_en_centimes", 0
    )
    nombre_d_operations = rapport_du_service.get("en_tete", {}).get(
        "nombre_de_ventes", 0
    )

    # Sous le total : les lignes a part (recharges, cartes videes, ecarts), puis
    # l'ouverture, l'impression et le tiroir.
    # / Under the total: separate lines, then opening, printing and the drawer.
    footer = _lignes_a_part_sous_le_total(rapport_du_service.get("reconciliation"))
    footer.extend(
        [
            f"{_('Ouverture')}: {date_ouverture}",
            f"{_('Impression')}: {maintenant.strftime(FORMAT_DE_DATE_DU_PIED)}",
            "",
        ]
    )
    footer.extend(
        _lignes_du_tiroir_du_rapport(rapport_du_service.get("caisse_especes"))
    )
    footer.extend(_lignes_des_offerts_du_rapport(rapport_du_service.get("offerts")))
    footer.extend(_lignes_des_points_du_rapport(rapport_du_service.get("points")))

    return {
        "header": {
            "title": _("TICKET X"),
            "subtitle": _("Consultation en cours"),
            "date": maintenant.strftime("%d/%m/%Y %H:%M"),
        },
        "articles": articles,
        "total": {
            "amount": chiffre_affaires_ttc,
            "label": f"{_('Opérations numérotées')}: {nombre_d_operations}",
        },
        "qrcode": None,
        "footer": footer,
    }


def _quantite_lisible_sur_un_ticket(quantite_en_texte):
    """
    Une quantite du rapport (texte d'un Decimal, ex. « 2.000 ») ecrite sur un ticket :
    un entier sans decimale, sinon deux decimales.
    / A report quantity written on a ticket: integer, otherwise two decimals.
    """
    quantite = Decimal(quantite_en_texte or "0")
    if quantite == quantite.to_integral_value():
        return int(quantite)
    return f"{quantite:.2f}"


def _lignes_des_offerts_du_rapport(section_offerts):
    """
    Lignes de pied des offerts, lues dans la section « offerts » du rapport d'une
    cloture unique : « Offerts: N art., X.XX EUR » sur une ligne si elle tient dans
    les 32 caracteres du ticket ; sinon repliee en deux lignes, « Offerts: N art. »
    puis « Valeur offerte: X.XX EUR ». Aucune ligne s'il n'y a pas d'offert.
    Hors argent : cette valeur n'entre jamais dans le TOTAL du ticket.
    / Footer lines of the GIFT button: one line if it fits 32 chars, otherwise
    folded into two lines. Empty without gifts.

    :param section_offerts: `rapport_json["offerts"]` (ou None)
    :return: liste de lignes (vide sans offert)
    """
    if not section_offerts or not section_offerts.get("par_produit"):
        return []
    quantite_affichee = _quantite_lisible_sur_un_ticket(section_offerts.get("quantite"))
    valeur_en_centimes = section_offerts.get("valeur_catalogue_en_centimes", 0)
    valeur_en_euros = f"{valeur_en_centimes / 100:.2f}"
    ligne_des_articles = f"{_('Offerts')}: {quantite_affichee} {_('art.')}"
    ligne_entiere = f"{ligne_des_articles}, {valeur_en_euros} EUR"
    if len(ligne_entiere) <= LARGEUR_D_UNE_LIGNE_DE_TICKET:
        return [ligne_entiere]
    return [
        ligne_des_articles,
        _ligne_de_montant_du_pied(_("Valeur offerte"), valeur_en_centimes),
    ]


def _lignes_des_points_du_rapport(section_points):
    """
    Lignes de pied des ventes en points ou en temps, une par monnaie, lues dans la
    section « points » du rapport d'une cloture unique : « Points fidélité (hors
    argent): 300.00 ». Le rapport ne garde pas le nombre d'articles par monnaie : il
    n'est pas imprime. Hors argent : jamais dans le TOTAL du ticket.
    / Footer lines of points/time sales, one per currency, from the single closure
    report. The report keeps no article count per currency.

    :param section_points: `rapport_json["points"]` (ou None), clé = uuid de la monnaie
    """
    lignes = []
    if not section_points:
        return lignes
    monnaies_triees_par_nom = sorted(
        section_points.values(), key=_nom_d_une_monnaie_du_rapport
    )
    for monnaie in monnaies_triees_par_nom:
        montant_affiche = f"{monnaie.get('total_en_centiemes', 0) / 100:.2f}"
        ligne_de_la_monnaie = (
            f"{monnaie.get('nom', '')} ({_('hors argent')}): {montant_affiche}"
        )
        # Trop large pour le ticket : la mention « hors argent » est retirée (le
        # nom de la monnaie de points suffit) ; si c'est encore trop large, le nom
        # est tronqué pour que le montant reste entier.
        # / Too wide for the ticket: the "hors argent" mention is dropped; if still
        # too wide, the name is cut so the amount stays whole.
        if len(ligne_de_la_monnaie) > LARGEUR_D_UNE_LIGNE_DE_TICKET:
            fin_de_la_ligne = f": {montant_affiche}"
            place_pour_le_nom = LARGEUR_D_UNE_LIGNE_DE_TICKET - len(fin_de_la_ligne)
            if place_pour_le_nom < 0:
                place_pour_le_nom = 0
            nom_tronque = monnaie.get("nom", "")[:place_pour_le_nom]
            ligne_de_la_monnaie = f"{nom_tronque}{fin_de_la_ligne}"
        lignes.append(ligne_de_la_monnaie)
    return lignes


def _nom_d_une_monnaie_du_rapport(monnaie):
    """La cle de tri d'une monnaie du rapport : son nom. / Sort key: the name."""
    return monnaie.get("nom", "")


def _lignes_des_moyens_du_rapport(section_chiffre_affaires):
    """
    Les lignes des tickets X et Z au-dessus du TOTAL : le chiffre d'affaires par
    moyen de paiement (`chiffre_affaires.par_moyen` du rapport), une ligne par moyen
    non nul. Ordre : celui de l'écran (`codes_des_moyens_dans_l_ordre`) : especes,
    carte bancaire, cheque, les autres moyens d'argent (par code), puis chaque moyen
    cashless (par code), puis « plusieurs moyens ».
    Les noms des moyens viennent de leur seule source (`nom_du_moyen_de_paiement`),
    lus par le code : « Espèces », « Carte bancaire », « Chèque » partout. « Plusieurs
    moyens » garde le libellé du rapport. Ces lignes s'additionnent en chiffre d'affaires TTC (le
    TOTAL du ticket) : une recharge n'y est pas, elle a sa ligne a part, sous le total.
    / Ticket lines above the TOTAL: revenue by payment method, one per non-zero
    method; they add up to the TOTAL. A top-up is not there.

    :param section_chiffre_affaires: `rapport["chiffre_affaires"]`
    :return: liste de lignes de ticket
    """
    par_moyen = section_chiffre_affaires.get("par_moyen", {})
    codes_dans_l_ordre_du_ticket = codes_des_moyens_dans_l_ordre(par_moyen)

    lignes = []
    for code_du_moyen in codes_dans_l_ordre_du_ticket:
        ligne_du_moyen = par_moyen[code_du_moyen]
        montant_du_moyen = ligne_du_moyen.get("total_en_centimes", 0)
        if not montant_du_moyen:
            continue
        if code_du_moyen == CLE_PLUSIEURS_MOYENS:
            nom_du_moyen = ligne_du_moyen.get("libelle", code_du_moyen)
        else:
            nom_du_moyen = nom_du_moyen_de_paiement(code_du_moyen)
        lignes.append(
            {
                "name": nom_du_moyen,
                "qty": 1,
                "price": montant_du_moyen,
                "total": montant_du_moyen,
            }
        )
    return lignes


def _lignes_a_part_sous_le_total(section_reconciliation):
    """
    Les lignes a part, sous le TOTAL des tickets X et Z : recharges (montant brut),
    recharges remboursees, cartes videes, ecarts d'encaissement, lues dans la
    reconciliation du rapport, chacune seulement si elle est non nulle. Ce n'est pas
    du chiffre d'affaires : elles ne sont pas dans le total. Montants signes (une
    recharge remboursee ou une carte videe rend de l'argent : negatif).
    / Separate lines under the TOTAL: gross top-ups, refunded top-ups, emptied
    cards, collection gaps, each only when non-zero. Not revenue. Signed amounts.

    :param section_reconciliation: `rapport["reconciliation"]` (ou None ; une
        ancienne cloture n'a pas les recharges remboursees)
    :return: liste de textes
    """
    lignes = []
    if not section_reconciliation:
        return lignes
    recharges = section_reconciliation.get("recharges_en_centimes", 0)
    recharges_remboursees = section_reconciliation.get(
        "recharges_remboursees_en_centimes", 0
    )
    cartes_videes = section_reconciliation.get("cartes_videes_en_centimes", 0)
    ecarts = section_reconciliation.get("ecarts_d_encaissement_en_centimes", 0)
    if recharges:
        lignes.append(_ligne_de_montant_du_pied(_("Recharges"), recharges))
    if recharges_remboursees:
        lignes.append(
            _ligne_de_montant_du_pied(_("Recharges remboursées"), recharges_remboursees)
        )
    if cartes_videes:
        lignes.append(_ligne_de_montant_du_pied(_("Cartes vidées"), cartes_videes))
    if ecarts:
        lignes.append(_ligne_de_montant_du_pied(_("Écarts d'encaissement"), ecarts))
    return lignes


def formatter_ticket_cloture(cloture):
    """
    Formate le ticket Z d'une cloture unique, depuis le rapport stocke dans la
    cloture (`rapport_json`). La forme du dictionnaire est celle que lisent les
    imprimantes (`escpos_builder.py`, `sunmi_inner.py`).
    / Formats the Z ticket of a single closure from its stored report, in the shape
    the printers read.

    LOCALISATION : laboutik/printing/formatters.py

    CONTENU :
    - en-tete : « CLOTURE CAISSE », le point de vente d'ou le Z est lance, la fin ;
    - au-dessus du total : le chiffre d'affaires par moyen de paiement, une ligne par
      moyen non nul ; elles s'additionnent en total ;
    - total : le chiffre d'affaires TTC, et le nombre d'operations numerotees ;
    - pied : les lignes a part (recharges, cartes videes, ecarts d'encaissement,
      seulement si non nulles), le numero de la cloture, debut et fin de la periode,
      la ligne des offerts, une ligne par monnaie de points (hors argent).
    Les heures s'ecrivent dans le fuseau fige dans l'en-tete du rapport : un Z garde
    les heures de son lieu, quel que soit le fuseau du serveur.
    / Header, one line per payment method, total = revenue incl. tax, footer with
      the closure number, the period, gifts and points. Hours in the report's frozen
      time zone.

    APPELE PAR : laboutik/views.py, `CaisseViewSet.cloturer`.

    :param cloture: comptabilite.ClotureCaisse
    :return: dict ticket_data
    """
    rapport = cloture.rapport_json or {}

    fuseau_du_rapport = fuseau_d_affichage_du_rapport(rapport)
    debut_dans_le_fuseau = timezone.localtime(cloture.datetime_debut, fuseau_du_rapport)
    fin_dans_le_fuseau = timezone.localtime(cloture.datetime_fin, fuseau_du_rapport)
    # L'en-tête garde la date longue ; le pied, la date courte (32 caractères).
    # / The header keeps the long date; the footer the short one (32 chars).
    date_de_fin = fin_dans_le_fuseau.strftime("%d/%m/%Y %H:%M")
    date_courte_de_debut = debut_dans_le_fuseau.strftime(FORMAT_DE_DATE_DU_PIED)
    date_courte_de_fin = fin_dans_le_fuseau.strftime(FORMAT_DE_DATE_DU_PIED)

    articles = _lignes_des_moyens_du_rapport(rapport.get("chiffre_affaires", {}))

    chiffre_affaires_ttc = rapport.get("chiffre_affaires", {}).get(
        "total_ttc_en_centimes", 0
    )

    nom_du_point_de_vente = ""
    if cloture.point_de_vente:
        nom_du_point_de_vente = cloture.point_de_vente.name

    # Sous le total : les lignes a part (recharges, cartes videes, ecarts), puis le
    # numero de la cloture et la periode.
    # / Under the total: separate lines, then the closure number and the period.
    footer = _lignes_a_part_sous_le_total(rapport.get("reconciliation"))
    footer += [
        f"{_('Clôture n°')} {cloture.numero_sequentiel}",
        f"{_('Début de période')}: {date_courte_de_debut}",
        f"{_('Fermeture')}: {date_courte_de_fin}",
    ]
    footer.extend(_lignes_des_offerts_du_rapport(rapport.get("offerts")))
    footer.extend(_lignes_des_points_du_rapport(rapport.get("points")))

    return {
        "header": {
            "title": _("CLOTURE CAISSE"),
            "subtitle": nom_du_point_de_vente,
            "date": date_de_fin,
        },
        "articles": articles,
        "total": {
            "amount": chiffre_affaires_ttc,
            "label": f"{_('Opérations numérotées')}: {cloture.nombre_transactions}",
        },
        "qrcode": None,
        "footer": footer,
    }


def formatter_recu_vider_carte(transactions_locales, transactions_ancien_fedow=()):
    """
    Formate le reçu d'un vidage de carte : séparé par Fedow et détaillé.
    / Formats a card-emptying receipt: split by Fedow and detailed.

    LOCALISATION : laboutik/printing/formatters.py

    Le reçu se lit de haut en bas :
    1. les mentions légales du lieu (nom, adresse, SIREN) ;
    2. la partie « Fedow local » : une ligne par monnaie reprise ;
    3. la partie « Ancien Fedow » : une ligne par monnaie reprise ;
    4. le total : l'argent rendu en espèces.
    Seules la monnaie locale (TLF) et la monnaie fédérée (FED) sont de l'argent rendu.
    Les jetons cadeau (TNF) sont écrits « repris, sans argent » et ne comptent pas
    dans le total.
    / Legal mentions, local part, old Fedow part, then the cash given back. Gift tokens
    are "taken back, no money" and are not in the total.

    Les clés sont celles que lisent les imprimantes (escpos_builder.py,
    sunmi_inner.py) : `price` / `total` par ligne, `business_name` / `address` pour
    les mentions légales. Un titre de partie ou une ligne sans argent porte
    `texte_seul` : l'imprimante écrit son nom seul.
    / Keys are the ones printers read. `texte_seul`: the printer writes the name only.

    APPELÉ PAR : laboutik/views.py, PaiementViewSet.vider_carte_imprimer_recu

    :param transactions_locales: `Transaction` REFUND du Fedow local, relues en base
    :param transactions_ancien_fedow: dicts relus sur l'ancien Fedow
        {"montant", "categorie", "nom", "code_monnaie"}
    :return: dict ticket_data compatible avec imprimer_async
    """
    from BaseBillet.models import Configuration
    from fedow_core.models import Asset

    now = timezone.localtime(timezone.now())

    config = Configuration.get_solo()

    # Mentions légales du lieu (nom, adresse, SIREN), comme le ticket de vente.
    # / Venue legal mentions, like the sale receipt.
    parties_adresse = []
    if config.adress:
        parties_adresse.append(config.adress)
    if config.postal_code:
        parties_adresse.append(str(config.postal_code))
    if config.city:
        parties_adresse.append(config.city)
    adresse_complete = " ".join(parties_adresse)

    legal = {
        "business_name": config.organisation or "",
        "address": adresse_complete,
        "siret": config.siren or "",
    }

    mention_des_jetons_cadeau = str(_("repris, sans argent"))
    articles = []
    argent_rendu_en_centimes = 0

    # Les lignes des deux Fedow : (titre de la partie, liste de (nom, montant,
    # catégorie, code de la monnaie)).
    # / Both Fedow parts: (title, list of (name, amount, category, currency code)).
    lignes_du_fedow_local = []
    for transaction_locale in transactions_locales:
        lignes_du_fedow_local.append(
            (
                transaction_locale.asset.name,
                transaction_locale.amount,
                transaction_locale.asset.category,
                transaction_locale.asset.currency_code,
            )
        )
    lignes_de_l_ancien_fedow = []
    for transaction_distante in transactions_ancien_fedow:
        lignes_de_l_ancien_fedow.append(
            (
                transaction_distante["nom"],
                transaction_distante["montant"],
                transaction_distante["categorie"],
                transaction_distante["code_monnaie"],
            )
        )
    parties_du_recu = [
        (str(_("Fedow local")), lignes_du_fedow_local),
        (str(_("Ancien Fedow")), lignes_de_l_ancien_fedow),
    ]

    for titre_de_la_partie, lignes_de_la_partie in parties_du_recu:
        if not lignes_de_la_partie:
            continue
        articles.append({"name": titre_de_la_partie.upper(), "texte_seul": True})
        for nom, montant_centimes, categorie, code_de_la_monnaie in lignes_de_la_partie:
            if categorie in (Asset.TLF, Asset.FED):
                argent_rendu_en_centimes += montant_centimes
                articles.append({
                    "name": nom,
                    "qty": 1,
                    "price": montant_centimes,
                    "total": montant_centimes,
                })
            elif categorie == Asset.TNF:
                # Arithmétique entière : euros et centimes séparés par // et %.
                # / Integer arithmetic.
                quantite_reprise = f"{montant_centimes // 100}.{montant_centimes % 100:02d}"
                articles.append({
                    "name": (
                        f"{nom} {quantite_reprise} {code_de_la_monnaie} : "
                        f"{mention_des_jetons_cadeau}"
                    ),
                    "texte_seul": True,
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
            "amount": argent_rendu_en_centimes,
            "label": str(_("Rendu en espèces")),
        },
        "is_duplicata": False,
        "is_simulation": False,
        "pied_ticket": str(_("Merci de votre visite.")),
        "qrcode": None,
        "footer": [],
    }

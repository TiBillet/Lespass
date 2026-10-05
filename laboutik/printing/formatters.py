"""
Formatters de tickets d'impression.
Transforment des objets Django en dicts ticket_data independants du backend.
/ Ticket formatting functions.
Transform Django objects into ticket_data dicts independent of the backend.

LOCALISATION : laboutik/printing/formatters.py

Chaque formatter retourne un dict avec la structure suivante :
{
    "header": {"title": str, "subtitle": str, "date": str,
               "numero": str (facultatif, « Vente n° 12 »),
               "date_d_impression": str (facultatif, imprimee sur un DUPLICATA)},
    "articles": [{"name": str, "qty": int, "price": int, "total": int,
                  "weight_detail": str (facultatif), "detail_offert": str (facultatif)}],
    "total": {"amount": int, "label": str},
    "qrcode": str or None,
    "footer": [str, ...],
}

Les montants sont en centimes (int), signes (un retour de consigne, un moyen
rembourse sont negatifs). Les imprimantes (escpos_builder.py, sunmi_inner.py) les
convertissent en euros.
Le ticket de vente (`formatter_ticket_vente`) lit la `Vente` : aucun calcul d'argent
ici, les montants sont ceux figes sur la vente, ses lignes et ses reglements.
/ Amounts are signed whole cents. The sale receipt reads the sale: no money
computation here.
"""

import textwrap
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from BaseBillet.models import PaymentMethod
from comptabilite.presentation import (
    codes_des_moyens_dans_l_ordre,
    fuseau_d_affichage_du_rapport,
    lignes_du_tiroir,
)
from comptabilite.rapport import CLE_PLUSIEURS_MOYENS, nom_du_moyen_de_paiement
from laboutik.affichage_des_ventes import (
    articles_de_la_vente_pour_l_affichage,
    nom_de_l_unite_de_la_vente,
    noms_des_monnaies_des_ventes,
    reglements_pour_l_affichage,
)


def _lignes_du_pied_du_ticket_de_vente(pied_ticket):
    """
    Le pied de ticket choisi par le lieu, replie en lignes de 32 caracteres au plus
    (papier 58 mm), coupees entre deux mots : l'imprimante ne coupe pas une ligne
    trop longue au milieu d'un mot. Un retour a la ligne du lieu est garde.
    / The venue's footer folded into lines of 32 characters at most, cut between
    words. The venue's own line breaks are kept.

    Une ligne vide voulue par le lieu (pour aerer le pied) est gardee : `textwrap`
    ne rend rien pour un texte vide, on la remet a la main.
    / A blank line wanted by the venue is kept (`textwrap` returns nothing for it).

    :param pied_ticket: le texte (`LaboutikConfiguration.pied_ticket`), peut etre vide
    :return: liste de lignes
    """
    lignes_du_pied = []
    paragraphes_du_pied = pied_ticket.splitlines()
    for paragraphe in paragraphes_du_pied:
        if not paragraphe.strip():
            lignes_du_pied.append("")
            continue
        lignes_repliees = textwrap.wrap(paragraphe, width=LARGEUR_D_UNE_LIGNE_DE_TICKET)
        lignes_du_pied.extend(lignes_repliees)
    return lignes_du_pied


def _ajouter_a_la_ligne_de_tva(tva_par_taux, cle_du_taux, ht, tva, ttc):
    """
    Ajoute des montants (centimes) a la ligne d'un taux de la « TVA par taux » du
    ticket, creee a zero si elle n'existe pas encore.
    / Adds amounts to a rate's row of the receipt's VAT breakdown, created if needed.

    LOCALISATION : laboutik/printing/formatters.py
    APPELEE PAR : `formatter_ticket_vente` (ce module), pour la part en jetons d'une
    ligne (au taux 0) et pour son reste (a son taux).

    :param tva_par_taux: dict {cle du taux: {"rate", "ht", "tva", "ttc"}}, modifie ici
    :param cle_du_taux: le taux en texte a deux decimales (ex. "20.00")
    :param ht: centimes hors taxes a ajouter
    :param tva: centimes de TVA a ajouter
    :param ttc: centimes TTC a ajouter
    """
    if cle_du_taux not in tva_par_taux:
        tva_par_taux[cle_du_taux] = {
            "rate": cle_du_taux,
            "ht": 0,
            "tva": 0,
            "ttc": 0,
        }
    tva_par_taux[cle_du_taux]["ht"] += ht
    tva_par_taux[cle_du_taux]["tva"] += tva
    tva_par_taux[cle_du_taux]["ttc"] += ttc


def formatter_ticket_vente(vente, operateur):
    """
    Formate le ticket client d'une vente (`Vente`) : vente, re-impression, DUPLICATA.
    Inclut les mentions legales (raison sociale, SIRET, TVA) conformement LNE exigence 3.
    / Formats the customer receipt of a sale. Includes legal mentions (LNE req. 3).

    LOCALISATION : laboutik/printing/formatters.py

    LE TICKET LIT LA VENTE, sans aucun calcul d'argent :
    - en-tete : le point de vente, le NUMERO DE LA VENTE (« Vente n° 12 », « Avoir
      n° 13 » pour un avoir ; sequence sans trou du lieu), l'operateur, la date de
      l'ENCAISSEMENT dans le fuseau du lieu ; un DUPLICATA imprime en plus la date
      d'impression (`date_d_impression`) ;
    - articles : ceux du detail de la vente a l'ecran
      (`articles_de_la_vente_pour_l_affichage`, laboutik/affichage_des_ventes.py) :
      les parts d'un article paye avec plusieurs moyens forment UN article, avec sa
      quantite reelle ; le nom du produit, puis celui du tarif s'il est different,
      puis l'evenement et sa date ; sa part offerte est imprimee sous l'article ;
    - TOTAL : le net vendu de la vente (`Vente.total_ttc`) ;
    - TVA par taux : la somme des HT et des TVA figes sur les lignes ;
    - detail des reglements : libelles et ordre de la liste des ventes
      (`reglements_pour_l_affichage`), sans l'offert (montre sous l'article) ; les
      imprimantes ne l'impriment qu'avec au moins deux moyens ;
    - pied : le pied du lieu, replie en lignes de 32 caracteres.
    / The receipt reads the sale, no money computation.

    APPELE PAR : laboutik/views.py, `PaiementViewSet.imprimer_ticket`.

    :param vente: la `Vente` reglee
    :param operateur: TibilletUser (caissier), ou None
    :return: dict ticket_data
    """
    from BaseBillet.models import Configuration, LigneArticle
    from BaseBillet.models_vente import Vente
    from laboutik.models import LaboutikConfiguration

    # --- Infos legales depuis Configuration (singleton du tenant) ---
    # / Legal info from Configuration (tenant singleton)
    config = Configuration.get_solo()
    laboutik_config = LaboutikConfiguration.get_solo()

    # Les dates du ticket, dans le fuseau du lieu : l'encaissement de la vente (la
    # date du justificatif), et le moment de l'impression (lu sur un DUPLICATA).
    # / Receipt dates in the venue's time zone: settlement, and printing time.
    fuseau_du_lieu = config.get_tzinfo()
    date_de_l_encaissement = timezone.localtime(
        vente.datetime_encaissement, fuseau_du_lieu
    )
    date_de_l_impression = timezone.localtime(timezone.now(), fuseau_du_lieu)

    # Le numero : « Avoir n° » pour un avoir, « Vente n° » sinon.
    # / The number: "Avoir n°" for a credit note, "Vente n°" otherwise.
    if vente.nature == Vente.Nature.AVOIR:
        numero_du_ticket = f"{_('Avoir n°')} {vente.numero}"
    else:
        numero_du_ticket = f"{_('Vente n°')} {vente.numero}"

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

    point_de_vente = vente.point_de_vente
    nom_du_point_de_vente = ""
    if point_de_vente is not None:
        nom_du_point_de_vente = point_de_vente.name

    legal = {
        "business_name": config.organisation or "",
        "address": adresse_complete,
        "siret": config.siren or "",
        "tva_number": tva_display,
        "terminal_id": nom_du_point_de_vente,
    }

    # --- La vente : ses lignes, ses reglements, son unite ---
    # / The sale: its lines, payments and unit
    lignes_de_la_vente = list(
        LigneArticle.objects.filter(vente=vente)
        .select_related(
            "pricesold__productsold__product__stock_inventaire",
            "pricesold__productsold__event",
            "pricesold__price",
        )
        .order_by("datetime", "pk")
    )
    reglements_de_la_vente = list(vente.reglements.all())
    nom_par_uuid_de_monnaie = noms_des_monnaies_des_ventes([vente])
    nom_de_l_unite = nom_de_l_unite_de_la_vente(vente, nom_par_uuid_de_monnaie)
    ticket_en_points = nom_de_l_unite != ""
    unite_du_ticket = "EUR"
    suffixe_de_l_unite = "EUR"
    if ticket_en_points:
        unite_du_ticket = nom_de_l_unite
        suffixe_de_l_unite = f" {nom_de_l_unite}"

    # --- Les articles : ceux du detail de la vente a l'ecran ---
    # / Items: the same as the sale detail screen
    articles_affiches = articles_de_la_vente_pour_l_affichage(
        lignes_de_la_vente, nom_de_l_unite
    )
    articles = []
    for article_affiche in articles_affiches:
        # Quantite lisible sur le papier : un entier quand elle est entiere, sinon
        # deux decimales. Jamais un Decimal : le ticket part en JSON (Celery).
        # / Readable quantity: an int when whole, else two decimals. Never a Decimal.
        # Une vente au poids ou au volume imprime sa quantité avec son unité
        # (« 0,350 kg ») : un nombre seul serait lu comme un nombre d'articles.
        # / A weight / volume sale prints its quantity with its unit.
        quantite_totale = article_affiche["quantite"]
        if article_affiche["est_vrac"]:
            quantite_imprimee = article_affiche["quantite_lisible"]
        elif quantite_totale == quantite_totale.to_integral_value():
            quantite_imprimee = int(quantite_totale)
        else:
            quantite_imprimee = f"{quantite_totale:.2f}"

        # Le nom imprime : le produit, puis le tarif s'il est different (« Biere
        # Demi »), puis l'evenement et sa date (« - Concert 12/10 »).
        # / Printed name: product, then the price name if different, then the event
        #   and its date.
        nom_imprime = article_affiche["nom"]
        if article_affiche["tarif"] and article_affiche["tarif"] != article_affiche["nom"]:
            nom_imprime = f"{nom_imprime} {article_affiche['tarif']}"
        if article_affiche["evenement"]:
            nom_imprime = f"{nom_imprime} - {article_affiche['evenement']}"
            if article_affiche["date_de_l_evenement"] is not None:
                date_locale_de_l_evenement = timezone.localtime(
                    article_affiche["date_de_l_evenement"], fuseau_du_lieu
                )
                nom_imprime = (
                    f"{nom_imprime} {date_locale_de_l_evenement.strftime('%d/%m')}"
                )

        article_du_ticket = {
            "name": nom_imprime,
            "qty": quantite_imprimee,
            "price": article_affiche["prix_unitaire"],
            "total": article_affiche["total"],
            "offert": article_affiche["part_offerte"],
        }

        # La part offerte, sous l'article : le total de l'article est son net vendu.
        # / The offered part, under the item: the item total is its net sold.
        if article_affiche["part_offerte"]:
            montant_offert = f"{article_affiche['part_offerte'] / 100:.2f}"
            article_du_ticket["detail_offert"] = (
                f"  {_('Offert')}: {montant_offert}{suffixe_de_l_unite}"
            )

        # Vente au poids ou au volume : la quantité avec son unité et le prix au kg / L,
        # sous l'article (« 0,350 kg x 12,90 €/kg » ; tireuse : « 50cl x 8,00 €/L »).
        # / Weight or volume sale: quantity with its unit and price per kg / L.
        poids_imprimable = (
            article_affiche["est_vrac"] and article_affiche["prix_par_unite"]
        )
        if poids_imprimable:
            # L'ecran ecrit le prix avec une espace insecable ; le papier, avec une
            # espace ordinaire (certaines imprimantes l'impriment mal).
            # / The screen uses a non-breaking space; paper gets a plain one.
            prix_par_unite_pour_le_papier = article_affiche["prix_par_unite"].replace(
                " ", " "
            )
            article_du_ticket["weight_detail"] = (
                f"  {article_affiche['quantite_lisible']}"
                f" x {prix_par_unite_pour_le_papier}"
            )

        articles.append(article_du_ticket)

    # --- TVA par taux : sommes des montants figes sur les lignes ---
    # Une vente en points ou en temps n'est pas de l'argent : pas de TVA.
    # La part payee en jetons cadeau d'une ligne (`part_en_jetons`) est vendue hors
    # TVA : elle va a la ligne du taux 0 (HT = TTC, TVA 0), le reste a son taux.
    # / VAT by rate: sums of the frozen line amounts. No VAT on a points sale. A line's
    # token part goes to the 0 rate row (HT = TTC, VAT 0), the rest to its rate.
    tva_breakdown = []
    total_ht_global = 0
    total_tva_global = 0
    if not ticket_en_points:
        cle_du_taux_zero = f"{Decimal(0):.2f}"
        tva_par_taux = {}
        for ligne in lignes_de_la_vente:
            cle_du_taux = f"{Decimal(ligne.vat or 0):.2f}"
            part_en_jetons = ligne.part_en_jetons
            reste_ht = ligne.total_ht - part_en_jetons
            reste_ttc = ligne.total_ttc - part_en_jetons
            if part_en_jetons != 0:
                _ajouter_a_la_ligne_de_tva(
                    tva_par_taux, cle_du_taux_zero, part_en_jetons, 0, part_en_jetons
                )
            ligne_entierement_en_jetons = (
                part_en_jetons != 0
                and reste_ht == 0
                and reste_ttc == 0
                and ligne.total_tva == 0
            )
            if ligne_entierement_en_jetons:
                continue
            _ajouter_a_la_ligne_de_tva(
                tva_par_taux, cle_du_taux, reste_ht, ligne.total_tva, reste_ttc
            )
        for ligne_de_tva in tva_par_taux.values():
            tva_breakdown.append(ligne_de_tva)
            total_ht_global += ligne_de_tva["ht"]
            total_tva_global += ligne_de_tva["tva"]

    # --- Detail des reglements : comme la liste des ventes, sans l'offert ---
    # / Payments detail: like the sales list, without the offered part
    reglements_affiches = reglements_pour_l_affichage(
        reglements_de_la_vente, nom_par_uuid_de_monnaie, nom_de_l_unite
    )
    cascade_detail = []
    for reglement_affiche in reglements_affiches:
        if reglement_affiche["moyen"] == PaymentMethod.FREE:
            continue
        cascade_detail.append(
            {"name": reglement_affiche["libelle"], "total": reglement_affiche["montant"]}
        )

    # Nom de l'operateur
    # / Operator name
    operateur_name = ""
    if operateur:
        operateur_name = operateur.email if operateur.email else str(operateur)

    # Pied de ticket personnalise, replie en 32 caracteres
    # / Custom receipt footer, folded to 32 characters
    pied_ticket = laboutik_config.pied_ticket or ""
    footer_lines = _lignes_du_pied_du_ticket_de_vente(pied_ticket)
    footer_lines.append(_("Merci de votre visite !"))

    return {
        "header": {
            "title": nom_du_point_de_vente,
            "numero": numero_du_ticket,
            "subtitle": operateur_name,
            "date": date_de_l_encaissement.strftime("%d/%m/%Y %H:%M"),
            "date_d_impression": date_de_l_impression.strftime("%d/%m/%Y %H:%M"),
        },
        "legal": legal,
        "articles": articles,
        "total": {
            "amount": vente.total_ttc,
            "label": "",
        },
        "tva_breakdown": tva_breakdown,
        "total_ht": total_ht_global,
        "total_tva": total_tva_global,
        # Unite des montants : "EUR", ou le nom de la monnaie de points / temps
        # / Amount unit: "EUR", or the points/time currency name
        "unite": unite_du_ticket,
        "cascade_detail": cascade_detail,
        "is_duplicata": False,
        # Mode ecole : les tickets portent la mention "SIMULATION" (LNE exigence 5)
        # / Training mode: receipts carry "SIMULATION" label (LNE req. 5)
        "is_simulation": laboutik_config.mode_ecole,
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

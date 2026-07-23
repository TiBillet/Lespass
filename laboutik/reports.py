"""
Service de calcul des rapports comptables pour la caisse LaBoutik.
/ Accounting report calculation service for the LaBoutik POS.

Utilise par :
- Ticket X (consultation en temps reel, pas de sauvegarde)
- Ticket Z (cloture de caisse, resultat persiste dans ClotureCaisse.rapport_json)

Tous les montants sont en centimes (int). Jamais de float pour les montants.
/ All amounts are in cents (int). Never use float for amounts.

LOCALISATION : laboutik/reports.py
"""

import hashlib
import logging

from django.db.models import Sum, Count, Q, Min, F, IntegerField
from django.db.models.functions import Cast, Round
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import (
    LigneArticle,
    SaleOrigin,
    PaymentMethod,
    Configuration,
    Product,
)
from laboutik.models import (
    LaboutikConfiguration,
    SortieCaisse,
)

logger = logging.getLogger(__name__)


def montant_ttc_centimes():
    """Expression d'agrégation du CA TTC en centimes ENTIERS.

    Le total monétaire d'une LigneArticle = amount × qty (prix unitaire × quantité,
    convention unifiée avec LigneArticle.total). Comme qty peut être fractionnaire
    (cascade NFC multi-asset), le produit est un Decimal sub-centime : on l'ARRONDIT
    au centime DANS la requête (Round) puis on le caste en entier (Cast) pour rester
    en centimes entiers (jamais de float/Decimal qui fuirait dans rapport_json).
    / TTC revenue aggregation in INTEGER cents: amount × qty, rounded to the cent and
    cast to int in the query (qty may be fractional for multi-asset NFC cascades).
    """
    return Cast(
        Round(Sum(F("amount") * F("qty"))),
        output_field=IntegerField(),
    )


# Les origines de vente qui pesent sur le rapport de caisse (ticket X et Z).
# / The sale origins that weigh on the register report (X and Z tickets).
#
# Le critere est : cet encaissement a-t-il eu lieu AU COMPTOIR, dans le perimetre
# que le caissier cloture en fin de service ?
#
# - LABOUTIK : la caisse elle-meme. Y compris le remboursement d'une carte, qui
#   sort des especes du tiroir (cf. WalletService.rembourser_en_especes).
# - TIREUSE : les tireuses connectees. Une biere tiree est une vente du comptoir
#   comme une autre ; elle porte un point de vente et decremente le stock.
#   L'exclure amputerait le chiffre d'affaires et fausserait la marge, puisque le
#   stock serait decompte sans recette en face.
#
# Ce qui reste dehors, volontairement :
#
# - QRCODE_MA et NFC_MA : les encaissements par QR code ou carte NFC. C'est un
#   autre usage que la caisse au comptoir, et les lieux qui pratiquent l'un ne
#   pratiquent pas l'autre. Les melanger dans un meme ticket Z n'aurait de sens
#   pour personne. Un chantier a venir rattachera ces encaissements a un point de
#   vente ; la question de leur place dans la cloture se reposera a ce moment-la.
# - LESPASS, API, WEBHOOK : les ventes en ligne. Elles sont suivies par le
#   service de comptabilite (comptabilite/services.py), qui exclut justement
#   LABOUTIK — les deux perimetres sont complementaires.
# - ADMIN : les operations administratives (avoirs, virements bancaires recus,
#   adhesions saisies a la main). Elles ne passent pas par le tiroir-caisse.
#
# / The test is: did this collection happen AT THE COUNTER, within what the
# cashier closes at the end of service? QR code and NFC collections are a
# different practice — venues doing one do not do the other — and online sales
# are covered by comptabilite/services.py, which excludes LABOUTIK.
ORIGINES_ENCAISSEES_PAR_LE_LIEU = [
    SaleOrigin.LABOUTIK,
    SaleOrigin.TIREUSE,
]


def sections_de_detail_pour_export(rapport_json):
    """
    Traduit un rapport de cloture vers les sections attendues par les exports.
    / Maps a closure report to the sections the exports expect.

    LOCALISATION : laboutik/reports.py

    Le PDF (`laboutik/pdf.py`) et le CSV (`laboutik/csv_export.py`) attendent
    `par_produit`, `par_categorie` et `par_tva`. Le rapport, lui, produit
    `detail_ventes` (groupe par categorie, avec le detail des articles) et `tva`.
    Sans cette traduction, les deux exports lisent des cles absentes et rendent
    des sections vides — sans lever la moindre erreur, puisqu'ils utilisent
    `.get(cle, {})`.

    / The PDF and CSV exports expect par_produit / par_categorie / par_tva, while
    the report produces detail_ventes and tva. Without this mapping both exports
    silently render empty sections, since they use .get(key, {}).

    Les cloture ANCIENNES portent l'ancien format directement dans leur
    `rapport_json` : on le renvoie tel quel plutot que de le reconstruire, pour
    qu'une cloture archivee se reimprime a l'identique.
    / OLD closures carry the old format directly: return it as-is so an archived
    closure reprints identically.

    :param rapport_json: dict stocke dans ClotureCaisse.rapport_json
    :return: dict avec les cles par_produit, par_categorie, par_tva
    """
    rapport_json = rapport_json or {}

    # Cloture d'avant le changement de format : elle porte deja les sections.
    # / Pre-format-change closure: it already carries the sections.
    if "par_produit" in rapport_json or "par_categorie" in rapport_json:
        return {
            "par_produit": rapport_json.get("par_produit", {}),
            "par_categorie": rapport_json.get("par_categorie", {}),
            "par_tva": rapport_json.get("par_tva", {}),
        }

    detail_ventes = rapport_json.get("detail_ventes", {})

    # `detail_ventes` groupe par categorie ; les exports veulent une liste plate
    # d'articles. Un meme produit peut apparaitre sous deux taux de TVA : on
    # cumule alors ses montants et ses quantites sous un seul nom.
    # / detail_ventes groups by category; the exports want a flat article list.
    # A product may appear under two VAT rates: we sum its amounts under one name.
    par_produit = {}
    par_categorie = {}
    for nom_categorie, donnees_categorie in detail_ventes.items():
        par_categorie[nom_categorie] = donnees_categorie.get("total_ttc", 0)

        for article in donnees_categorie.get("articles", []):
            nom_article = article.get("nom")
            if nom_article not in par_produit:
                par_produit[nom_article] = {"total": 0, "qty": 0}
            par_produit[nom_article]["total"] += article.get("total_ttc", 0)
            par_produit[nom_article]["qty"] += article.get("qty_total", 0)

    return {
        "par_produit": par_produit,
        "par_categorie": par_categorie,
        # `tva` porte deja exactement la forme attendue : un dictionnaire indexe
        # par libelle de taux, avec taux / total_ht / total_tva / total_ttc.
        # / `tva` already has the expected shape.
        "par_tva": rapport_json.get("tva", {}),
    }


class RapportComptableService:
    """
    Calcule les rapports comptables pour une periode et un point de vente donnes.
    Chaque methode retourne un dict serialisable JSON.
    / Calculates accounting reports for a given period and point of sale.
    Each method returns a JSON-serializable dict.
    """

    def __init__(self, point_de_vente, datetime_debut, datetime_fin):
        """
        Initialise le service avec le point de vente et la periode.
        / Initialize the service with the point of sale and the period.

        :param point_de_vente: PointDeVente instance
        :param datetime_debut: debut de la periode (datetime avec timezone)
        :param datetime_fin: fin de la periode (datetime avec timezone)
        """
        self.pv = point_de_vente
        self.debut = datetime_debut
        self.fin = datetime_fin

        # Queryset de base : lignes valides encaissees par le lieu dans la periode.
        # / Base queryset: valid lines collected by the venue within the period.
        self.lignes = LigneArticle.objects.filter(
            sale_origin__in=ORIGINES_ENCAISSEES_PAR_LE_LIEU,
            datetime__gte=self.debut,
            datetime__lte=self.fin,
            status=LigneArticle.VALID,
        ).select_related(
            "pricesold__productsold__product__categorie_pos",
            "carte",
        )

    # ------------------------------------------------------------------
    # 1. Totaux par moyen de paiement / Totals by payment method
    # ------------------------------------------------------------------
    def calculer_totaux_par_moyen(self):
        """
        Especes (CA), CB (CC), cashless local (LE+LG), cheque (CH), federe (SF), total.
        Enrichi avec le detail cashless par asset et le code devise.
        Le federe (FED reseau) est DISTINCT du cashless local — confusion de compta a ne jamais refaire.
        / Cash, credit card, local cashless, check, federated (FED network), total.
        Enriched with cashless detail by asset and currency code.
        """
        total_especes = (
            self.lignes.filter(
                payment_method=PaymentMethod.CASH,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        total_carte_bancaire = (
            self.lignes.filter(
                payment_method=PaymentMethod.CC,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        # NFC / cashless : LOCAL_EURO (monnaie fiduciaire) + LOCAL_GIFT (cadeau)
        # / NFC / cashless: LOCAL_EURO (fiat) + LOCAL_GIFT (gift)
        total_cashless = (
            self.lignes.filter(
                payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        total_cheque = (
            self.lignes.filter(
                payment_method=PaymentMethod.CHEQUE,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        # Federe : monnaie FED du reseau (Fedow distant), DISTINCTE du cashless local.
        # Le FED a son propre moyen de paiement (STRIPE_FED) — ne jamais le melanger au cashless.
        # / Federated: FED network currency (remote Fedow), DISTINCT from local cashless.
        # FED has its own payment method (STRIPE_FED) — never mix it with local cashless.
        total_federe = (
            self.lignes.filter(
                payment_method=PaymentMethod.STRIPE_FED,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        total_general = (
            total_especes
            + total_carte_bancaire
            + total_cashless
            + total_cheque
            + total_federe
        )

        # Detail cashless par nom de monnaie (pas par UUID d'asset).
        # En test, il peut y avoir des dizaines d'assets avec le meme nom.
        # On regroupe par nom pour avoir une seule ligne par monnaie.
        # / Cashless detail by currency name (not by asset UUID).
        # In test, there can be dozens of assets with the same name.
        # We group by name to get one line per currency.
        cashless_detail = []
        lignes_cashless_par_asset = (
            self.lignes.filter(
                payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
                asset__isnull=False,
            )
            .values("asset")
            .annotate(
                montant=montant_ttc_centimes(),
            )
            .order_by("-montant")
        )

        # Prefetch tous les assets en une seule requete (evite N+1)
        # / Prefetch all assets in one query (avoids N+1)
        from fedow_core.models import Asset as FedowAsset

        asset_uuids = [ligne["asset"] for ligne in lignes_cashless_par_asset]
        assets_par_uuid = {
            a.uuid: a for a in FedowAsset.objects.filter(uuid__in=asset_uuids)
        }

        # Regrouper par nom de monnaie (pas par UUID)
        # / Group by currency name (not by UUID)
        totaux_par_nom_monnaie = {}
        for ligne in lignes_cashless_par_asset:
            asset_uuid = ligne["asset"]
            montant = ligne["montant"] or 0
            asset_obj = assets_par_uuid.get(asset_uuid)
            nom_asset = asset_obj.name if asset_obj else str(_("Inconnu"))
            code_asset = asset_obj.currency_code if asset_obj else ""

            if nom_asset not in totaux_par_nom_monnaie:
                totaux_par_nom_monnaie[nom_asset] = {
                    "nom": nom_asset,
                    "code": code_asset,
                    "montant": 0,
                }
            totaux_par_nom_monnaie[nom_asset]["montant"] += montant

        for nom_monnaie in totaux_par_nom_monnaie:
            cashless_detail.append(totaux_par_nom_monnaie[nom_monnaie])

        config_tenant = Configuration.get_solo()
        code_devise = config_tenant.currency_code or "EUR"

        return {
            "especes": total_especes,
            "carte_bancaire": total_carte_bancaire,
            "cashless": total_cashless,
            "cashless_detail": cashless_detail,
            "cheque": total_cheque,
            "federe": total_federe,
            "total": total_general,
            "currency_code": code_devise,
        }

    # ------------------------------------------------------------------
    # 2. Detail des ventes par article, groupe par categorie
    # / Sales detail by article, grouped by category
    # ------------------------------------------------------------------
    def calculer_detail_ventes(self):
        """
        Par article avec qty vendus/offerts, CA TTC/HT, TVA, cout, benefice.
        Groupe par categorie.
        / By article with sold/gifted qty, revenue incl./excl. tax, VAT, cost, profit.
        Grouped by category.
        """
        produits_agreg = (
            self.lignes.values(
                "pricesold__productsold__product__name",
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__prix_achat",
                "vat",
                "payment_method",
            )
            .annotate(
                total_ttc=montant_ttc_centimes(),
                total_qty=Sum("qty"),
            )
            .order_by(
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__name",
            )
        )

        # Methodes de paiement "cadeau" / Gift payment methods
        methodes_cadeau = [PaymentMethod.LOCAL_GIFT]
        if hasattr(PaymentMethod, "EXTERIEUR_GIFT"):
            methodes_cadeau.append(PaymentMethod.EXTERIEUR_GIFT)

        # Regrouper par (categorie, produit, taux_tva) en separant vendus/offerts
        # / Group by (category, product, vat_rate) separating sold/gifted
        cle_articles = {}
        for ligne in produits_agreg:
            nom_categorie = ligne[
                "pricesold__productsold__product__categorie_pos__name"
            ] or str(_("Sans catégorie"))
            nom_produit = ligne["pricesold__productsold__product__name"] or str(
                _("Inconnu")
            )
            prix_achat_unit = ligne["pricesold__productsold__product__prix_achat"] or 0
            total_ttc = ligne["total_ttc"] or 0
            total_qty = float(ligne["total_qty"] or 0)
            taux_tva = float(ligne["vat"] or 0)
            moyen_paiement = ligne["payment_method"]

            cle = f"{nom_categorie}|{nom_produit}|{taux_tva}"
            if cle not in cle_articles:
                cle_articles[cle] = {
                    "categorie": nom_categorie,
                    "nom": nom_produit,
                    "taux_tva": taux_tva,
                    "prix_achat_unit": prix_achat_unit,
                    "qty_vendus": 0.0,
                    "qty_offerts": 0.0,
                    "ttc_vendus": 0,
                    "ttc_offerts": 0,
                }

            if moyen_paiement in methodes_cadeau:
                cle_articles[cle]["qty_offerts"] += total_qty
                cle_articles[cle]["ttc_offerts"] += total_ttc
            else:
                cle_articles[cle]["qty_vendus"] += total_qty
                cle_articles[cle]["ttc_vendus"] += total_ttc

        # Construire la structure finale par categorie
        # / Build final structure by category
        categories = {}
        for cle, article in cle_articles.items():
            nom_categorie = article["categorie"]
            qty_total = article["qty_vendus"] + article["qty_offerts"]
            total_ttc = article["ttc_vendus"] + article["ttc_offerts"]
            taux_tva = article["taux_tva"]

            # Calcul HT depuis TTC : HT = TTC / (1 + taux/100)
            # / Compute excl. tax from incl. tax: HT = TTC / (1 + rate/100)
            if taux_tva > 0:
                total_ht = int(round(total_ttc / (1 + taux_tva / 100)))
            else:
                total_ht = total_ttc
            total_tva = total_ttc - total_ht

            cout_total = article["prix_achat_unit"] * int(qty_total)
            benefice = total_ht - cout_total

            # Poids/volume total vendu pour cet article (somme des weight_quantity)
            # + unite (GR / CL) lue sur Stock du produit en une seule query.
            # Null si l'article ne se vend pas au poids.
            # / Total weight/volume sold for this article (sum of weight_quantity)
            # + unit (GR / CL) read from product Stock in a single query.
            # Null if the article is not sold by weight.
            poids_total_agreg = self.lignes.filter(
                pricesold__productsold__product__name=article["nom"],
                vat=taux_tva,
                weight_quantity__isnull=False,
            ).aggregate(
                total=Sum("weight_quantity"),
                unite=Min(
                    "pricesold__productsold__product__stock_inventaire__unite"
                ),
            )
            poids_total = poids_total_agreg["total"]
            unite_poids = poids_total_agreg["unite"]  # "GR" / "CL" / None

            if nom_categorie not in categories:
                categories[nom_categorie] = {"articles": [], "total_ttc": 0}

            categories[nom_categorie]["articles"].append(
                {
                    "nom": article["nom"],
                    "qty_vendus": article["qty_vendus"],
                    "qty_offerts": article["qty_offerts"],
                    "qty_total": qty_total,
                    "total_ttc": total_ttc,
                    "total_ht": total_ht,
                    "total_tva": total_tva,
                    "taux_tva": taux_tva,
                    "prix_achat_unit": article["prix_achat_unit"],
                    "cout_total": cout_total,
                    "benefice": benefice,
                    "poids_total": poids_total,  # int en g ou cl, ou None si pas de vente au poids
                    "unite_poids": unite_poids,  # "GR" / "CL" / None — unite du Stock pour conversion d'affichage
                }
            )
            categories[nom_categorie]["total_ttc"] += total_ttc

        # Trier les categories : alphabetique, "Sans catégorie" en dernier.
        # / Sort categories: alphabetical, "Uncategorized" last.
        nom_sans_categorie = str(_("Sans catégorie"))
        categories_triees = {}
        for nom in sorted(categories.keys()):
            if nom != nom_sans_categorie:
                categories_triees[nom] = categories[nom]
        # Ajouter "Sans catégorie" a la fin si elle existe
        # / Add "Uncategorized" at the end if it exists
        if nom_sans_categorie in categories:
            categories_triees[nom_sans_categorie] = categories[nom_sans_categorie]

        return categories_triees

    # ------------------------------------------------------------------
    # 3. TVA par taux / VAT by rate
    # ------------------------------------------------------------------
    def calculer_tva(self):
        """
        Par taux de TVA : total_ttc, total_ht, total_tva.
        Logique identique a views.py:1020-1043.
        / By VAT rate: total incl., excl., VAT amount.
        """
        tva_agreg = (
            self.lignes.values("vat")
            .annotate(
                total_ttc=montant_ttc_centimes(),
            )
            .order_by("vat")
        )

        rapport_par_tva = {}
        for ligne in tva_agreg:
            taux_tva = float(ligne["vat"] or 0)
            total_ttc_centimes = ligne["total_ttc"] or 0

            # Calcul HT depuis TTC : HT = TTC / (1 + taux/100)
            # / Compute HT from TTC: HT = TTC / (1 + rate/100)
            if taux_tva > 0:
                total_ht_centimes = int(
                    round(total_ttc_centimes / (1 + taux_tva / 100))
                )
                total_tva_centimes = total_ttc_centimes - total_ht_centimes
            else:
                total_ht_centimes = total_ttc_centimes
                total_tva_centimes = 0

            cle_tva = f"{taux_tva:.2f}%"
            rapport_par_tva[cle_tva] = {
                "taux": taux_tva,
                "total_ttc": total_ttc_centimes,
                "total_ht": total_ht_centimes,
                "total_tva": total_tva_centimes,
            }

        return rapport_par_tva

    # ------------------------------------------------------------------
    # 4. Solde de caisse / Cash drawer balance
    # ------------------------------------------------------------------
    def calculer_solde_caisse(self):
        """
        Fond de caisse + total especes - sorties de caisse de la periode.
        Le solde represente ce qui est physiquement dans le tiroir-caisse.
        / Cash float + total cash - cash withdrawals for the period.
        Balance represents what's physically in the cash drawer.

        LOCALISATION : laboutik/reports.py
        """
        config = LaboutikConfiguration.get_solo()
        fond_de_caisse = config.fond_de_caisse or 0

        entrees_especes = (
            self.lignes.filter(
                payment_method=PaymentMethod.CASH,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )

        # Soustraire les sorties de caisse effectuees pendant la periode.
        # Pas de filtre par point de vente : la caisse est globale au tenant
        # (meme logique que la cloture ClotureCaisse).
        # / Subtract cash withdrawals made during the period.
        # No point_de_vente filter: the cash drawer is global per tenant
        # (same logic as ClotureCaisse closure).
        sorties_especes = (
            SortieCaisse.objects.filter(
                datetime__gte=self.debut,
                datetime__lte=self.fin,
            ).aggregate(total=Sum("montant_total"))["total"]
            or 0
        )

        return {
            "fond_de_caisse": fond_de_caisse,
            "entrees_especes": entrees_especes,
            "sorties_especes": sorties_especes,
            "solde": fond_de_caisse + entrees_especes - sorties_especes,
        }

    # ------------------------------------------------------------------
    # 5. Recharges cashless / Cashless top-ups
    # ------------------------------------------------------------------
    def calculer_recharges(self):
        """
        Filtre les lignes dont le produit a methode_caisse in (RE, RC, TM).
        Agrege par nom de monnaie (asset) et par moyen de paiement.
        / Filter lines whose product has methode_caisse in (RE, RC, TM).
        Aggregate by currency name (asset) and payment method.
        """
        methodes_recharge = [
            Product.RECHARGE_EUROS,
            Product.RECHARGE_CADEAU,
            Product.RECHARGE_TEMPS,
        ]

        recharges = (
            self.lignes.filter(
                pricesold__productsold__product__methode_caisse__in=methodes_recharge,
            )
            .values(
                "pricesold__productsold__product__name",
                "pricesold__productsold__product__methode_caisse",
                "payment_method",
                "asset",
            )
            .annotate(
                total=montant_ttc_centimes(),
                nb=Count("uuid"),
            )
            .order_by("pricesold__productsold__product__name")
        )

        # Prefetch les noms des assets pour afficher le nom de la monnaie
        # / Prefetch asset names to display the currency name
        from fedow_core.models import Asset as FedowAsset

        asset_uuids = [l["asset"] for l in recharges if l.get("asset")]
        assets_par_uuid = {}
        if asset_uuids:
            assets_par_uuid = {
                a.uuid: a for a in FedowAsset.objects.filter(uuid__in=asset_uuids)
            }

        resultat = {}
        for ligne in recharges:
            nom_produit = ligne["pricesold__productsold__product__name"] or "?"
            methode = ligne["pricesold__productsold__product__methode_caisse"]
            moyen = ligne["payment_method"] or "UK"

            # Nom de la monnaie depuis l'asset (si disponible)
            # / Currency name from asset (if available)
            asset_uuid = ligne.get("asset")
            asset_obj = assets_par_uuid.get(asset_uuid) if asset_uuid else None
            nom_monnaie = asset_obj.name if asset_obj else ""

            cle = f"{nom_produit}_{moyen}"
            resultat[cle] = {
                "nom_produit": nom_produit,
                "nom_monnaie": nom_monnaie,
                "methode_caisse": methode,
                "moyen_paiement": moyen,
                "total": ligne["total"] or 0,
                "nb": ligne["nb"] or 0,
            }

        # Total general des recharges / Overall top-up total
        total_recharges = sum(v["total"] for v in resultat.values())
        return {
            "detail": resultat,
            "total": total_recharges,
        }

    # ------------------------------------------------------------------
    # 6. Adhesions / Memberships
    # ------------------------------------------------------------------
    def calculer_adhesions(self):
        """
        Lignes avec membership non null. Classe par produit, tarif et moyen de paiement.
        / Lines with non-null membership. Grouped by product, price tier and payment method.
        """
        adhesions = (
            self.lignes.filter(
                membership__isnull=False,
            )
            .values(
                "pricesold__productsold__product__name",
                "pricesold__price__name",
                "payment_method",
            )
            .annotate(
                total=montant_ttc_centimes(),
                nb=Count("uuid"),
            )
            .order_by("pricesold__productsold__product__name", "pricesold__price__name")
        )

        detail = {}
        for ligne in adhesions:
            nom_produit = ligne["pricesold__productsold__product__name"] or str(
                _("Inconnu")
            )
            nom_tarif = ligne["pricesold__price__name"] or ""
            moyen = ligne["payment_method"] or "UK"

            # Cle : "Produit — Tarif (moyen)" pour regroupement unique
            # / Key: "Product — Price tier (method)" for unique grouping
            label_tarif = f"{nom_produit} — {nom_tarif}" if nom_tarif else nom_produit
            cle = f"{label_tarif}_{moyen}"
            detail[cle] = {
                "nom_produit": nom_produit,
                "nom_tarif": nom_tarif,
                "moyen_paiement": moyen,
                "total": ligne["total"] or 0,
                "nb": ligne["nb"] or 0,
            }

        total_adhesions = sum(v["total"] for v in detail.values())
        nb_adhesions = sum(v["nb"] for v in detail.values())
        return {
            "detail": detail,
            "total": total_adhesions,
            "nb": nb_adhesions,
        }

    # ------------------------------------------------------------------
    # 7. Remboursements / Refunds
    # ------------------------------------------------------------------
    def calculer_remboursements(self):
        """
        Lignes avec statut CREDIT_NOTE ou montant negatif.
        On elargit le filtre status pour inclure les avoirs.
        / Lines with CREDIT_NOTE status or negative amount.
        We widen the status filter to include credit notes.
        """
        # Les avoirs (CREDIT_NOTE) ne sont pas dans self.lignes (filtre VALID).
        # On fait une requete separee.
        # / Credit notes are not in self.lignes (VALID filter).
        # We make a separate query.
        remboursements = (
            LigneArticle.objects.filter(
                sale_origin__in=ORIGINES_ENCAISSEES_PAR_LE_LIEU,
                datetime__gte=self.debut,
                datetime__lte=self.fin,
            )
            .filter(
                Q(status=LigneArticle.CREDIT_NOTE) | Q(amount__lt=0),
            )
            .aggregate(
                total=montant_ttc_centimes(),
                nb=Count("uuid"),
            )
        )

        return {
            "total": remboursements["total"] or 0,
            "nb": remboursements["nb"] or 0,
        }

    # ------------------------------------------------------------------
    # 8. Habitus (cartes NFC distinctes) / NFC card stats
    # ------------------------------------------------------------------
    def calculer_habitus(self):
        """
        Statistiques cartes NFC : nb cartes, panier moyen, medianes, soldes wallets.
        / NFC card stats: card count, average basket, medians, wallet balances.
        """
        import statistics

        # Depenses par carte dans la periode / Spending per card in period
        depenses_par_carte = list(
            self.lignes.filter(
                carte__isnull=False,
            )
            .values("carte")
            .annotate(
                total=montant_ttc_centimes(),
            )
            .values_list("total", flat=True)
        )

        nb_cartes = len(depenses_par_carte)
        total = sum(d or 0 for d in depenses_par_carte)
        panier_moyen = int(round(total / nb_cartes)) if nb_cartes > 0 else 0

        depense_mediane = 0
        if nb_cartes > 0:
            depense_mediane = int(statistics.median(depenses_par_carte))

        # Recharges par carte dans la periode / Top-ups per card in period
        recharges_par_carte = list(
            self.lignes.filter(
                carte__isnull=False,
                pricesold__productsold__product__methode_caisse__in=[
                    Product.RECHARGE_EUROS,
                    Product.RECHARGE_CADEAU,
                    Product.RECHARGE_TEMPS,
                ],
            )
            .values("carte")
            .annotate(
                total=montant_ttc_centimes(),
            )
            .values_list("total", flat=True)
        )

        recharge_mediane = 0
        if recharges_par_carte:
            recharge_mediane = int(statistics.median(recharges_par_carte))

        # Soldes des wallets lies aux cartes actives (via fedow_core.Token)
        # / Wallet balances for active cards (via fedow_core.Token)
        reste_moyenne = 0
        med_on_card = 0
        try:
            from fedow_core.models import Token as FedowToken, Asset as FedowAsset
            from QrcodeCashless.models import CarteCashless

            cartes_actives_ids = (
                self.lignes.filter(
                    carte__isnull=False,
                )
                .values_list("carte", flat=True)
                .distinct()
            )

            # Recuperer les wallets via CarteCashless.user.wallet
            # / Get wallets via CarteCashless.user.wallet
            wallets_ids = CarteCashless.objects.filter(
                pk__in=cartes_actives_ids,
                user__isnull=False,
                user__wallet__isnull=False,
            ).values_list("user__wallet", flat=True)

            # Soldes en monnaie locale (TLF) / Balances in local currency (TLF)
            soldes = list(
                FedowToken.objects.filter(
                    wallet__in=wallets_ids,
                    asset__category=FedowAsset.TLF,
                ).values_list("value", flat=True)
            )

            if soldes:
                reste_moyenne = int(round(sum(soldes) / len(soldes)))
                med_on_card = int(statistics.median(soldes))
        except Exception as erreur_soldes:
            # fedow_core pas encore actif ou pas de donnees
            # / fedow_core not yet active or no data
            logger.warning("Calcul soldes wallets impossible : %s", erreur_soldes)
            pass

        # Nouveaux membres dans la periode / New members in period
        from BaseBillet.models import Membership

        nouveaux_membres = Membership.objects.filter(
            date_added__gte=self.debut,
            date_added__lte=self.fin,
        ).count()

        return {
            "nb_cartes": nb_cartes,
            "total": total,
            "panier_moyen": panier_moyen,
            "depense_mediane": depense_mediane,
            "recharge_mediane": recharge_mediane,
            "reste_moyenne": reste_moyenne,
            "med_on_card": med_on_card,
            "nouveaux_membres": nouveaux_membres,
        }

    # ------------------------------------------------------------------
    # 9. Billets / Tickets (reservations)
    # ------------------------------------------------------------------
    def calculer_billets(self):
        """
        Lignes avec reservation non null.
        Classe par evenement (date + nom) et par tarif (produit + prix).
        / Lines with non-null reservation.
        Grouped by event (date + name) and by price tier (product + price name).
        """
        billets = (
            self.lignes.filter(
                reservation__isnull=False,
            )
            .values(
                "reservation__event__name",
                "reservation__event__datetime",
                "pricesold__productsold__product__name",
                "pricesold__price__name",
            )
            .annotate(
                nb=Count("uuid"),
                total=montant_ttc_centimes(),
            )
            .order_by("reservation__event__datetime", "reservation__event__name")
        )

        detail = {}
        for ligne in billets:
            nom_event = ligne["reservation__event__name"] or str(_("Inconnu"))
            datetime_event = ligne["reservation__event__datetime"]
            nom_produit = ligne["pricesold__productsold__product__name"] or ""
            nom_tarif = ligne["pricesold__price__name"] or ""

            # Formater la date de l'event si disponible
            # / Format event date if available
            date_str = ""
            if datetime_event:
                from django.utils import timezone as tz

                date_str = tz.localtime(datetime_event).strftime("%d/%m/%Y %H:%M")

            # Cle : "Event (date) — Produit / Tarif"
            # / Key: "Event (date) — Product / Price tier"
            label_event = f"{nom_event} ({date_str})" if date_str else nom_event
            label_tarif = f"{nom_produit} / {nom_tarif}" if nom_tarif else nom_produit
            cle = f"{label_event}__{label_tarif}"

            detail[cle] = {
                "nom_event": nom_event,
                "date_event": date_str,
                "nom_produit": nom_produit,
                "nom_tarif": nom_tarif,
                "nb": ligne["nb"] or 0,
                "total": ligne["total"] or 0,
            }

        nb_total = sum(v["nb"] for v in detail.values())
        total_montant = sum(v["total"] for v in detail.values())
        return {
            "detail": detail,
            "nb": nb_total,
            "total": total_montant,
        }

    # ------------------------------------------------------------------
    # 10. Synthese des operations / Operations summary
    # ------------------------------------------------------------------
    def calculer_synthese_operations(self):
        """
        Tableau croise type (vente/recharge/adhesion/billet) x moyen (espece/cb/nfc).
        / Cross-table: type (sale/top-up/membership/ticket) x method (cash/card/nfc).
        """
        # Definir les filtres par type d'operation
        # / Define filters by operation type
        types_operations = {
            "ventes": Q(pricesold__productsold__product__methode_caisse=Product.VENTE),
            "recharges": Q(
                pricesold__productsold__product__methode_caisse__in=[
                    Product.RECHARGE_EUROS,
                    Product.RECHARGE_CADEAU,
                    Product.RECHARGE_TEMPS,
                ]
            ),
            "adhesions": Q(membership__isnull=False),
            "billets": Q(reservation__isnull=False),
        }

        # Moyens de paiement regroupes / Grouped payment methods
        moyens = {
            "especes": Q(payment_method=PaymentMethod.CASH),
            "carte_bancaire": Q(payment_method=PaymentMethod.CC),
            "cashless": Q(
                payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT]
            ),
            "cheque": Q(payment_method=PaymentMethod.CHEQUE),
        }

        synthese = {}
        for nom_type, filtre_type in types_operations.items():
            ligne = {}
            for nom_moyen, filtre_moyen in moyens.items():
                montant = (
                    self.lignes.filter(filtre_type & filtre_moyen).aggregate(
                        total=montant_ttc_centimes(),
                    )["total"]
                    or 0
                )
                ligne[nom_moyen] = montant
            ligne["total"] = sum(ligne.values())
            synthese[nom_type] = ligne

        return synthese

    # ------------------------------------------------------------------
    # 11. Operateurs / Operators
    # ------------------------------------------------------------------
    def calculer_operateurs(self):
        """
        Grouper par operateur. Pour l'instant retourne un dict vide
        (le champ operateur sur LigneArticle n'existe pas encore).
        / Group by operator. Returns empty dict for now
        (operator field on LigneArticle doesn't exist yet).
        """
        return {}

    # ------------------------------------------------------------------
    # 12. Ventilation du CA par point de vente / Revenue breakdown by POS
    # ------------------------------------------------------------------
    def calculer_ventilation_par_pv(self):
        """
        Chiffre d'affaires par point de vente.
        Utilise la FK point_de_vente sur LigneArticle.
        / Revenue per point of sale.
        Uses the point_de_vente FK on LigneArticle.

        LOCALISATION : laboutik/reports.py
        """
        resultats = (
            self.lignes.filter(
                point_de_vente__isnull=False,
            )
            .values(
                "point_de_vente__name",
                "point_de_vente__uuid",
            )
            .annotate(
                total_ttc=montant_ttc_centimes(),
            )
            .order_by("-total_ttc")
        )

        ventilation = []
        for ligne in resultats:
            ventilation.append(
                {
                    "nom": ligne["point_de_vente__name"],
                    "uuid": str(ligne["point_de_vente__uuid"]),
                    "total_ttc": ligne["total_ttc"] or 0,
                }
            )

        # Lignes sans PV (anciennes donnees avant la FK)
        # / Lines without PV (old data before FK was added)
        total_sans_pv = (
            self.lignes.filter(
                point_de_vente__isnull=True,
            ).aggregate(total=montant_ttc_centimes())["total"]
            or 0
        )
        if total_sans_pv > 0:
            ventilation.append(
                {
                    "nom": str(_("Non attribué")),
                    "uuid": "",
                    "total_ttc": total_sans_pv,
                }
            )

        return ventilation

    # ------------------------------------------------------------------
    # 13. Infos legales / Legal information
    # ------------------------------------------------------------------
    def _infos_legales(self):
        """
        Lit Configuration.get_solo() (SHARED_APPS BaseBillet) pour SIRET, adresse, etc.
        / Reads Configuration.get_solo() for SIRET, address, etc.
        """
        config = Configuration.get_solo()
        return {
            "organisation": config.organisation or "",
            "adresse": config.adress or "",
            "code_postal": config.postal_code or "",
            "ville": config.city or "",
            "siren": config.siren or "",
            "tva_number": config.tva_number or "",
            "email": config.email or "",
            "phone": config.phone or "",
        }

    # ------------------------------------------------------------------
    # Rapport complet / Full report
    # ------------------------------------------------------------------
    def generer_rapport_complet(self):
        """
        Appelle les 13 methodes et retourne un dict avec 13 cles.
        / Calls all 13 methods and returns a dict with 13 keys.
        """
        return {
            "totaux_par_moyen": self.calculer_totaux_par_moyen(),
            "detail_ventes": self.calculer_detail_ventes(),
            "tva": self.calculer_tva(),
            "solde_caisse": self.calculer_solde_caisse(),
            "recharges": self.calculer_recharges(),
            "adhesions": self.calculer_adhesions(),
            "remboursements": self.calculer_remboursements(),
            "habitus": self.calculer_habitus(),
            "billets": self.calculer_billets(),
            "synthese_operations": self.calculer_synthese_operations(),
            "operateurs": self.calculer_operateurs(),
            "ventilation_par_pv": self.calculer_ventilation_par_pv(),
            "infos_legales": self._infos_legales(),
        }

    # ------------------------------------------------------------------
    # Hash des lignes couvertes / Hash of covered lines
    # ------------------------------------------------------------------
    def calculer_hash_lignes(self):
        """
        SHA-256 des lignes couvertes par la periode.
        Filet de securite pour la cloture : garantit qu'aucune ligne
        n'a ete ajoutee/modifiee entre le calcul du rapport et la sauvegarde.
        / SHA-256 of lines covered by the period.
        Safety net for closure: ensures no line was added/modified
        between report calculation and save.
        """
        # Ordonner par uuid pour un hash deterministe
        # / Order by uuid for a deterministic hash
        lignes_ordonnees = self.lignes.order_by("uuid").values_list(
            "uuid",
            "amount",
            "status",
        )

        hasher = hashlib.sha256()
        for uuid_val, montant, statut in lignes_ordonnees:
            # Chaque ligne contribue : uuid|montant|statut
            # / Each line contributes: uuid|amount|status
            hasher.update(f"{uuid_val}|{montant}|{statut}".encode("utf-8"))

        return hasher.hexdigest()

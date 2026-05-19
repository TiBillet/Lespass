"""
Service de calcul des rapports comptables — app comptabilite V1.
/ Accounting report calculation service — comptabilite app V1.

LOCALISATION : comptabilite/services.py

Adapte de laboutik/reports.py (V2) pour le perimetre V1 :
- Reservations evenements + adhesions uniquement
- Pas de POS (LaBoutik), pas de stats NFC/Fedow
- Pas de fond de caisse, pas de recharges cashless

Tous les montants sont en CENTIMES (int). Jamais de float.
/ All amounts are in CENTS (int). Never float.
"""
import copy
import hashlib
import logging
from decimal import Decimal

from django.db import connection
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class RapportComptableService:
    """
    Calcule un rapport comptable agrege pour une periode.
    / Calculates an aggregated accounting report for a period.

    Service stateless : on l'instancie pour une periode, on appelle
    generer_rapport_complet(), on recupere un dict pret a stocker dans
    ClotureCaisse.rapport_json.
    """

    def __init__(self, datetime_debut, datetime_fin):
        self.datetime_debut = datetime_debut
        self.datetime_fin = datetime_fin
        self.queryset = self._base_queryset()

    def _base_queryset(self):
        """
        Queryset de base : lignes eligibles pour la cloture comptable V1.
        Exclut LABOUTIK (POS), garde V/P/F/N.
        / Base queryset: lines eligible for the V1 accounting closure.
        """
        from BaseBillet.models import LigneArticle, SaleOrigin
        return LigneArticle.objects.filter(
            datetime__gte=self.datetime_debut,
            datetime__lt=self.datetime_fin,
            status__in=[
                LigneArticle.VALID,
                LigneArticle.PAID,
                LigneArticle.FREERES,
                LigneArticle.CREDIT_NOTE,
            ],
        ).exclude(sale_origin=SaleOrigin.LABOUTIK).select_related(
            "pricesold__productsold__product",
            "reservation__event",
            "membership__price",
        )

    # ------------------------------------------------------------------
    # 1. Totaux par moyen de paiement / Totals by payment method
    # ------------------------------------------------------------------
    def calculer_totaux_par_moyen(self) -> dict:
        """
        Totaux par PaymentMethod (12 valeurs possibles + UNKNOWN).
        / Totals per PaymentMethod (12 values + UNKNOWN).

        Total = Sum(amount * qty) : amount est unitaire (centimes),
        qty est decimal. Cast en int apres aggregate.
        """
        from BaseBillet.models import PaymentMethod

        agrege = (
            self.queryset
            .values("payment_method")
            .annotate(
                total_decimal=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
                nb=Count("pk"),
            )
        )

        resultats = {}
        total_global = 0
        labels = dict(PaymentMethod.choices)

        for ligne in agrege:
            code = ligne["payment_method"] or PaymentMethod.UNKNOWN
            total_centimes = int(ligne["total_decimal"])
            resultats[code] = {
                "label": str(labels.get(code, code)),
                "total": total_centimes,
                "nb": ligne["nb"],
            }
            total_global += total_centimes

        resultats["total"] = total_global
        resultats["currency_code"] = "EUR"
        return resultats

    # ------------------------------------------------------------------
    # 2. TVA par taux / VAT breakdown by rate
    # ------------------------------------------------------------------
    def calculer_tva(self) -> dict:
        """
        Ventilation par taux de TVA.
        vat est un pourcentage (5.5 = 5.5%). Conversion HT/TVA :
          total_ht = round(total_ttc * 100 / (100 + vat))
          total_tva = total_ttc - total_ht
        / VAT breakdown by rate. vat is a percentage.
        """
        agrege = (
            self.queryset
            .values("vat")
            .annotate(total_decimal=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")))
        )
        resultats = {}
        for ligne in agrege:
            vat = ligne["vat"] or Decimal("0")
            total_ttc = int(ligne["total_decimal"])
            if total_ttc == 0:
                continue
            vat_float = float(vat)
            if vat_float > 0:
                total_ht = int(round(total_ttc * 100 / (100 + vat_float)))
            else:
                total_ht = total_ttc
            total_tva = total_ttc - total_ht
            key = f"{vat_float:.2f}"
            resultats[key] = {
                "taux": vat_float,
                "total_ttc": total_ttc,
                "total_ht": total_ht,
                "total_tva": total_tva,
            }
        return resultats

    # ------------------------------------------------------------------
    # 3. Remboursements et avoirs / Refunds and credit notes
    # ------------------------------------------------------------------
    def calculer_remboursements(self) -> dict:
        """
        Avoirs (status=CREDIT_NOTE) presents dans _base_queryset.
        Remboursements (status=REFUNDED) hors queryset → requete dediee.
        / Credit notes (in base queryset) + refunds (separate query).
        """
        from BaseBillet.models import LigneArticle, SaleOrigin

        credit_notes = (
            self.queryset
            .filter(status=LigneArticle.CREDIT_NOTE)
            .aggregate(
                total=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
                nb=Count("pk"),
            )
        )

        refunded = (
            LigneArticle.objects.filter(
                datetime__gte=self.datetime_debut,
                datetime__lt=self.datetime_fin,
                status=LigneArticle.REFUNDED,
            )
            .exclude(sale_origin=SaleOrigin.LABOUTIK)
            .aggregate(
                total=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
                nb=Count("pk"),
            )
        )

        return {
            "credit_notes": {
                "total": int(credit_notes["total"]),
                "nb": credit_notes["nb"],
            },
            "refunded": {
                "total": int(refunded["total"]),
                "nb": refunded["nb"],
            },
        }

    # ------------------------------------------------------------------
    # 4. Detail des ventes par categorie d'article
    # / Sales detail grouped by article category
    # ------------------------------------------------------------------
    def calculer_detail_ventes(self) -> dict:
        """
        Detail des ventes groupe par Product.categorie_article (BILLET, ADHESION,
        FREERES, etc.). Pour chaque categorie : liste d'articles avec qty
        payants/offerts/total + HT/TVA/TTC + taux_tva.

        Une seule requete SQL groupee par (categorie, nom_produit, vat, offert).
        / Single SQL grouped by (category, product_name, vat, offert).
        """
        from BaseBillet.models import Product, PaymentMethod
        from django.db.models import Case, When, Value, CharField

        # Choices code -> label de Product.CATEGORIE_ARTICLE_CHOICES (utilisees pour le rendu)
        # / Code -> label of Product.CATEGORIE_ARTICLE_CHOICES (for rendering)
        try:
            categorie_labels = dict(Product.CATEGORIE_ARTICLE_CHOICES)
        except AttributeError:
            categorie_labels = {}

        # Annote chaque ligne avec un flag 'offert'. Une ligne est offerte si :
        # - le moyen de paiement est FREE (cas adhesion prix libre = 0)
        # - OU le montant est zero (cas billet prix libre = 0, qui garde
        #   payment_method=STRIPE_NOFED car la ligne est creee avant le webhook).
        # Le OR est evalue cote SQL dans un CASE WHEN ; ne genere PAS de N+1.
        # / Annotate each row with an 'offert' flag. A row is offered if:
        # - payment_method is FREE (free-priced membership at 0)
        # - OR amount is zero (free-priced ticket at 0, which keeps
        #   payment_method=STRIPE_NOFED because the line is created before the webhook).
        # The OR is evaluated server-side in a CASE WHEN — no N+1.
        rows = (
            self.queryset
            .annotate(
                offert_flag=Case(
                    When(
                        Q(payment_method=PaymentMethod.FREE) | Q(amount=0),
                        then=Value("Y"),
                    ),
                    default=Value("N"),
                    output_field=CharField(max_length=1),
                )
            )
            .values(
                "pricesold__productsold__product__categorie_article",
                "pricesold__productsold__product__name",
                "vat",
                "offert_flag",
            )
            .annotate(
                total_ttc=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
                qty_total=Coalesce(Sum("qty"), Decimal("0")),
            )
        )

        par_categorie = {}

        for row in rows:
            nom_produit = row["pricesold__productsold__product__name"]
            if not nom_produit:
                # Aucune ligne sans produit n'a de sens dans le rapport
                # / No rows without a product make sense in the report
                continue

            categorie = row["pricesold__productsold__product__categorie_article"] or "ZZZ"
            ttc = int(row["total_ttc"])
            qty = float(row["qty_total"])
            offert = row["offert_flag"] == "Y"
            vat = float(row["vat"] or 0)

            par_categorie.setdefault(categorie, {
                "nom_categorie": str(categorie_labels.get(categorie, categorie)),
                "articles": {},
                "total_ttc": 0,
            })

            articles = par_categorie[categorie]["articles"]
            article = articles.setdefault(nom_produit, {
                "nom_produit": nom_produit,
                "qty_payants": 0.0,
                "qty_offerts": 0.0,
                "qty_total": 0.0,
                "total_ttc": 0,
                "total_ht": 0,
                "total_tva": 0,
                "taux_tva": vat,
            })

            # Calcul HT/TVA a partir du TTC et du taux
            # / HT/TVA computation from TTC and rate
            if vat > 0 and ttc != 0:
                ht = int(round(ttc * 100 / (100 + vat)))
            else:
                ht = ttc

            if offert:
                article["qty_offerts"] += qty
            else:
                article["qty_payants"] += qty
            article["qty_total"] += qty
            article["total_ttc"] += ttc
            article["total_ht"] += ht
            article["total_tva"] += ttc - ht
            # Si le produit a plusieurs taux (cas rare), on garde le plus eleve
            # / If a product has several rates (rare), keep the highest
            if vat > article["taux_tva"]:
                article["taux_tva"] = vat

            par_categorie[categorie]["total_ttc"] += ttc

        # Conversion dict articles -> list
        # / dict articles -> list
        for cat in par_categorie.values():
            cat["articles"] = list(cat["articles"].values())

        return par_categorie

    # ------------------------------------------------------------------
    # 6. Infos legales du tenant / Legal info from tenant Configuration
    # ------------------------------------------------------------------
    def calculer_infos_legales(self) -> dict:
        """
        Recupere depuis Configuration.get_solo() les infos legales.
        Tous les champs retournes sont des string (vide si non renseigne).
        / Returns 8 string fields (empty if not set).
        """
        from BaseBillet.models import Configuration
        config = Configuration.get_solo()

        # postal_address peut etre une FK vers PostalAddress (street_address dispo)
        adresse = ""
        if getattr(config, "postal_address", None):
            adresse = str(getattr(config.postal_address, "street_address", "") or "")

        def _safe_str(attr_name):
            val = getattr(config, attr_name, None)
            return str(val) if val is not None else ""

        return {
            "organisation": _safe_str("organisation"),
            "adresse": adresse,
            "code_postal": _safe_str("postal_code"),
            "ville": _safe_str("city"),
            "siren": _safe_str("siren"),
            "tva_number": _safe_str("tva_number"),
            "email": _safe_str("email"),
            "phone": _safe_str("phone"),
        }

    # ------------------------------------------------------------------
    # 7. Hash chain SHA-256 des lignes (filet de securite)
    # / SHA-256 hash chain of lines (safety net)
    # ------------------------------------------------------------------
    def calculer_hash_lignes(self) -> str:
        """
        SHA-256 des tuples (pk, amount, qty, status) tries par pk.
        Change si une ligne est modifiee/ajoutee/supprimee post-cloture.
        / SHA-256 of sorted (pk, amount, qty, status) tuples.
        """
        lignes = list(
            self.queryset
            .order_by("pk")
            .values("pk", "amount", "qty", "status")
        )
        payload = "|".join(
            f"{l['pk']}:{l['amount']}:{l['qty']}:{l['status']}"
            for l in lignes
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # 8. Rapport complet (assemblage 6 sections + meta)
    # / Full report (6 sections + meta assembly)
    # ------------------------------------------------------------------
    def generer_rapport_complet(self) -> dict:
        """
        Compose le rapport complet, directement stockable dans
        ClotureCaisse.rapport_json (JSONField).
        / Build the full report, directly storable in rapport_json JSONField.
        """
        return {
            "totaux_par_moyen": self.calculer_totaux_par_moyen(),
            "tva": self.calculer_tva(),
            "detail_ventes": self.calculer_detail_ventes(),
            "remboursements": self.calculer_remboursements(),
            "infos_legales": self.calculer_infos_legales(),
            "meta": {
                "datetime_debut": self.datetime_debut.isoformat(),
                "datetime_fin": self.datetime_fin.isoformat(),
                "schema": connection.schema_name,
            },
        }


# ============================================================================
# Helpers de presentation partages par tous les exports (CSV, Tableur, PDF).
# Le rapport admin (template _sections_rapport.html) consomme directement
# detail_ventes (structure hierarchique). Les exports ont besoin d'une
# liste APLATIE : c'est ce que produit aplatir_detail_ventes().
# / Presentation helpers shared by every export (CSV, Spreadsheet, PDF).
# The admin report consumes the hierarchical structure directly ; exports
# need a FLATTENED list with the same columns as the admin display.
# ============================================================================

# Colonnes du tableau "Detail des ventes par categorie" telles qu'affichees
# dans l'admin. Les exports doivent rendre EXACTEMENT les memes colonnes.
# / Columns of the "Sales detail by category" table as shown in the admin.
# Exports MUST render EXACTLY the same columns.
COLONNES_DETAIL_VENTES = [
    "Categorie",
    "Produit",
    "Payants",
    "Offerts",
    "Quantite totale",
    "Taux TVA %",
    "HT",
    "TVA",
    "TTC",
]


def aplatir_detail_ventes(rapport_json: dict) -> list:
    """
    Aplatit la structure hierarchique detail_ventes en une liste de dicts.
    Chaque element correspond a UNE ligne du tableau "Detail des ventes
    par categorie" tel qu'affiche dans l'admin.

    / Flatten the hierarchical detail_ventes into a list of dicts. Each
    item is ONE row of the admin "Sales detail by category" table.

    Cles retournees pour chaque ligne (montants en centimes) :
      categorie_code  -- 'A', 'B', 'F', 'G', 'Q' (ou autre)
      categorie_nom   -- libelle FR de la categorie
      nom_produit     -- nom du produit
      qty_payants     -- float
      qty_offerts     -- float
      qty_total       -- float
      taux_tva        -- float (%)
      total_ht        -- int (centimes)
      total_tva       -- int (centimes)
      total_ttc       -- int (centimes)
    """
    lignes = []
    detail = rapport_json.get("detail_ventes") or {}
    for cat_code, cat in detail.items():
        if not isinstance(cat, dict):
            continue
        nom_categorie = cat.get("nom_categorie", cat_code)
        for article in cat.get("articles", []):
            if not isinstance(article, dict):
                continue
            lignes.append({
                "categorie_code": cat_code,
                "categorie_nom": nom_categorie,
                "nom_produit": article.get("nom_produit", ""),
                "qty_payants": float(article.get("qty_payants", 0)),
                "qty_offerts": float(article.get("qty_offerts", 0)),
                "qty_total": float(article.get("qty_total", 0)),
                "taux_tva": float(article.get("taux_tva", 0)),
                "total_ht": int(article.get("total_ht", 0)),
                "total_tva": int(article.get("total_tva", 0)),
                "total_ttc": int(article.get("total_ttc", 0)),
            })
    return lignes


# Mapping des 12 PaymentMethod V1 vers 4 categories d'affichage + "Autres".
# Le rapport_json stocke les 12 valeurs brutes ; l'agregation n'est faite
# qu'au moment du rendu (admin + exports). Pour ajouter/modifier une
# categorie, editer ce mapping en un seul endroit.
# / Mapping of 12 V1 PaymentMethod codes to 4 display categories + "Other".
# Aggregation happens at render time only. Edit this mapping in one place.
CATEGORIES_PAIEMENT_AFFICHAGE = [
    ("especes", _("Espèces"), ["CA"]),
    ("cb", _("Carte bancaire (terminal POS)"), ["CC"]),
    ("en_ligne", _("Paiements en ligne"), ["SF", "SN", "SP", "SR", "TR"]),
    ("cashless", _("Cashless (NFC / monnaie locale)"), ["LE", "LG", "QR"]),
    ("autres", _("Autres"), ["CH", "NA", "UK"]),
]


def agreger_paiements_par_categorie(totaux_par_moyen: dict) -> list:
    """
    Agrege les totaux_par_moyen (12 codes PaymentMethod) en 4 categories
    d'affichage + "Autres". Retourne une liste de dict pretes a afficher.
    / Aggregate 12 PaymentMethod codes into 4 display categories + "Other".

    Une categorie est INCLUSE dans le retour uniquement si elle a au moins
    une transaction (total != 0 ou nb > 0).
    """
    if not totaux_par_moyen:
        return []
    categories = []
    for slug, label, codes in CATEGORIES_PAIEMENT_AFFICHAGE:
        total = 0
        nb = 0
        for code in codes:
            item = totaux_par_moyen.get(code)
            if isinstance(item, dict):
                total += item.get("total", 0)
                nb += item.get("nb", 0)
        if total == 0 and nb == 0:
            # On masque les categories vides pour ne pas alourdir l'affichage
            # / Skip empty categories to keep the display compact
            continue
        categories.append({
            "slug": slug,
            "label": str(label),
            "total": total,
            "total_euros": f"{total / 100:.2f}",
            "nb": nb,
        })
    return categories


def enrichir_rapport_pour_affichage(rapport: dict) -> dict:
    """
    Ajoute des cles formatees (_euros suffixe) au rapport pour eviter les
    filtres custom dans les templates. Modifie une copie, pas l'original.

    Cette fonction est partagee par TOUS les consommateurs d'affichage :
    - admin (template _sections_rapport.html, vue temps reel)
    - export PDF (template pdf/rapport_comptable.html)
    Cela garantit que les exports affichent EXACTEMENT les memes donnees
    et formats que le rapport admin.

    / Adds _euros-suffixed keys to the report. Shared by every display
    consumer (admin templates + PDF export) so they show EXACTLY the same
    data and formats.
    """
    if not rapport:
        return {}
    r = copy.deepcopy(rapport)

    # totaux_par_moyen : ajoute total_euros pour chaque code + le grand total
    # + cle additionnelle 'categories' = 4 categories agregees pour l'affichage.
    # / totaux_par_moyen: add total_euros + aggregated 4-category view.
    if "totaux_par_moyen" in r and isinstance(r["totaux_par_moyen"], dict):
        for k, v in r["totaux_par_moyen"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"
        if "total" in r["totaux_par_moyen"]:
            r["totaux_par_moyen"]["total_euros"] = f"{r['totaux_par_moyen']['total'] / 100:.2f}"
        r["totaux_par_moyen"]["categories"] = agreger_paiements_par_categorie(
            r["totaux_par_moyen"]
        )

    # tva : HT/TVA/TTC en euros
    # / vat: HT/VAT/incl. tax in euros
    if "tva" in r and isinstance(r["tva"], dict):
        for taux, v in r["tva"].items():
            if isinstance(v, dict):
                v["total_ttc_euros"] = f"{v.get('total_ttc', 0) / 100:.2f}"
                v["total_ht_euros"] = f"{v.get('total_ht', 0) / 100:.2f}"
                v["total_tva_euros"] = f"{v.get('total_tva', 0) / 100:.2f}"

    # detail_ventes : enrichit chaque categorie + chaque article
    # / detail_ventes: enrich each category and article
    if "detail_ventes" in r and isinstance(r["detail_ventes"], dict):
        for cat in r["detail_ventes"].values():
            if not isinstance(cat, dict):
                continue
            if "total_ttc" in cat:
                cat["total_ttc_euros"] = f"{cat['total_ttc'] / 100:.2f}"
            for article in cat.get("articles", []):
                if not isinstance(article, dict):
                    continue
                article["total_ttc_euros"] = f"{article.get('total_ttc', 0) / 100:.2f}"
                article["total_ht_euros"] = f"{article.get('total_ht', 0) / 100:.2f}"
                article["total_tva_euros"] = f"{article.get('total_tva', 0) / 100:.2f}"

    # remboursements : credit_notes + refunded en euros
    # / refunds: credit notes + refunded amounts in euros
    if "remboursements" in r and isinstance(r["remboursements"], dict):
        for k, v in r["remboursements"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"

    return r

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
import hashlib
import logging
from decimal import Decimal

from django.db import connection
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import Coalesce

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

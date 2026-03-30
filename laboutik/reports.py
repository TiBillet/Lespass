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

from django.db.models import Sum, Count, Q
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
    CommandeSauvegarde,
)

logger = logging.getLogger(__name__)


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

        # Queryset de base : lignes valides de la caisse dans la periode.
        # Le filtre exact sale_origin=SaleOrigin.LABOUTIK exclut automatiquement
        # les lignes LABOUTIK_TEST (mode ecole, LNE exigence 5).
        # / Base queryset: valid POS lines within the period.
        # The exact sale_origin=SaleOrigin.LABOUTIK filter automatically excludes
        # LABOUTIK_TEST lines (training mode, LNE req. 5).
        self.lignes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=self.debut,
            datetime__lte=self.fin,
            status=LigneArticle.VALID,
        ).select_related(
            'pricesold__productsold__product__categorie_pos',
            'carte',
        )

    # ------------------------------------------------------------------
    # 1. Totaux par moyen de paiement / Totals by payment method
    # ------------------------------------------------------------------
    def calculer_totaux_par_moyen(self):
        """
        Especes (CA), CB (CC), cashless (LE+LG), cheque (CH), total.
        Enrichi avec le detail cashless par asset et le code devise.
        / Cash, credit card, cashless, check, total.
        Enriched with cashless detail by asset and currency code.
        """
        total_especes = self.lignes.filter(
            payment_method=PaymentMethod.CASH,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_carte_bancaire = self.lignes.filter(
            payment_method=PaymentMethod.CC,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # NFC / cashless : LOCAL_EURO (monnaie fiduciaire) + LOCAL_GIFT (cadeau)
        # / NFC / cashless: LOCAL_EURO (fiat) + LOCAL_GIFT (gift)
        total_cashless = self.lignes.filter(
            payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_cheque = self.lignes.filter(
            payment_method=PaymentMethod.CHEQUE,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_general = total_especes + total_carte_bancaire + total_cashless + total_cheque

        # Detail cashless par asset (nom de la monnaie)
        # / Cashless detail by asset (currency name)
        cashless_detail = []
        lignes_cashless_par_asset = self.lignes.filter(
            payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
            asset__isnull=False,
        ).values('asset').annotate(
            montant=Sum('amount'),
        ).order_by('-montant')

        # Prefetch tous les assets en une seule requete (evite N+1)
        # / Prefetch all assets in one query (avoids N+1)
        from fedow_core.models import Asset as FedowAsset
        asset_uuids = [ligne['asset'] for ligne in lignes_cashless_par_asset]
        assets_par_uuid = {
            a.uuid: a for a in FedowAsset.objects.filter(uuid__in=asset_uuids)
        }

        for ligne in lignes_cashless_par_asset:
            asset_uuid = ligne['asset']
            montant = ligne['montant'] or 0
            asset_obj = assets_par_uuid.get(asset_uuid)
            nom_asset = asset_obj.name if asset_obj else str(_("Inconnu"))
            code_asset = asset_obj.currency_code if asset_obj else ""
            cashless_detail.append({
                "nom": nom_asset,
                "code": code_asset,
                "montant": montant,
            })

        config_tenant = Configuration.get_solo()
        code_devise = config_tenant.currency_code or "EUR"

        return {
            "especes": total_especes,
            "carte_bancaire": total_carte_bancaire,
            "cashless": total_cashless,
            "cashless_detail": cashless_detail,
            "cheque": total_cheque,
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
        produits_agreg = self.lignes.values(
            'pricesold__productsold__product__name',
            'pricesold__productsold__product__categorie_pos__name',
            'pricesold__productsold__product__prix_achat',
            'vat',
            'payment_method',
        ).annotate(
            total_ttc=Sum('amount'),
            total_qty=Sum('qty'),
        ).order_by(
            'pricesold__productsold__product__categorie_pos__name',
            'pricesold__productsold__product__name',
        )

        # Methodes de paiement "cadeau" / Gift payment methods
        methodes_cadeau = [PaymentMethod.LOCAL_GIFT]
        if hasattr(PaymentMethod, 'EXTERIEUR_GIFT'):
            methodes_cadeau.append(PaymentMethod.EXTERIEUR_GIFT)

        # Regrouper par (categorie, produit, taux_tva) en separant vendus/offerts
        # / Group by (category, product, vat_rate) separating sold/gifted
        cle_articles = {}
        for ligne in produits_agreg:
            nom_categorie = ligne['pricesold__productsold__product__categorie_pos__name'] or str(_("Sans catégorie"))
            nom_produit = ligne['pricesold__productsold__product__name'] or str(_("Inconnu"))
            prix_achat_unit = ligne['pricesold__productsold__product__prix_achat'] or 0
            total_ttc = ligne['total_ttc'] or 0
            total_qty = float(ligne['total_qty'] or 0)
            taux_tva = float(ligne['vat'] or 0)
            moyen_paiement = ligne['payment_method']

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

            if nom_categorie not in categories:
                categories[nom_categorie] = {"articles": [], "total_ttc": 0}

            categories[nom_categorie]["articles"].append({
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
            })
            categories[nom_categorie]["total_ttc"] += total_ttc

        return categories

    # ------------------------------------------------------------------
    # 3. TVA par taux / VAT by rate
    # ------------------------------------------------------------------
    def calculer_tva(self):
        """
        Par taux de TVA : total_ttc, total_ht, total_tva.
        Logique identique a views.py:1020-1043.
        / By VAT rate: total incl., excl., VAT amount.
        """
        tva_agreg = self.lignes.values('vat').annotate(
            total_ttc=Sum('amount'),
        ).order_by('vat')

        rapport_par_tva = {}
        for ligne in tva_agreg:
            taux_tva = float(ligne['vat'] or 0)
            total_ttc_centimes = ligne['total_ttc'] or 0

            # Calcul HT depuis TTC : HT = TTC / (1 + taux/100)
            # / Compute HT from TTC: HT = TTC / (1 + rate/100)
            if taux_tva > 0:
                total_ht_centimes = int(round(total_ttc_centimes / (1 + taux_tva / 100)))
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
        Fond de caisse (de LaboutikConfiguration) + total especes.
        / Cash float (from LaboutikConfiguration) + total cash.
        """
        config = LaboutikConfiguration.get_solo()
        fond_de_caisse = config.fond_de_caisse or 0

        entrees_especes = self.lignes.filter(
            payment_method=PaymentMethod.CASH,
        ).aggregate(total=Sum('amount'))['total'] or 0

        return {
            "fond_de_caisse": fond_de_caisse,
            "entrees_especes": entrees_especes,
            "solde": fond_de_caisse + entrees_especes,
        }

    # ------------------------------------------------------------------
    # 5. Recharges cashless / Cashless top-ups
    # ------------------------------------------------------------------
    def calculer_recharges(self):
        """
        Filtre les lignes dont le produit a methode_caisse in (RE, RC, TM).
        Agrege par methode_caisse et par moyen de paiement.
        / Filter lines whose product has methode_caisse in (RE, RC, TM).
        Aggregate by POS method and payment method.
        """
        methodes_recharge = [Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS]

        recharges = self.lignes.filter(
            pricesold__productsold__product__methode_caisse__in=methodes_recharge,
        ).values(
            'pricesold__productsold__product__methode_caisse',
            'payment_method',
        ).annotate(
            total=Sum('amount'),
            nb=Count('uuid'),
        ).order_by('pricesold__productsold__product__methode_caisse')

        resultat = {}
        for ligne in recharges:
            methode = ligne['pricesold__productsold__product__methode_caisse']
            moyen = ligne['payment_method'] or 'UK'
            cle = f"{methode}_{moyen}"
            resultat[cle] = {
                "methode_caisse": methode,
                "moyen_paiement": moyen,
                "total": ligne['total'] or 0,
                "nb": ligne['nb'] or 0,
            }

        # Total general des recharges / Overall top-up total
        total_recharges = sum(v['total'] for v in resultat.values())
        return {
            "detail": resultat,
            "total": total_recharges,
        }

    # ------------------------------------------------------------------
    # 6. Adhesions / Memberships
    # ------------------------------------------------------------------
    def calculer_adhesions(self):
        """
        Lignes avec membership non null. Compter et sommer par moyen.
        / Lines with non-null membership. Count and sum by payment method.
        """
        adhesions = self.lignes.filter(
            membership__isnull=False,
        ).values(
            'payment_method',
        ).annotate(
            total=Sum('amount'),
            nb=Count('uuid'),
        ).order_by('payment_method')

        detail = {}
        for ligne in adhesions:
            moyen = ligne['payment_method'] or 'UK'
            detail[moyen] = {
                "total": ligne['total'] or 0,
                "nb": ligne['nb'] or 0,
            }

        total_adhesions = sum(v['total'] for v in detail.values())
        nb_adhesions = sum(v['nb'] for v in detail.values())
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
        remboursements = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=self.debut,
            datetime__lte=self.fin,
        ).filter(
            Q(status=LigneArticle.CREDIT_NOTE) | Q(amount__lt=0),
        ).aggregate(
            total=Sum('amount'),
            nb=Count('uuid'),
        )

        return {
            "total": remboursements['total'] or 0,
            "nb": remboursements['nb'] or 0,
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
            ).values('carte').annotate(
                total=Sum('amount'),
            ).values_list('total', flat=True)
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
                    Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS,
                ],
            ).values('carte').annotate(
                total=Sum('amount'),
            ).values_list('total', flat=True)
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

            cartes_actives_ids = self.lignes.filter(
                carte__isnull=False,
            ).values_list('carte', flat=True).distinct()

            # Recuperer les wallets via CarteCashless.user.wallet
            # / Get wallets via CarteCashless.user.wallet
            wallets_ids = CarteCashless.objects.filter(
                pk__in=cartes_actives_ids,
                user__isnull=False,
                user__wallet__isnull=False,
            ).values_list('user__wallet', flat=True)

            # Soldes en monnaie locale (TLF) / Balances in local currency (TLF)
            soldes = list(
                FedowToken.objects.filter(
                    wallet__in=wallets_ids,
                    asset__category=FedowAsset.TLF,
                ).values_list('value', flat=True)
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
        Lignes avec reservation non null. Compter par evenement.
        / Lines with non-null reservation. Count by event.
        """
        billets = self.lignes.filter(
            reservation__isnull=False,
        ).values(
            'reservation__event__name',
        ).annotate(
            nb=Count('uuid'),
            total=Sum('amount'),
        ).order_by('reservation__event__name')

        detail = {}
        for ligne in billets:
            nom_event = ligne['reservation__event__name'] or str(_("Inconnu"))
            detail[nom_event] = {
                "nb": ligne['nb'] or 0,
                "total": ligne['total'] or 0,
            }

        nb_total = sum(v['nb'] for v in detail.values())
        total_montant = sum(v['total'] for v in detail.values())
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
            "recharges": Q(pricesold__productsold__product__methode_caisse__in=[
                Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS,
            ]),
            "adhesions": Q(membership__isnull=False),
            "billets": Q(reservation__isnull=False),
        }

        # Moyens de paiement regroupes / Grouped payment methods
        moyens = {
            "especes": Q(payment_method=PaymentMethod.CASH),
            "carte_bancaire": Q(payment_method=PaymentMethod.CC),
            "cashless": Q(payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT]),
        }

        synthese = {}
        for nom_type, filtre_type in types_operations.items():
            ligne = {}
            for nom_moyen, filtre_moyen in moyens.items():
                montant = self.lignes.filter(filtre_type & filtre_moyen).aggregate(
                    total=Sum('amount'),
                )['total'] or 0
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
        resultats = self.lignes.filter(
            point_de_vente__isnull=False,
        ).values(
            'point_de_vente__name',
            'point_de_vente__uuid',
        ).annotate(
            total_ttc=Sum('amount'),
        ).order_by('-total_ttc')

        ventilation = []
        for ligne in resultats:
            ventilation.append({
                'nom': ligne['point_de_vente__name'],
                'uuid': str(ligne['point_de_vente__uuid']),
                'total_ttc': ligne['total_ttc'] or 0,
            })

        # Lignes sans PV (anciennes donnees avant la FK)
        # / Lines without PV (old data before FK was added)
        total_sans_pv = self.lignes.filter(
            point_de_vente__isnull=True,
        ).aggregate(total=Sum('amount'))['total'] or 0
        if total_sans_pv > 0:
            ventilation.append({
                'nom': str(_("Non attribué")),
                'uuid': '',
                'total_ttc': total_sans_pv,
            })

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
        lignes_ordonnees = self.lignes.order_by('uuid').values_list(
            'uuid', 'amount', 'status',
        )

        hasher = hashlib.sha256()
        for uuid_val, montant, statut in lignes_ordonnees:
            # Chaque ligne contribue : uuid|montant|statut
            # / Each line contributes: uuid|amount|status
            hasher.update(f"{uuid_val}|{montant}|{statut}".encode('utf-8'))

        return hasher.hexdigest()

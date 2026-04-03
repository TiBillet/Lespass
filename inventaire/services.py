"""
Service de gestion de stock : décrémentation atomique, mouvements, résumé clôture.
/ Stock management service: atomic decrement, movements, closure summary.

LOCALISATION : inventaire/services.py
"""

import logging

from django.db.models import F

from inventaire.models import (
    MouvementStock,
    Stock,
    StockInsuffisant,
    TypeMouvement,
)

logger = logging.getLogger(__name__)


class StockService:
    """
    Service statique pour les opérations de stock.
    Toutes les méthodes sont des @staticmethod — pas d'état interne.
    / Static service for stock operations. All methods are @staticmethod.
    """

    @staticmethod
    def decrementer_pour_vente(stock, contenance, qty, ligne_article=None):
        """
        Décrémente le stock après une vente POS.
        Utilise F() pour un update atomique sans verrou.
        / Decrements stock after a POS sale. Uses F() for lockless atomic update.

        :param stock: instance Stock
        :param contenance: int ou None. Quantité par unité vendue. None=1.
        :param qty: int. Nombre d'unités vendues.
        :param ligne_article: LigneArticle ou None.
        :raises StockInsuffisant: si stock bloquant et insuffisant.
        """
        contenance_effective = contenance or 1
        delta = qty * contenance_effective
        stock_avant = stock.quantite

        if stock.autoriser_vente_hors_stock:
            Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") - delta)
        else:
            lignes_mises_a_jour = Stock.objects.filter(
                pk=stock.pk,
                quantite__gte=delta,
            ).update(quantite=F("quantite") - delta)

            if not lignes_mises_a_jour:
                raise StockInsuffisant(stock.product, delta, stock.quantite)

        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=TypeMouvement.VE,
            quantite=-delta,
            quantite_avant=stock_avant,
            ligne_article=ligne_article,
            cree_par=None,
        )

        logger.info(
            f"Stock décrémenté : {stock.product.name} "
            f"-{delta} {stock.get_unite_display()} "
            f"(avant={stock_avant})"
        )

    @staticmethod
    def creer_mouvement(stock, type_mouvement, quantite, motif="", utilisateur=None):
        """
        Crée un mouvement de stock manuel (réception, perte, offert, débit mètre).
        Le signe du delta est déduit du type.
        / Creates a manual stock movement. Delta sign is inferred from type.

        :param stock: instance Stock
        :param type_mouvement: TypeMouvement choice
        :param quantite: int positif. La quantité concernée.
        :param motif: str optionnel.
        :param utilisateur: TibilletUser ou None.
        """
        types_negatifs = [
            TypeMouvement.PE,
            TypeMouvement.OF,
            TypeMouvement.DM,
        ]
        if type_mouvement in types_negatifs:
            delta = -abs(quantite)
        else:
            delta = abs(quantite)

        stock_avant = stock.quantite

        Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") + delta)

        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=type_mouvement,
            quantite=delta,
            quantite_avant=stock_avant,
            motif=motif,
            cree_par=utilisateur,
        )

        logger.info(
            f"Mouvement stock {type_mouvement} : {stock.product.name} "
            f"{'+' if delta > 0 else ''}{delta} {stock.get_unite_display()} "
            f"motif='{motif}'"
        )

    @staticmethod
    def ajuster_inventaire(stock, stock_reel, motif="", utilisateur=None):
        """
        Ajustement inventaire : l'utilisateur donne le stock réel compté.
        Le système calcule le delta (réel - actuel).
        / Inventory adjustment: user gives real counted stock. System computes delta.

        :param stock: instance Stock
        :param stock_reel: int. Stock réel compté.
        :param motif: str optionnel.
        :param utilisateur: TibilletUser ou None.
        """
        stock_avant = stock.quantite
        delta = stock_reel - stock_avant

        Stock.objects.filter(pk=stock.pk).update(quantite=stock_reel)

        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=TypeMouvement.AJ,
            quantite=delta,
            quantite_avant=stock_avant,
            motif=motif,
            cree_par=utilisateur,
        )

        logger.info(
            f"Ajustement inventaire : {stock.product.name} "
            f"{stock_avant} → {stock_reel} (delta={delta:+d})"
        )


class ResumeStockService:
    """
    Service pour le résumé stock intégré aux clôtures de caisse.
    / Service for stock summary integrated into cash closures.
    """

    @staticmethod
    def generer_resume(mouvements_sans_cloture):
        """
        Génère un résumé JSON-serializable des mouvements de stock.
        / Generates a JSON-serializable summary of stock movements.
        """
        produits_data = {}

        for mouvement in mouvements_sans_cloture.select_related("stock__product"):
            nom_produit = mouvement.stock.product.name
            product_uuid = str(mouvement.stock.product.uuid)

            if product_uuid not in produits_data:
                produits_data[product_uuid] = {
                    "nom": nom_produit,
                    "unite": mouvement.stock.unite,
                    "ventes": 0,
                    "receptions": 0,
                    "pertes": 0,
                    "offerts": 0,
                    "debit_metre": 0,
                    "ajustements": 0,
                }

            donnees = produits_data[product_uuid]
            type_mv = mouvement.type_mouvement

            if type_mv == TypeMouvement.VE:
                donnees["ventes"] += mouvement.quantite
            elif type_mv == TypeMouvement.RE:
                donnees["receptions"] += mouvement.quantite
            elif type_mv == TypeMouvement.PE:
                donnees["pertes"] += mouvement.quantite
            elif type_mv == TypeMouvement.OF:
                donnees["offerts"] += mouvement.quantite
            elif type_mv == TypeMouvement.DM:
                donnees["debit_metre"] += mouvement.quantite
            elif type_mv == TypeMouvement.AJ:
                donnees["ajustements"] += mouvement.quantite

        # Alertes stock bas / Low stock alerts
        alertes = []
        for stock in Stock.objects.select_related("product").all():
            if stock.est_en_alerte() or stock.est_en_rupture():
                alertes.append(
                    {
                        "nom": stock.product.name,
                        "quantite": stock.quantite,
                        "unite": stock.unite,
                        "seuil": stock.seuil_alerte,
                        "en_rupture": stock.est_en_rupture(),
                    }
                )

        return {
            "par_produit": list(produits_data.values()),
            "alertes": alertes,
        }

    @staticmethod
    def rattacher_a_cloture(cloture):
        """
        Rattache tous les mouvements sans clôture à la clôture donnée.
        / Attaches all movements without closure to the given closure.
        """
        nombre_rattaches = MouvementStock.objects.filter(
            cloture__isnull=True,
        ).update(cloture=cloture)

        logger.info(
            f"Clôture {cloture.pk} : {nombre_rattaches} mouvements stock rattachés"
        )
        return nombre_rattaches

"""
Vues DRF pour la gestion de stock (actions manuelles + capteur debit metre).
/ DRF views for stock management (manual actions + flow meter sensor).

LOCALISATION : inventaire/views.py
"""

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from BaseBillet.models import Product
from BaseBillet.permissions import HasLaBoutikAccess
from inventaire.models import Stock, TypeMouvement, UniteStock
from inventaire.serializers import DebitMetreSerializer, MouvementRapideSerializer
from inventaire.services import StockService


class StockViewSet(viewsets.ViewSet):
    """
    Actions manuelles sur le stock : reception, perte, offert.
    / Manual stock actions: reception, loss, offered.
    """

    permission_classes = [HasLaBoutikAccess]

    @action(detail=True, methods=["POST"])
    def reception(self, request, pk=None):
        """Ajouter du stock (livraison). / Add stock (delivery)."""
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.RE,
            quantite=serializer.validated_data["quantite"],
            motif=serializer.validated_data.get("motif", ""),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response(
            {
                "stock_actuel": stock.quantite,
                "unite": stock.unite,
            }
        )

    @action(detail=True, methods=["POST"])
    def perte(self, request, pk=None):
        """Retirer du stock (perte/casse). / Remove stock (loss/breakage)."""
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.PE,
            quantite=serializer.validated_data["quantite"],
            motif=serializer.validated_data.get("motif", ""),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response(
            {
                "stock_actuel": stock.quantite,
                "unite": stock.unite,
            }
        )

    @action(detail=True, methods=["POST"])
    def offert(self, request, pk=None):
        """Retirer du stock (offert). / Remove stock (offered)."""
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.OF,
            quantite=serializer.validated_data["quantite"],
            motif=serializer.validated_data.get("motif", ""),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response(
            {
                "stock_actuel": stock.quantite,
                "unite": stock.unite,
            }
        )


class DebitMetreViewSet(viewsets.ViewSet):
    """
    Endpoint pour le capteur debit metre (Raspberry Pi).
    Decremente le stock en centilitres a chaque tirage.
    / Flow meter sensor endpoint (Raspberry Pi). Decrements stock in CL per pour.
    """

    permission_classes = [HasLaBoutikAccess]

    def create(self, request):
        """Enregistrer un debit metre. / Record a meter debit."""
        serializer = DebitMetreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_uuid = serializer.validated_data["product_uuid"]
        quantite_cl = serializer.validated_data["quantite_cl"]
        capteur_id = serializer.validated_data["capteur_id"]

        product = get_object_or_404(Product, uuid=product_uuid)

        # Verifier que le produit a un stock en centilitres
        # / Check the product has stock in centiliters
        if not hasattr(product, "stock_inventaire"):
            return Response(
                {"detail": _("Ce produit n'a pas de stock inventaire.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stock = product.stock_inventaire
        if stock.unite != UniteStock.CL:
            return Response(
                {"detail": _("Le stock de ce produit n'est pas en centilitres.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.DM,
            quantite=quantite_cl,
            motif=capteur_id,
        )

        stock.refresh_from_db()
        return Response(
            {
                "stock_actuel": stock.quantite,
                "unite": stock.unite,
                "product_uuid": str(product.uuid),
            },
            status=status.HTTP_201_CREATED,
        )

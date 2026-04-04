"""
Vues DRF pour la gestion de stock (actions manuelles + capteur debit metre).
+ Vue Django classique pour les actions manuelles depuis l'admin.
/ DRF views for stock management (manual actions + flow meter sensor).
+ Plain Django view for manual actions from admin.

LOCALISATION : inventaire/views.py
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from BaseBillet.models import Product
from BaseBillet.permissions import HasLaBoutikAccess
from inventaire.models import MouvementStock, Stock, TypeMouvement, UniteStock
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


# ---------------------------------------------------------------------------
# Vue Django classique pour les actions manuelles depuis l'admin
# / Plain Django view for manual stock actions from admin
# ---------------------------------------------------------------------------


def stock_action_view(request, stock_uuid):
    """
    Vue pour les actions manuelles de stock depuis l'admin.
    Reçoit un POST avec type_mouvement, quantite, motif.
    Retourne un partial HTML (feedback + formulaire rechargé).
    / View for manual stock actions from admin.

    LOCALISATION : inventaire/views.py

    FLUX :
    1. Reçoit POST depuis stock_actions.html (bouton HTMX)
    2. Valide avec StockActionSerializer
    3. Dispatche vers StockService selon type_mouvement
    4. Relit le stock depuis la DB (refresh_from_db)
    5. Rend le partial stock_actions_partial.html
    """
    from inventaire.serializers import StockActionSerializer
    from laboutik.views import _formater_stock_lisible

    stock = get_object_or_404(Stock, pk=stock_uuid)

    serializer = StockActionSerializer(data=request.POST)

    message_feedback = None
    erreur_feedback = None

    if serializer.is_valid():
        type_mouvement = serializer.validated_data["type_mouvement"]
        quantite = serializer.validated_data["quantite"]
        motif = serializer.validated_data.get("motif", "")
        utilisateur = request.user if request.user.is_authenticated else None

        if type_mouvement == TypeMouvement.AJ:
            # Ajustement : quantite = stock réel compté
            # / Adjustment: quantite = real counted stock
            StockService.ajuster_inventaire(
                stock=stock,
                stock_reel=quantite,
                motif=motif,
                utilisateur=utilisateur,
            )
        else:
            # Réception, offert, perte
            # / Reception, offered, loss
            StockService.creer_mouvement(
                stock=stock,
                type_mouvement=type_mouvement,
                quantite=quantite,
                motif=motif,
                utilisateur=utilisateur,
            )

        stock.refresh_from_db()

        # Construire le message de feedback
        # / Build feedback message
        label_type = dict(StockActionSerializer.TYPES_MANUELS_CHOICES).get(
            type_mouvement, type_mouvement
        )
        stock_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
        message_feedback = f"{label_type} effectuée. Stock actuel : {stock_lisible}"
    else:
        # Extraire les messages d'erreur lisibles (pas le dict brut)
        # / Extract readable error messages (not the raw dict)
        messages_erreur = []
        for champ, erreurs in serializer.errors.items():
            for erreur in erreurs:
                messages_erreur.append(str(erreur))
        erreur_feedback = " ".join(messages_erreur)
        stock.refresh_from_db()

    # Derniers mouvements manuels pour l'aperçu (pas les ventes/débits auto)
    # / Recent manual movements for preview (not auto sales/meter debits)
    derniers_mouvements = (
        MouvementStock.objects.filter(stock=stock)
        .exclude(type_mouvement__in=[TypeMouvement.VE, TypeMouvement.DM])
        .select_related("cree_par")
        .order_by("-cree_le")[:5]
    )

    contexte = {
        "stock": stock,
        "product_name": stock.product.name,
        "derniers_mouvements": derniers_mouvements,
        "message_feedback": message_feedback,
        "erreur_feedback": erreur_feedback,
        "stock_action_url": f"/admin/inventaire/stock/{stock.pk}/action/",
    }

    html = render_to_string(
        "admin/inventaire/stock_actions_partial.html",
        contexte,
        request=request,
    )
    return HttpResponse(html)

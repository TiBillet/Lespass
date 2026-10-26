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
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from BaseBillet.models import Product
from BaseBillet.permissions import HasLaBoutikAccess
from inventaire.models import (
    MouvementStock,
    Stock,
    TypeMouvement,
    UniteStock,
    stock_suivi_du_produit_ou_none,
)
from inventaire.serializers import (
    DebitMetreSerializer,
    MouvementRapideSerializer,
    ReprendreSuiviSerializer,
    StockActionSerializer,
)
from inventaire.services import StockService
from laboutik.views import _formater_stock_lisible


# Message des opérations refusées sur un stock non suivi (Stock.actif faux).
# / Message for operations refused on an untracked stock.
MESSAGE_SUIVI_DESACTIVE = _("Le suivi de stock est désactivé pour ce produit.")


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
        if not stock.actif:
            return Response(
                {"detail": MESSAGE_SUIVI_DESACTIVE}, status=status.HTTP_400_BAD_REQUEST
            )
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
        if not stock.actif:
            return Response(
                {"detail": MESSAGE_SUIVI_DESACTIVE}, status=status.HTTP_400_BAD_REQUEST
            )
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
        if not stock.actif:
            return Response(
                {"detail": MESSAGE_SUIVI_DESACTIVE}, status=status.HTTP_400_BAD_REQUEST
            )
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

        # Verifier que le produit a un stock suivi, en centilitres.
        # Un stock non suivi (actif=False) est refuse comme une absence de stock.
        # / Check the product has a tracked stock in centiliters
        stock = stock_suivi_du_produit_ou_none(product)
        if stock is None:
            return Response(
                {"detail": _("Ce produit n'a pas de stock inventaire.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
    stock = get_object_or_404(Stock, pk=stock_uuid)

    # Stock non suivi : aucune opération. Le panneau renvoyé est celui de
    # l'état non suivi (formulaire « Suivre le stock »).
    # / Untracked stock: no operation, the resume form is shown.
    if not stock.actif:
        return _rendre_panneau_stock(
            request, stock, erreur_feedback=MESSAGE_SUIVI_DESACTIVE
        )

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

    return _rendre_panneau_stock(
        request,
        stock,
        message_feedback=message_feedback,
        erreur_feedback=erreur_feedback,
    )


def _rendre_panneau_stock(request, stock, message_feedback=None, erreur_feedback=None):
    """
    Rend le panneau d'opérations de stock (stock_actions_partial.html).
    / Renders the stock operations panel.

    LOCALISATION : inventaire/views.py

    Utilisée par les trois vues qui répondent au panneau en HTMX :
    stock_action_view, stock_desactiver_suivi_view, stock_reprendre_suivi_view.
    Le partial choisit son état (suivi / non suivi) d'après stock.actif.
    / Used by the three views answering the panel. The partial picks its state.
    """
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
        "stock_action_url": reverse(
            "staff_admin:inventaire_stock_action", args=[stock.pk]
        ),
    }

    html = render_to_string(
        "admin/inventaire/stock_actions_partial.html",
        contexte,
        request=request,
    )
    return HttpResponse(html)


def stock_desactiver_suivi_view(request, stock_uuid):
    """
    Désactive le suivi d'un stock depuis le panneau d'opérations de l'admin.
    / Deactivates stock tracking from the admin operations panel.

    LOCALISATION : inventaire/views.py

    FLUX :
    1. Reçoit le POST du bouton « Désactiver le suivi » (stock_actions_partial.html)
    2. StockService.desactiver_suivi : actif=False, aucun mouvement, caisses prévenues
    3. Rend le panneau dans l'état « non suivi »

    Routée par StockAdmin.get_urls (Administration/admin/inventaire.py),
    derrière admin_view : mêmes droits que les opérations de stock.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    stock = get_object_or_404(Stock, pk=stock_uuid)
    if stock.actif:
        StockService.desactiver_suivi(stock)

    return _rendre_panneau_stock(
        request,
        stock,
        message_feedback=_("Suivi du stock désactivé. Le journal est conservé."),
    )


def stock_reprendre_suivi_view(request, stock_uuid):
    """
    Reprend le suivi d'un stock depuis le panneau d'opérations de l'admin.
    / Resumes stock tracking from the admin operations panel.

    LOCALISATION : inventaire/views.py

    FLUX :
    1. Reçoit le POST du formulaire « Suivre le stock — quantité comptée »
    2. Valide avec ReprendreSuiviSerializer (quantité obligatoire, 0 accepté)
    3. StockService.reprendre_suivi : actif=True + ajustement « Reprise du suivi »
    4. Rend le panneau dans l'état « suivi », ou l'erreur dans l'état « non suivi »

    Routée par StockAdmin.get_urls (Administration/admin/inventaire.py).
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    stock = get_object_or_404(Stock, pk=stock_uuid)

    # Déjà suivi (double clic, deux onglets) : rien à reprendre
    # / Already tracked: nothing to resume
    if stock.actif:
        return _rendre_panneau_stock(request, stock)

    serializer = ReprendreSuiviSerializer(data=request.POST)
    if not serializer.is_valid():
        messages_erreur = []
        for champ, erreurs in serializer.errors.items():
            for erreur in erreurs:
                messages_erreur.append(str(erreur))
        return _rendre_panneau_stock(
            request, stock, erreur_feedback=" ".join(messages_erreur)
        )

    utilisateur = request.user if request.user.is_authenticated else None
    StockService.reprendre_suivi(
        stock=stock,
        quantite_comptee=serializer.validated_data["quantite_comptee"],
        utilisateur=utilisateur,
    )
    stock.refresh_from_db()

    stock_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
    return _rendre_panneau_stock(
        request,
        stock,
        message_feedback=_("Le stock est suivi. Stock actuel : %(stock)s")
        % {"stock": stock_lisible},
    )

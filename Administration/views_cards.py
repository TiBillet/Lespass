"""
Administration/views_cards.py — Vues custom admin pour les cartes NFC.
Administration/views_cards.py — Custom admin views for NFC cards.

Patterns FALC /djc :
- viewsets.ViewSet (NOT ModelViewSet), methodes explicites
- serializers.Serializer pour la validation
- HTML server-rendered (HTMX partials)
- Permissions : superuser OU admin tenant ET carte du tenant

3 endpoints HTMX consommes par CarteCashlessAdmin.change_form_before_template :
- panel : etat tokens + historique + bouton 'Rembourser'
- modal : modal de confirmation avec checkbox VV et aide FALC
- confirm : execution du refund, retour HTMX (HX-Refresh pour rechargement)
"""
import logging

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from Administration.serializers import CardRefundConfirmSerializer
from QrcodeCashless.models import CarteCashless
from fedow_core.exceptions import NoEligibleTokens
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService

logger = logging.getLogger(__name__)

# Nombre de transactions recentes affichees dans le panel
# Number of recent transactions displayed in the panel
NB_TRANSACTIONS_RECENTES = 15


def _check_admin_or_superuser_for_card(request, carte: CarteCashless) -> None:
    """
    Verifie que l'utilisateur peut acceder a cette carte.
    Verifies the user can access this card.

    - Superuser : OK toutes les cartes.
    - Admin tenant : OK seulement si carte.detail.origine == tenant courant.
    """
    if request.user.is_superuser:
        return
    if not TenantAdminPermissionWithRequest(request):
        raise PermissionDenied(_("Accès administrateur requis."))
    if carte.detail is None or carte.detail.origine_id != connection.tenant.pk:
        raise PermissionDenied(
            _("Cette carte n'appartient pas à votre lieu.")
        )


def _wallet_de_la_carte(carte: CarteCashless):
    """Retourne le wallet actif de la carte (user.wallet ou wallet_ephemere)."""
    if carte.user is not None and carte.user.wallet is not None:
        return carte.user.wallet
    return carte.wallet_ephemere


def _tokens_eligibles(wallet, tenant):
    """Tokens eligibles au remboursement : TLF du tenant + FED, value > 0."""
    return Token.objects.filter(
        wallet=wallet,
        value__gt=0,
    ).filter(
        Q(asset__category=Asset.TLF, asset__tenant_origin=tenant)
        | Q(asset__category=Asset.FED)
    ).select_related('asset', 'asset__tenant_origin').order_by('asset__category')


def _transactions_recentes(wallet, limite=NB_TRANSACTIONS_RECENTES):
    """
    Historique des N dernieres transactions du wallet (entrantes + sortantes).
    Recent N transactions of the wallet (incoming + outgoing).
    """
    if wallet is None:
        return []
    return list(
        Transaction.objects.filter(
            Q(sender=wallet) | Q(receiver=wallet),
        )
        .select_related('asset', 'sender', 'receiver')
        .order_by('-datetime')[:limite]
    )


class CardRefundViewSet(viewsets.ViewSet):
    """
    Endpoints HTMX consommes par CarteCashlessAdmin.change_form_before_template.

    URLs (montees par CarteCashlessAdmin.get_urls) :
    - GET  <uuid>/refund-panel/   -> panel()
    - GET  <uuid>/refund-modal/   -> modal()
    - POST <uuid>/refund-confirm/ -> confirm()
    """
    permission_classes = [IsAuthenticated]

    def panel(self, request, pk=None):
        """
        GET : partial HTMX — etat tokens eligibles + historique + bouton 'Rembourser'.
        GET: HTMX partial — eligible tokens state + history + 'Refund' button.
        """
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)

        tenant = connection.tenant
        wallet = _wallet_de_la_carte(carte)

        if wallet is None:
            contexte = {
                "carte": carte,
                "wallet": None,
                "tokens_eligibles": [],
                "transactions_recentes": [],
                "total_fiduciaire_centimes": 0,
                "carte_vierge": True,
            }
            return render(request, "admin/cards/refund_panel.html", contexte)

        tokens = list(_tokens_eligibles(wallet, tenant))
        # Total fiduciaire = TLF du tenant + FED, en centimes euros
        # Fiduciary total = tenant's TLF + FED, in euro cents
        total_fiduciaire = sum(t.value for t in tokens)

        contexte = {
            "carte": carte,
            "wallet": wallet,
            "tokens_eligibles": tokens,
            "transactions_recentes": _transactions_recentes(wallet),
            "total_fiduciaire_centimes": total_fiduciaire,
            "carte_vierge": False,
        }
        return render(request, "admin/cards/refund_panel.html", contexte)

    def modal(self, request, pk=None):
        """
        GET : partial HTMX — modal de confirmation avec checkbox VV + aide FALC.
        GET: HTMX partial — confirmation modal with VV checkbox + FALC help text.
        """
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)

        tenant = connection.tenant
        wallet = _wallet_de_la_carte(carte)

        tokens = list(_tokens_eligibles(wallet, tenant)) if wallet else []
        total_fiduciaire = sum(t.value for t in tokens)

        contexte = {
            "carte": carte,
            "tokens_eligibles": tokens,
            "total_fiduciaire_centimes": total_fiduciaire,
        }
        return render(request, "admin/cards/refund_modal.html", contexte)

    def confirm(self, request, pk=None):
        """
        POST : execute le refund, retourne partial + HX-Refresh pour reload.
        POST: execute refund, return partial + HX-Refresh to reload.
        """
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)

        serializer = CardRefundConfirmSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)
        vider_carte = serializer.validated_data["vider_carte"]

        tenant = connection.tenant
        receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant)

        try:
            resultat = WalletService.rembourser_en_especes(
                carte=carte,
                tenant=tenant,
                receiver_wallet=receiver_wallet,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                vider_carte=vider_carte,
            )
        except NoEligibleTokens:
            contexte = {
                "success": False,
                "message": _("Aucun solde remboursable sur cette carte."),
            }
            response = render(request, "admin/cards/refund_toast.html", contexte)
            # Pas de HX-Refresh en cas d'echec : on garde le modal ferme mais la page est OK
            # No HX-Refresh on failure: modal closes but page stays as-is
            return response

        # Formatage entier pour respecter la decision n°8 (centimes en int PARTOUT, pas de float)
        # Integer formatting to respect decision #8 (cents as int EVERYWHERE, no float)
        total_centimes = resultat['total_centimes']
        euros = total_centimes // 100
        cents = total_centimes % 100
        montant_str = f"{euros},{cents:02d} €"

        contexte = {
            "success": True,
            "message": _("Remboursement effectué : %(amount)s") % {
                "amount": montant_str,
            },
        }
        response = render(request, "admin/cards/refund_toast.html", contexte)
        # HX-Refresh force le rechargement complet de la fiche carte
        # HX-Refresh forces a full reload of the card detail page
        response["HX-Refresh"] = "true"
        return response

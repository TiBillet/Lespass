"""
Administration/views_bank_transfers.py — Vues custom admin pour le suivi
de la dette pot central -> tenant (Phase 2).

Patterns FALC /djc :
- viewsets.ViewSet (NOT ModelViewSet), methodes explicites
- serializers.Serializer pour la validation
- HTML server-rendered (HTMX)
- Permissions : superuser pour saisir/consulter dashboard,
  tenant admin pour historique tenant.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from Administration.serializers import BankTransferCreateSerializer
from fedow_core.exceptions import MontantSuperieurDette
from fedow_core.models import Transaction
from fedow_core.services import BankTransferService

logger = logging.getLogger(__name__)


def _check_superuser(request):
    """
    Verifie que l'utilisateur est superuser. Si non, rend une page HTML
    "Acces refuse" propre (au lieu d'un JSON 403 brut DRF Browsable API).
    Retourne None si superuser, sinon un HttpResponse 403 a renvoyer immediatement.
    / Verifies user is superuser. If not, returns a clean HTML "Access denied"
    page (instead of a raw DRF Browsable API JSON 403).
    Returns None if superuser, otherwise a 403 HttpResponse to return immediately.
    """
    if request.user.is_superuser:
        return None
    contexte = {
        "msg_type": "error",
        "msg_content": _("Acces superuser uniquement."),
    }
    response = render(request, "laboutik/partial/hx_messages.html", contexte, status=403)
    return response


class BankTransfersViewSet(viewsets.ViewSet):
    """
    Vues admin pour la dette pot central -> tenant.

    Routes (montees par StaffAdminSite.get_urls()) :
    - GET  /admin/bank-transfers/                       -> list (dashboard superuser)
    - POST /admin/bank-transfers/                       -> create (saisie virement)
    - GET  /admin/bank-transfers/historique/            -> historique (global, superuser)
    - GET  /admin/bank-transfers/historique-tenant/     -> historique_tenant (lecture seule, tenant admin)
    """
    permission_classes = [IsAuthenticated]

    def _render_dashboard(self, request, flash=None):
        """
        Rend le dashboard avec un flash message optionnel injecte dans le contexte.
        Contourne le bug des `messages.success` invisibles apres redirect depuis
        une vue wrappee par `admin_site.admin_view()` (cf. tests/PIEGES.md).

        / Renders the dashboard with an optional flash message in context.
        Workaround for `messages.success` swallowed after a redirect from a view
        wrapped by `admin_site.admin_view()` (see tests/PIEGES.md).

        `flash` format : {"type": "success"|"error", "msg": str}
        """
        dettes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
        contexte = {
            "dettes": dettes,
            "total_global_centimes": sum(d["dette_centimes"] for d in dettes),
            "flash": flash,
        }
        return render(request, "admin/bank_transfers/dashboard.html", contexte)

    def list(self, request):
        """GET /admin/bank-transfers/ : dashboard superuser (table de toutes les dettes)."""
        forbidden = _check_superuser(request)
        if forbidden is not None:
            return forbidden
        return self._render_dashboard(request)

    def create(self, request):
        """POST /admin/bank-transfers/ : enregistre un virement bancaire recu."""
        forbidden = _check_superuser(request)
        if forbidden is not None:
            return forbidden
        serializer = BankTransferCreateSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)

        try:
            tx = BankTransferService.enregistrer_virement(
                tenant=serializer.validated_data["tenant_uuid"],
                asset=serializer.validated_data["asset_uuid"],
                montant_en_centimes=serializer.validated_data["montant_centimes"],
                date_virement=serializer.validated_data["date_virement"],
                reference_bancaire=serializer.validated_data["reference"],
                comment=serializer.validated_data.get("comment", ""),
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                admin_email=request.user.email,
            )
        except MontantSuperieurDette:
            return self._render_dashboard(request, flash={
                "type": "error",
                "msg": _("Sur-versement detecte. Verifier la dette actuelle."),
            })

        return self._render_dashboard(request, flash={
            "type": "success",
            "msg": _("Virement enregistre : %(amount)s vers %(tenant)s.") % {
                "amount": f"{tx.amount / 100:.2f} EUR",
                "tenant": tx.tenant.name,
            },
        })

    @action(detail=False, methods=["GET"], url_path="historique")
    def historique(self, request):
        """GET /admin/bank-transfers/historique/ : liste globale (superuser)."""
        forbidden = _check_superuser(request)
        if forbidden is not None:
            return forbidden
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
        ).select_related("receiver", "asset", "tenant").order_by("-datetime")
        contexte = {"transactions": transactions, "scope": "global"}
        return render(request, "admin/bank_transfers/historique.html", contexte)

    @action(detail=False, methods=["GET"], url_path="historique-tenant")
    def historique_tenant(self, request):
        """GET /admin/bank-transfers/historique-tenant/ : liste filtree (tenant admin, lecture seule)."""
        if not TenantAdminPermissionWithRequest(request):
            raise PermissionDenied()
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
            tenant=connection.tenant,
        ).select_related("asset").order_by("-datetime")
        contexte = {"transactions": transactions, "scope": "tenant"}
        return render(request, "admin/bank_transfers/historique.html", contexte)

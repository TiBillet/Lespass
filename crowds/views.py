from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import logging


from rest_framework import viewsets, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone
import json

from BaseBillet.views import get_context
from BaseBillet.models import Tag
from fedow_public.models import AssetFedowPublic
from .models import Initiative, Contribution, CrowdConfig, Vote, Participation, BudgetItem
from .serializers import (
    BudgetItemProposalSerializer,
    ContributionCreateSerializer,
    ParticipationCreateSerializer,
    ParticipationCompleteSerializer,
)

from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


# Create your views here.
class InitiativeViewSet(viewsets.ViewSet):
    """
    ViewSet affichant les projets à financer et gérant les contributions.
    Compatible avec HTMX et Stripe.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def _participations_context(self, initiative):
        participations = initiative.participations.select_related("participant").order_by("-created_at")
        return {
            "participations": participations,
            "initiative": initiative,
        }

    def _contributions_context(self, initiative):
        contributions = initiative.contributions.select_related("contributor").order_by("-created_at")
        return {
            "contributions": contributions,
            "initiative": initiative,
        }

    def _budget_items_context(self, initiative):
        items = initiative.budget_items.select_related("contributor", "validator").order_by("-created_at")
        return {
            "budget_items": items,
            "initiative": initiative,
        }

    # ------------------------
    # Liste des projets
    # ------------------------
    def list(self, request):
        """
        Affiche la liste des projets avec le thème TiBillet + HTMX (pas de blink).
        """

        active_slug = (request.GET.get("tag") or "").strip()
        search_query = (request.GET.get("q") or "").strip()

        initiatives_qs = (
            Initiative.objects.filter(archived=False)
            .annotate(votes_total=Count("votes", distinct=True))
            .prefetch_related("tags")
        )
        # Filtering by tag
        active_tag = None
        if active_slug:
            active_tag = Tag.objects.filter(slug=active_slug).first()
            if active_tag:
                initiatives_qs = initiatives_qs.filter(tags__slug=active_slug)
        # Full-text lite search across name, description, tag name
        if search_query:
            initiatives_qs = initiatives_qs.filter(
                Q(name__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(tags__name__icontains=search_query)
            )
        # Order by votes then date, and distinct because of M2M joins
        initiatives_qs = initiatives_qs.order_by("-votes_total", "-created_at").distinct()

        paginator = Paginator(initiatives_qs, 9)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        context = get_context(request)
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "page_obj": page_obj,
            "initiatives": page_obj.object_list,
            "active_tag": active_tag,
            "all_tags": Tag.objects.filter(initiatives__isnull=False).distinct(),
            "search_query": search_query,
        })

        # HTMX request: return only the list partial to avoid full reload
        hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
        if request.headers.get("HX-Request") and hx_target == "crowds_list":
            return render(request, "crowds/partial/list.html", context)

        return render(request, "crowds/views/list.html", context)

    # ------------------------
    # Détail d’un projet
    # ------------------------
    def retrieve(self, request, pk=None):
        """
        Affiche le détail d’un projet dans la charte graphique TiBillet.
        """
        # Précharge les tags pour éviter les requêtes supplémentaires dans le template
        initiative = get_object_or_404(
            Initiative.objects.prefetch_related("tags"), pk=pk
        )
        contributions = initiative.contributions.select_related("contributor").order_by("-created_at")
        budget_items = initiative.budget_items.select_related("contributor", "validator").order_by("-created_at")

        context = get_context(request)
        # Précharger les votants pour éviter le N+1
        votes = initiative.votes.select_related("user").order_by("-created_at")
        participations = initiative.participations.select_related("participant").order_by("-created_at")
        # Help texts for Contribution form in Swal
        from django.utils.translation import gettext as _
        name_help = Contribution._meta.get_field("contributor_name").help_text or _("Votre nom ou celui de votre organisation (affiché publiquement)")
        desc_help = Contribution._meta.get_field("description").help_text or _("Un petit mot pour décrire votre contribution")
        # Ne passer que les variables réellement utilisées par les templates
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiative": initiative,
            "contributions": contributions,
            "budget_items": budget_items,
            "contrib_name_help": name_help,
            "contrib_desc_help": desc_help,
            "votes": votes,
            "participations": participations,
        })

        return render(request, "crowds/views/detail.html", context)

    @action(detail=True, methods=["post"], url_path="vote")
    def vote(self, request, pk=None):
        """
        Enregistre un vote de pertinence pour une initiative.
        - Nécessite un utilisateur authentifié (SessionAuthentication).
        - Idempotent: multiple POST par le même user n'ajoute pas de nouveau vote.
        Retourne toujours du HTML (partiel de badge de votes) pour HTMX.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            # Retourner simplement le badge inchangé (HTML) avec statut 401
            context = get_context(request)
            context.update({"initiative": initiative})
            response = render(request, "crowds/partial/votes_badge.html", context)
            response.status_code = 401
            return response

        # Crée le vote si inexistant (idempotent)
        _, created = Vote.objects.get_or_create(initiative=initiative, user=request.user)
        # Retourner le badge mis à jour + un évènement HTMX pour feedback UI
        context = get_context(request)
        context.update({"initiative": initiative})
        response = render(request, "crowds/partial/votes_badge.html", context)
        # Déclenche un évènement custom côté client sans JSON dans le body
        # HTMX parse automatiquement le JSON du header HX-Trigger en tant que detail
        try:
            response["HX-Trigger"] = json.dumps({
                "crowds:vote": {"created": created, "uuid": str(initiative.uuid)}
            })
        except Exception:
            # En cas d'erreur de sérialisation, on envoie une forme simple
            response["HX-Trigger"] = "crowds:vote"
        return response

    @action(detail=True, methods=["post"], url_path="participate")
    def participate(self, request, pk=None):
        """
        Déclare une participation à une initiative.
        Champs attendus: description (str), requested_amount_cents (int > 0) optionnel (bénévolat possible)
        Réponses:
         - 401 si non connecté
         - Si HX-Request avec HX-Target == 'participations_list' → renvoie le partiel HTML mis à jour
         - Sinon JSON { ok, id }
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 401
            return response

        # Validation via DRF serializer (et sanitation HTML)
        serializer = ParticipationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Invalid participation request: %s", serializer.errors)
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response

        data = serializer.validated_data
        amount = serializer.amount if data.get("requested_amount") else None

        Participation.objects.create(
            initiative=initiative,
            participant=request.user,
            description=data.get("description") or "",
            amount=amount,
            state=Participation.State.REQUESTED,
        )
        context = get_context(request)
        context.update(self._participations_context(initiative))
        return render(request, "crowds/partial/participations.html", context)

    @action(detail=True, methods=["post"], url_path="budget/propose")
    def propose_budget_item(self, request, pk=None):
        """
        Propose une nouvelle ligne budgétaire pour une initiative.
        Champs attendus:
          - description (str, requis, min 5 chars)
          - amount_eur (float/decimal > 0)

        Réponses:
          - 401 JSON {error} si non connecté
          - 400 JSON {error} si invalide
          - 200 JSON {ok: true, html: '<...>'} avec le partiel #budget_items_list mis à jour
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            return JsonResponse({"error": "auth_required"}, status=401)

        serializer = BudgetItemProposalSerializer(data=request.POST)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)

        # Création de la proposition
        BudgetItem.objects.create(
            initiative=initiative,
            contributor=request.user,
            description=serializer.validated_data["description"],
            amount=serializer.amount,
            state=BudgetItem.State.REQUESTED,
        )

        # Rendu du partiel mis à jour
        context = get_context(request)
        context.update(self._budget_items_context(initiative))
        html = render(request, "crowds/partial/budget_items.html", context).content.decode("utf-8")
        return JsonResponse({"ok": True, "html": html})


    @action(detail=True, methods=["post"], url_path=r"budget-items/(?P<bid>[^/.]+)/approve")
    def approve_budget_item(self, request, pk=None, bid=None):
        """
        Approuve une proposition de ligne budgétaire.
        Réservé aux admins/staff. Retourne toujours le partiel HTML mis à jour.
        """
        initiative = get_object_or_404(Initiative, pk=pk)

        def _render(status_code=200):
            ctx = get_context(request)
            ctx.update(self._budget_items_context(initiative))
            resp = render(request, "crowds/partial/budget_items.html", ctx)
            resp.status_code = status_code
            return resp

        if not request.user.is_authenticated:
            return _render(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render(status_code=403)

        item = get_object_or_404(BudgetItem, pk=bid, initiative=initiative)
        if item.state != BudgetItem.State.REQUESTED:
            return _render(status_code=400)
        try:
            item.state = BudgetItem.State.APPROVED
            item.validator = request.user
            item.save(update_fields=["state", "validator"])
        except Exception:
            # En cas d'erreur, on renvoie le partiel sans changer l'état
            return _render(status_code=400)
        return _render(status_code=200)


    @action(detail=True, methods=["post"], url_path=r"budget-items/(?P<bid>[^/.]+)/reject")
    def reject_budget_item(self, request, pk=None, bid=None):
        """
        Rejette une proposition de ligne budgétaire.
        Réservé aux admins/staff. Retourne toujours le partiel HTML mis à jour.
        """
        initiative = get_object_or_404(Initiative, pk=pk)

        def _render(status_code=200):
            ctx = get_context(request)
            ctx.update(self._budget_items_context(initiative))
            resp = render(request, "crowds/partial/budget_items.html", ctx)
            resp.status_code = status_code
            return resp

        if not request.user.is_authenticated:
            return _render(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render(status_code=403)

        item = get_object_or_404(BudgetItem, pk=bid, initiative=initiative)
        if item.state != BudgetItem.State.REQUESTED:
            return _render(status_code=400)
        try:
            item.state = BudgetItem.State.REJECTED
            item.validator = request.user
            item.save(update_fields=["state", "validator"])
        except Exception:
            return _render(status_code=400)
        return _render(status_code=200)


    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/complete")
    def complete_participation(self, request, pk=None, pid=None):
        """
        Marque une participation comme terminée (par l'utilisateur propriétaire).
        Champs attendus: time_spent_minutes (int > 0)
        Autorisé uniquement si l'état actuel est REQUESTED ou APPROVED_ADMIN.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        part = get_object_or_404(Participation, pk=pid, initiative=initiative)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 401
            return response

        if part.participant_id != request.user.id:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 403
            return response
        # Vérifier l'état courant
        if part.state not in (Participation.State.REQUESTED, Participation.State.APPROVED_ADMIN):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response
        try:
            minutes = int(request.POST.get("time_spent_minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response
        part.time_spent_minutes = minutes
        part.state = Participation.State.COMPLETED_USER
        part.save(update_fields=["time_spent_minutes", "state", "updated_at"])
        context = get_context(request)
        context.update(self._participations_context(initiative))
        return render(request, "crowds/partial/participations.html", context)

    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/approve")
    def approve_participation(self, request, pk=None, pid=None):
        """
        Validation admin d'une participation (étape 2): REQUESTED -> APPROVED_ADMIN.
        Réservé aux admins/staff. Retourne le partiel si HX-Target == 'participations_list'.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        part = get_object_or_404(Participation, pk=pid, initiative=initiative)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 401
            return response
        if not (request.user.is_staff or request.user.is_superuser):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 403
            return response
        if part.state != Participation.State.REQUESTED:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response
        part.state = Participation.State.APPROVED_ADMIN
        part.save(update_fields=["state", "updated_at"])
        context = get_context(request)
        context.update(self._participations_context(initiative))
        return render(request, "crowds/partial/participations.html", context)

    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/validate")
    def validate_participation(self, request, pk=None, pid=None):
        """
        Validation finale admin (étape 4): COMPLETED_USER -> VALIDATED_ADMIN.
        Réservé aux admins/staff. Retourne le partiel si HX-Target == 'participations_list'.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        part = get_object_or_404(Participation, pk=pid, initiative=initiative)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 401
            return response
        if not (request.user.is_staff or request.user.is_superuser):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 403
            return response
        if part.state != Participation.State.COMPLETED_USER:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response
        part.state = Participation.State.VALIDATED_ADMIN
        part.save(update_fields=["state", "updated_at"])
        context = get_context(request)
        context.update(self._participations_context(initiative))
        return render(request, "crowds/partial/participations.html", context)

    @action(detail=True, methods=["post"], url_path="contribute")
    def contribute(self, request, pk=None):
        """
        Crée une contribution financière à une initiative.
        Champs attendus (POST): amount (centimes), contributor_name (str), description (str, optionnel)
        Retourne toujours du HTML: le partiel 'crowds/partial/contributions.html'.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._contributions_context(initiative))
            response = render(request, "crowds/partial/contributions.html", context)
            response.status_code = 401
            return response

        # Validation via DRF serializer (et sanitation HTML)
        serializer = ContributionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            context = get_context(request)
            context.update(self._contributions_context(initiative))
            response = render(request, "crowds/partial/contributions.html", context)
            response.status_code = 400
            return response

        # Create
        data = serializer.validated_data
        Contribution.objects.create(
            initiative=initiative,
            contributor=request.user,
            contributor_name=data.get("contributor_name") or "",
            description=data.get("description") or "",
            amount=data.get("amount") or 0,
        )
        context = get_context(request)
        context.update(self._contributions_context(initiative))
        return render(request, "crowds/partial/contributions.html", context)

    @action(detail=True, methods=["post"], url_path=r"contributions/(?P<cid>[^/.]+)/mark-paid")
    def mark_contribution_paid(self, request, pk=None, cid=None):
        """
        Marque une contribution comme payée (admin/staff uniquement).
        Retourne toujours le partiel HTML des contributions.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        # Toujours renvoyer le partiel HTML (règle HTMX)
        def _render(status_code=200):
            ctx = get_context(request)
            ctx.update(self._contributions_context(initiative))
            resp = render(request, "crowds/partial/contributions.html", ctx)
            resp.status_code = status_code
            return resp
        if not request.user.is_authenticated:
            return _render(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render(status_code=403)
        contrib = get_object_or_404(Contribution, pk=cid, initiative=initiative)
        # Met à jour seulement si nécessaire
        try:
            if contrib.payment_status not in [Contribution.PaymentStatus.PAID, Contribution.PaymentStatus.PAID_ADMIN]:
                contrib.payment_status = Contribution.PaymentStatus.PAID_ADMIN
                contrib.paid_at = timezone.now()
                contrib.save(update_fields=["payment_status", "paid_at"]) 
        except Exception:
            # même en cas d'erreur, renvoyer le partiel (l'état restera inchangé)
            pass
        return _render(status_code=200)

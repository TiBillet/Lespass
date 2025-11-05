from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.conf import settings

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
from .models import Initiative, Contribution, CrowdConfig, Vote, Participation

from django.contrib.auth import get_user_model
from .demo_data import seed as seed_crowds_demo

User = get_user_model()


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

    # ------------------------
    # Liste des projets
    # ------------------------
    def list(self, request):
        """
        Affiche la liste des projets avec le thème TiBillet + HTMX (pas de blink).
        """
        # if settings.TEST:
        #     seed_crowds_demo()

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
        initiative = get_object_or_404(Initiative, pk=pk)
        contributions = initiative.contributions.select_related("contributor").order_by("-created_at")

        context = get_context(request)
        # Précharger les votants pour éviter le N+1
        votes = initiative.votes.select_related("user").order_by("-created_at")
        participations = initiative.participations.select_related("participant").order_by("-created_at")
        # Help texts for Contribution form in Swal
        from django.utils.translation import gettext as _
        name_help = Contribution._meta.get_field("contributor_name").help_text or _("Votre nom ou celui de votre organisation (affiché publiquement)")
        desc_help = Contribution._meta.get_field("description").help_text or _("Un petit mot pour décrire votre contribution")
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiative": initiative,
            "contributions": contributions,
            "contrib_name_help": name_help,
            "contrib_desc_help": desc_help,
            "votes": votes,
            "voters_count": votes.count(),
            "participations": participations,
            # "funded_eur": (initiative.funded_amount or 0) / 100,
            "goal_eur": (initiative.funding_goal or 0) / 100,
            # Progression des demandes de participations vs financements
            # "requested_eur": initiative.requested_total_eur,
            "requested_percent_int": initiative.requested_vs_funded_percent_int,
            "requested_percent_int_capped": min(100, initiative.requested_vs_funded_percent_int),
            "requested_color": initiative.requested_ratio_color,
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
        Champs attendus: description (str), requested_amount_cents (int > 0)
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
        desc = (request.POST.get("description") or "").strip()
        try:
            amount = int(request.POST.get("requested_amount_cents") or 0)
        except (TypeError, ValueError):
            amount = 0
        if not desc or amount <= 0:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 400
            return response

        Participation.objects.create(
            initiative=initiative,
            participant=request.user,
            description=desc,
            requested_amount_cents=amount,
            state=Participation.State.REQUESTED,
        )
        context = get_context(request)
        context.update(self._participations_context(initiative))
        return render(request, "crowds/partial/participations.html", context)

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
        # Inputs
        try:
            amount = int(request.POST.get("amount") or request.POST.get("amount_cents") or 0)
        except (TypeError, ValueError):
            amount = 0
        contributor_name = (request.POST.get("contributor_name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        if amount <= 0 or not contributor_name:
            context = get_context(request)
            context.update(self._contributions_context(initiative))
            response = render(request, "crowds/partial/contributions.html", context)
            response.status_code = 400
            return response
        # Create
        Contribution.objects.create(
            initiative=initiative,
            contributor=request.user,
            contributor_name=contributor_name,
            description=description,
            amount=amount,
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

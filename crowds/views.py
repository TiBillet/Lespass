from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.conf import settings

from rest_framework import viewsets, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action

from django.core.paginator import Paginator
from django.db.models import Count

from BaseBillet.views import get_context
from fedow_public.models import AssetFedowPublic
from .models import Initiative, Contribution, CrowdConfig, Vote, Participation
from django.contrib.auth import get_user_model

User = get_user_model()

def demo_data():
    if settings.DEBUG:
        if not Initiative.objects.all():
            project1 = Initiative.objects.create(
                name="Demo Project",
                description="This is a demo project",
                funding_goal=1000,
                asset=AssetFedowPublic.objects.get(category=AssetFedowPublic.STRIPE_FED_FIAT),
            )

            Contribution.objects.create(
                initiative=project1,
                contributor=User.objects.get(email="jturbeaux@pm.me"),
                amount=100,
            )

            project2 = Initiative.objects.create(
                name="Demo Project 2",
                description="This is a demo project 2",
                funding_goal=10000,
                asset=AssetFedowPublic.objects.get(category=AssetFedowPublic.STRIPE_FED_FIAT),
            )
            Contribution.objects.create(
                initiative=project2,
                contributor=User.objects.get(email="jturbeaux@pm.me"),
                amount=1500,
            )

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

    # ------------------------
    # Liste des projets
    # ------------------------
    def list(self, request):
        """
        Affiche la liste des projets avec le thème TiBillet + HTMX (pas de blink).
        """
        if settings.DEBUG:
            demo_data()

        initiatives_qs = (
            Initiative.objects.all()
            .annotate(votes_total=Count("votes", distinct=True))
            .order_by("-votes_total", "-created_at")
        )
        paginator = Paginator(initiatives_qs, 9)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        context = get_context(request)
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "page_obj": page_obj,
            "initiatives": page_obj.object_list,
        })

        # HTMX request: return only the list partial to avoid full reload
        if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "crowds_list":
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
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiative": initiative,
            "contributions": contributions,
            "votes": votes,
            "voters_count": votes.count(),
            "participations": participations,
            "funded_eur": (initiative.funded_amount or 0) / 100,
            "goal_eur": (initiative.funding_goal or 0) / 100,
            # Progression des demandes de participations vs financements
            "requested_eur": initiative.requested_total_eur,
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
        Vote.objects.get_or_create(initiative=initiative, user=request.user)
        # Retourner le badge mis à jour
        context = get_context(request)
        context.update({"initiative": initiative})
        return render(request, "crowds/partial/votes_badge.html", context)

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


from decimal import Decimal

from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.conf import settings
import logging

from rest_framework import viewsets, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action

from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q, Sum, F, DecimalField, ExpressionWrapper
from django.utils import timezone
from django.utils.translation import gettext as _, gettext
import json

from BaseBillet.views import get_context
from BaseBillet.models import (
    Tag,
    Product,
    Price,
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    SaleOrigin,
    Configuration,
)
from Customers.models import Client
from fedow_public.models import AssetFedowPublic
from .models import Initiative, Contribution, CrowdConfig, Vote, Participation, BudgetItem, GlobalFunding
from .serializers import (
    BudgetItemProposalSerializer,
    ContributionCreateSerializer,
    GlobalFundingCreateSerializer,
    GlobalFundingAllocateSerializer,
    ParticipationCreateSerializer,
    ParticipationCompleteSerializer,
)
from ApiBillet.serializers import get_or_create_price_sold
from PaiementStripe.views import CreationPaiementStripe

from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

GLOBAL_FUNDING_ALLOC_NAME = "Répartition globale"


def _user_funded_cache_key(tenant_id, user_id):
    return f"crowds:user-funded:{tenant_id}:{user_id}"


def get_user_funded_total(user):
    """
    FR: Calcule le total financé par un utilisateur spécifique.
        Prend en compte le financement global ET les contributions aux projets.
    EN: Compute the total amount funded by a specific user.
        Includes global funding AND project contributions.
    """
    if not user or not user.is_authenticated:
        return 0
    tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
    cache_key = _user_funded_cache_key(tenant_id, user.pk)
    cached_total = cache.get(cache_key)
    if cached_total is not None:
        return cached_total

    # FR: Somme des financements globaux / EN: Sum of global fundings
    total_global_funding = GlobalFunding.objects.filter(user=user).aggregate(total=Sum("amount_funded")).get("total") or 0
    # FR: Somme des contributions directes / EN: Sum of direct contributions
    total_project_contributions = Contribution.objects.filter(contributor=user).aggregate(total=Sum("amount")).get("total") or 0
    
    grand_total = total_global_funding + total_project_contributions
    
    # FR: Cache court (1 min) car les paiements Stripe peuvent changer la valeur vite
    # EN: Short cache (1 min) as Stripe payments can change values quickly
    cache.set(cache_key, grand_total, 60)
    return grand_total


def clear_user_funded_cache(user):
    """
    FR: Supprime le cache du montant financé pour un utilisateur.
    EN: Clears the funded amount cache for a user.
    """
    tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
    cache.delete(_user_funded_cache_key(tenant_id, user.pk))


class GlobalFundingViewset(viewsets.ViewSet):
    """
    FR: Gère le financement "global" (don non affecté à un projet précis au départ).
    EN: Manages "global" funding (donation not assigned to a specific project initially).
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def _get_or_create_crowdfunding_price(self) -> Price:
        """
        FR: Récupère ou crée le produit technique utilisé pour le financement global.
        EN: Retrieves or creates the technical product used for global funding.
        """
        product = Product.objects.filter(name__iexact="crowdfunding").order_by("pk").first()
        if not product:
            product = Product.objects.create(
                name="crowdfunding",
                categorie_article=Product.NONE,
                publish=False,
                nominative=False,
            )
        price = product.prices.order_by("pk").first()
        if not price:
            price = Price.objects.create(
                product=product,
                name="Libre",
                prix=Decimal("0.00"),
                free_price=True,
                publish=False,
            )
        return price

    def create(self, request):
        """
        FR: Crée une intention de financement global et redirige vers Stripe.
        EN: Creates a global funding intention and redirects to Stripe.
        """
        if not request.user.is_authenticated:
            return JsonResponse({"error": _("Authentication required.")}, status=401)

        serializer = GlobalFundingCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)

        data = serializer.validated_data
        amount_cents = data.get("amount") or 0
        if amount_cents <= 0:
            return JsonResponse({"error": _("Invalid amount.")}, status=400)

        # FR: Préparation de la ligne comptable (LigneArticle)
        # EN: Accounting line preparation (LigneArticle)
        price_obj = self._get_or_create_crowdfunding_price()
        amount_decimal = (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
        price_sold_obj = get_or_create_price_sold(price_obj, custom_amount=amount_decimal)

        accounting_line = LigneArticle.objects.create(
            pricesold=price_sold_obj,
            qty=1,
            amount=amount_cents,
            payment_method=PaymentMethod.STRIPE_NOFED,
            sale_origin=SaleOrigin.LESPASS,
        )

        # FR: Création de l'objet GlobalFunding
        # EN: Creation of the GlobalFunding object
        global_funding_instance = GlobalFunding.objects.create(
            user=request.user,
            amount_funded=amount_cents,
            amount_to_be_included=amount_cents,
            contributor_name=data.get("contributor_name") or "",
            description=data.get("description") or "",
            ligne_article=accounting_line,
        )

        # FR: Métadonnées pour Stripe (pour le webhook de retour)
        # EN: Metadata for Stripe (for return webhook)
        stripe_metadata = {
            "tenant": f"{connection.tenant.uuid}",
            "global_funding_uuid": f"{global_funding_instance.pk}",
            "user": f"{request.user.email}",
        }

        # FR: Initialisation du paiement via le builder TiBillet
        # EN: Payment initialization via TiBillet builder
        payment_builder = CreationPaiementStripe(
            user=request.user,
            liste_ligne_article=[accounting_line],
            metadata=stripe_metadata,
            reservation=None,
            source=Paiement_stripe.FRONT_CROWDS,
            success_url="stripe_return/",
            cancel_url="stripe_return/",
            absolute_domain=request.build_absolute_uri("/crowd/global-funding/"),
        )

        if not payment_builder.is_valid():
            return JsonResponse(
                {"error": _("Erreur lors de la création du paiement.")},
                status=400,
            )

        # FR: Passage en UNPAID en attendant le retour de Stripe
        # EN: Set to UNPAID while waiting for Stripe return
        payment_db_obj = payment_builder.paiement_stripe_db
        payment_db_obj.lignearticles.all().update(status=LigneArticle.UNPAID)
        
        # FR: On invalide le cache car l'utilisateur a initié un flux
        # EN: Invalidate cache since user initiated a flow
        clear_user_funded_cache(request.user)
        
        return JsonResponse({"stripe_url": payment_builder.checkout_session.url})

    @action(detail=True, methods=["get"], url_path="stripe_return")
    def stripe_return(self, request, pk=None):
        """
        FR: Retour de Stripe (succès ou annulation) vers la page liste des projets.
        EN: Stripe return (success or cancel) back to the list page.
        """
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=pk)
        paiement_stripe.update_checkout_status()
        paiement_stripe.refresh_from_db()

        # TODO traitement en cours False, ligne article valide, mail envoyé

        return HttpResponseRedirect("/crowd/")

    @action(detail=False, methods=["get"], url_path="funded-total")
    def funded_total(self, request):
        """
        FR: Retourne un fragment HTMX "J'ai financé X".
        EN: Returns the HTMX fragment "I funded X".
        """
        context = get_context(request)
        context.update({
            "user_funded_total": get_user_funded_total(request.user),
            "global_funding_currency": context["config"].currency_code,
        })
        return render(request, "crowds/partial/global_funding_amount.html", context)

    @action(detail=False, methods=["post"], url_path="allocate")
    def allocate(self, request):
        """
        FR: Répartit un montant vers un projet et réduit la somme à répartir.
        EN: Allocates an amount to a project and reduces the remaining pool.
        """
        if not request.user.is_authenticated:
            return JsonResponse({"error": _("Authentication required.")}, status=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": _("Permission denied.")}, status=403)

        serializer = GlobalFundingAllocateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)

        initiative = get_object_or_404(Initiative, pk=serializer.validated_data["initiative"])
        amount = serializer.amount or 0
        if amount <= 0:
            return JsonResponse({"error": _("Invalid amount.")}, status=400)

        recharge_total_eur = LigneArticle.objects.filter(
            carte__isnull=False,
            paiement_stripe__isnull=False,
            paiement_stripe__status__in=[Paiement_stripe.PAID, Paiement_stripe.VALID],
            payment_method__in=[PaymentMethod.STRIPE_FED, PaymentMethod.STRIPE_NOFED, PaymentMethod.STRIPE_SEPA_NOFED],
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("pricesold__prix") * F("qty"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        ).get("total") or Decimal("0.00")
        recharge_total = int(recharge_total_eur * 100)
        global_funding_total = GlobalFunding.objects.aggregate(total=Sum("amount_funded")).get("total") or 0
        allocated_total = Contribution.objects.filter(
            contributor_name=GLOBAL_FUNDING_ALLOC_NAME
        ).aggregate(total=Sum("amount")).get("total") or 0
        available_total = recharge_total + global_funding_total - allocated_total
        if available_total < 0:
            available_total = 0
        if amount > available_total:
            return JsonResponse({"error": _("Amount exceeds remaining pool.")}, status=400)

        Contribution.objects.create(
            initiative=initiative,
            contributor=request.user,
            contributor_name=GLOBAL_FUNDING_ALLOC_NAME,
            description=_("Répartition du financement global"),
            amount=amount,
            payment_status=Contribution.PaymentStatus.PAID_ADMIN,
            paid_at=timezone.now(),
        )

        return JsonResponse({"ok": True})


# Create your views here.
class InitiativeViewSet(viewsets.ViewSet):
    """
    ViewSet affichant les projets à financer et gérant les contributions.
    Compatible avec HTMX et Stripe.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def _should_show_user_source(self, initiative, list_name, users):
        tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
        list_size = len(users)
        cache_key = f"crowds:user-source:{initiative.pk}:{list_name}:{tenant_id}:{list_size}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        source_ids = {u.client_source_id for u in users if u and u.client_source_id}
        show = len(source_ids) > 1 or (tenant_id is not None and any(sid != tenant_id for sid in source_ids))
        cache.set(cache_key, show, 60)
        return show

    def _participations_context(self, initiative):
        participations = list(
            initiative.participations.select_related("participant__client_source").order_by("-created_at")
        )
        show_participations_origin = self._should_show_user_source(
            initiative, "participations", [p.participant for p in participations]
        )
        return {
            "participations": participations,
            "initiative": initiative,
            "show_participations_origin": show_participations_origin,
        }

    def _contributions_context(self, initiative):
        contributions = list(
            initiative.contributions.select_related("contributor__client_source").order_by("-created_at")
        )
        show_contributions_origin = self._should_show_user_source(
            initiative, "contributions", [c.contributor for c in contributions if c.contributor_id]
        )
        return {
            "contributions": contributions,
            "initiative": initiative,
            "show_contributions_origin": show_contributions_origin,
        }

    def _budget_items_context(self, initiative):
        items = list(
            initiative.budget_items.select_related(
                "contributor__client_source", "validator__client_source"
            ).order_by("-created_at")
        )
        show_budget_items_origin = self._should_show_user_source(
            initiative, "budget_items", [bi.contributor for bi in items if bi.contributor_id]
        )
        return {
            "budget_items": items,
            "initiative": initiative,
            "show_budget_items_origin": show_budget_items_origin,
        }

    # ------------------------
    # Liste des projets
    # ------------------------
    def list(self, request):
        """
        FR: Affiche la liste des projets avec le thème TiBillet + HTMX.
            Gère le filtrage par tag, la recherche plein texte et l'exclusion des archivés.
        EN: Displays the list of projects with TiBillet theme + HTMX.
            Handles tag filtering, full-text search, and archived exclusion.
        """

        active_tag_slug = (request.GET.get("tag") or "").strip()
        search_query_str = (request.GET.get("q") or "").strip()

        # FR: On vérifie si le tag "Archivé" est sélectionné pour montrer les projets clos
        # EN: Check if "Archived" tag is selected to show closed projects
        is_showing_archived = (active_tag_slug == "archive")

        # FR: Queryset de base : exclut les archivés par défaut
        # EN: Base queryset: exclude archived by default
        if is_showing_archived:
            initiatives_queryset = (
                Initiative.objects.all()
                .annotate(votes_total=Count("votes", distinct=True))
                .prefetch_related("tags")
            )
        else:
            initiatives_queryset = (
                Initiative.objects.filter(archived=False)
                .annotate(votes_total=Count("votes", distinct=True))
                .prefetch_related("tags")
            )

        # FR: Filtrage par tag / EN: Tag filtering
        active_tag_obj = None
        if active_tag_slug:
            active_tag_obj = Tag.objects.filter(slug=active_tag_slug).first()
            if active_tag_obj:
                initiatives_queryset = initiatives_queryset.filter(tags__slug=active_tag_slug)
        
        # FR: Recherche plein texte (nom, description, tag)
        # EN: Full-text search (name, description, tag)
        if search_query_str:
            initiatives_queryset = initiatives_queryset.filter(
                Q(name__icontains=search_query_str)
                | Q(description__icontains=search_query_str)
                | Q(tags__name__icontains=search_query_str)
            )
            
        # FR: Tri par votes puis par date de création
        # EN: Sort by votes then by creation date
        initiatives_queryset = initiatives_queryset.order_by("-votes_total", "-created_at").distinct()

        # FR: On convertit en liste (affichage global sans pagination)
        # EN: Convert to list (global display without pagination)
        initiatives_list = list(initiatives_queryset)

        view_context = get_context(request)
        contributor_name_help = Contribution._meta.get_field("contributor_name").help_text or _(
            "Votre nom ou celui de votre organisation (affiché publiquement)")
        contribution_description_help = Contribution._meta.get_field("description").help_text or _(
            "Un petit mot pour décrire votre contribution")
            
        view_context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiatives": initiatives_list,
            "active_tag": active_tag_obj,
            "all_tags": Tag.objects.filter(initiatives__isnull=False).distinct(),
            "search_query": search_query_str,
            "contrib_name_help": contributor_name_help,
            "contrib_desc_help": contribution_description_help,
        })

        # FR: Requête HTMX : on ne renvoie que le fragment de liste
        # EN: HTMX request: only return the list fragment
        htmx_target = (request.headers.get("HX-Target") or "").lstrip("#")
        if request.headers.get("HX-Request") and htmx_target == "crowds_list":
            return render(request, "crowds/partial/list.html", view_context)

        # FR: Requête standard : on ajoute le résumé global au contexte
        # EN: Standard request: add global summary to context
        view_context.update(self._summary_context())
        view_context.update({
            "user_funded_total": get_user_funded_total(request.user),
            "global_funding_currency": view_context["config"].currency_code,
        })
        return render(request, "crowds/views/list.html", view_context)

    def _summary_context(self):
        """
        FR: Calcule les statistiques globales pour le bandeau de résumé et les détails.
            Inclut les montants financés, les objectifs, les participations et le temps passé.
        EN: Compute global statistics for the summary bar and details.
            Includes funded amounts, goals, participations, and time spent.
        """
        tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
        cache_key = f"crowds:list:summary:{tenant_id}"
        cached_summary = cache.get(cache_key)
        if cached_summary is not None:
            return cached_summary

        # FR: On ne prend en compte que les initiatives actives (non archivées)
        # EN: Only active initiatives (not archived) are considered
        active_initiatives_queryset = Initiative.objects.filter(archived=False)

        # FR: Statistiques de financement (contributions payées)
        # EN: Funding statistics (paid contributions)
        total_funded_amount = Contribution.objects.filter(
            initiative__in=active_initiatives_queryset,
            payment_status__in=[Contribution.PaymentStatus.PAID_ADMIN, Contribution.PaymentStatus.PAID],
        ).aggregate(total=Sum("amount")).get("total") or 0

        # FR: Total des participations déjà validées par l'admin
        # EN: Total of participations already validated by an admin
        total_validated_participation_amount = Participation.objects.filter(
            initiative__in=active_initiatives_queryset
        ).filter(state=Participation.State.VALIDATED_ADMIN
        ).aggregate(total=Sum("amount")).get("total") or 0

        # FR: Temps total passé par les participants (tous projets confondus)
        # EN: Total time spent by participants (across all projects)
        total_time_spent_minutes = Participation.objects.aggregate(
            total=Sum("time_spent_minutes")
        ).get("total") or 0

        # FR: Objectif total de financement (somme des lignes budgétaires approuvées)
        # EN: Total funding goal (sum of approved budget items)
        total_funding_goal = BudgetItem.objects.filter(
            state=BudgetItem.State.APPROVED,
            initiative__in=active_initiatives_queryset
        ).aggregate(total=Sum("amount")).get("total") or 0

        # FR: Calcul du pourcentage de financement global
        # EN: Calculation of global funding percentage
        global_funding_percent = 0
        if total_funding_goal:
            global_funding_percent = int(round((total_funded_amount / total_funding_goal) * 100))

        # FR: Nombre de contributeurs uniques (votants + participants + financeurs)
        # EN: Count of unique contributors (voters + participants + funders)
        unique_contributor_ids = set(Vote.objects.values_list("user_id", flat=True))
        unique_contributor_ids.update(Participation.objects.values_list("participant_id", flat=True))
        unique_contributor_ids.update(
            Contribution.objects.exclude(contributor_id__isnull=True).values_list("contributor_id", flat=True)
        )
        total_participants_count = User.objects.filter(id__in=unique_contributor_ids).count()

        # FR: Vérification si les contributeurs proviennent de plusieurs lieux/organisations
        # EN: Check if contributors come from multiple locations/organizations
        source_client_ids = User.objects.filter(id__in=unique_contributor_ids, client_source_id__isnull=False).values_list(
            "client_source_id", flat=True).distinct()
        has_multiple_sources = len(source_client_ids) > 1 or (
                tenant_id is not None and any(sid != tenant_id for sid in source_client_ids)
        )

        # FR: Liste des 9 dernières participations actives pour affichage rapide
        # EN: List of the last 9 active participations for quick display
        active_participations_queryset = Participation.objects.exclude(
            state__in=[Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN]
        ).select_related("participant", "initiative").order_by("-created_at")[:9]
        
        formatted_active_participations = []
        for p in active_participations_queryset:
            formatted_active_participations.append({
                "participant": p.participant.full_name_or_email(),
                "initiative": p.initiative.name,
                "description": p.description,
                "amount": p.amount,
                "currency": p.initiative.currency,
            })
            
        total_active_participations_count = Participation.objects.exclude(
            state__in=[Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN]
        ).count()

        # FR: Calcul du pool de financement global à répartir
        # EN: Calculation of the global funding pool to allocate
        total_stripe_recharges_eur = LigneArticle.objects.filter(
            carte__isnull=False,
            paiement_stripe__isnull=False,
            paiement_stripe__status__in=[Paiement_stripe.PAID, Paiement_stripe.VALID],
            payment_method__in=[PaymentMethod.STRIPE_FED, PaymentMethod.STRIPE_NOFED, PaymentMethod.STRIPE_SEPA_NOFED],
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("pricesold__prix") * F("qty"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        ).get("total") or Decimal("0.00")
        
        total_stripe_recharges_cents = int(total_stripe_recharges_eur * 100)
        total_direct_global_funding = GlobalFunding.objects.aggregate(total=Sum("amount_funded")).get("total") or 0
        total_already_allocated = Contribution.objects.filter(
            contributor_name=GLOBAL_FUNDING_ALLOC_NAME
        ).aggregate(total=Sum("amount")).get("total") or 0
        
        funding_to_allocate = total_stripe_recharges_cents + total_direct_global_funding - total_already_allocated
        if funding_to_allocate < 0:
            funding_to_allocate = 0

        # FR: Agrégation par devise pour le détail des monnaies
        # EN: Aggregation by currency for currency details
        initiatives_currency_data = list(
            Initiative.objects.filter(archived=False).values_list("uuid", "asset_id", "currency")
        )
        all_asset_ids = {aid for _, aid, _ in initiatives_currency_data if aid}
        
        asset_currency_code_by_id = {}
        if all_asset_ids:
            asset_currency_code_by_id = {
                asset_id: code for asset_id, code in AssetFedowPublic.objects.filter(
                    pk__in=all_asset_ids
                ).values_list("id", "currency_code")
            }
            
        currency_by_initiative_id = {}
        for initiative_uuid, asset_id, cur in initiatives_currency_data:
            if asset_id and asset_id in asset_currency_code_by_id:
                currency_by_initiative_id[initiative_uuid] = asset_currency_code_by_id[asset_id]
            else:
                currency_by_initiative_id[initiative_uuid] = cur or ""

        currency_blocks_data = {}
        for cur in currency_by_initiative_id.values():
            if not cur:
                continue
            currency_blocks_data.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks_data[cur]["projects"] += 1

        for row in Contribution.objects.values("initiative_id").annotate(total=Sum("amount")):
            cur = currency_by_initiative_id.get(row["initiative_id"], "")
            if not cur:
                continue
            currency_blocks_data.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks_data[cur]["funding"] += row["total"] or 0

        for row in Participation.objects.values("initiative_id").annotate(total=Sum("amount")):
            cur = currency_by_initiative_id.get(row["initiative_id"], "")
            if not cur:
                continue
            currency_blocks_data.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks_data[cur]["participation"] += row["total"] or 0

        # FR: Préparation des initiatives pour la modale de répartition admin
        # EN: Prepare initiatives for the admin allocation modal
        initiatives_for_allocation = []
        for initiative in Initiative.objects.filter(archived=False).only("uuid", "name"):
            initiatives_for_allocation.append({
                "uuid": str(initiative.uuid),
                "name": initiative.name,
                "url": initiative.get_absolute_url(),
            })

        # FR: Indicateurs de budget restant à réclamer
        # EN: Indicators for remaining budget to be claimed
        remaining_to_claim_amount = total_funded_amount - total_validated_participation_amount
        claim_ratio_percent = 0
        if total_funded_amount > 0:
            claim_ratio_percent = (total_validated_participation_amount / total_funded_amount) * 100

        # FR: Système de couleur pour l'alerte de budget (Vert < 70%, Jaune < 90%, Rouge >= 90%)
        # EN: Color system for budget alert (Green < 70%, Yellow < 90%, Red >= 90%)
        budget_claim_alert_color = "success"
        if claim_ratio_percent >= 90:
            budget_claim_alert_color = "danger"
        elif claim_ratio_percent >= 70:
            budget_claim_alert_color = "warning"

        summary_context_data = {
            "summary_time_spent_minutes": total_time_spent_minutes,
            "summary_funding_goal_total": total_funding_goal,
            "summary_funding_percent": global_funding_percent,
            "summary_currency_blocks": [
                {
                    "code": code,
                    "projects": data["projects"],
                    "funding": data["funding"],
                    "participation": data["participation"],
                }
                for code, data in sorted(currency_blocks_data.items(), key=lambda item: item[0])
            ],
            "summary_participants_count": total_participants_count,
            "summary_sources_count": len(source_client_ids),
            "summary_has_multiple_sources": has_multiple_sources,
            "summary_active_participations": formatted_active_participations,
            "summary_active_participations_count": total_active_participations_count,
            "summary_funding_to_allocate": funding_to_allocate,
            "summary_initiatives_for_alloc": initiatives_for_allocation,
            # FR: Textes d'aide pour le formulaire de financement global
            # EN: Help texts for Global Funding form
            "contrib_name_help": Contribution._meta.get_field("contributor_name").help_text or gettext(
                "Votre nom ou celui de votre organisation (affiché publiquement)"),
            "contrib_desc_help": Contribution._meta.get_field("description").help_text or gettext(
                "Un petit mot pour décrire votre contribution"),
            # FR: Indicateurs de budget financé vs réclamé
            # EN: Indicators for funded vs claimed budget
            "summary_remaining_to_claim": max(0, remaining_to_claim_amount),
            "summary_claim_ratio": claim_ratio_percent,
            "summary_claim_color": budget_claim_alert_color,
        }
        cache.set(cache_key, summary_context_data, 60)
        return summary_context_data

    # ------------------------
    # Détail d’un projet
    # ------------------------
    def retrieve(self, request, pk=None):
        """
        FR: Affiche le détail complet d’un projet spécifique.
            Inclut les contributions, les lignes budgétaires et les participations.
        EN: Displays complete detail of a specific project.
            Includes contributions, budget items, and participations.
        """
        try:
            # FR: On vérifie l'existence de l'initiative / EN: Check initiative existence
            if not Initiative.objects.filter(pk=pk).exists():
                return redirect('/contrib')
        except ValidationError:
            # FR: pk n'est pas un UUID valide / EN: pk is not a valid UUID
            return redirect('/contrib')

        initiative_obj = get_object_or_404(
            Initiative.objects.prefetch_related("tags"), pk=pk
        )
        
        # FR: Préparation des contextes spécifiques / EN: Prepare specific contexts
        contributions_data = self._contributions_context(initiative_obj)
        budget_items_data = self._budget_items_context(initiative_obj)
        participations_data = self._participations_context(initiative_obj)

        view_context = get_context(request)
        
        # FR: Précharger les votants pour éviter le N+1
        # EN: Preload voters to avoid N+1 queries
        project_votes = list(initiative_obj.votes.select_related("user__client_source").order_by("-created_at"))
        
        # FR: Décide si on affiche l'origine géographique des votants
        # EN: Decide whether to show voters' geographical origin
        should_show_votes_origin = self._should_show_user_source(
            initiative_obj, "votes", [v.user for v in project_votes]
        )
        
        # FR: Textes d'aide pour les formulaires / EN: Help texts for forms
        from django.utils.translation import gettext as _
        contrib_name_help_text = Contribution._meta.get_field("contributor_name").help_text or _(
            "Votre nom ou celui de votre organisation (affiché publiquement)")
        contrib_desc_help_text = Contribution._meta.get_field("description").help_text or _(
            "Un petit mot pour décrire votre contribution")
            
        view_context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiative": initiative_obj,
            "contrib_name_help": contrib_name_help_text,
            "contrib_desc_help": contrib_desc_help_text,
            "votes": project_votes,
            "show_votes_origin": should_show_votes_origin,
        })
        view_context.update(contributions_data)
        view_context.update(budget_items_data)
        view_context.update(participations_data)

        return render(request, "crowds/views/detail.html", view_context)

    @action(detail=True, methods=["post"], url_path="vote")
    def vote(self, request, pk=None):
        """
        FR: Enregistre un vote de pertinence pour une initiative.
            - Nécessite un utilisateur authentifié.
            - Idempotent: multiple POST par le même utilisateur n'ajoute pas de nouveau vote.
            - Retourne du HTML (fragment badge de votes) pour mise à jour via HTMX.
        EN: Registers a relevance vote for an initiative.
            - Requires an authenticated user.
            - Idempotent: multiple POSTs by the same user do not add a new vote.
            - Returns HTML (vote badge fragment) for HTMX update.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            # FR: Si non connecté, on renvoie le badge sans changement avec un statut 401
            # EN: If not logged in, return unchanged badge with 401 status
            context = get_context(request)
            context.update({"initiative": initiative})
            response = render(request, "crowds/partial/votes_badge.html", context)
            response.status_code = 401
            return response

        # FR: Crée le vote si inexistant (get_or_create assure l'idempotence)
        # EN: Create vote if it doesn't exist (get_or_create ensures idempotency)
        _, created = Vote.objects.get_or_create(initiative=initiative, user=request.user)
        
        # FR: Retourner le badge mis à jour + un évènement HTMX pour retour visuel
        # EN: Return updated badge + HTMX event for visual feedback
        context = get_context(request)
        context.update({"initiative": initiative})
        response = render(request, "crowds/partial/votes_badge.html", context)
        
        # FR: Déclenche un évènement custom côté client via les headers HTMX
        # EN: Trigger a custom client-side event via HTMX headers
        try:
            response["HX-Trigger"] = json.dumps({
                "crowds:vote": {"created": created, "uuid": str(initiative.uuid)}
            })
        except Exception:
            response["HX-Trigger"] = "crowds:vote"
        return response

    @action(detail=True, methods=["post"], url_path="participate")
    def participate(self, request, pk=None):
        """
        FR: Déclare une participation (action) à une initiative.
            Champs attendus: description, amount (optionnel pour bénévolat).
        EN: Declares a participation (action) to an initiative.
            Expected fields: description, amount (optional for pro-bono).
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        if not request.user.is_authenticated:
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = 401
            return response

        # FR: Validation via DRF serializer (inclut le nettoyage HTML)
        # EN: Validation via DRF serializer (includes HTML sanitation)
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
        
        # FR: Retourne la liste des participations mise à jour (HTMX)
        # EN: Returns the updated list of participations (HTMX)
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
        FR: Approuve une proposition de ligne budgétaire.
            Réservé aux administrateurs. Retourne le fragment HTML mis à jour.
        EN: Approves a budget item proposal.
            Reserved for administrators. Returns the updated HTML fragment.
        """
        initiative = get_object_or_404(Initiative, pk=pk)

        def _render_updated_fragment(status_code=200):
            ctx = get_context(request)
            ctx.update(self._budget_items_context(initiative))
            resp = render(request, "crowds/partial/budget_items.html", ctx)
            resp.status_code = status_code
            return resp

        if not request.user.is_authenticated:
            return _render_updated_fragment(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render_updated_fragment(status_code=403)

        budget_item = get_object_or_404(BudgetItem, pk=bid, initiative=initiative)
        if budget_item.state != BudgetItem.State.REQUESTED:
            return _render_updated_fragment(status_code=400)
        try:
            budget_item.state = BudgetItem.State.APPROVED
            budget_item.validator = request.user
            budget_item.save(update_fields=["state", "validator"])
        except Exception:
            return _render_updated_fragment(status_code=400)
        return _render_updated_fragment(status_code=200)

    @action(detail=True, methods=["post"], url_path=r"budget-items/(?P<bid>[^/.]+)/reject")
    def reject_budget_item(self, request, pk=None, bid=None):
        """
        FR: Rejette une proposition de ligne budgétaire.
            Réservé aux administrateurs. Retourne le fragment HTML mis à jour.
        EN: Rejects a budget item proposal.
            Reserved for administrators. Returns the updated HTML fragment.
        """
        initiative = get_object_or_404(Initiative, pk=pk)

        def _render_updated_fragment(status_code=200):
            ctx = get_context(request)
            ctx.update(self._budget_items_context(initiative))
            resp = render(request, "crowds/partial/budget_items.html", ctx)
            resp.status_code = status_code
            return resp

        if not request.user.is_authenticated:
            return _render_updated_fragment(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render_updated_fragment(status_code=403)

        budget_item = get_object_or_404(BudgetItem, pk=bid, initiative=initiative)
        if budget_item.state != BudgetItem.State.REQUESTED:
            return _render_updated_fragment(status_code=400)
        try:
            budget_item.state = BudgetItem.State.REJECTED
            budget_item.validator = request.user
            budget_item.save(update_fields=["state", "validator"])
        except Exception:
            return _render_updated_fragment(status_code=400)
        return _render_updated_fragment(status_code=200)

    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/complete")
    def complete_participation(self, request, pk=None, pid=None):
        """
        FR: Marque une participation comme terminée par l'utilisateur.
            Met à jour le temps passé et change l'état vers COMPLETED_USER.
        EN: Marks a participation as completed by the user.
            Updates time spent and changes state to COMPLETED_USER.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        participation_obj = get_object_or_404(Participation, pk=pid, initiative=initiative)
        
        # FR: Aide pour renvoyer le fragment en cas d'erreur
        # EN: Helper to return fragment on error
        def _render_participations(status_code=200):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = status_code
            return response

        if not request.user.is_authenticated:
            return _render_participations(401)

        if participation_obj.participant_id != request.user.id:
            return _render_participations(403)
            
        # FR: On ne peut compléter qu'une participation demandée ou déjà approuvée
        # EN: Can only complete a requested or already approved participation
        if participation_obj.state not in (Participation.State.REQUESTED, Participation.State.APPROVED_ADMIN):
            return _render_participations(400)
            
        try:
            time_spent_minutes = int(request.POST.get("time_spent_minutes") or 0)
        except (TypeError, ValueError):
            time_spent_minutes = 0
            
        if time_spent_minutes <= 0:
            return _render_participations(400)
            
        participation_obj.time_spent_minutes = time_spent_minutes
        participation_obj.state = Participation.State.COMPLETED_USER
        participation_obj.save(update_fields=["time_spent_minutes", "state", "updated_at"])
        
        return _render_participations(200)

    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/approve")
    def approve_participation(self, request, pk=None, pid=None):
        """
        FR: Approbation admin d'une participation (étape 2 du flux).
            Passe l'état de REQUESTED à APPROVED_ADMIN.
        EN: Admin approval of a participation (step 2 of the flow).
            Moves state from REQUESTED to APPROVED_ADMIN.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        participation_obj = get_object_or_404(Participation, pk=pid, initiative=initiative)
        
        def _render_participations(status_code=200):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = status_code
            return response

        if not request.user.is_authenticated:
            return _render_participations(401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render_participations(403)
            
        if participation_obj.state != Participation.State.REQUESTED:
            return _render_participations(400)
            
        participation_obj.state = Participation.State.APPROVED_ADMIN
        participation_obj.save(update_fields=["state", "updated_at"])
        
        return _render_participations(200)

    @action(detail=True, methods=["post"], url_path=r"participations/(?P<pid>[^/.]+)/validate")
    def validate_participation(self, request, pk=None, pid=None):
        """
        FR: Validation finale admin d'une participation terminée (étape 4 du flux).
            Passe l'état de COMPLETED_USER à VALIDATED_ADMIN.
        EN: Final admin validation of a completed participation (step 4 of the flow).
            Moves state from COMPLETED_USER to VALIDATED_ADMIN.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        participation_obj = get_object_or_404(Participation, pk=pid, initiative=initiative)
        
        def _render_participations(status_code=200):
            context = get_context(request)
            context.update(self._participations_context(initiative))
            response = render(request, "crowds/partial/participations.html", context)
            response.status_code = status_code
            return response

        if not request.user.is_authenticated:
            return _render_participations(401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render_participations(403)
            
        if participation_obj.state != Participation.State.COMPLETED_USER:
            return _render_participations(400)
            
        participation_obj.state = Participation.State.VALIDATED_ADMIN
        participation_obj.save(update_fields=["state", "updated_at"])
        
        return _render_participations(200)

    @action(detail=True, methods=["post"], url_path="contribute")
    def contribute(self, request, pk=None):
        """
        FR: Crée une contribution financière à une initiative.
            Champs attendus: amount (en centimes), contributor_name, description.
        EN: Creates a financial contribution to an initiative.
            Expected fields: amount (in cents), contributor_name, description.
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        
        def _render_contributions(status_code=200):
            context = get_context(request)
            context.update(self._contributions_context(initiative))
            response = render(request, "crowds/partial/contributions.html", context)
            response.status_code = status_code
            return response

        if not request.user.is_authenticated:
            return _render_contributions(401)

        # FR: Validation via DRF serializer (inclut le nettoyage HTML)
        # EN: Validation via DRF serializer (includes HTML sanitation)
        contribution_serializer = ContributionCreateSerializer(data=request.data)
        if not contribution_serializer.is_valid():
            return _render_contributions(400)

        validated_contrib_data = contribution_serializer.validated_data
        Contribution.objects.create(
            initiative=initiative,
            contributor=request.user,
            contributor_name=validated_contrib_data.get("contributor_name") or "",
            description=validated_contrib_data.get("description") or "",
            amount=validated_contrib_data.get("amount") or 0,
        )
        
        return _render_contributions(200)

    @action(detail=True, methods=["post"], url_path=r"contributions/(?P<cid>[^/.]+)/mark-paid")
    def mark_contribution_paid(self, request, pk=None, cid=None):
        """
        FR: Marque une contribution comme payée par un administrateur.
            Réservé aux admins/staff.
        EN: Marks a contribution as paid by an administrator.
            Reserved for admins/staff.
        """
        initiative = get_object_or_404(Initiative, pk=pk)

        def _render_contributions(status_code=200):
            ctx = get_context(request)
            ctx.update(self._contributions_context(initiative))
            resp = render(request, "crowds/partial/contributions.html", ctx)
            resp.status_code = status_code
            return resp

        if not request.user.is_authenticated:
            return _render_contributions(status_code=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return _render_contributions(status_code=403)
            
        contribution_obj = get_object_or_404(Contribution, pk=cid, initiative=initiative)
        
        try:
            if contribution_obj.payment_status not in [Contribution.PaymentStatus.PAID, Contribution.PaymentStatus.PAID_ADMIN]:
                contribution_obj.payment_status = Contribution.PaymentStatus.PAID_ADMIN
                contribution_obj.paid_at = timezone.now()
                contribution_obj.save(update_fields=["payment_status", "paid_at"])
        except Exception:
            pass
            
        return _render_contributions(status_code=200)

    @action(detail=True, methods=["post"], url_path="close")
    def close_initiative(self, request, pk=None):
        """
        Clôture une initiative (admin/staff uniquement).
        L'initiative reste visible mais n'est plus modifiable et affiche un badge "Clôturé".
        Ajoute automatiquement le tag "Clôturé".
        Retourne une redirection vers la page de détail.
        """
        if not request.user.is_authenticated:
            return JsonResponse({"error": _("Authentication required.")}, status=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": _("Permission denied.")}, status=403)

        initiative = get_object_or_404(Initiative, pk=pk)
        initiative.closed = True
        initiative.save(update_fields=["closed"])

        # Add "Clôturé" tag
        closed_tag, created = Tag.objects.get_or_create(
            slug="cloture",
            defaults={
                "name": _("Clôturé"),
                "color": "#6c757d"  # Bootstrap secondary gray
            }
        )
        initiative.tags.add(closed_tag)

        return HttpResponseRedirect(initiative.get_absolute_url())

    @action(detail=True, methods=["post"], url_path="archive")
    def archive_initiative(self, request, pk=None):
        """
        Archive une initiative (admin/staff uniquement).
        L'initiative est clôturée et n'apparaît plus dans la liste.
        Ajoute automatiquement les tags "Clôturé" et "Archivé".
        Retourne une redirection vers la liste des initiatives.
        """
        if not request.user.is_authenticated:
            return JsonResponse({"error": _("Authentication required.")}, status=401)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": _("Permission denied.")}, status=403)

        initiative = get_object_or_404(Initiative, pk=pk)
        initiative.closed = True
        initiative.archived = True
        initiative.save(update_fields=["closed", "archived"])

        # Add "Clôturé" tag
        closed_tag, created = Tag.objects.get_or_create(
            slug="cloture",
            defaults={
                "name": _("Clôturé"),
                "color": "#6c757d"  # Bootstrap secondary gray
            }
        )
        initiative.tags.add(closed_tag)

        # Add "Archivé" tag
        archived_tag, created = Tag.objects.get_or_create(
            slug="archive",
            defaults={
                "name": _("Archivé"),
                "color": "#dc3545"  # Bootstrap danger red
            }
        )
        initiative.tags.add(archived_tag)

        from django.urls import reverse
        return HttpResponseRedirect(reverse("crowds-list"))

    @action(detail=False, methods=["get"], url_path="sankey")
    def sankey(self, request):
        """
        Sankey diagram data provider (HTMX modal)
        Doc from : https://plotly.com/python/sankey-diagram/

        FR: Prépare les données pour le diagramme de Sankey (chargé à la demande dans une modale).
            Le flux visualisé est en 3 colonnes fixes: Financeurs → Initiatives → Participants.
            Mise en cache du contexte pour optimiser les performances.
        EN: Build data for the Sankey diagram (lazy‑loaded in a Bootstrap modal).
            The flow has 3 fixed columns: Funders → Initiatives → Participants.
            Cached context for performance optimization.
        """
        tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
        cache_key = f"crowds:sankey:data:{tenant_id}"
        context = cache.get(cache_key)

        if context is not None:
            return render(request, "crowds/partial/sankey.html", context)

        # ---------- 1) Collecte des données / Gather data ----------
        paid_contribs = (
            Contribution.objects
            .filter(
                payment_status__in=[Contribution.PaymentStatus.PAID, Contribution.PaymentStatus.PAID_ADMIN],
                initiative__archived=False,
            )
            .select_related('initiative', 'contributor')
        )
        validated_parts = (
            Participation.objects
            .filter(state__in=[
                Participation.State.VALIDATED_ADMIN,
                Participation.State.APPROVED_ADMIN,
                Participation.State.COMPLETED_USER,
            ],
                initiative__archived=False,
            )
            .select_related('initiative', 'participant')
        )

        # ---------- 2) Agrégation des flux / Aggregate flows ----------
        # FR: On agrège les montants en unités (ex: euros), en ignorant les valeurs nulles ou négatives.
        # EN: Aggregate amounts in units (e.g. euros), ignoring null/negative values.
        contrib_flow = {}  # (funder_label, initiative_label) -> float amount
        for c in paid_contribs:
            funder_label = c.get_contriutor_name or _("Financeur Anonyme")  # FR: libellé financeur / EN: funder label
            init_label = c.initiative.name
            amount_unit = float((c.amount or 0) / 100)
            if amount_unit <= 0:
                continue
            contrib_flow[(funder_label, init_label)] = contrib_flow.get((funder_label, init_label), 0.0) + amount_unit

        part_flow = {}  # (initiative_label, participant_label) -> float amount
        for p in validated_parts:
            init_label = p.initiative.name
            participant_label = p.participant.full_name_or_email()
            amount_unit = float(((p.amount or 0) / 100))
            if amount_unit <= 0:
                continue
            part_flow[(init_label, participant_label)] = part_flow.get((init_label, participant_label),
                                                                       0.0) + amount_unit

        # ---------- 3) Construction des nœuds (ordre déterministe) / Build nodes (deterministic order) ----------
        # FR: On fige l'ordre pour simplifier les diffs visuels et faciliter le debug.
        # EN: Freeze ordering for stable indices and easier debugging.
        funders = {f for (f, _) in contrib_flow.keys()}
        initiatives = {i for (_, i) in contrib_flow.keys()} | {i for (i, _) in part_flow.keys()}
        participants = {u for (_, u) in part_flow.keys()}

        nodes: list[str] = []
        node_types: list[str] = []  # parallel array to keep each node's type
        node_index: dict[tuple[str, str], int] = {}

        def _add_nodes(labels: set[str], ntype: str):
            for label in sorted(labels):  # stable order inside each column
                node_index[(ntype, label)] = len(nodes)
                nodes.append(label)
                node_types.append(ntype)

        _add_nodes(funders, 'funder')
        _add_nodes(initiatives, 'initiative')
        _add_nodes(participants, 'participant')

        # ---------- 4) Liens / Links ----------
        links = {'source': [], 'target': [], 'value': []}

        for (funder_label, init_label), val in contrib_flow.items():
            links['source'].append(node_index[('funder', funder_label)])
            links['target'].append(node_index[('initiative', init_label)])
            links['value'].append(val)

        for (init_label, participant_label), val in part_flow.items():
            links['source'].append(node_index[('initiative', init_label)])
            links['target'].append(node_index[('participant', participant_label)])
            links['value'].append(val)

        # ---------- 5) Positionnement fixe / Fixed positions ----------
        # FR: On verrouille la colonne de chaque type (x) et on répartit les nœuds verticalement (y).
        # EN: Lock each group on a fixed X and spread items evenly on Y.
        node_x = [0.0] * len(nodes)
        node_y = [0.0] * len(nodes)
        x_by_type = {'funder': 0.0, 'initiative': 0.5, 'participant': 1.0}
        idx_by_type = {'funder': [], 'initiative': [], 'participant': []}

        for idx, ntype in enumerate(node_types):
            idx_by_type[ntype].append(idx)

        for ntype, idxs in idx_by_type.items():
            n = max(1, len(idxs))
            for rank, idx in enumerate(idxs):
                node_x[idx] = x_by_type[ntype]
                node_y[idx] = (rank + 1) / (n + 1)  # FR: espacement régulier / EN: evenly spaced

        # ---------- 6) Contexte pour le template / Template context ----------
        context = {
            'nodes': nodes,
            'links': links,
            'node_x': node_x,
            'node_y': node_y,
            'global_funding_currency': Configuration.get_solo().currency_code,
        }
        # FR: On met en cache pour 1 heure (sera invalidé par signal)
        # EN: Cache for 1 hour (invalidated via signals)
        cache.set(cache_key, context, 3600)
        return render(request, "crowds/partial/sankey.html", context)

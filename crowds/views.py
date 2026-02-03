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
    FR: Total financé par l'utilisateur (global + contributions aux projets).
    EN: Total funded by the user (global funding + project contributions).
    """
    if not user or not user.is_authenticated:
        return 0
    tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
    cache_key = _user_funded_cache_key(tenant_id, user.pk)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    total_global = GlobalFunding.objects.filter(user=user).aggregate(total=Sum("amount_funded")).get("total") or 0
    total_contrib = Contribution.objects.filter(contributor=user).aggregate(total=Sum("amount")).get("total") or 0
    total = total_global + total_contrib
    cache.set(cache_key, total, 60)
    return total


def clear_user_funded_cache(user):
    tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
    cache.delete(_user_funded_cache_key(tenant_id, user.pk))


class GlobalFundingViewset(viewsets.ViewSet):
    """
    Pour le bouton financer le projet global
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def _get_or_create_crowdfunding_price(self) -> Price:
        """
        FR: Crée (si besoin) un couple Product/Price "crowdfunding" pour un paiement libre.
        EN: Create (if needed) a "crowdfunding" Product/Price pair for open amount payments.
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
        FR: Lance un paiement Stripe pour un financement global.
        EN: Starts a Stripe checkout for global funding.
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

        price = self._get_or_create_crowdfunding_price()
        amount_decimal = (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
        price_sold = get_or_create_price_sold(price, custom_amount=amount_decimal)

        ligne_article = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=amount_cents,
            payment_method=PaymentMethod.STRIPE_NOFED,
            sale_origin=SaleOrigin.LESPASS,
        )

        global_funding = GlobalFunding.objects.create(
            user=request.user,
            amount_funded=amount_cents,
            amount_to_be_included=amount_cents,
            contributor_name=data.get("contributor_name") or "",
            description=data.get("description") or "",
            ligne_article=ligne_article,
        )

        metadata = {
            "tenant": f"{connection.tenant.uuid}",
            "global_funding_uuid": f"{global_funding.pk}",
            "user": f"{request.user.email}",
        }

        paiement_builder = CreationPaiementStripe(
            user=request.user,
            liste_ligne_article=[ligne_article],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.FRONT_CROWDS,
            success_url="stripe_return/",
            cancel_url="stripe_return/",
            absolute_domain=request.build_absolute_uri("/crowd/global-funding/"),
        )

        if not paiement_builder.is_valid():
            return JsonResponse(
                {"error": _("Erreur lors de la création du paiement.")},
                status=400,
            )

        paiement_stripe = paiement_builder.paiement_stripe_db
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)
        clear_user_funded_cache(request.user)
        return JsonResponse({"stripe_url": paiement_builder.checkout_session.url})

    @action(detail=True, methods=["get"], url_path="stripe_return")
    def stripe_return(self, request, pk=None):
        """
        FR: Retour de Stripe (succès ou annulation) vers la page liste des projets.
        EN: Stripe return (success or cancel) back to the list page.
        """
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=pk)
        paiement_stripe.update_checkout_status()
        paiement_stripe.refresh_from_db()

        #TODO traitement en cours False, ligne article valide, mail envoyé

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
        Affiche la liste des projets avec le thème TiBillet + HTMX (pas de blink).
        """

        active_slug = (request.GET.get("tag") or "").strip()
        search_query = (request.GET.get("q") or "").strip()

        # Check if "Archivé" tag is selected
        show_archived = (active_slug == "archive")

        # Base queryset: exclude archived by default, unless "Archivé" tag is selected
        if show_archived:
            initiatives_qs = (
                Initiative.objects.all()
                .annotate(votes_total=Count("votes", distinct=True))
                .prefetch_related("tags")
            )
        else:
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

        # No pagination: display all initiatives on a single page
        initiatives = list(initiatives_qs)

        context = get_context(request)
        name_help = Contribution._meta.get_field("contributor_name").help_text or _("Votre nom ou celui de votre organisation (affiché publiquement)")
        desc_help = Contribution._meta.get_field("description").help_text or _("Un petit mot pour décrire votre contribution")
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiatives": initiatives,
            "active_tag": active_tag,
            "all_tags": Tag.objects.filter(initiatives__isnull=False).distinct(),
            "search_query": search_query,
            "contrib_name_help": name_help,
            "contrib_desc_help": desc_help,
        })

        # HTMX request: return only the list partial to avoid full reload
        hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
        if request.headers.get("HX-Request") and hx_target == "crowds_list":
            return render(request, "crowds/partial/list.html", context)

        context.update(self._summary_context())
        context.update({
            "user_funded_total": get_user_funded_total(request.user),
            "global_funding_currency": context["config"].currency_code,
        })
        return render(request, "crowds/views/list.html", context)

    def _summary_context(self):
        tenant_id = getattr(getattr(connection, "tenant", None), "pk", None)
        cache_key = f"crowds:list:summary:{tenant_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Filter active initiatives (not closed and not archived) for funding stats
        active_initiatives = Initiative.objects.filter(archived=False, closed=False)

        # Funding stats only for active initiatives
        funding_total = Contribution.objects.filter(
            initiative__in=active_initiatives
        ).aggregate(total=Sum("amount")).get("total") or 0

        participation_total_valid = Participation.objects.filter(
            initiative__in=active_initiatives
        ).exclude(
            state__in=[Participation.State.REQUESTED, Participation.State.REJECTED]
        ).aggregate(total=Sum("amount")).get("total") or 0

        time_spent_total = Participation.objects.aggregate(
            total=Sum("time_spent_minutes")
        ).get("total") or 0

        # Funding goal only for active initiatives
        funding_goal_total = BudgetItem.objects.filter(
            state=BudgetItem.State.APPROVED,
            initiative__in=active_initiatives
        ).aggregate(total=Sum("amount")).get("total") or 0

        funding_percent = 0
        if funding_goal_total:
            funding_percent = int(round((funding_total / funding_goal_total) * 100))

        # Participants count (voters + participants + contributors)
        user_ids = set(Vote.objects.values_list("user_id", flat=True))
        user_ids.update(Participation.objects.values_list("participant_id", flat=True))
        user_ids.update(
            Contribution.objects.exclude(contributor_id__isnull=True).values_list("contributor_id", flat=True)
        )
        participants_count = User.objects.filter(id__in=user_ids).count()

        source_ids = User.objects.filter(id__in=user_ids, client_source_id__isnull=False).values_list("client_source_id", flat=True).distinct()
        source_logos = []
        has_multiple_sources = len(source_ids) > 1 or (
            tenant_id is not None and any(sid != tenant_id for sid in source_ids)
        )
        if has_multiple_sources:
            from django_tenants.utils import schema_context
            from BaseBillet.models import Configuration
            for client in Client.objects.filter(pk__in=source_ids):
                logo_url = None
                logo_link = None
                logo_cache_key = f"crowds:tenant:logo:{client.pk}"
                cached_logo = cache.get(logo_cache_key)
                if isinstance(cached_logo, dict):
                    logo_url = cached_logo.get("logo_url")
                    logo_link = cached_logo.get("logo_link")
                else:
                    try:
                        with schema_context(client.schema_name):
                            cfg = Configuration.get_solo()
                            if cfg.logo:
                                logo_url = cfg.logo.thumbnail.url
                            logo_link = cfg.full_url()
                    except Exception:
                        logo_url = None
                        logo_link = None
                    cache.set(logo_cache_key, {"logo_url": logo_url, "logo_link": logo_link}, 3600)
                source_logos.append({
                    "name": client.name,
                    "logo_url": logo_url,
                    "url": logo_link,
                })

        active_participations_qs = Participation.objects.exclude(
            state__in=[Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN]
        ).select_related("participant", "initiative").order_by("-created_at")[:9]
        active_participations = []
        for p in active_participations_qs:
            active_participations.append({
                "participant": p.participant.full_name_or_email(),
                "initiative": p.initiative.name,
                "description": p.description,
                "amount": p.amount,
                "currency": p.initiative.currency,
            })
        active_participations_count = Participation.objects.exclude(
            state__in=[Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN]
        ).count()

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
        funding_to_allocate = recharge_total + global_funding_total - allocated_total
        if funding_to_allocate < 0:
            funding_to_allocate = 0

        initiatives_rows = list(
            Initiative.objects.filter(archived=False).values_list("uuid", "asset_id", "currency")
        )
        asset_ids = {aid for _, aid, _ in initiatives_rows if aid}
        currency_codes = {cur for _, aid, cur in initiatives_rows if not aid and cur}
        if asset_ids:
            asset_codes = set(
                AssetFedowPublic.objects.filter(pk__in=asset_ids).values_list("currency_code", flat=True)
            )
            currency_codes.update(asset_codes)
        currency_codes = {c for c in currency_codes if c}
        summary_multi_currency = len(currency_codes) > 1
        currency = next(iter(currency_codes), "")

        asset_code_by_id = {}
        if asset_ids:
            asset_code_by_id = {
                asset_id: code for asset_id, code in AssetFedowPublic.objects.filter(
                    pk__in=asset_ids
                ).values_list("id", "currency_code")
            }
        initiative_currency = {}
        for initiative_id, asset_id, cur in initiatives_rows:
            if asset_id and asset_id in asset_code_by_id:
                initiative_currency[initiative_id] = asset_code_by_id[asset_id]
            else:
                initiative_currency[initiative_id] = cur or ""

        currency_blocks = {}
        for cur in initiative_currency.values():
            if not cur:
                continue
            currency_blocks.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks[cur]["projects"] += 1

        for row in Contribution.objects.values("initiative_id").annotate(total=Sum("amount")):
            cur = initiative_currency.get(row["initiative_id"], "")
            if not cur:
                continue
            currency_blocks.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks[cur]["funding"] += row["total"] or 0

        for row in Participation.objects.values("initiative_id").annotate(total=Sum("amount")):
            cur = initiative_currency.get(row["initiative_id"], "")
            if not cur:
                continue
            currency_blocks.setdefault(cur, {"projects": 0, "funding": 0, "participation": 0})
            currency_blocks[cur]["participation"] += row["total"] or 0

        initiatives_for_alloc = []
        for initiative in Initiative.objects.filter(archived=False).only("uuid", "name"):
            initiatives_for_alloc.append({
                "uuid": str(initiative.uuid),
                "name": initiative.name,
                "url": initiative.get_absolute_url(),
            })

        # Calculations for remaining budget to claim
        remaining_to_claim = funding_total - participation_total_valid
        claim_ratio = 0
        if funding_total > 0:
            claim_ratio = (participation_total_valid / funding_total) * 100

        claim_color = "success"
        if claim_ratio >= 90:
            claim_color = "danger"
        elif claim_ratio >= 70:
            claim_color = "warning"

        summary = {
            "summary_time_spent_minutes": time_spent_total,
            "summary_funding_goal_total": funding_goal_total,
            "summary_funding_percent": funding_percent,
            "summary_currency_blocks": [
                {
                    "code": code,
                    "projects": data["projects"],
                    "funding": data["funding"],
                    "participation": data["participation"],
                }
                for code, data in sorted(currency_blocks.items(), key=lambda item: item[0])
            ],
            "summary_participants_count": participants_count,
            "summary_source_logos": source_logos,
            "summary_has_multiple_sources": has_multiple_sources,
            "summary_active_participations": active_participations,
            "summary_active_participations_count": active_participations_count,
            "summary_funding_to_allocate": funding_to_allocate,
            "summary_initiatives_for_alloc": initiatives_for_alloc,
            # Help texts for Global Funding Swal
            "contrib_name_help": Contribution._meta.get_field("contributor_name").help_text or gettext("Votre nom ou celui de votre organisation (affiché publiquement)"),
            "contrib_desc_help": Contribution._meta.get_field("description").help_text or gettext("Un petit mot pour décrire votre contribution"),
            # New info: funding vs participation
            "summary_remaining_to_claim": max(0, remaining_to_claim),
            "summary_claim_ratio": claim_ratio,
            "summary_claim_color": claim_color,
        }
        cache.set(cache_key, summary, 60)
        return summary

    # ------------------------
    # Détail d’un projet
    # ------------------------
    def retrieve(self, request, pk=None):
        """
        Affiche le détail d’un projet dans la charte graphique TiBillet.
        """
        # Précharge les tags pour éviter les requêtes supplémentaires dans le template
        try :
            if not Initiative.objects.filter(pk=pk).exists():
                return redirect('/contrib')
        except ValidationError:
            # pk n'est pas un uuid valide :
            return redirect('/contrib')

        initiative = get_object_or_404(
            Initiative.objects.prefetch_related("tags"), pk=pk
        )
        contributions_context = self._contributions_context(initiative)
        budget_items_context = self._budget_items_context(initiative)

        context = get_context(request)
        # Précharger les votants pour éviter le N+1
        votes = list(initiative.votes.select_related("user__client_source").order_by("-created_at"))
        show_votes_origin = self._should_show_user_source(
            initiative, "votes", [v.user for v in votes]
        )
        participations_context = self._participations_context(initiative)
        # Help texts for Contribution form in Swal
        from django.utils.translation import gettext as _
        name_help = Contribution._meta.get_field("contributor_name").help_text or _("Votre nom ou celui de votre organisation (affiché publiquement)")
        desc_help = Contribution._meta.get_field("description").help_text or _("Un petit mot pour décrire votre contribution")
        # Ne passer que les variables réellement utilisées par les templates
        context.update({
            "crowd_config": CrowdConfig.get_solo(),
            "initiative": initiative,
            "contrib_name_help": name_help,
            "contrib_desc_help": desc_help,
            "votes": votes,
            "show_votes_origin": show_votes_origin,
        })
        context.update(contributions_context)
        context.update(budget_items_context)
        context.update(participations_context)

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

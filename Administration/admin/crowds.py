import logging
from decimal import Decimal

from django.contrib import admin, messages
from django.db import models
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.forms.widgets import WysiwygWidget
from solo.admin import SingletonModelAdmin

from Administration.admin.site import staff_admin_site, sanitize_textfields
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import Configuration
from crowds.models import Contribution, Vote, Participation, CrowdConfig, Initiative, BudgetItem

logger = logging.getLogger(__name__)


@admin.register(CrowdConfig, site=staff_admin_site)
class CrowdConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    fieldsets = (
        (_("Général"), {"fields": ("active",)}),
        (_("Affichage"), {"fields": (
            "title",
            "description",
            "vote_button_name",
            "name_goal",
            "name_funding",
            "name_participations",
            "contributor_covenant",
            "pro_bono_name",
        )}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        obj: CrowdConfig
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


class ContributionInline(TabularInline):
    """
    FR: Inline pour les contributions financières d'une initiative.
        L'ajout direct depuis l'admin est désactivé pour éviter les erreurs d'intégrité (ex: participant_id NULL).
    EN: Inline for financial contributions of an initiative.
        Direct addition from admin is disabled to prevent integrity errors (e.g. participant_id NULL).
    """
    model = Contribution
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite de charger 200k users dans un select: champ en saisie par ID
    # EN: Avoid loading 200k users in a select: field input by ID
    raw_id_fields = ("contributor",)

    fields = (
        "contributor_name",
        "contributor",
        "description",
        "amount",
        "amount_eur_display",
        "payment_status",
        "paid_at",
        "created_at",
    )
    readonly_fields = ("amount_eur_display", "created_at", "contributor")

    def amount_eur_display(self, obj):
        if not obj:
            return ""
        return f"{obj.amount_eur:.2f} {obj.initiative.currency}"

    amount_eur_display.short_description = _("Montant")

    # FR: Permissions : on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "initiative")


class VoteInline(TabularInline):
    model = Vote
    fk_name = 'initiative'
    extra = 0
    can_delete = True
    readonly_fields = ("created_at", "user")
    fields = ("user", "created_at")
    # Saisie par ID pour éviter l'autocomplete sur une très grande table user
    raw_id_fields = ("user",)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Pas de modification du vote: on peut supprimer/ajouter
        return False

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")


class BudgetItemInline(TabularInline):
    """
    FR: Inline pour les lignes budgétaires (objectifs à financer).
        L'ajout direct est interdit ici pour forcer l'usage du front ou un flux contrôlé.
    EN: Inline for budget items (funding goals).
        Direct addition is forbidden here to force use of the front-end or a controlled flow.
    """
    model = BudgetItem
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite les gros menus déroulants de users / EN: Avoid large user dropdowns
    raw_id_fields = ("contributor", "validator")

    fields = (
        "contributor",
        "description",
        "amount",
        "state",
        "validator",
        "created_at",
    )
    readonly_fields = ("created_at", "contributor", "validator")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "validator")


class ParticipationInline(TabularInline):
    """
    FR: Inline pour les participations (actions des utilisateurs).
        L'ajout est bloqué car il manquait souvent le participant_id (IntegrityError).
    EN: Inline for participations (user actions).
        Addition is blocked because participant_id was often missing (IntegrityError).
    """
    model = Participation
    fk_name = 'initiative'
    # FR: On NE PROPOSE PAS de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    # FR: Evite le chargement massif des users / EN: Avoid massive user loading
    raw_id_fields = ("participant",)
    fields = (
        "participant",
        "description",
        "amount",
        "state",
        "time_spent_minutes",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "participant")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("participant")


@admin.register(Initiative, site=staff_admin_site)
class InitiativeAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    list_display = (
        "name",
        "created_at",
        "funded_amount_display",
        "funding_goal_display",
        "progress_percent_int",
        "currency",
        "votes_count",
    )

    fields = (
        "name",
        "short_description",
        "description",
        "currency",
        "img",
        "tags",
        "archived",
        "vote",
        "budget_contributif",
        "direct_debit",
    )

    list_filter = ("created_at", "tags")
    search_fields = ("name", "description", "tags__name")
    date_hierarchy = "created_at"
    inlines = [VoteInline, BudgetItemInline, ContributionInline, ParticipationInline]
    ordering = ("-created_at",)
    filter_horizontal = ("tags",)
    autocomplete_fields = ("tags",)
    # Optimise les requêtes en changelist (FK direct)
    list_select_related = ("asset",)

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_queryset(self, request):
        # Optimise les agrégations et évite les N+1 en liste admin
        qs = super().get_queryset(request)
        qs = (
            qs
            .select_related("asset")
            .prefetch_related("tags")
            .annotate(
                funded_total=models.Sum("contributions__amount", distinct=True),
                funding_goal_total=models.Sum(
                    models.Case(
                        models.When(budget_items__state="approved", then=models.F("budget_items__amount")),
                        default=models.Value(0),
                        output_field=models.IntegerField(),
                    ),
                    distinct=True,
                ),
                votes_total=models.Count("votes", distinct=True),
            )
        )
        return qs

    def save_model(self, request, obj, form, change):
        obj: Initiative
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)

        # FR: Si direct_debit est activé, vérifier qu'un compte Stripe est connecté.
        #     Sans Stripe, le paiement en ligne ne peut pas fonctionner.
        # EN: If direct_debit is enabled, check that a Stripe account is connected.
        if obj.direct_debit:
            config = Configuration.get_solo()
            stripe_est_configure = bool(
                config.stripe_connect_account or config.stripe_connect_account_test
            )
            if not stripe_est_configure:
                from django.contrib import messages
                obj.direct_debit = False
                messages.error(
                    request,
                    _("Paiement direct désactivé : aucun compte Stripe n'est connecté. "
                      "Configurez Stripe dans Paramètres avant d'activer le paiement direct.")
                )

        super().save_model(request, obj, form, change)

    def currency(self, obj: Initiative):
        if obj.asset:
            return obj.asset.currency_code
        return obj.currency

    currency.short_description = _("Devise")

    def funded_amount_display(self, obj):
        total = getattr(obj, "funded_total", None)
        if total is None:
            total = obj.total_funded_amount
        decimal_amount = Decimal(total or 0) / Decimal("100")
        return f"{decimal_amount:.2f}"

    funded_amount_display.short_description = _("Financé")

    def funding_goal_display(self, obj):
        # Objectif = somme des lignes budgétaires approuvées
        goal = getattr(obj, "funding_goal_total", None)
        if goal is None:
            goal = obj.total_funding_amount
        decimal_amount = Decimal(goal or 0) / Decimal("100")
        return f"{decimal_amount:.2f} {self.currency(obj)}"

    funding_goal_display.short_description = _("Objectif")

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

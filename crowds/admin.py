# from django.contrib import admin
# from django.utils.translation import gettext_lazy as _
# from django.utils.html import format_html
#
# from Administration.admin_tenant import staff_admin_site
# from .models import CrowdConfig, Initiative, Contribution, Vote, Participation, Tag
#
# try:
#     # django-solo admin for singleton config
#     from solo.admin import SingletonModelAdmin
# except Exception:  # pragma: no cover - fallback if solo not available
#     SingletonModelAdmin = admin.ModelAdmin
#
#
#
#
#
#
# @admin.register(Contribution, site=staff_admin_site)
# class ContributionAdmin(admin.ModelAdmin):
#     list_display = ("initiative", "contributor", "amount_eur_display", "created_at")
#     search_fields = ("initiative__name", "contributor__email")
#     list_filter = ("initiative",)
#     date_hierarchy = "created_at"
#     ordering = ("-created_at",)
#
#     def amount_eur_display(self, obj):
#         return f"{obj.amount_eur:.2f} {obj.initiative.asset.currency_code}"
#
#     amount_eur_display.short_description = _("Montant")
#
#
# @admin.register(Vote, site=staff_admin_site)
# class VoteAdmin(admin.ModelAdmin):
#     list_display = ("initiative", "user", "created_at")
#     search_fields = ("initiative__name", "user__email")
#     list_filter = ("initiative",)
#     date_hierarchy = "created_at"
#     ordering = ("-created_at",)
#
#
# @admin.register(Participation, site=staff_admin_site)
# class ParticipationAdmin(admin.ModelAdmin):
#     list_display = (
#         "initiative",
#         "participant",
#         "requested_amount_display",
#         "state",
#         "time_spent_minutes",
#         "created_at",
#     )
#     list_filter = ("state", "initiative")
#     search_fields = ("initiative__name", "participant__email", "description")
#     date_hierarchy = "created_at"
#     ordering = ("-created_at",)
#     fields = (
#         "initiative",
#         "participant",
#         "description",
#         "requested_amount_cents",
#         "state",
#         "time_spent_minutes",
#         "created_at",
#         "updated_at",
#     )
#     readonly_fields = ("created_at", "updated_at")
#     list_editable = ("state",)
#
#     actions = ("action_approve", "action_validate",)
#
#     @admin.action(description=_("Approuver la demande (REQUESTED → APPROVED_ADMIN)"))
#     def action_approve(self, request, queryset):
#         updated = 0
#         for part in queryset.select_for_update():
#             if part.state == Participation.State.REQUESTED:
#                 part.state = Participation.State.APPROVED_ADMIN
#                 part.save(update_fields=["state", "updated_at"])
#                 updated += 1
#         self.message_user(request, _("{} participation(s) approuvée(s).").format(updated))
#
#     @admin.action(description=_("Valider la participation (COMPLETED_USER → VALIDATED_ADMIN)"))
#     def action_validate(self, request, queryset):
#         updated = 0
#         for part in queryset.select_for_update():
#             if part.state == Participation.State.COMPLETED_USER:
#                 part.state = Participation.State.VALIDATED_ADMIN
#                 part.save(update_fields=["state", "updated_at"])
#                 updated += 1
#         self.message_user(request, _("{} participation(s) validée(s).").format(updated))
#
#     def requested_amount_display(self, obj):
#         return f"{(obj.requested_amount_cents or 0)/100:.2f} {obj.initiative.asset.currency_code}"
#
#     requested_amount_display.short_description = _("Montant demandé")
#

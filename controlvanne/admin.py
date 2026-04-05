"""
Admin du module tireuse connectee (controlvanne).
/ Admin for the connected tap module (controlvanne).

LOCALISATION : controlvanne/admin.py

Admins enregistres sur staff_admin_site :
- DebitmetreAdmin
- CarteMaintenanceAdmin
- TireuseBecAdmin
- RfidSessionAdmin
- HistoriqueTireuseAdmin
- HistoriqueCarteAdmin
- HistoriqueMaintenanceAdmin
- SessionCalibrationAdmin
- ConfigurationAdmin
"""

import csv
import datetime

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from .models import (
    CarteMaintenance,
    Configuration,
    Debimetre,
    HistoriqueCarte,
    HistoriqueMaintenance,
    HistoriqueTireuse,
    RfidSession,
    SessionCalibration,
    TireuseBec,
)


# ──────────────────────────────────────────────────────────────────────
# Filtre plage de dates (inputs Du / Au)
# / Date range filter (From / To inputs)
# ──────────────────────────────────────────────────────────────────────


class DateRangeFilter(SimpleListFilter):
    """
    Filtre plage de dates avec inputs HTML date_from / date_to.
    Le template est dans controlvanne/templates/admin/date_range_filter.html.
    / Date range filter with HTML date_from / date_to inputs.
    Template is in controlvanne/templates/admin/date_range_filter.html.
    """

    title = _("Period")
    parameter_name = "date_from"
    template = "admin/date_range_filter.html"

    def expected_parameters(self):
        # Les deux parametres geres par ce filtre
        # / Both parameters managed by this filter
        return ["date_from", "date_to"]

    def lookups(self, request, model_admin):
        # Requis par SimpleListFilter meme si on ne l'utilise pas
        # / Required by SimpleListFilter even if unused
        return (("_", "—"),)

    def choices(self, changelist):
        yield {
            "selected": not (
                changelist.params.get("date_from") or changelist.params.get("date_to")
            ),
            "query_string": changelist.get_query_string(
                remove=["date_from", "date_to"]
            ),
            "display": _("All"),
        }

    def queryset(self, request, queryset):
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        try:
            if date_from:
                queryset = queryset.filter(
                    started_at__date__gte=datetime.date.fromisoformat(date_from)
                )
            if date_to:
                queryset = queryset.filter(
                    started_at__date__lte=datetime.date.fromisoformat(date_to)
                )
        except ValueError:
            pass
        return queryset


# ──────────────────────────────────────────────────────────────────────
# DebitmetreAdmin — gestion des capteurs de debit
# / DebitmetreAdmin — flow meter management
# ──────────────────────────────────────────────────────────────────────


@admin.register(Debimetre, site=staff_admin_site)
class DebitmetreAdmin(ModelAdmin):
    """
    Admin pour les debitmetres (capteurs de debit).
    La colonne flow_calibration_factor est editable directement dans la liste.
    / Admin for flow meters (flow sensors).
    The flow_calibration_factor column is editable directly in the list.
    """

    list_display = ("name", "flow_calibration_factor")
    list_editable = ("flow_calibration_factor",)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# ──────────────────────────────────────────────────────────────────────
# CarteMaintenanceAdmin — cartes NFC de maintenance
# / CarteMaintenanceAdmin — maintenance NFC cards
# ──────────────────────────────────────────────────────────────────────


@admin.register(CarteMaintenance, site=staff_admin_site)
class CarteMaintenanceAdmin(ModelAdmin):
    """
    Admin pour les cartes NFC de maintenance des tireuses.
    autocomplete_fields sur carte pour choisir une CarteCashless existante.
    / Admin for tap maintenance NFC cards.
    autocomplete_fields on carte to select an existing CarteCashless.
    """

    list_display = ("carte_tag_id", "produit", "notes")
    raw_id_fields = ("carte",)
    search_fields = ("carte__tag_id", "produit", "notes")

    @admin.display(description=_("Card (tag_id)"))
    def carte_tag_id(self, obj):
        # Afficher le tag_id de la carte associee
        # / Display the tag_id of the linked card
        return obj.carte.tag_id if obj.carte else "—"

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# ──────────────────────────────────────────────────────────────────────
# TireuseBecAdmin — tireuse physique (admin principal)
# / TireuseBecAdmin — physical tap (main admin)
# ──────────────────────────────────────────────────────────────────────


@admin.register(TireuseBec, site=staff_admin_site)
class TireuseBecAdmin(ModelAdmin):
    """
    Admin principal pour les tireuses physiques.
    list_editable sur fut_actif, debimetre, enabled pour modifier rapidement depuis la liste.
    / Main admin for physical taps.
    list_editable on fut_actif, debimetre, enabled for quick updates from the list.
    """

    list_display = (
        "nom_tireuse",
        "fut_actif",
        "debimetre",
        "prix_effectif_display",
        "volume_restant_cl",
        "enabled",
    )
    list_editable = ("fut_actif", "debimetre", "enabled")
    readonly_fields = ("uuid",)
    fields = (
        "nom_tireuse",
        "fut_actif",
        "debimetre",
        "point_de_vente",
        "pairing_device",
        "seuil_mini_ml",
        "appliquer_reserve",
        "enabled",
        "notes",
    )
    search_fields = ("nom_tireuse", "notes")

    @admin.display(description=_("Price/Liter"))
    def prix_effectif_display(self, obj):
        """Prix au litre depuis le fut actif.
        / Per-liter price from the active keg."""
        prix = obj.prix_litre  # propriete calculee / computed property
        if prix and prix > 0:
            return f"{prix}"
        return "—"

    @admin.display(description=_("Remaining (cl)"), ordering="reservoir_ml")
    def volume_restant_cl(self, obj):
        """Volume restant en centilitres.
        / Remaining volume in centiliters."""
        return f"{float(obj.reservoir_ml) / 10:.0f} cl"

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# ──────────────────────────────────────────────────────────────────────
# RfidSessionAdmin — toutes les sessions RFID
# / RfidSessionAdmin — all RFID sessions
# ──────────────────────────────────────────────────────────────────────


@admin.register(RfidSession, site=staff_admin_site)
class RfidSessionAdmin(ModelAdmin):
    """
    Vue en lecture seule de toutes les sessions RFID.
    / Read-only view of all RFID sessions.
    """

    list_display = (
        "tireuse_bec",
        "liquid_label_snapshot",
        "uid",
        "authorized",
        "started_at",
        "ended_at",
        "volume_servi_cl",
    )
    list_filter = ("authorized", "tireuse_bec")
    search_fields = ("uid", "label_snapshot")
    date_hierarchy = "started_at"

    # Lecture seule — pas de creation ni de modification
    # / Read-only — no creation or modification
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Volume (cl)"), ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        """Volume servi en centilitres.
        / Volume served in centiliters."""
        return f"{obj.volume_delta_ml / 10:.1f}"


# ──────────────────────────────────────────────────────────────────────
# Export CSV — fonctions partagees entre historiques
# / CSV export — shared functions between histories
# ──────────────────────────────────────────────────────────────────────


def _export_tireuse_csv(modeladmin, request, queryset):
    """
    Exporte les sessions de debit par tireuse au format CSV.
    / Exports tap volume sessions as CSV.
    """
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_tireuse.csv"'
    writer = csv.writer(resp, delimiter=";")
    writer.writerow(
        [
            _("Date"),
            _("Tap"),
            _("Card UID"),
            _("Card name"),
            _("Beverage"),
            _("Volume (cl)"),
            _("Duration (s)"),
            _("Sale line"),
        ]
    )
    for session in queryset.order_by("started_at"):
        writer.writerow(
            [
                session.started_at.strftime("%Y-%m-%d %H:%M"),
                session.tireuse_bec.nom_tireuse if session.tireuse_bec else "",
                session.uid,
                session.label_snapshot,
                session.liquid_label_snapshot,
                f"{float(session.volume_delta_ml / 10):.1f}",
                session.duration_seconds or "",
                session.ligne_article_id or "",
            ]
        )
    return resp


_export_tireuse_csv.short_description = _("Export CSV")


def _export_cartes_csv(modeladmin, request, queryset):
    """
    Exporte les sessions par carte au format CSV.
    / Exports card sessions as CSV.
    """
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_cartes.csv"'
    writer = csv.writer(resp, delimiter=";")
    writer.writerow(
        [
            _("Date"),
            _("Card UID"),
            _("Card name"),
            _("Tap"),
            _("Beverage"),
            _("Volume (cl)"),
            _("Duration (s)"),
            _("Sale line"),
        ]
    )
    for session in queryset.order_by("started_at"):
        writer.writerow(
            [
                session.started_at.strftime("%Y-%m-%d %H:%M"),
                session.uid,
                session.label_snapshot,
                session.tireuse_bec.nom_tireuse if session.tireuse_bec else "",
                session.liquid_label_snapshot,
                f"{float(session.volume_delta_ml / 10):.1f}",
                session.duration_seconds or "",
                session.ligne_article_id or "",
            ]
        )
    return resp


_export_cartes_csv.short_description = _("Export CSV")


# ──────────────────────────────────────────────────────────────────────
# HistoriqueTireuseAdmin — debits normaux par tireuse
# / HistoriqueTireuseAdmin — normal volumes per tap
# ──────────────────────────────────────────────────────────────────────


@admin.register(HistoriqueTireuse, site=staff_admin_site)
class HistoriqueTireuseAdmin(ModelAdmin):
    """
    Historique des sessions de service normales (ni maintenance ni calibration).
    Inclut un filtre plage de dates et un export CSV.
    / History of normal service sessions (not maintenance or calibration).
    Includes date range filter and CSV export.
    """

    list_display = (
        "started_at",
        "tireuse_bec",
        "liquid_label_snapshot",
        "uid",
        "label_snapshot",
        "authorized",
        "volume_servi_cl",
    )
    list_filter = (DateRangeFilter, "tireuse_bec", "authorized")
    search_fields = ("uid", "label_snapshot", "liquid_label_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_tireuse_csv]

    def get_queryset(self, request):
        # Exclure les sessions de maintenance et de calibration
        # / Exclude maintenance and calibration sessions
        return (
            super()
            .get_queryset(request)
            .filter(is_maintenance=False, is_calibration=False)
        )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Volume (cl)"), ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        """Volume servi en centilitres.
        / Volume served in centiliters."""
        return f"{obj.volume_delta_ml / 10:.1f}"


# ──────────────────────────────────────────────────────────────────────
# HistoriqueCarteAdmin — mouvements par carte NFC
# / HistoriqueCarteAdmin — movements per NFC card
# ──────────────────────────────────────────────────────────────────────


@admin.register(HistoriqueCarte, site=staff_admin_site)
class HistoriqueCarteAdmin(ModelAdmin):
    """
    Historique des sessions centrees sur la carte NFC utilisee.
    Inclut un filtre plage de dates et un export CSV.
    / History of sessions focused on the NFC card used.
    Includes date range filter and CSV export.
    """

    list_display = (
        "started_at",
        "label_snapshot",
        "uid",
        "tireuse_bec",
        "liquid_label_snapshot",
        "authorized",
        "volume_servi_cl",
    )
    list_filter = (DateRangeFilter, "tireuse_bec", "authorized")
    search_fields = ("uid", "label_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_cartes_csv]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Volume (cl)"), ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        """Volume servi en centilitres.
        / Volume served in centiliters."""
        return f"{obj.volume_delta_ml / 10:.1f}"


# ──────────────────────────────────────────────────────────────────────
# HistoriqueMaintenanceAdmin — sessions de maintenance
# / HistoriqueMaintenanceAdmin — maintenance sessions
# ──────────────────────────────────────────────────────────────────────


def _export_maintenance_csv(modeladmin, request, queryset):
    """
    Exporte les sessions de maintenance au format CSV.
    / Exports maintenance sessions as CSV.
    """
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_maintenance.csv"'
    writer = csv.writer(resp, delimiter=";")
    writer.writerow(
        [
            _("Date"),
            _("Tap"),
            _("Card UID"),
            _("Maintenance card"),
            _("Cleaning product"),
            _("Volume (cl)"),
            _("Duration (s)"),
        ]
    )
    total_vol = 0
    for session in queryset.order_by("started_at"):
        vol_cl = float(session.volume_delta_ml / 10)
        total_vol += vol_cl
        writer.writerow(
            [
                session.started_at.strftime("%Y-%m-%d %H:%M"),
                session.tireuse_bec.nom_tireuse if session.tireuse_bec else "",
                session.uid,
                str(session.carte_maintenance) if session.carte_maintenance else "",
                session.produit_maintenance_snapshot,
                f"{vol_cl:.1f}",
                session.duration_seconds or "",
            ]
        )
    # Ligne de total en bas du CSV / Total row at the bottom
    writer.writerow([])
    writer.writerow([_("TOTAL"), "", "", "", "", f"{total_vol:.1f}", ""])
    return resp


_export_maintenance_csv.short_description = _("Export CSV")


@admin.register(HistoriqueMaintenance, site=staff_admin_site)
class HistoriqueMaintenanceAdmin(ModelAdmin):
    """
    Historique filtre sur les sessions de maintenance (is_maintenance=True).
    / History filtered on maintenance sessions (is_maintenance=True).
    """

    list_display = (
        "started_at",
        "tireuse_bec",
        "uid",
        "carte_maintenance",
        "produit_maintenance_snapshot",
        "volume_servi_cl",
        "duree_s",
    )
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid", "produit_maintenance_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_maintenance_csv]

    def get_queryset(self, request):
        # Filtrer uniquement les sessions de maintenance
        # / Filter only maintenance sessions
        return super().get_queryset(request).filter(is_maintenance=True)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Volume (cl)"), ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        """Volume servi en centilitres.
        / Volume served in centiliters."""
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description=_("Duration (s)"), ordering="ended_at")
    def duree_s(self, obj):
        """Duree de la session en secondes.
        / Session duration in seconds."""
        duree = obj.duration_seconds
        return int(duree) if duree is not None else "—"


# ──────────────────────────────────────────────────────────────────────
# SessionCalibrationAdmin — sessions de calibration du debitmetre
# / SessionCalibrationAdmin — flow meter calibration sessions
# ──────────────────────────────────────────────────────────────────────


@admin.register(SessionCalibration, site=staff_admin_site)
class SessionCalibrationAdmin(ModelAdmin):
    """
    Historique filtre sur les sessions de calibration (is_calibration=True).
    Affiche le volume mesure par Django vs le volume reel verse dans un verre gradue,
    et calcule l'ecart en pourcentage.
    / History filtered on calibration sessions (is_calibration=True).
    Shows the volume measured by Django vs the actual volume poured in a graduated glass,
    and calculates the percentage difference.
    """

    list_display = (
        "started_at",
        "tireuse_bec",
        "uid",
        "volume_servi_cl",
        "volume_reel_cl",
        "ecart_pct",
        "duree_s",
    )
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid",)
    date_hierarchy = "started_at"

    def get_queryset(self, request):
        # Filtrer uniquement les sessions de calibration
        # / Filter only calibration sessions
        return super().get_queryset(request).filter(is_calibration=True)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Django (cl)"), ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        """Volume mesure par le debitmetre en centilitres.
        / Volume measured by the flow meter in centiliters."""
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description=_("Glass (cl)"), ordering="volume_reel_ml")
    def volume_reel_cl(self, obj):
        """Volume reel verse dans un verre gradue en centilitres.
        / Actual volume poured in a graduated glass in centiliters."""
        if obj.volume_reel_ml:
            return f"{obj.volume_reel_ml / 10:.1f}"
        return "—"

    @admin.display(description=_("Deviation"))
    def ecart_pct(self, obj):
        """Ecart entre le volume Django et le volume reel en pourcentage.
        / Deviation between Django volume and actual volume as a percentage."""
        if obj.volume_reel_ml and obj.volume_delta_ml:
            ecart = (
                (float(obj.volume_delta_ml) - float(obj.volume_reel_ml))
                / float(obj.volume_reel_ml)
                * 100
            )
            return f"{ecart:+.1f}%"
        return "—"

    @admin.display(description=_("Duration (s)"), ordering="ended_at")
    def duree_s(self, obj):
        """Duree de la session en secondes.
        / Session duration in seconds."""
        duree = obj.duration_seconds
        return int(duree) if duree is not None else "—"


# ──────────────────────────────────────────────────────────────────────
# ConfigurationAdmin — singleton de configuration
# / ConfigurationAdmin — configuration singleton
# ──────────────────────────────────────────────────────────────────────


@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(ModelAdmin):
    """
    Admin singleton : un seul objet possible (django-solo).
    La vue liste redirige directement vers le formulaire unique.
    / Singleton admin: only one object possible (django-solo).
    The list view redirects directly to the single form.
    """

    def has_add_permission(self, request, obj=None):
        # Bloquer l'ajout si l'objet existe deja
        # / Block addition if object already exists
        return not Configuration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Le singleton ne doit pas etre supprime
        # / The singleton must not be deleted
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def changelist_view(self, request, extra_context=None):
        """
        Redirige la vue liste directement vers le formulaire de configuration unique.
        / Redirect the list view directly to the single configuration form.
        """
        from django.shortcuts import redirect
        from django.urls import reverse

        obj = Configuration.get_solo()
        return redirect(
            reverse("staff_admin:controlvanne_configuration_change", args=[obj.pk])
        )

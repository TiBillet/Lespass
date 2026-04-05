import csv
import datetime
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import (Card, CarteMaintenance, Configuration, Debimetre, Fut, HistoriqueCarte,
                     HistoriqueFut, HistoriqueMaintenance, HistoriqueTireuse,
                     RfidSession, SessionCalibration, TireuseBec)
from .forms import TireuseBecForm


# ---------------------------------------------------------------------------
# Filtre plage de dates (inputs Du / Au)
# ---------------------------------------------------------------------------
class DateRangeFilter(SimpleListFilter):
    title = "Période"
    parameter_name = "date_from"
    template = "admin/date_range_filter.html"

    def expected_parameters(self):
        return ["date_from", "date_to"]

    def lookups(self, request, model_admin):
        return (("_", "—"),)  # requis par SimpleListFilter

    def choices(self, changelist):
        yield {
            "selected": not (changelist.params.get("date_from") or changelist.params.get("date_to")),
            "query_string": changelist.get_query_string(remove=["date_from", "date_to"]),
            "display": "Toutes",
        }

    def queryset(self, request, queryset):
        date_from = request.GET.get("date_from")
        date_to   = request.GET.get("date_to")
        try:
            if date_from:
                queryset = queryset.filter(started_at__date__gte=datetime.date.fromisoformat(date_from))
            if date_to:
                queryset = queryset.filter(started_at__date__lte=datetime.date.fromisoformat(date_to))
        except ValueError:
            pass
        return queryset


@admin.register(Fut)
class FutAdmin(ModelAdmin):
    list_display = (
        "nom",
        "brasseur",
        "type_biere",
        "degre_alcool",
        "volume_fut_l",
        "quantite_stock",
        "prix_litre",
        "prix_achat",
    )
    list_editable = ("quantite_stock", "prix_litre", "prix_achat")
    list_filter = ("type_biere", "brasseur")
    search_fields = ("nom", "brasseur")


class HistoriqueFutInline(TabularInline):
    model = HistoriqueFut
    extra = 0
    readonly_fields = (
        "fut",
        "mis_en_service_le",
        "retire_le",
        "volume_initial_l",
        "volume_final_l",
        "volume_consomme",
    )
    fields = readonly_fields
    ordering = ("-mis_en_service_le",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Volume initial (L)")
    def volume_initial_l(self, obj):
        return f"{float(obj.volume_initial_ml) / 1000:.1f} L"

    @admin.display(description="Volume final (L)")
    def volume_final_l(self, obj):
        if obj.volume_final_ml is not None:
            return f"{float(obj.volume_final_ml) / 1000:.1f} L"
        return "En service"

    @admin.display(description="Consommé (L)")
    def volume_consomme(self, obj):
        v = obj.volume_consomme_l
        if v is not None:
            return f"{v:.1f} L"
        return "—"


@admin.register(HistoriqueFut)
class HistoriqueFutAdmin(ModelAdmin):
    list_display = (
        "tireuse_bec",
        "fut",
        "mis_en_service_le",
        "retire_le",
        "volume_initial_l",
        "volume_final_l",
        "volume_consomme",
    )
    list_filter = ("tireuse_bec", "fut__type_biere")
    date_hierarchy = "mis_en_service_le"
    readonly_fields = (
        "tireuse_bec",
        "fut",
        "mis_en_service_le",
        "retire_le",
        "volume_initial_ml",
        "volume_final_ml",
    )

    @admin.display(description="Volume initial (L)")
    def volume_initial_l(self, obj):
        return f"{float(obj.volume_initial_ml) / 1000:.1f} L"

    @admin.display(description="Volume final (L)")
    def volume_final_l(self, obj):
        if obj.volume_final_ml is not None:
            return f"{float(obj.volume_final_ml) / 1000:.1f} L"
        return "En service"

    @admin.display(description="Consommé (L)")
    def volume_consomme(self, obj):
        v = obj.volume_consomme_l
        if v is not None:
            return f"{v:.1f} L"
        return "—"


@admin.register(TireuseBec)
class TireuseBecAdmin(ModelAdmin):
    inlines = [HistoriqueFutInline]
    form = TireuseBecForm
    actions = ["calibrer_debimetre"]
    list_display = (
        "name_with_uuid",
        "fut_actif",
        "debimetre",
        "monnaie",
        "prix_effectif_display",
        "col_25cl",
        "col_33cl",
        "col_50cl",
        "volume_restant_cl",
        "seuil_mini_cl",
        "appliquer_reserve",
        "enabled",
        "notes",
    )
    list_editable = (
        "fut_actif",
        "debimetre",
        "monnaie",
        "enabled",
    )
    search_fields = ("nom_tireuse", "notes")

    @admin.display(description="Name")
    def name_with_uuid(self, obj):
        return format_html('<span title="UUID: {}">{}</span>', obj.uuid, obj.nom_tireuse)

    @admin.display(description="UUID")
    def uuid_readonly(self, obj):
        return format_html(
            '<code class="uuid-copy" style="cursor:pointer;padding:4px 8px;background:#f0f0f0;border-radius:4px;font-size:12px;" onclick="navigator.clipboard.writeText(\'{}\');alert(\'UUID copié!\')" title="Cliquer pour copier">{}</code>',
            obj.uuid,
            obj.uuid,
        )

    def get_readonly_fields(self, request, obj=None):
        base = ("uuid", "col_25cl", "col_33cl", "col_50cl", "volume_restant_cl", "seuil_mini_cl", "prix_effectif_display")
        # prix_litre_override réservé aux superusers
        if not request.user.is_superuser:
            base += ("prix_litre_override",)
        return base + super().get_readonly_fields(request, obj)

    @admin.display(description="Volume restant (cl)", ordering="reservoir_ml")
    def volume_restant_cl(self, obj):
        return f"{float(obj.reservoir_ml) / 10:.0f} cl"

    @admin.display(description="Seuil mini (cl)", ordering="seuil_mini_ml")
    def seuil_mini_cl(self, obj):
        return f"{float(obj.seuil_mini_ml) / 10:.0f} cl"

    @admin.display(description="Prix/Litre")
    def prix_effectif_display(self, obj):
        pL = obj.prix_litre  # propriété calculée
        label = f"{pL} {obj.monnaie}"
        if obj.prix_litre_override is not None and obj.prix_litre_override > 0:
            return format_html('<span title="Override actif">{} ✎</span>', label)
        return label

    def _prix_volume(self, obj, cl):
        from decimal import Decimal
        pL = obj.prix_litre  # propriété calculée
        if pL and pL > 0:
            val = (pL * Decimal(str(cl)) / 100).quantize(Decimal("0.01"))
            return f"{val} {obj.monnaie}"
        return "—"

    @admin.display(description="25 cl")
    def col_25cl(self, obj):
        return self._prix_volume(obj, 25)

    @admin.display(description="33 cl")
    def col_33cl(self, obj):
        return self._prix_volume(obj, 33)

    @admin.display(description="50 cl")
    def col_50cl(self, obj):
        return self._prix_volume(obj, 50)

    # def push_kiosk_url(self, request, queryset):
    #     ch = get_channel_layer()
    #     n = 0
    #     for tb in queryset:
    #         url = f"{request.scheme}://{request.get_host()}/?tireuse_bec={tb.uuid}"
    #         async_to_sync(ch.group_send)(
    #             f"rfid_state.{tb.uuid}",
    #             {"type": "state_update", "payload": {"kiosk_url": url}},
    #         )
    #         n += 1
    #     self.message_user(request, f"Nouvelle URL envoyée à {n} kiosque(s) via WebSocket.")
    #
    # push_kiosk_url.short_description = "Envoyer la bonne URL au kiosque (WebSocket)"

    def calibrer_debimetre(self, request, queryset):
        """Redirige vers le wizard de calibration pour la tireuse sélectionnée."""
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        if queryset.count() != 1:
            self.message_user(
                request,
                "Sélectionnez une seule tireuse pour lancer la calibration.",
                messages.WARNING,
            )
            return
        tireuse = queryset.first()
        return HttpResponseRedirect(
            reverse("calibration_page", kwargs={"uuid": tireuse.uuid})
        )

    calibrer_debimetre.short_description = "Calibrer le débitmètre"



@admin.register(Debimetre)
class DebitmetreAdmin(ModelAdmin):
    list_display = ("name", "flow_calibration_factor")
    list_editable = ("flow_calibration_factor",)


@admin.register(Card)
class CardAdmin(ModelAdmin):
    list_display = ("label", "uid", "solde_colore", "is_active", "valid_from", "valid_to")
    list_editable = ("is_active",)
    search_fields = ("uid", "label")
    list_filter = ("is_active",)
    ordering = ("-balance",)

    @admin.display(description="Solde", ordering="balance")
    def solde_colore(self, obj):
        if obj.balance <= 0:
            color = "#e74c3c"
        elif obj.balance < 5:
            color = "#f39c12"
        else:
            color = "#27ae60"
        return format_html(
            '<b style="color:{}">{} {}</b>',
            color, obj.balance, "€",
        )

    actions = ["afficher_total", "export_cartes_csv"]

    @admin.action(description="Afficher le solde total de la sélection")
    def afficher_total(self, request, queryset):
        from django.db.models import Sum
        total = queryset.aggregate(t=Sum("balance"))["t"] or 0
        nb = queryset.count()
        self.message_user(
            request,
            f"Solde total ({nb} carte(s) sélectionnée(s)) : {total:.2f} €",
            messages.INFO,
        )

    @admin.action(description="Exporter en CSV")
    def export_cartes_csv(self, request, queryset):
        from django.db.models import Sum
        resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        resp["Content-Disposition"] = 'attachment; filename="cartes_soldes.csv"'
        w = csv.writer(resp, delimiter=";")
        w.writerow(["UID", "Nom carte", "Solde (€)", "Active", "Valide depuis", "Fin validité"])
        for c in queryset.order_by("-balance"):
            w.writerow([
                c.uid, c.label, f"{c.balance:.2f}",
                "Oui" if c.is_active else "Non",
                c.valid_from.strftime("%Y-%m-%d") if c.valid_from else "",
                c.valid_to.strftime("%Y-%m-%d") if c.valid_to else "",
            ])
        total = queryset.aggregate(t=Sum("balance"))["t"] or 0
        w.writerow([])
        w.writerow(["TOTAL", "", f"{total:.2f}", "", "", ""])
        return resp


@admin.register(RfidSession)
class RfidSessionAdmin(ModelAdmin):
    list_display = ("tireuse_bec", "liquid_label_snapshot", "uid", "authorized",
                    "started_at", "ended_at", "volume_servi_cl", "label_snapshot")
    list_filter = ("authorized", "tireuse_bec")
    search_fields = ("uid", "label_snapshot", "liquid_label_snapshot")
    date_hierarchy = "started_at"

    @admin.display(description="Volume servi (cl)", ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        return f"{obj.volume_delta_ml / 10:.1f}"


# ---------------------------------------------------------------------------
# Historique tireuses
# ---------------------------------------------------------------------------
def _export_tireuses_csv(modeladmin, request, queryset):
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_tireuses.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["Date", "Tireuse", "Boisson", "UID carte", "Nom carte",
                "Volume servi (cl)", "Unités débitées", "Durée (s)", "Autorisé"])
    total_vol = 0
    total_units = 0
    for s in queryset.order_by("started_at"):
        vol_cl = float(s.volume_delta_ml / 10)
        total_vol += vol_cl
        total_units += float(s.charged_units or 0)
        w.writerow([
            s.started_at.strftime("%Y-%m-%d %H:%M"),
            s.tireuse_bec.nom_tireuse if s.tireuse_bec else "",
            s.liquid_label_snapshot,
            s.uid,
            s.label_snapshot,
            f"{vol_cl:.1f}",
            f"{float(s.charged_units or 0):.2f}",
            s.duration_seconds or "",
            "Oui" if s.authorized else "Non",
        ])
    w.writerow([])
    w.writerow(["TOTAL", "", "", "", "", f"{total_vol:.1f}", f"{total_units:.2f}", "", ""])
    return resp

_export_tireuses_csv.short_description = "Exporter en CSV"


@admin.register(HistoriqueTireuse)
class HistoriqueTireuseAdmin(ModelAdmin):
    list_display = ("started_at", "tireuse_bec", "liquid_label_snapshot",
                    "uid", "label_snapshot", "volume_servi_cl",
                    "montant", "duree_s")
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid", "label_snapshot", "liquid_label_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_tireuses_csv]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Volume (cl)", ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description="Montant", ordering="charged_units")
    def montant(self, obj):
        if obj.charged_units:
            return f"{obj.charged_units:.2f} {obj.unit_label_snapshot}"
        return "—"

    @admin.display(description="Durée (s)", ordering="ended_at")
    def duree_s(self, obj):
        d = obj.duration_seconds
        return int(d) if d is not None else "—"


# ---------------------------------------------------------------------------
# Historique cartes
# ---------------------------------------------------------------------------
def _export_cartes_csv(modeladmin, request, queryset):
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_cartes.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["Date", "UID", "Nom carte", "Tireuse", "Boisson",
                "Volume servi (cl)", "Unités débitées",
                "Solde avant", "Solde après", "Durée (s)"])
    for s in queryset.order_by("started_at"):
        w.writerow([
            s.started_at.strftime("%Y-%m-%d %H:%M"),
            s.uid,
            s.label_snapshot,
            s.tireuse_bec.nom_tireuse if s.tireuse_bec else "",
            s.liquid_label_snapshot,
            f"{float(s.volume_delta_ml / 10):.1f}",
            f"{float(s.charged_units or 0):.2f}",
            f"{s.balance_avant:.2f}" if s.balance_avant is not None else "",
            f"{s.balance_apres:.2f}" if s.balance_apres is not None else "",
            s.duration_seconds or "",
        ])
    return resp

_export_cartes_csv.short_description = "Exporter en CSV"


@admin.register(HistoriqueCarte)
class HistoriqueCarteAdmin(ModelAdmin):
    list_display = ("started_at", "label_snapshot", "uid", "tireuse_bec",
                    "liquid_label_snapshot", "volume_servi_cl",
                    "montant", "balance_avant", "balance_apres")
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid", "label_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_cartes_csv]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Volume (cl)", ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description="Montant", ordering="charged_units")
    def montant(self, obj):
        if obj.charged_units:
            return f"{obj.charged_units:.2f} {obj.unit_label_snapshot}"
        return "—"


# ---------------------------------------------------------------------------
# Cartes maintenance
# ---------------------------------------------------------------------------
@admin.register(CarteMaintenance)
class CarteMaintenanceAdmin(ModelAdmin):
    list_display = ("label", "uid", "is_active", "produit", "notes")
    list_editable = ("is_active",)
    search_fields = ("uid", "label", "produit")
    list_filter = ("is_active",)


# ---------------------------------------------------------------------------
# Historique maintenance
# ---------------------------------------------------------------------------
def _export_maintenance_csv(modeladmin, request, queryset):
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="historique_maintenance.csv"'
    w = csv.writer(resp, delimiter=";")
    w.writerow(["Date", "Tireuse", "UID carte", "Carte maintenance", "Produit", "Volume (cl)", "Durée (s)"])
    total_vol = 0
    for s in queryset.order_by("started_at"):
        vol_cl = float(s.volume_delta_ml / 10)
        total_vol += vol_cl
        w.writerow([
            s.started_at.strftime("%Y-%m-%d %H:%M"),
            s.tireuse_bec.nom_tireuse if s.tireuse_bec else "",
            s.uid,
            str(s.carte_maintenance) if s.carte_maintenance else "",
            s.produit_maintenance_snapshot,
            f"{vol_cl:.1f}",
            s.duration_seconds or "",
        ])
    w.writerow([])
    w.writerow(["TOTAL", "", "", "", "", f"{total_vol:.1f}", ""])
    return resp

_export_maintenance_csv.short_description = "Exporter en CSV"


@admin.register(HistoriqueMaintenance)
class HistoriqueMaintenanceAdmin(ModelAdmin):
    list_display = ("started_at", "tireuse_bec", "uid", "carte_maintenance",
                    "produit_maintenance_snapshot", "volume_servi_cl", "duree_s")
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid", "produit_maintenance_snapshot")
    date_hierarchy = "started_at"
    actions = [_export_maintenance_csv]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_maintenance=True)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Volume (cl)", ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description="Durée (s)", ordering="ended_at")
    def duree_s(self, obj):
        d = obj.duration_seconds
        return int(d) if d is not None else "—"


# ---------------------------------------------------------------------------
# Sessions calibration
# ---------------------------------------------------------------------------
@admin.register(SessionCalibration)
class SessionCalibrationAdmin(ModelAdmin):
    list_display = ("started_at", "tireuse_bec", "uid",
                    "volume_servi_cl", "volume_reel_cl", "ecart_pct", "duree_s_cal")
    list_filter = (DateRangeFilter, "tireuse_bec")
    search_fields = ("uid",)
    date_hierarchy = "started_at"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_calibration=True)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Django (cl)", ordering="volume_delta_ml")
    def volume_servi_cl(self, obj):
        return f"{obj.volume_delta_ml / 10:.1f}"

    @admin.display(description="Verre (cl)", ordering="volume_reel_ml")
    def volume_reel_cl(self, obj):
        if obj.volume_reel_ml:
            return f"{obj.volume_reel_ml / 10:.1f}"
        return "—"

    @admin.display(description="Écart")
    def ecart_pct(self, obj):
        if obj.volume_reel_ml and obj.volume_delta_ml:
            ecart = (
                (float(obj.volume_delta_ml) - float(obj.volume_reel_ml))
                / float(obj.volume_reel_ml) * 100
            )
            return f"{ecart:+.1f}%"
        return "—"

    @admin.display(description="Durée (s)", ordering="ended_at")
    def duree_s_cal(self, obj):
        d = obj.duration_seconds
        return int(d) if d is not None else "—"


# ---------------------------------------------------------------------------
# Configuration serveur (singleton)
# ---------------------------------------------------------------------------
@admin.register(Configuration)
class ConfigurationAdmin(ModelAdmin):
    """
    Singleton : un seul objet possible.
    La liste redirige directement vers le formulaire de cet objet.
    """

    def has_add_permission(self, request):
        # On bloque l'ajout si l'objet existe déjà
        return not Configuration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Redirige la vue liste directement vers le formulaire unique
        from django.shortcuts import redirect
        from django.urls import reverse
        obj = Configuration.get()
        return redirect(reverse("admin:controlvanne_configuration_change", args=[obj.pk]))

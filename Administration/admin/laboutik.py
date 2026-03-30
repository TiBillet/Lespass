"""
Administration des modeles LaBoutik (caisse, points de vente, imprimantes, tables, commandes).
/ Admin for LaBoutik models (POS, points of sale, printers, tables, orders).

LOCALISATION : Administration/admin/laboutik.py
"""
import logging

from django import forms
from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from Administration.admin.products import ICON_POS, IconPickerWidget
from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from laboutik.models import (
    LaboutikConfiguration,
    Printer,
    PointDeVente, CartePrimaire, CategorieTable, Table,
    CommandeSauvegarde, ArticleCommandeSauvegarde,
    ClotureCaisse,
    ImpressionLog,
)

logger = logging.getLogger(__name__)


@admin.register(LaboutikConfiguration, site=staff_admin_site)
class LaboutikConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    """Admin singleton pour la configuration globale de l'interface caisse.
    Singleton admin for the global POS interface configuration.
    LOCALISATION : Administration/admin/laboutik.py"""
    compressed_fields = True
    warn_unsaved_form = True

    # Le compteur de tickets est en lecture seule pour eviter une remise a zero accidentelle.
    # / Receipt counter is read-only to prevent accidental reset.
    readonly_fields = ('compteur_tickets',)

    fieldsets = (
        (_('Interface caisse / POS interface'), {
            'fields': (
                'taille_police_articles',
                'mode_ecole',
            ),
        }),
        (_('Sunmi Cloud'), {
            'fields': (
                'sunmi_app_id',
                'sunmi_app_key',
            ),
            'description': _(
                "Identifiants Sunmi Cloud (stockes chiffres). "
                "/ Sunmi Cloud credentials (stored encrypted)."
            ),
        }),
        (_('Ticket de vente / Sale receipt'), {
            'fields': (
                'pied_ticket',
                'compteur_tickets',
            ),
            'description': _(
                "Personnalisation des tickets de vente. "
                "/ Sale receipt customization."
            ),
        }),
    )

    def has_add_permission(self, request):
        # Singleton : pas de creation manuelle — get_or_create suffit
        # Singleton: no manual creation — get_or_create is enough
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class PointDeVenteForm(forms.ModelForm):
    """Formulaire pour les points de vente avec selecteur visuel d'icones.
    Form for points of sale with visual icon picker.
    LOCALISATION : Administration/admin/laboutik.py"""

    icon = forms.ChoiceField(
        choices=[("", _("— Aucune icône —"))] + list(ICON_POS),
        required=False,
        label=_("Icon"),
        widget=IconPickerWidget(),
    )

    class Meta:
        model = PointDeVente
        fields = '__all__'


@admin.register(PointDeVente, site=staff_admin_site)
class PointDeVenteAdmin(ModelAdmin):
    """Admin pour les points de vente.
    Admin for points of sale.
    LOCALISATION : Administration/admin/laboutik.py"""
    form = PointDeVenteForm
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('name', 'comportement', 'service_direct', 'hidden')
    list_filter = ['comportement', 'hidden']
    search_fields = ['name']
    ordering = ('poid_liste', 'name')
    filter_horizontal = ('products', 'categories')

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'icon',
                'comportement',
                'poid_liste',
                'hidden',
            ),
        }),
        (_('Options'), {
            'fields': (
                'service_direct',
                'afficher_les_prix',
                'accepte_especes',
                'accepte_carte_bancaire',
                'accepte_cheque',
                'accepte_commandes',
                'printer',
            ),
        }),
        (_('Products & categories'), {
            'fields': (
                'products',
                'categories',
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Printer, site=staff_admin_site)
class PrinterAdmin(ModelAdmin):
    """Admin pour les imprimantes thermiques (Sunmi Cloud / Inner / LAN).
    Admin for thermal printers (Sunmi Cloud / Inner / LAN).
    LOCALISATION : Administration/admin/laboutik.py"""
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('name', 'printer_type', 'dots_per_line', 'sunmi_serial_number', 'active')
    list_filter = ['printer_type', 'active']
    search_fields = ['name', 'sunmi_serial_number']
    ordering = ('name',)

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'printer_type',
                'dots_per_line',
                'active',
            ),
        }),
        (_('Sunmi Cloud'), {
            'fields': (
                'sunmi_serial_number',
            ),
            'description': _(
                "Serial number required for Sunmi Cloud printers only."
            ),
        }),
        (_('Sunmi LAN'), {
            'fields': (
                'ip_address',
            ),
            'description': _(
                "IP address required for LAN printers only (same subnet)."
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(CartePrimaire, site=staff_admin_site)
class CartePrimaireAdmin(ModelAdmin):
    """Admin pour les cartes primaires (operateurs de caisse).
    Admin for primary cards (POS operators).
    LOCALISATION : Administration/admin/laboutik.py"""
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('carte', 'edit_mode', 'datetime')
    list_filter = ['edit_mode']
    search_fields = ['carte__tag_id', 'carte__number']
    filter_horizontal = ('points_de_vente',)

    fieldsets = (
        (None, {
            'fields': (
                'carte',
                'edit_mode',
                'points_de_vente',
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(CategorieTable, site=staff_admin_site)
class CategorieTableAdmin(ModelAdmin):
    """Admin minimal pour les categories de table (Phase 4 = restaurant).
    Minimal admin for table categories (Phase 4 = restaurant).
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('name', 'icon')
    search_fields = ['name']

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Table, site=staff_admin_site)
class TableAdmin(ModelAdmin):
    """Admin minimal pour les tables de restaurant (Phase 4 = restaurant).
    Minimal admin for restaurant tables (Phase 4 = restaurant).
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('name', 'categorie', 'statut', 'ephemere', 'archive')
    list_filter = ['statut', 'categorie', 'archive']
    search_fields = ['name']
    ordering = ('poids', 'name')

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Commandes de restaurant (Phase 4) ---
# --- Restaurant orders (Phase 4) ---

class ArticleCommandeSauvegardeInline(TabularInline):
    """Inline lecture seule pour les articles d'une commande.
    Read-only inline for order articles.
    LOCALISATION : Administration/admin/laboutik.py"""
    model = ArticleCommandeSauvegarde
    extra = 0
    fields = ('product', 'price', 'qty', 'reste_a_payer', 'reste_a_servir', 'statut')
    readonly_fields = ('product', 'price', 'qty', 'reste_a_payer', 'reste_a_servir', 'statut')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommandeSauvegarde, site=staff_admin_site)
class CommandeSauvegardeAdmin(ModelAdmin):
    """Admin lecture seule pour l'historique des commandes de restaurant.
    Read-only admin for restaurant order history.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('uuid', 'table', 'statut', 'responsable', 'datetime', 'archive')
    list_filter = ['statut', 'archive']
    search_fields = ['uuid', 'commentaire']
    ordering = ('-datetime',)
    readonly_fields = (
        'uuid', 'service', 'responsable', 'table', 'datetime',
        'statut', 'commentaire', 'archive',
    )
    inlines = [ArticleCommandeSauvegardeInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Cloture de caisse (Phase 5) ---
# --- Cash register closure (Phase 5) ---

@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """Admin lecture seule pour les clotures de caisse.
    Document comptable immuable — aucune modification possible.
    Read-only admin for cash register closures.
    Immutable accounting document — no modification allowed.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = (
        'niveau', 'numero_sequentiel',
        'responsable', 'point_de_vente',
        'datetime_cloture',
        'total_general', 'total_perpetuel',
        'nombre_transactions', 'badge_integrite',
    )
    list_filter = ['niveau']
    search_fields = ['point_de_vente__name', 'responsable__email']
    ordering = ('-datetime_cloture',)
    readonly_fields = (
        'uuid', 'point_de_vente', 'responsable',
        'datetime_ouverture', 'datetime_cloture',
        'niveau', 'numero_sequentiel',
        'total_especes', 'total_carte_bancaire', 'total_cashless',
        'total_general', 'total_perpetuel',
        'nombre_transactions', 'hash_lignes', 'rapport_json',
    )

    fieldsets = (
        (_('Identification'), {
            'fields': (
                'uuid', 'point_de_vente', 'responsable',
                'niveau', 'numero_sequentiel',
            ),
        }),
        (_('Période'), {
            'fields': (
                'datetime_ouverture', 'datetime_cloture',
            ),
        }),
        (_('Totaux'), {
            'fields': (
                'total_especes', 'total_carte_bancaire', 'total_cashless',
                'total_general', 'total_perpetuel',
            ),
        }),
        (_('Détails'), {
            'fields': (
                'nombre_transactions', 'hash_lignes', 'rapport_json',
            ),
        }),
    )

    actions_row = ["voir_rapport", "exporter_csv", "exporter_pdf", "exporter_excel"]

    @action(
        description=_("View report"),
        url_path="voir-rapport",
        permissions=["custom_actions_row"],
    )
    def voir_rapport(self, request, object_id):
        """
        Affiche le rapport comptable en HTML structure (pas JSON brut).
        / Displays the accounting report as structured HTML (not raw JSON).
        LOCALISATION : Administration/admin/laboutik.py
        """
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        context = {
            **self.admin_site.each_context(request),
            "cloture": cloture,
            "rapport": rapport,
            "title": f"Rapport — {cloture.get_niveau_display()} #{cloture.numero_sequentiel}",
        }
        return TemplateResponse(
            request,
            "admin/cloture_detail.html",
            context,
        )

    @action(
        description=_("Export CSV"),
        url_path="exporter-csv",
        permissions=["custom_actions_row"],
    )
    def exporter_csv(self, request, object_id):
        """
        Exporte le rapport de cloture en CSV (delimiteur ;).
        / Exports the closure report as CSV (delimiter ;).
        LOCALISATION : Administration/admin/laboutik.py
        """
        import csv
        from django.http import HttpResponse

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # BOM UTF-8 pour compatibilite Excel
        # / UTF-8 BOM for Excel compatibility
        response.write('\ufeff')

        writer = csv.writer(response, delimiter=';')

        # En-tete general / General header
        writer.writerow([str(_("Closure report"))])
        writer.writerow([
            str(_("Level")), cloture.get_niveau_display(),
            str(_("Number")), cloture.numero_sequentiel,
        ])
        writer.writerow([str(_("Date")), str(cloture.datetime_cloture)])
        writer.writerow([str(_("Perpetual total")), cloture.total_perpetuel])
        writer.writerow([])

        # Ecrire chaque section du rapport / Write each report section
        for section_name, section_data in rapport.items():
            writer.writerow([section_name.upper()])

            if isinstance(section_data, dict):
                for cle, valeur in section_data.items():
                    writer.writerow([cle, valeur])
            elif isinstance(section_data, list):
                if section_data and isinstance(section_data[0], dict):
                    headers = list(section_data[0].keys())
                    writer.writerow(headers)
                    for item in section_data:
                        writer.writerow([item.get(h, '') for h in headers])
                else:
                    for item in section_data:
                        writer.writerow([item])
            else:
                writer.writerow([section_data])

            writer.writerow([])

        return response

    @action(
        description=_("Export PDF"),
        url_path="exporter-pdf",
        permissions=["custom_actions_row"],
    )
    def exporter_pdf(self, request, object_id):
        """
        Exporte le rapport de cloture en PDF A4 (WeasyPrint).
        / Exports the closure report as A4 PDF (WeasyPrint).
        LOCALISATION : Administration/admin/laboutik.py
        """
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from BaseBillet.models import Configuration

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}
        config = Configuration.get_solo()

        # Adresse complete assemblee depuis les parties disponibles
        # / Full address assembled from available parts
        parties_adresse = []
        if config.adress:
            parties_adresse.append(config.adress)
        if config.postal_code:
            parties_adresse.append(str(config.postal_code))
        if config.city:
            parties_adresse.append(config.city)

        context = {
            "cloture": cloture,
            "rapport": rapport,
            "config_org": config.organisation or "",
            "config_siret": config.siren or "",
            "config_address": " ".join(parties_adresse),
            "now": timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M"),
        }

        html_string = render_to_string(
            "laboutik/pdf/rapport_comptable.html", context,
        )
        pdf_bytes = HTML(string=html_string).write_pdf()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(
        description=_("Export Excel"),
        url_path="exporter-excel",
        permissions=["custom_actions_row"],
    )
    def exporter_excel(self, request, object_id):
        """
        Exporte le rapport de cloture en Excel (1 onglet par section).
        / Exports the closure report as Excel (1 sheet per section).
        LOCALISATION : Administration/admin/laboutik.py
        """
        import openpyxl
        from django.http import HttpResponse
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        wb = openpyxl.Workbook()
        # Supprimer la feuille par defaut / Remove default sheet
        wb.remove(wb.active)

        bold_font = Font(bold=True)

        for section_name, section_data in rapport.items():
            # Nom d'onglet tronque a 31 caracteres (limite Excel)
            # / Sheet name truncated to 31 chars (Excel limit)
            sheet_name = section_name[:31]
            ws = wb.create_sheet(title=sheet_name)

            if isinstance(section_data, dict):
                ws.append(["Cle", "Valeur"])
                ws['A1'].font = bold_font
                ws['B1'].font = bold_font
                for cle, valeur in section_data.items():
                    ws.append([str(cle), str(valeur)])

            elif isinstance(section_data, list) and section_data:
                if isinstance(section_data[0], dict):
                    headers = list(section_data[0].keys())
                    ws.append(headers)
                    for col_idx in range(1, len(headers) + 1):
                        ws.cell(row=1, column=col_idx).font = bold_font
                    for item in section_data:
                        ws.append([item.get(h, '') for h in headers])
                else:
                    for item in section_data:
                        ws.append([str(item)])
            else:
                ws.append([str(section_data)])

            # Auto-largeur des colonnes / Auto-width columns
            for col_idx in range(1, ws.max_column + 1):
                max_length = 0
                for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
                    for cell in row:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_length + 2, 50)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_("Integrity"))
    def badge_integrite(self, obj):
        """
        Badge vert si hash_lignes est present, tiret si vide.
        Pour les clotures M/A, le hash n'est pas applicable.
        / Green badge if hash_lignes present, dash if empty.
        For M/A closures, hash is not applicable.
        """
        from django.utils.html import format_html
        if obj.niveau != ClotureCaisse.JOURNALIERE:
            return format_html('<span style="color: gray;">—</span>')
        if obj.hash_lignes:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: orange;">—</span>')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Journal des impressions (conformite LNE exigence 9) ---
# --- Print audit log (LNE compliance req. 9) ---

@admin.register(ImpressionLog, site=staff_admin_site)
class ImpressionLogAdmin(ModelAdmin):
    """Admin lecture seule pour la tracabilite des impressions.
    Read-only admin for print tracking.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = (
        'datetime', 'type_justificatif', 'is_duplicata',
        'uuid_transaction', 'printer', 'operateur', 'format_emission',
    )
    list_filter = ('type_justificatif', 'is_duplicata', 'format_emission')
    search_fields = ('uuid_transaction',)
    ordering = ('-datetime',)
    readonly_fields = (
        'uuid', 'datetime', 'ligne_article', 'uuid_transaction',
        'cloture', 'operateur', 'printer', 'type_justificatif',
        'is_duplicata', 'format_emission',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

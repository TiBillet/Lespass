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

# --- Helpers d'export pour ClotureCaisseAdmin ---
# Definis HORS de la classe pour eviter qu'Unfold les wrappe avec @action.
# / Defined OUTSIDE the class to prevent Unfold from wrapping them with @action.

def _euros(centimes):
    """Convertit des centimes (int) en euros (float arrondi). / Converts cents to euros."""
    if centimes is None:
        return 0.0
    return round(centimes / 100, 2)


def _ecrire_rapport_csv_excel(writer, cloture, rapport):
    """
    Ecrit le rapport section par section dans un writer generique.
    Le writer doit implementer append_title, append_row, append_header, append_blank.
    / Writes the report section by section into a generic writer.
    """
    e = _euros

    # --- En-tete ---
    writer.append_title(str(_("Closure report")))
    writer.append_row([str(_("Level")), cloture.get_niveau_display()])
    writer.append_row([str(_("Number")), f"#{cloture.numero_sequentiel}"])
    writer.append_row([str(_("Point of sale")), cloture.point_de_vente.name if cloture.point_de_vente else "—"])
    writer.append_row([str(_("Responsible")), str(cloture.responsable or "—")])
    writer.append_row([str(_("Period")), f"{cloture.datetime_ouverture} → {cloture.datetime_cloture}"])
    writer.append_blank()

    # --- Section 1 : Totaux par moyen de paiement ---
    section = rapport.get("totaux_par_moyen", {})
    if section:
        writer.append_title(str(_("Totals by payment method")))
        writer.append_header([str(_("Payment method")), str(_("Amount"))])
        writer.append_row([str(_("Cash")), e(section.get("especes", 0))])
        writer.append_row([str(_("Credit card")), e(section.get("carte_bancaire", 0))])
        writer.append_row([str(_("Cashless")), e(section.get("cashless", 0))])
        for asset in section.get("cashless_detail", []):
            writer.append_row([f"  ↳ {asset['nom']} ({asset['code']})", e(asset["montant"])])
        writer.append_row([str(_("Check")), e(section.get("cheque", 0))])
        writer.append_row([str(_("Total")), e(section.get("total", 0))])
        writer.append_blank()

    # --- Section 2 : Detail des ventes ---
    section = rapport.get("detail_ventes", {})
    if section:
        writer.append_title(str(_("Sales detail")))
        writer.append_header([
            str(_("Category")), str(_("Product")),
            str(_("Sold")), str(_("Free")), str(_("Total qty")),
            str(_("HT")), str(_("VAT")), str(_("TTC")),
            str(_("Cost")), str(_("Profit")),
        ])
        for cat_nom, cat_data in section.items():
            for article in cat_data.get("articles", []):
                writer.append_row([
                    cat_nom, article.get("nom", "—"),
                    article.get("qty_vendus", 0), article.get("qty_offerts", 0),
                    article.get("qty_total", 0),
                    e(article.get("total_ht", 0)), e(article.get("total_tva", 0)),
                    e(article.get("total_ttc", 0)),
                    e(article.get("cout_total", 0)), e(article.get("benefice", 0)),
                ])
            writer.append_row([f"Total {cat_nom}", "", "", "", "", "", "", e(cat_data.get("total_ttc", 0)), "", ""])
        writer.append_blank()

    # --- Section 3 : TVA ---
    section = rapport.get("tva", {})
    if section:
        writer.append_title(str(_("VAT breakdown")))
        writer.append_header([str(_("Rate")), str(_("HT")), str(_("VAT")), str(_("TTC"))])
        for taux, data in section.items():
            writer.append_row([taux, e(data.get("total_ht", 0)), e(data.get("total_tva", 0)), e(data.get("total_ttc", 0))])
        writer.append_blank()

    # --- Section 4 : Solde caisse ---
    section = rapport.get("solde_caisse", {})
    if section:
        writer.append_title(str(_("Cash register balance")))
        writer.append_row([str(_("Opening float")), e(section.get("fond_de_caisse", 0))])
        writer.append_row([str(_("Cash income")), e(section.get("entrees_especes", 0))])
        writer.append_row([str(_("Balance")), e(section.get("solde", 0))])
        writer.append_blank()

    # --- Section 5 : Recharges ---
    section = rapport.get("recharges", {})
    if section and section.get("detail"):
        writer.append_title(str(_("Cashless top-ups")))
        writer.append_header([str(_("Product")), str(_("Currency")), str(_("Payment method")), str(_("Amount")), str(_("Count"))])
        for cle, rec in section["detail"].items():
            writer.append_row([rec.get("nom_produit", "—"), rec.get("nom_monnaie", "—"), rec.get("moyen_paiement", "—"), e(rec.get("total", 0)), rec.get("nb", 0)])
        writer.append_row([str(_("Total")), "", "", e(section.get("total", 0)), ""])
        writer.append_blank()

    # --- Section 6 : Adhesions ---
    section = rapport.get("adhesions", {})
    if section and section.get("detail"):
        writer.append_title(str(_("Memberships")))
        writer.append_header([str(_("Product")), str(_("Price tier")), str(_("Payment method")), str(_("Count")), str(_("Amount"))])
        for cle, adh in section["detail"].items():
            writer.append_row([adh.get("nom_produit", "—"), adh.get("nom_tarif", "—"), adh.get("moyen_paiement", "—"), adh.get("nb", 0), e(adh.get("total", 0))])
        writer.append_row([str(_("Total")), "", "", section.get("nb", 0), e(section.get("total", 0))])
        writer.append_blank()

    # --- Section 7 : Remboursements ---
    section = rapport.get("remboursements", {})
    if section:
        writer.append_title(str(_("Refunds")))
        writer.append_row([str(_("Count")), section.get("nb", 0)])
        writer.append_row([str(_("Total")), e(section.get("total", 0))])
        writer.append_blank()

    # --- Section 8 : Habitus ---
    section = rapport.get("habitus", {})
    if section:
        writer.append_title(str(_("Customer statistics")))
        writer.append_row([str(_("Cards used")), section.get("nb_cartes", 0)])
        writer.append_row([str(_("Total spent")), e(section.get("total", 0))])
        writer.append_row([str(_("Average basket")), e(section.get("panier_moyen", 0))])
        writer.append_row([str(_("Median spend")), e(section.get("depense_mediane", 0))])
        writer.append_row([str(_("Median top-up")), e(section.get("recharge_mediane", 0))])
        writer.append_blank()

    # --- Section 9 : Billets ---
    section = rapport.get("billets", {})
    if section and section.get("detail"):
        writer.append_title(str(_("Tickets")))
        writer.append_header([str(_("Event")), str(_("Date")), str(_("Product / Price tier")), str(_("Count")), str(_("Amount"))])
        for cle, b in section["detail"].items():
            tarif_label = b.get("nom_produit", "")
            if b.get("nom_tarif"):
                tarif_label += f" / {b['nom_tarif']}"
            writer.append_row([b.get("nom_event", "—"), b.get("date_event", "—"), tarif_label, b.get("nb", 0), e(b.get("total", 0))])
        writer.append_row([str(_("Total")), "", "", section.get("nb", 0), e(section.get("total", 0))])
        writer.append_blank()

    # --- Section 10 : Synthese ---
    section = rapport.get("synthese_operations", {})
    if section:
        writer.append_title(str(_("Operations summary")))
        writer.append_header([str(_("Operation")), str(_("Cash")), str(_("Credit card")), str(_("Cashless")), str(_("Total"))])
        for op_nom, op_data in section.items():
            writer.append_row([op_nom.title(), e(op_data.get("especes", 0)), e(op_data.get("carte_bancaire", 0)), e(op_data.get("cashless", 0)), e(op_data.get("total", 0))])
        writer.append_blank()


@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """Admin lecture seule pour les clotures de caisse.
    Document comptable immuable — aucune modification possible.
    Read-only admin for cash register closures.
    Immutable accounting document — no modification allowed.
    LOCALISATION : Administration/admin/laboutik.py"""

    def _recalculer_rapport(self, cloture):
        """
        Recalcule le rapport a la volee depuis les LigneArticle.
        Garantit que les modifications de reports.py sont visibles
        sans avoir a regenerer les clotures existantes.
        / Recalculates the report on-the-fly from LigneArticle.
        Ensures reports.py changes are visible
        without regenerating existing closures.
        """
        from laboutik.reports import RapportComptableService
        service = RapportComptableService(
            point_de_vente=cloture.point_de_vente,
            datetime_debut=cloture.datetime_ouverture,
            datetime_fin=cloture.datetime_cloture,
        )
        return service.generer_rapport_complet()

    list_display = (
        'datetime_cloture',
        'niveau', 'numero_sequentiel',
        'responsable',
        'ca_ttc_euros',
    )
    list_display_links = ('datetime_cloture',)
    list_filter = ['niveau']
    search_fields = ['point_de_vente__name', 'responsable__email']
    ordering = ('-datetime_cloture',)
    # Pas de fieldsets — tout le contenu est dans le change_form_before_template.
    # Le rapport comptable remplace le formulaire standard.
    # / No fieldsets — all content is in the change_form_before_template.
    # The accounting report replaces the standard form.
    fieldsets = ()
    readonly_fields = ()
    change_form_before_template = "admin/cloture/rapport_before.html"

    @admin.display(description=_("Revenue incl. tax"))
    def ca_ttc_euros(self, obj):
        """Affiche le total general en euros. / Displays grand total in euros."""
        from django.utils.html import format_html
        euros = obj.total_general / 100
        euros_formate = f"{euros:,.2f} €".replace(",", " ")
        return format_html('<span style="font-variant-numeric: tabular-nums;">{}</span>', euros_formate)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Injecte le rapport recalcule dans le contexte du template before.
        Le template before affiche le rapport complet + boutons export.
        / Injects the recalculated report into the before template context.
        The before template displays the full report + export buttons.
        LOCALISATION : Administration/admin/laboutik.py
        """
        extra_context = extra_context or {}
        if object_id:
            cloture = get_object_or_404(ClotureCaisse, pk=object_id)
            extra_context["rapport"] = self._recalculer_rapport(cloture)
            extra_context["cloture_obj"] = cloture
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        """
        URLs custom pour les exports (CSV, PDF, Excel).
        Le rapport est affiche via changeform_view (pas d'URL custom).
        / Custom URLs for exports (CSV, PDF, Excel).
        The report is displayed via changeform_view (no custom URL).
        """
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/exporter-csv/',
                self.admin_site.admin_view(self.exporter_csv),
                name='laboutik_cloturecaisse_exporter_csv',
            ),
            path(
                '<path:object_id>/exporter-pdf/',
                self.admin_site.admin_view(self.exporter_pdf),
                name='laboutik_cloturecaisse_exporter_pdf',
            ),
            path(
                '<path:object_id>/exporter-excel/',
                self.admin_site.admin_view(self.exporter_excel),
                name='laboutik_cloturecaisse_exporter_excel',
            ),
        ]
        return custom_urls + urls

    def exporter_csv(self, request, object_id):
        """
        Exporte le rapport de cloture en CSV structure (delimiteur ;).
        Meme structure que le HTML, pas de JSON brut.
        / Exports the closure report as structured CSV (delimiter ;).
        Same structure as HTML, no raw JSON.
        LOCALISATION : Administration/admin/laboutik.py
        """
        import csv
        from django.http import HttpResponse

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = self._recalculer_rapport(cloture)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')

        csv_writer = csv.writer(response, delimiter=';')

        # Adaptateur CSV pour le writer generique
        # / CSV adapter for the generic writer
        class CsvWriterAdapter:
            def append_title(self, titre):
                csv_writer.writerow([])
                csv_writer.writerow([titre.upper()])
            def append_header(self, cols):
                csv_writer.writerow(cols)
            def append_row(self, cols):
                csv_writer.writerow(cols)
            def append_blank(self):
                csv_writer.writerow([])

        _ecrire_rapport_csv_excel(CsvWriterAdapter(), cloture, rapport)
        return response

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
        rapport = self._recalculer_rapport(cloture)
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

    def exporter_excel(self, request, object_id):
        """
        Exporte le rapport de cloture en Excel (1 seul onglet, mise en forme soignee).
        Meme structure que le HTML, pas de JSON brut.
        / Exports the closure report as Excel (single sheet, clean formatting).
        Same structure as HTML, no raw JSON.
        LOCALISATION : Administration/admin/laboutik.py
        """
        import openpyxl
        from django.http import HttpResponse
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = self._recalculer_rapport(cloture)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rapport"

        # Styles
        titre_font = Font(bold=True, size=14)
        section_font = Font(bold=True, size=11, color="FFFFFF")
        section_fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
        header_font = Font(bold=True, size=10)
        header_fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        total_font = Font(bold=True, size=10)
        total_fill = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='DDDDDD'),
            right=Side(style='thin', color='DDDDDD'),
            top=Side(style='thin', color='DDDDDD'),
            bottom=Side(style='thin', color='DDDDDD'),
        )

        # Adaptateur Excel pour le writer generique
        # / Excel adapter for the generic writer
        current_row = [1]
        max_cols_used = [1]

        class ExcelWriterAdapter:
            def append_title(self, titre):
                row = current_row[0]
                cell = ws.cell(row=row, column=1, value=titre)
                cell.font = section_font
                cell.fill = section_fill
                # Etendre le fond sur 10 colonnes pour l'effet visuel
                # / Extend background across 10 columns for visual effect
                for col in range(2, 11):
                    c = ws.cell(row=row, column=col)
                    c.fill = section_fill
                current_row[0] += 1

            def append_header(self, cols):
                row = current_row[0]
                for idx, col_val in enumerate(cols, 1):
                    cell = ws.cell(row=row, column=idx, value=col_val)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.border = thin_border
                max_cols_used[0] = max(max_cols_used[0], len(cols))
                current_row[0] += 1

            def append_row(self, cols):
                row = current_row[0]
                for idx, col_val in enumerate(cols, 1):
                    cell = ws.cell(row=row, column=idx, value=col_val)
                    cell.border = thin_border
                    # Aligner les nombres a droite
                    # / Right-align numbers
                    if isinstance(col_val, (int, float)):
                        cell.alignment = Alignment(horizontal='right')
                        cell.number_format = '#,##0.00'
                max_cols_used[0] = max(max_cols_used[0], len(cols))
                current_row[0] += 1

            def append_blank(self):
                current_row[0] += 1

        _ecrire_rapport_csv_excel(ExcelWriterAdapter(), cloture, rapport)

        # Auto-largeur des colonnes / Auto-width columns
        for col_idx in range(1, max_cols_used[0] + 1):
            max_length = 0
            for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
                for cell in row:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_length + 3, 40)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

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

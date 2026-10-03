"""
Admin Unfold pour l'app comptabilite : la liste des clôtures, la fiche d'une clôture
(son rapport stocké), le rapport temps réel et les exports.
/ Unfold admin for the comptabilite app: closures list, closure page (its stored
report), real-time report and exports.

LOCALISATION : comptabilite/admin.py

FLUX :
- fiche d'une clôture : `changeform_view` → `sections_pour_affichage(rapport_json)`
  (comptabilite/presentation.py) → gabarit `comptabilite/admin/change_form_before.html`
  → `_sections_rapport.html` ;
- rapport temps réel : `rapport_temps_reel` → `RapportDesVentes(debut, fin).rapport_x()`
  (comptabilite/rapport.py) → `sections_pour_affichage` → gabarit
  `comptabilite/views/rapport_temps_reel.html` → `_sections_rapport.html`.
/ Flow: closure page and real-time report both go through sections_pour_affichage.
"""
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from comptabilite.fec import generer_fec_cloture
from comptabilite.models import ClotureCaisse
from comptabilite.presentation import euros_a_la_francaise, sections_pour_affichage
from comptabilite.rapport import RapportDesVentes
from comptabilite.ventilation import EcritureDesequilibree
from laboutik.plan_comptable import CompteComptableManquant


# Helpers d'affichage definis AU NIVEAU MODULE (pas methodes de classe).
# Unfold wrappe les methodes d'un ModelAdmin avec son systeme @action, ce qui
# peut causer des bugs sur des helpers internes. (cf. tests/PIEGES.md)
# / Display helpers defined AT MODULE LEVEL (not class methods). Unfold wraps
# ModelAdmin methods via @action which can break internal helpers.


def _parse_datetime_param(value, defaut, fuseau_du_lieu):
    """
    Parse une string ISO (depuis un GET param ou <input type="datetime-local">)
    en datetime aware. Si invalide ou vide, retourne defaut.
    / Parse an ISO string into an aware datetime. Falls back to defaut if invalid.

    Format attendu : 'YYYY-MM-DDTHH:MM' (input HTML5 datetime-local, sans tz).
    Une heure saisie sans fuseau est une heure du LIEU (`fuseau_du_lieu`), jamais
    celle du serveur.
    / A typed hour without time zone is the venue's hour, never the server's.
    """
    if not value:
        return defaut
    try:
        from datetime import datetime
        from django.utils import timezone
        dt = datetime.fromisoformat(value)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, fuseau_du_lieu)
        return dt
    except (ValueError, TypeError):
        return defaut


def _telecharger(bytes_data, filename, content_type):
    """
    Construit une HttpResponse de telechargement (Content-Disposition: attachment).
    / Build an HttpResponse for download (attachment).
    """
    from django.http import HttpResponse
    response = HttpResponse(bytes_data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """
    Admin read-only pour les clotures comptables.
    / Read-only admin for accounting closures.
    """

    # Conventions projet Unfold (non negociables, cf. skill unfold §22).
    # / Project Unfold conventions (mandatory).
    compressed_fields = True
    warn_unsaved_form = True

    list_display = (
        "datetime_fin",
        "niveau",
        "numero_sequentiel",
        "responsable",
        "ca_ttc",
        "nombre_transactions",
    )
    list_filter = ("niveau",)
    search_fields = ("responsable__email",)
    ordering = ("-datetime_fin",)

    # Aucun fieldset : l'edition est interdite. La fiche detail affiche le rapport
    # via change_form_before_template (rendu AVANT les fieldsets, qui sont caches en CSS).
    # / No fieldset: editing forbidden. Detail view shows the report via
    # change_form_before_template (rendered BEFORE fieldsets, hidden via CSS).
    fieldsets = ()
    change_form_before_template = "comptabilite/admin/change_form_before.html"
    list_before_template = "comptabilite/admin/changelist_before.html"

    def get_urls(self):
        """
        Ajoute la route /rapport-temps-reel/ AVANT les routes standard de l'admin.
        L'ordre est important : sinon Django interpreterait 'rapport-temps-reel' comme un UUID.
        / Add /rapport-temps-reel/ BEFORE standard admin routes (order matters).
        """
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "rapport-temps-reel/",
                self.admin_site.admin_view(self.rapport_temps_reel),
                name="comptabilite_cloturecaisse_temps_reel",
            ),
            path(
                "<uuid:object_id>/exporter-csv/",
                self.admin_site.admin_view(self.exporter_csv),
                name="comptabilite_cloturecaisse_csv",
            ),
            path(
                "<uuid:object_id>/exporter-excel/",
                self.admin_site.admin_view(self.exporter_excel),
                name="comptabilite_cloturecaisse_excel",
            ),
            path(
                "<uuid:object_id>/exporter-pdf/",
                self.admin_site.admin_view(self.exporter_pdf),
                name="comptabilite_cloturecaisse_pdf",
            ),
            path(
                "<uuid:object_id>/exporter-fec/",
                self.admin_site.admin_view(self.exporter_fec),
                name="comptabilite_cloturecaisse_fec",
            ),
        ]
        return custom + urls

    def exporter_csv(self, request, object_id):
        """
        Telecharge la cloture au format CSV (sections + totaux).
        / Download the cloture as CSV (sections + totals).
        """
        from django.shortcuts import get_object_or_404
        from comptabilite.csv_export import generer_csv_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_csv_cloture(cloture))

    def exporter_excel(self, request, object_id):
        """
        Telecharge la cloture au format Excel (.xlsx).
        / Download the cloture as Excel (.xlsx).
        """
        from django.shortcuts import get_object_or_404
        from comptabilite.excel_export import generer_excel_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_excel_cloture(cloture))

    def exporter_pdf(self, request, object_id):
        """
        Telecharge la cloture au format PDF A4 (WeasyPrint).
        / Download the cloture as PDF A4 (WeasyPrint).
        """
        from django.shortcuts import get_object_or_404
        from comptabilite.pdf import generer_pdf_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_pdf_cloture(cloture))

    def exporter_fec(self, request, object_id):
        """
        Telecharge la cloture au format FEC (Fichier des Ecritures Comptables,
        norme francaise A47 A-1). Encodage UTF-8 sans BOM, tabulation, 18 colonnes.
        / Download the cloture as FEC (French legal accounting format).

        Refus (compte manquant, écriture déséquilibrée) : rien n'est téléchargé ; un
        message d'erreur s'affiche sur la fiche de la clôture. Un compte manquant
        renvoie à l'écran « Plan complet ? ».
        / Refusal (missing account, unbalanced entry): nothing is downloaded; an error
        message is shown on the closure page.
        """
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        adresse_de_la_fiche = reverse(
            "staff_admin:comptabilite_cloturecaisse_change", args=[cloture.pk]
        )
        try:
            contenu, nom_du_fichier, type_du_contenu = generer_fec_cloture(cloture)
        except CompteComptableManquant as compte_manquant:
            messages.error(
                request,
                _(
                    "Export FEC refusé : %(raison)s Voir « Plan complet ? » en tête "
                    "du plan comptable."
                )
                % {"raison": str(compte_manquant)},
            )
            return redirect(adresse_de_la_fiche)
        except EcritureDesequilibree as ecriture_desequilibree:
            messages.error(
                request,
                _("Export FEC refusé : %(raison)s")
                % {"raison": str(ecriture_desequilibree)},
            )
            return redirect(adresse_de_la_fiche)
        return _telecharger(contenu, nom_du_fichier, type_du_contenu)

    def rapport_temps_reel(self, request):
        """
        Vue admin custom : le rapport X (temps réel, jamais stocké) sur une période
        choisie. Les sections du Z sans l'intégrité, plus l'habitus des cartes et les
        opérateurs (`RapportDesVentes.rapport_x()`).
        / Custom admin view: the X report (never stored) over a chosen period.

        Bornes par defaut : le service en cours, de la fin de la derniere cloture
        journaliere (J) a maintenant ; sans J, de la premiere vente reglee du lieu ; sans
        vente, maintenant -> maintenant (rapport vide).
        L'utilisateur peut surcharger via les GET params datetime_debut /
        datetime_fin (format ISO 'YYYY-MM-DDTHH:MM', input HTML5 datetime-local).
        Les heures saisies et affichees sont en HEURE DU LIEU
        (`Configuration.get_tzinfo()`), jamais celle du serveur.
        Pas de polling : F5 manuel suffit.
        / Default bounds: the current service, from the end of the last J to now. Hours
        are typed and shown in the venue's time zone.
        """
        from django.db.models import Min
        from django.shortcuts import render
        from django.utils import timezone

        from BaseBillet.models import Configuration
        from BaseBillet.models_vente import Vente

        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()

        # --- Bornes par defaut : depuis la fin de la derniere J, jusqu'a maintenant
        # / Default bounds: from the end of the last J to now
        fin_defaut = timezone.now()
        derniere_j = (
            ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
            .order_by("-numero_sequentiel")
            .first()
        )
        if derniere_j is not None:
            debut_defaut = derniere_j.datetime_fin
        else:
            premiere_heure_d_encaissement = Vente.objects.filter(
                statut=Vente.Statut.REGLEE
            ).aggregate(premiere_heure=Min("datetime_encaissement"))["premiere_heure"]
            if premiere_heure_d_encaissement is not None:
                debut_defaut = premiere_heure_d_encaissement
            else:
                debut_defaut = fin_defaut

        # --- Override depuis GET params si presents (heures du lieu)
        # / Override via GET params if present (venue hours)
        datetime_debut = _parse_datetime_param(
            request.GET.get("datetime_debut"), defaut=debut_defaut,
            fuseau_du_lieu=fuseau_du_lieu,
        )
        datetime_fin = _parse_datetime_param(
            request.GET.get("datetime_fin"), defaut=fin_defaut,
            fuseau_du_lieu=fuseau_du_lieu,
        )

        # Garde-fou : si debut > fin, on inverse (typo utilisateur)
        # / Safety: swap if start > end (user typo)
        if datetime_debut > datetime_fin:
            datetime_debut, datetime_fin = datetime_fin, datetime_debut

        # Le rapport X du moteur unique : la borne de fin est exclue.
        # / The single engine's X report: the end bound is excluded.
        rapport_x = RapportDesVentes(datetime_debut, datetime_fin).rapport_x()

        context = {
            **self.admin_site.each_context(request),
            "title": _("Rapport temps réel"),
            "rapport": rapport_x,
            "sections": sections_pour_affichage(rapport_x),
            "datetime_debut": datetime_debut,
            "datetime_fin": datetime_fin,
            # Format pour input HTML5 datetime-local : 'YYYY-MM-DDTHH:MM', heure du lieu
            # / Format for HTML5 datetime-local input, venue time
            "datetime_debut_input": timezone.localtime(
                datetime_debut, fuseau_du_lieu
            ).strftime("%Y-%m-%dT%H:%M"),
            "datetime_fin_input": timezone.localtime(
                datetime_fin, fuseau_du_lieu
            ).strftime("%Y-%m-%dT%H:%M"),
            # La periode affichee, en heure du lieu
            # / The shown period, venue time
            "datetime_debut_affiche": timezone.localtime(
                datetime_debut, fuseau_du_lieu
            ).strftime("%d/%m/%Y %H:%M"),
            "datetime_fin_affiche": timezone.localtime(
                datetime_fin, fuseau_du_lieu
            ).strftime("%d/%m/%Y %H:%M"),
            "nombre_de_ventes": rapport_x["en_tete"]["nombre_de_ventes"],
            "opts": self.model._meta,
        }
        return render(request, "comptabilite/views/rapport_temps_reel.html", context)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """
        Injecte la clôture et les sections de son rapport stocké dans le contexte du
        gabarit. Le rapport n'est jamais recalculé : c'est celui scellé à la clôture.
        / Injects the closure and its stored report's sections into the template.
        """
        extra_context = extra_context or {}
        if object_id:
            from django.shortcuts import get_object_or_404
            cloture = get_object_or_404(ClotureCaisse, pk=object_id)
            extra_context["cloture"] = cloture
            extra_context["sections"] = sections_pour_affichage(cloture.rapport_json)
        return super().changeform_view(request, object_id, form_url, extra_context)

    # --- Permissions : modele immuable ---
    # / Permissions: immutable model

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        # Creation uniquement via Celery ou management command.
        # / Creation only via Celery or management command.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # --- Colonnes d'affichage ---
    # / Display columns

    @admin.display(description=_("Chiffre d'affaires TTC"), ordering="total_general")
    def ca_ttc(self, obj):
        return euros_a_la_francaise(obj.total_general)

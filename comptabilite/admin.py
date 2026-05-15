"""
Admin Unfold pour l'app comptabilite.
/ Unfold admin for the comptabilite app.

LOCALISATION : comptabilite/admin.py

S1 : admin liste minimaliste, read-only. ClotureCaisseAdmin sera enrichi en S3
avec change_form_before_template (rapport visuel) et en S4 avec les exports.

/ S1: minimal read-only list admin. ClotureCaisseAdmin will be enriched in S3
with change_form_before_template (visual report) and in S4 with exports.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from comptabilite.models import ClotureCaisse


# Helpers d'affichage definis AU NIVEAU MODULE (pas methodes de classe).
# Unfold wrappe les methodes d'un ModelAdmin avec son systeme @action, ce qui
# peut causer des bugs sur des helpers internes. (cf. tests/PIEGES.md)
# / Display helpers defined AT MODULE LEVEL (not class methods). Unfold wraps
# ModelAdmin methods via @action which can break internal helpers.

def _format_euros(centimes: int) -> str:
    """
    Formate un montant en centimes en chaine euros lisible.
    / Format a cents amount as a readable euros string.
    """
    if centimes is None:
        return "—"
    return f"{centimes / 100:.2f} €"


# Mapping des 12 PaymentMethod V1 vers 4 categories d'affichage + "Autres".
# Le rapport_json stocke en base reste fin (12 valeurs) ; on agrege uniquement
# pour l'affichage. Pour ajouter/modifier une categorie, editer ce mapping.
# / Mapping of 12 V1 PaymentMethod codes to 4 display categories + "Other".
# The stored rapport_json keeps the 12 raw values intact ; aggregation happens
# only at render time.
CATEGORIES_PAIEMENT_AFFICHAGE = [
    ("especes", _("Cash"), ["CA"]),
    ("cb", _("Credit card (POS terminal)"), ["CC"]),
    ("en_ligne", _("Online payments"), ["SF", "SN", "SP", "SR", "TR"]),
    ("cashless", _("Cashless (NFC / local currency)"), ["LE", "LG", "QR"]),
    ("autres", _("Other"), ["CH", "NA", "UK"]),
]


def _agreger_paiements_par_categorie(totaux_par_moyen: dict) -> list:
    """
    Agrege les totaux_par_moyen (12 codes PaymentMethod) en 4 categories
    d'affichage + "Autres". Retourne une liste de dict pretes a afficher.
    / Aggregate 12 PaymentMethod codes into 4 display categories + "Other".

    Une categorie est INCLUSE dans le retour uniquement si elle a au moins
    une transaction (total != 0 ou nb > 0). La categorie "Autres" suit la
    meme regle (cachee si vide).
    """
    if not totaux_par_moyen:
        return []
    categories = []
    for slug, label, codes in CATEGORIES_PAIEMENT_AFFICHAGE:
        total = 0
        nb = 0
        for code in codes:
            item = totaux_par_moyen.get(code)
            if isinstance(item, dict):
                total += item.get("total", 0)
                nb += item.get("nb", 0)
        if total == 0 and nb == 0:
            # On masque les categories vides pour ne pas alourdir l'affichage
            # / Skip empty categories to keep the display compact
            continue
        categories.append({
            "slug": slug,
            "label": str(label),
            "total": total,
            "total_euros": f"{total / 100:.2f}",
            "nb": nb,
        })
    return categories


def _enrichir_rapport_pour_template(rapport: dict) -> dict:
    """
    Ajoute des cles formatees (_euros suffixe) au rapport pour eviter
    les filtres custom dans le template. Modifie une copie, pas l'original.
    / Adds _euros-suffixed keys to the report dict to avoid custom template filters.
    """
    import copy
    if not rapport:
        return {}
    r = copy.deepcopy(rapport)

    # totaux_par_moyen : ajoute total_euros pour total + agrege en 4 categories
    # / totaux_par_moyen: add total_euros + aggregate into 4 display categories
    if "totaux_par_moyen" in r and isinstance(r["totaux_par_moyen"], dict):
        for k, v in r["totaux_par_moyen"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"
        if "total" in r["totaux_par_moyen"]:
            r["totaux_par_moyen"]["total_euros"] = f"{r['totaux_par_moyen']['total'] / 100:.2f}"
        # Cle additionnelle : 4 categories agregees pour l'affichage
        # / Extra key: 4 aggregated categories for display
        r["totaux_par_moyen"]["categories"] = _agreger_paiements_par_categorie(
            r["totaux_par_moyen"]
        )

    # tva : ttc/ht/tva en euros
    if "tva" in r and isinstance(r["tva"], dict):
        for taux, v in r["tva"].items():
            if isinstance(v, dict):
                v["total_ttc_euros"] = f"{v.get('total_ttc', 0) / 100:.2f}"
                v["total_ht_euros"] = f"{v.get('total_ht', 0) / 100:.2f}"
                v["total_tva_euros"] = f"{v.get('total_tva', 0) / 100:.2f}"

    # adhesions / billets : total + detail
    for section_key in ("adhesions", "billets"):
        if section_key in r and isinstance(r[section_key], dict):
            section = r[section_key]
            if "total" in section:
                section["total_euros"] = f"{section['total'] / 100:.2f}"
            for v in section.get("detail", {}).values():
                if "total" in v:
                    v["total_euros"] = f"{v['total'] / 100:.2f}"

    # remboursements : credit_notes + refunded
    if "remboursements" in r and isinstance(r["remboursements"], dict):
        for k, v in r["remboursements"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"

    # synthese_operations : valeurs en euros (transforme int en dict {total, total_euros})
    if "synthese_operations" in r:
        for section, moyens in r["synthese_operations"].items():
            if isinstance(moyens, dict):
                r["synthese_operations"][section] = {
                    code: {"total": val, "total_euros": f"{val / 100:.2f}"}
                    for code, val in moyens.items()
                }

    return r


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
        ]
        return custom + urls

    def rapport_temps_reel(self, request):
        """
        Vue admin custom : agrege en temps reel les LigneArticle depuis la
        derniere cloture journaliere jusqu'a maintenant.
        / Custom admin view: real-time aggregation since last daily closure.
        """
        from django.shortcuts import render
        from django.utils import timezone
        from comptabilite.services import RapportComptableService

        derniere = (
            ClotureCaisse.objects
            .filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
            .order_by("-datetime_fin")
            .first()
        )
        if derniere:
            datetime_debut = derniere.datetime_fin
        else:
            # Pas de cloture J : on prend depuis ce matin minuit local
            # / No daily closure yet: take from local midnight today
            now_local = timezone.localtime()
            datetime_debut = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        datetime_fin = timezone.now()

        service = RapportComptableService(datetime_debut, datetime_fin)
        rapport_brut = service.generer_rapport_complet()
        rapport = _enrichir_rapport_pour_template(rapport_brut)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Real-time report"),
            "rapport": rapport,
            "datetime_debut": datetime_debut,
            "datetime_fin": datetime_fin,
            "nb_transactions": service.queryset.count(),
            "opts": self.model._meta,
        }
        return render(request, "comptabilite/views/rapport_temps_reel.html", context)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """
        Injecte la cloture + son rapport pre-formate dans le context du template.
        / Inject the cloture + its pre-formatted report into the template context.
        """
        extra_context = extra_context or {}
        if object_id:
            from django.shortcuts import get_object_or_404
            cloture = get_object_or_404(ClotureCaisse, pk=object_id)
            rapport_pretty = _enrichir_rapport_pour_template(cloture.rapport_json or {})
            extra_context["cloture"] = cloture
            extra_context["rapport"] = rapport_pretty
            extra_context["datetime_debut"] = cloture.datetime_debut
            extra_context["datetime_fin"] = cloture.datetime_fin
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

    @admin.display(description=_("Total TTC"), ordering="total_general")
    def ca_ttc(self, obj):
        return _format_euros(obj.total_general)

"""
Administration du planning des bénévoles (app booking).
/ Admin for the volunteer planning (booking app).

LOCALISATION : Administration/admin/benevolat.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.6)

Ce module est importé par Administration/admin_tenant.py pour son effet de bord :
ses décorateurs @admin.register enregistrent les admins sur staff_admin_site.
/ Imported by admin_tenant.py for its side effect: @admin.register runs on import.

- TacheBenevoleAdmin : le catalogue des tâches du lieu.
- PlanningBenevoleAdmin : la fiche du planning et ses besoins (en lignes).
- InscriptionBenevoleAdmin : la liste des inscriptions, en lecture seule, avec suppression.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import RelatedDropdownFilter

# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tiré de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin
from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from booking.models import (
    BesoinBenevole,
    InscriptionBenevole,
    PlanningBenevole,
    TacheBenevole,
)


def nom_complet_et_email(user):
    """
    « Prénom Nom · email » pour l'équipe du lieu. Les parties vides sont sautées.
    / "First Last · email" for the venue team. Empty parts are skipped.

    LOCALISATION : Administration/admin/benevolat.py
    """
    morceaux_du_nom = []
    if user.first_name:
        morceaux_du_nom.append(user.first_name)
    if user.last_name:
        morceaux_du_nom.append(user.last_name)

    if not morceaux_du_nom:
        return user.email
    return f"{' '.join(morceaux_du_nom)} · {user.email}"


@admin.register(TacheBenevole, site=staff_admin_site)
class TacheBenevoleAdmin(ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class BesoinBenevoleInline(TabularInline):
    """
    Les besoins d'un planning, saisis en lignes sur sa fiche.
    / The needs of a planning, entered as rows on its page.

    LOCALISATION : Administration/admin/benevolat.py

    Un besoin saisi un jour fermé est enregistré quand même : un lieu fermé au public
    peut avoir besoin de bénévoles ce jour-là (inventaire, ménage de fond).
    La colonne « Fermeture » le signale, sans bloquer.
    / A need on a closed day is saved anyway; the "Closure" column only warns.
    """
    model = BesoinBenevole
    extra = 0
    fields = ["date", "tache", "heure_debut", "heure_fin", "nombre_souhaite", "inscrits", "fermeture"]
    readonly_fields = ["inscrits", "fermeture"]

    @admin.display(description=_("Inscrit·es"))
    def inscrits(self, besoin):
        # Une ligne vide du formulaire n'a pas encore de besoin en base.
        # / An empty form row has no saved need yet.
        if besoin._state.adding:
            return "—"

        noms_des_inscrits = []
        for inscription in besoin.inscriptions.select_related("user"):
            noms_des_inscrits.append(nom_complet_et_email(inscription.user))

        compteur = f"{len(noms_des_inscrits)}/{besoin.nombre_souhaite}"
        if not noms_des_inscrits:
            return compteur
        return f"{compteur} : {', '.join(noms_des_inscrits)}"

    @admin.display(description=_("Fermeture"))
    def fermeture(self, besoin):
        if besoin._state.adding:
            return "—"

        libelle_de_fermeture = besoin.planning.libelle_de_fermeture(besoin.date)
        if libelle_de_fermeture is None:
            return "—"
        return _("Fermé : %(libelle)s") % {"libelle": libelle_de_fermeture}

    # Un inline a ses propres permissions : sans ces méthodes, Django demande
    # booking.view_besoinbenevole…, que l'admin d'un lieu n'a pas, et la fiche du
    # planning s'affiche sans ses besoins.
    # / An inline has its own permissions: without these, a venue admin sees the
    # planning page without its needs.
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(PlanningBenevole, site=staff_admin_site)
class PlanningBenevoleAdmin(ModelAdmin):
    list_display = ["name", "slug", "published", "calendrier"]
    search_fields = ["name", "slug"]
    fields = [
        "name",
        "slug",
        "description",
        "published",
        "adhesions_requises",
        "calendrier",
        "delai_desinscription_heures",
    ]
    prepopulated_fields = {"slug": ("name",)}

    # L'autocomplétion des adhésions est servie par ProductAdmin. Django y applique le
    # limit_choices_to du champ (adhésions seulement) ; ProductAdmin.get_search_results
    # retire les produits archivés.
    # / Served by ProductAdmin, which applies the field's limit_choices_to.
    autocomplete_fields = ["adhesions_requises"]

    inlines = [BesoinBenevoleInline]

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(InscriptionBenevole, site=staff_admin_site)
class InscriptionBenevoleAdmin(ModelAdmin):
    """
    La liste des inscriptions : consulter, chercher, supprimer.
    / The sign-ups list: view, search, delete.

    LOCALISATION : Administration/admin/benevolat.py

    PAS D'AJOUT ICI. On inscrit quelqu'un depuis la page du planning, qui a une
    recherche par nom limitée aux personnes du lieu (spec §5.10). Un champ « user »
    éditable serait une liste de TOUS les comptes de l'instance (AuthBillet est en
    SHARED_APPS) : page lente, et emails des autres lieux visibles. Et
    autocomplete_fields = ["user"] lève admin.E039 : TibilletUser n'a pas d'admin
    sur staff_admin_site.
    / No add form here: a user select would list every account of the instance,
    and autocomplete on "user" raises admin.E039.
    """
    ordering = ["-besoin__date", "besoin__heure_debut"]
    list_display = ["benevole", "besoin", "planning", "created_at", "inscrit_par"]
    list_filter = [
        ("besoin__planning", RelatedDropdownFilter),
        "besoin__date",
    ]
    search_fields = ["user__first_name", "user__last_name", "user__email"]
    list_select_related = ["user", "besoin__tache", "besoin__planning", "inscrit_par"]

    # Tout est en lecture seule : une inscription n'a rien de modifiable.
    # / Everything is read-only: a sign-up has nothing to edit.
    readonly_fields = ["benevole", "besoin", "created_at", "rappel_envoye_le", "inscrit_par"]
    fields = ["benevole", "besoin", "created_at", "rappel_envoye_le", "inscrit_par"]

    @admin.display(description=_("Bénévole"), ordering="user__last_name")
    def benevole(self, inscription):
        return nom_complet_et_email(inscription.user)

    @admin.display(description=_("Planning"), ordering="besoin__planning__name")
    def planning(self, inscription):
        return inscription.besoin.planning

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

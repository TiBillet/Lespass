"""
Administration du planning des bénévoles (app booking).
/ Admin for the volunteer planning (booking app).

LOCALISATION : Administration/admin/benevolat.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.6)

Ce module est importé par Administration/admin_tenant.py pour son effet de bord :
ses décorateurs @admin.register enregistrent les admins sur staff_admin_site.
/ Imported by admin_tenant.py for its side effect: @admin.register runs on import.

- TacheBenevoleAdmin : le catalogue des tâches du lieu.
- PlanningBenevoleAdmin : la fiche du planning avec, selon son type, ses besoins à venir
  (ponctuel) ou sa semaine type (hebdomadaire, §11.2), et l'action « Répéter des besoins »
  (spec §5.7, plannings ponctuels seulement).
- BesoinBenevoleAdmin : la page « Besoins », tous les besoins de tous les plannings,
  « À venir » par défaut (§11.2).
- InscriptionBenevoleAdmin : la liste des inscriptions, en lecture seule, avec suppression.
"""
import datetime
import uuid

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import RelatedDropdownFilter
from unfold.decorators import action

# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tiré de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin
from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import Configuration
from booking.models import (
    BesoinBenevole,
    InscriptionBenevole,
    LigneDeSemaineType,
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


def prenom_ou_debut_de_l_email(user):
    """
    Le prénom, court, pour la colonne « Inscrit·es » de la fiche du planning. Sans prénom :
    les 6 premiers caractères de l'email (assez pour reconnaître la personne).
    / The first name for the sign-ups column; without one, the email's first 6 characters.

    LOCALISATION : Administration/admin/benevolat.py
    """
    if user.first_name and user.first_name.strip():
        return user.first_name.strip()
    return user.email[:6]


# TacheBenevoleAdmin reste enregistré même sans entrée de menu : c'est lui qui sert la
# fenêtre « ajouter une tâche » du bouton à côté du champ « Tâche » des inlines.
# / Kept registered without a menu entry: it serves the inlines' "add a task" popup.
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
    peut avoir besoin de bénévoles ce jour-là (inventaire, ménage de fond). La colonne
    « Fermeture » de la page « Besoins » le signale.
    / A need on a closed day is saved anyway; the "Needs" page shows the closure.

    Une nouvelle tâche se crée sans quitter la fiche : bouton à côté du champ « Tâche »
    (fenêtre d'ajout de TacheBenevoleAdmin, qui reste enregistré pour ça).
    / A new task is created from the button next to the "Tâche" field.

    Seulement les besoins À VENIR (d'aujourd'hui, au fuseau du lieu) : le passé reste
    en base (D33) et se consulte sur la page « Besoins ».
    / Upcoming needs only: the past stays in the database, on the "Needs" page.
    """
    model = BesoinBenevole
    extra = 0
    fields = ["date", "tache", "heure_debut", "heure_fin", "nombre_souhaite", "inscrits"]
    readonly_fields = ["inscrits"]

    def get_queryset(self, request):
        # Précharge ce que lit la colonne « Inscrit·es » : sans ça, chaque ligne fait
        # plusieurs requêtes, et « Répéter » crée des centaines de lignes.
        # « tache » : lue par BesoinBenevole.__str__, le titre de chaque ligne.
        # / Prefetch what the sign-ups column reads: no per-row queries.
        from booking.benevolat import aujourd_hui_au_lieu

        return super().get_queryset(request).filter(
            date__gte=aujourd_hui_au_lieu(),
        ).select_related(
            "tache",
        ).prefetch_related(
            "inscriptions__user",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # La liste déroulante « Tâche » relit la table des tâches pour CHAQUE ligne de
        # l'inline. On lit les choix une fois par requête et on les réutilise.
        # La validation reste faite par le queryset du champ.
        # / The "Tâche" select re-queries for each inline row: read the choices once.
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "tache" and formfield is not None:
            if not hasattr(request, "_choix_des_taches_benevoles"):
                request._choix_des_taches_benevoles = list(formfield.choices)
            formfield.choices = request._choix_des_taches_benevoles
        return formfield

    @admin.display(description=_("Inscrit·es"))
    def inscrits(self, besoin):
        # Une ligne vide du formulaire n'a pas encore de besoin en base.
        # / An empty form row has no saved need yet.
        if besoin._state.adding:
            return "—"

        prenoms_des_inscrits = []
        for inscription in besoin.inscriptions.all():
            prenoms_des_inscrits.append(prenom_ou_debut_de_l_email(inscription.user))

        compteur = f"{len(prenoms_des_inscrits)}/{besoin.nombre_souhaite}"
        if not prenoms_des_inscrits:
            return compteur
        return f"{compteur} : {', '.join(prenoms_des_inscrits)}"

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


class LigneDeSemaineTypeInline(TabularInline):
    """
    La semaine type d'un planning hebdomadaire, saisie en lignes sur sa fiche (§11.2).
    / The template week of a weekly planning, entered as rows on its page.

    LOCALISATION : Administration/admin/benevolat.py

    Enregistrer la fiche répercute les lignes sur les besoins futurs sans inscrit
    (PlanningBenevoleAdmin.save_related → booking/benevolat.py,
    appliquer_la_semaine_type_modifiee).
    / Saving the page applies the rows to future needs without sign-up.
    """
    model = LigneDeSemaineType
    extra = 0
    fields = ["jour_de_la_semaine", "tache", "heure_debut", "heure_fin", "nombre_souhaite"]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # La colonne est étroite : sans largeur minimale, on lit « Ven… » au lieu de
        # « Vendredi ». Style en ligne : Unfold n'a pas les classes Tailwind sur mesure.
        # / Narrow column: a minimum width keeps the full day name readable.
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "jour_de_la_semaine" and formfield is not None:
            formfield.widget.attrs["style"] = "min-width: 9rem;"
        return formfield

    def get_queryset(self, request):
        # « tache » : lue par LigneDeSemaineType.__str__, le titre de chaque ligne.
        # / "tache" is read by __str__, each row's title.
        return super().get_queryset(request).select_related("tache")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Même parade que BesoinBenevoleInline : les choix « Tâche » lus une fois par requête.
        # / Same as BesoinBenevoleInline: the "Tâche" choices read once per request.
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "tache" and formfield is not None:
            if not hasattr(request, "_choix_des_taches_benevoles"):
                request._choix_des_taches_benevoles = list(formfield.choices)
            formfield.choices = request._choix_des_taches_benevoles
        return formfield

    # Mêmes raisons que BesoinBenevoleInline : un inline a ses propres permissions.
    # / Same reasons as BesoinBenevoleInline: an inline has its own permissions.
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


def adresse_des_besoins_du_planning(planning):
    """La page « Besoins » filtrée sur ce planning. / The "Needs" page filtered on this planning."""
    return f"{reverse('staff_admin:booking_besoinbenevole_changelist')}?planning__uuid__exact={planning.pk}"


def message_de_la_semaine_type(bilan, planning):
    """
    « N besoins créés, M mis à jour, P supprimés. K besoins avec des inscrits n'ont pas
    été modifiés : voir la page Besoins. » La seconde phrase seulement si K > 0.
    None s'il n'y a rien à dire.
    / The admin message after saving a template week, or None if nothing happened.
    """
    rien_n_a_change = (
        bilan["crees"] == 0 and bilan["mis_a_jour"] == 0
        and bilan["supprimes"] == 0 and bilan["avec_inscrits"] == 0
    )
    if rien_n_a_change:
        return None

    texte = _("%(crees)s besoins créés, %(mis_a_jour)s mis à jour, %(supprimes)s supprimés.") % {
        "crees": bilan["crees"],
        "mis_a_jour": bilan["mis_a_jour"],
        "supprimes": bilan["supprimes"],
    }
    if not bilan["avec_inscrits"]:
        return texte

    texte_des_inscrits = _("%(nombre)s besoins avec des inscrits n'ont pas été modifiés :") % {
        "nombre": bilan["avec_inscrits"],
    }
    return format_html(
        '{} {} <a href="{}">{}</a>.',
        texte, texte_des_inscrits, adresse_des_besoins_du_planning(planning), _("voir la page Besoins"),
    )


# ---------------------------------------------------------------------------
# « Répéter des besoins » (spec §5.7) / "Repeat needs"
# Le formulaire et le calcul sont HORS de la classe d'admin : Unfold enveloppe les
# méthodes d'un ModelAdmin (skill unfold, piège 23).
# / Form and computation live OUTSIDE the admin class (Unfold wraps its methods).
# ---------------------------------------------------------------------------

JOURS = "jours"
SEMAINES = "semaines"


class RepeterDesBesoinsForm(forms.Form):
    """
    Le formulaire de « Répéter des besoins ». Un forms.Form : c'est permis dans l'admin.
    / The "Repeat needs" form. A forms.Form: allowed in the admin.

    LOCALISATION : Administration/admin/benevolat.py
    """
    debut_du_modele = forms.DateField(
        label=_("Modèle : du"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    fin_du_modele = forms.DateField(
        label=_("au"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    repeter_tous_les = forms.IntegerField(
        label=_("Répéter tous les"),
        min_value=1,
        max_value=52,
        initial=1,
    )
    unite = forms.ChoiceField(
        label=_("Unité"),
        choices=[(JOURS, _("jour(s)")), (SEMAINES, _("semaine(s)"))],
        initial=SEMAINES,
    )
    nombre_de_fois = forms.IntegerField(
        label=_("Nombre de fois"),
        min_value=1,
        max_value=52,
        initial=4,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Même style que les champs de la balance (admin/comptable/balance.html) :
        # la page n'est pas un formulaire de modèle, Unfold ne les habille pas.
        # / Same look as the balance page fields: Unfold doesn't style a plain form.
        for champ in self.fields.values():
            champ.widget.attrs["class"] = (
                "border border-base-200 dark:border-base-700 rounded-default px-3 py-2 bg-white dark:bg-base-900"
            )

    def clean(self):
        donnees = super().clean()
        debut = donnees.get("debut_du_modele")
        fin = donnees.get("fin_du_modele")
        if debut and fin and fin < debut:
            raise forms.ValidationError(_("La fin du modèle doit être le même jour que le début, ou après."))
        # Une période modèle d'un mois au plus : au-delà, × 52 copies ferait des milliers
        # de besoins d'un coup.
        # / A model period of one month at most.
        if debut and fin and (fin - debut).days > 30:
            raise forms.ValidationError(_("La période modèle ne peut pas dépasser 31 jours."))
        return donnees


def calculer_l_apercu(planning, donnees_du_formulaire):
    """
    Les trois listes de l'aperçu (à créer, sautés, ignorés), pour ce planning et ce
    formulaire validé. Ne touche pas la base en écriture.
    / The preview's three lists for this planning and this validated form. No write.

    LOCALISATION : Administration/admin/benevolat.py
    Le calcul lui-même est dans booking/benevolat.py (calculer_repetitions, sans base).
    """
    from booking.benevolat import calculer_repetitions, cle_d_un_besoin, plage_horaire

    besoins_modele = list(
        planning.besoins.filter(
            date__gte=donnees_du_formulaire["debut_du_modele"],
            date__lte=donnees_du_formulaire["fin_du_modele"],
        ).select_related("tache").order_by("date", "heure_debut")
    )

    ecart_en_jours = donnees_du_formulaire["repeter_tous_les"]
    if donnees_du_formulaire["unite"] == SEMAINES:
        ecart_en_jours = ecart_en_jours * 7

    periodes_fermees = []
    if planning.calendrier_id is not None:
        periodes_fermees = list(planning.calendrier.closed_periods.all())

    besoins_existants = set()
    for besoin in planning.besoins.all():
        besoins_existants.add(cle_d_un_besoin(besoin.tache_id, besoin.date, besoin.heure_debut, besoin.heure_fin))

    apercu = calculer_repetitions(
        besoins_modele, ecart_en_jours, donnees_du_formulaire["nombre_de_fois"],
        periodes_fermees, besoins_existants,
    )
    # La plage horaire à afficher (« 18h–21h » ou « Journée »), pour le gabarit.
    # / Display time range, for the template.
    for nom_de_la_liste in ["a_creer", "sautes", "ignores"]:
        for copie in apercu[nom_de_la_liste]:
            copie["plage"] = plage_horaire(copie["modele"])
    apercu["besoins_modele"] = besoins_modele
    return apercu


@admin.register(PlanningBenevole, site=staff_admin_site)
class PlanningBenevoleAdmin(ModelAdmin):
    list_display = ["name", "slug", "type_de_planning", "published", "calendrier"]
    search_fields = ["name", "slug"]
    fields = [
        "name",
        "slug",
        "page_publique",
        "description",
        "adhesions_requises",
        "calendrier",
        "delai_desinscription_heures",
        "type_de_planning",
        "horizon_en_semaines",
        "besoins_crees_jusqu_au",
        "tous_les_besoins",
        # En dernier : on règle le planning, puis on l'active.
        # / Last: set up the planning, then switch it on.
        "published",
    ]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["page_publique", "besoins_crees_jusqu_au", "tous_les_besoins"]

    # Les champs de la semaine type n'apparaissent qu'en mode « Chaque semaine ».
    # / Template-week fields only show in "every week" mode.
    conditional_fields = {
        "horizon_en_semaines": "type_de_planning == 'HEBDOMADAIRE'",
        "besoins_crees_jusqu_au": "type_de_planning == 'HEBDOMADAIRE'",
    }

    @admin.display(description=_("Besoins"))
    def tous_les_besoins(self, planning):
        if planning._state.adding:
            return "—"
        return format_html(
            '<a href="{}">{}</a>', adresse_des_besoins_du_planning(planning), _("Voir tous les besoins de ce planning"),
        )

    def get_inlines(self, request, obj):
        """
        Les inlines suivent le type ENREGISTRÉ du planning :
        - hebdomadaire → la semaine type ;
        - ponctuel (et création) → les besoins à venir.
        Jamais les deux à la fois. Après un changement de type, on enregistre, puis on
        saisit la semaine type (aide du champ type_de_planning).
        / Inlines follow the SAVED type.

        Au POST, obj porte encore le type enregistré : Django crée les formsets
        (_changeform_view, _create_formsets) AVANT de valider le formulaire, qui seul
        y copie le type envoyé. Les inlines restent donc ceux qui ont été affichés.
        / On POST, Django builds the formsets BEFORE validating the form: obj still
        holds the saved type.
        """
        if obj is not None and obj.type_de_planning == PlanningBenevole.HEBDOMADAIRE:
            return [LigneDeSemaineTypeInline]
        return [BesoinBenevoleInline]

    def save_related(self, request, form, formsets, change):
        """
        Après l'enregistrement des lignes de la semaine type : répercute les changements
        sur les besoins futurs (D30) et ouvre les semaines manquantes.
        / After saving the template-week rows: apply them to future needs, open weeks.

        FLUX :
        1. AVANT super() : les besoins des lignes supprimées. Après, SET_NULL efface le
           lien et on ne les retrouverait plus.
        2. super() enregistre les lignes. Le formset garde new_objects et changed_objects
           (avec les noms des champs modifiés : on y voit un changement de jour).
        3. booking/benevolat.py, appliquer_la_semaine_type_modifiee : mises à jour,
           suppressions, créations, sous verrou.
        4. Le message « N créés, M mis à jour, P supprimés… ».
        """
        from booking.benevolat import appliquer_la_semaine_type_modifiee

        formset_des_lignes = None
        for formset in formsets:
            if formset.model is LigneDeSemaineType:
                formset_des_lignes = formset

        besoins_des_lignes_supprimees = []
        if formset_des_lignes is not None:
            uuids_des_lignes_supprimees = []
            for formulaire_de_ligne in formset_des_lignes.deleted_forms:
                if not formulaire_de_ligne.instance._state.adding:
                    uuids_des_lignes_supprimees.append(formulaire_de_ligne.instance.pk)
            besoins_des_lignes_supprimees = list(
                BesoinBenevole.objects.filter(
                    ligne_de_semaine_type__in=uuids_des_lignes_supprimees,
                ).values_list("pk", flat=True)
            )

        super().save_related(request, form, formsets, change)

        planning = form.instance
        if planning.type_de_planning != PlanningBenevole.HEBDOMADAIRE and formset_des_lignes is None:
            return

        lignes_modifiees = []
        lignes_qui_changent_de_jour = []
        lignes_ajoutees = []
        if formset_des_lignes is not None:
            for ligne, champs_modifies in formset_des_lignes.changed_objects:
                lignes_modifiees.append(ligne)
                if "jour_de_la_semaine" in champs_modifies:
                    lignes_qui_changent_de_jour.append(ligne)
            lignes_ajoutees = list(formset_des_lignes.new_objects)

        # Planning réactivé : des lignes ajoutées ou changées de jour pendant la pause
        # n'ont pas leurs créneaux dans les semaines déjà ouvertes (jusqu'à
        # besoins_crees_jusqu_au), et la création normale ne repasse jamais avant cette
        # date. On traite donc toutes les lignes comme nouvelles : les créneaux qui
        # existent déjà sont ignorés (doublons). Conséquence assumée (D35) : un créneau
        # supprimé à la main dans ces semaines revient à la réactivation.
        # / Reactivated planning: every row is treated as new to fill the open weeks.
        planning_vient_d_etre_reactive = "published" in form.changed_data and planning.published
        if planning_vient_d_etre_reactive:
            lignes_ajoutees = list(planning.semaine_type.all())

        bilan = appliquer_la_semaine_type_modifiee(
            planning, besoins_des_lignes_supprimees, lignes_modifiees,
            lignes_qui_changent_de_jour, lignes_ajoutees,
        )
        message = message_de_la_semaine_type(bilan, planning)
        if message is not None:
            messages.info(request, message)

    @admin.display(description=_("Page publique"))
    def page_publique(self, planning):
        if planning._state.adding or not planning.slug:
            return "—"
        adresse = reverse("benevolat-planning", kwargs={"slug": planning.slug})
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', adresse, _("Voir la page publique"))

    # L'autocomplétion des adhésions est servie par ProductAdmin. Django y applique le
    # limit_choices_to du champ (adhésions seulement) ; ProductAdmin.get_search_results
    # retire les produits archivés.
    # / Served by ProductAdmin, which applies the field's limit_choices_to.
    autocomplete_fields = ["adhesions_requises"]

    inlines = [BesoinBenevoleInline]

    # Bouton « Répéter des besoins » en haut de la fiche. Il mène à la vue repeter,
    # branchée par get_urls (une page à elle, avec son aperçu).
    # / "Repeat needs" button at the top of the change page.
    actions_detail = ["ouvrir_repeter"]

    @action(
        description=_("Répéter des besoins"),
        url_path="ouvrir-repeter",
        permissions=["custom_actions_detail"],
    )
    def ouvrir_repeter(self, request, object_id):
        return redirect(reverse("staff_admin:booking_planningbenevole_repeter", args=[object_id]))

    def has_custom_actions_detail_permission(self, request, object_id=None):
        # « Répéter » est masqué pour un planning hebdomadaire : la semaine type le
        # remplace (D34). La vue repeter le refuse aussi.
        # / "Repeat" is hidden for a weekly planning; the repeter view refuses it too.
        if not TenantAdminPermissionWithRequest(request):
            return False
        if object_id is None:
            return True
        return not PlanningBenevole.objects.filter(
            pk=object_id, type_de_planning=PlanningBenevole.HEBDOMADAIRE,
        ).exists()

    def get_urls(self):
        urls_standard = super().get_urls()
        urls_du_planning = [
            path(
                "<path:object_id>/repeter/",
                self.admin_site.admin_view(self.repeter),
                name="booking_planningbenevole_repeter",
            ),
        ]
        return urls_du_planning + urls_standard

    def repeter(self, request, object_id):
        """
        Page « Répéter des besoins » (spec §5.7).
        / "Repeat needs" page.

        LOCALISATION : Administration/admin/benevolat.py
        Gabarit : Administration/templates/admin/booking/planning_repeter.html

        FLUX :
        1. GET : le formulaire, pré-rempli avec les 7 premiers jours du planning.
        2. POST sans « confirmer » : l'aperçu (à créer, sautés, ignorés). Rien n'est écrit.
        3. POST avec « confirmer » : on recalcule (la base a pu changer depuis l'aperçu),
           on crée tout dans une seule transaction, puis retour à la fiche du planning.
        """
        if not TenantAdminPermissionWithRequest(request):
            raise PermissionDenied

        # Une adresse bricolée (pas un uuid) donne 404, pas une erreur 500.
        # / A tampered address (not a uuid) gives a 404, not a 500.
        try:
            uuid_du_planning = uuid.UUID(str(object_id))
        except ValueError:
            raise Http404
        planning = get_object_or_404(PlanningBenevole, pk=uuid_du_planning)

        # INDISPENSABLE même si le bouton est masqué : la page reste joignable par son
        # adresse. Un planning hebdomadaire a sa semaine type (D34).
        # / Needed even with the button hidden: the page is still reachable by URL.
        if planning.type_de_planning == PlanningBenevole.HEBDOMADAIRE:
            raise PermissionDenied

        apercu = None

        if request.method == "POST":
            formulaire = RepeterDesBesoinsForm(request.POST)
            if formulaire.is_valid():
                apercu = calculer_l_apercu(planning, formulaire.cleaned_data)

                if not apercu["besoins_modele"]:
                    formulaire.add_error(None, _("Aucun besoin dans cette période : rien à répéter."))
                    apercu = None
                elif request.POST.get("confirmer") == "1":
                    with transaction.atomic():
                        nouveaux_besoins = []
                        for copie in apercu["a_creer"]:
                            besoin_modele = copie["modele"]
                            nouveaux_besoins.append(BesoinBenevole(
                                planning=planning,
                                tache_id=besoin_modele.tache_id,
                                date=copie["date"],
                                heure_debut=besoin_modele.heure_debut,
                                heure_fin=besoin_modele.heure_fin,
                                nombre_souhaite=besoin_modele.nombre_souhaite,
                            ))
                        BesoinBenevole.objects.bulk_create(nouveaux_besoins)

                    messages.success(request, _(
                        "%(crees)s besoins créés, %(sautes)s sautés (fermeture), "
                        "%(ignores)s ignorés (déjà présents)."
                    ) % {
                        "crees": len(apercu["a_creer"]),
                        "sautes": len(apercu["sautes"]),
                        "ignores": len(apercu["ignores"]),
                    })
                    return redirect(reverse("staff_admin:booking_planningbenevole_change", args=[planning.pk]))
        else:
            # Pré-rempli : les 7 premiers jours du planning (ou à partir d'aujourd'hui).
            # / Pre-filled: the planning's first 7 days (or from today).
            premier_besoin = planning.besoins.order_by("date").first()
            if premier_besoin is not None:
                debut_propose = premier_besoin.date
            else:
                fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
                debut_propose = timezone.now().astimezone(fuseau_du_lieu).date()
            formulaire = RepeterDesBesoinsForm(initial={
                "debut_du_modele": debut_propose,
                "fin_du_modele": debut_propose + datetime.timedelta(days=6),
            })

        contexte = {
            **self.admin_site.each_context(request),
            "title": _("Répéter des besoins"),
            "planning": planning,
            "formulaire": formulaire,
            "apercu": apercu,
            "adresse_de_la_fiche": reverse("staff_admin:booking_planningbenevole_change", args=[planning.pk]),
        }
        return render(request, "admin/booking/planning_repeter.html", contexte)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class BesoinsAVenirFilter(admin.SimpleListFilter):
    """
    « À venir » par défaut, « Passés », « Tous ». Même mécanisme qu'EventDateFilter
    (Administration/admin_tenant.py) : le premier choix (aucune valeur) est renommé
    « À venir » et filtre ; « Tous » a sa propre valeur.
    / "Upcoming" by default, like EventDateFilter.

    Aujourd'hui = la date du lieu (booking/benevolat.py, aujourd_hui_au_lieu).
    """
    title = _("Quand")
    parameter_name = "quand"

    def choices(self, changelist):
        choix = list(super().choices(changelist))
        choix[0]["display"] = _("À venir")
        return choix

    def lookups(self, request, model_admin):
        return [
            ("passes", _("Passés")),
            ("tous", _("Tous")),
        ]

    def queryset(self, request, queryset):
        from booking.benevolat import aujourd_hui_au_lieu

        if self.value() is None:
            return queryset.filter(date__gte=aujourd_hui_au_lieu())
        if self.value() == "passes":
            return queryset.filter(date__lt=aujourd_hui_au_lieu())
        return queryset


class BesoinsAvecInscritsFilter(admin.SimpleListFilter):
    """
    « Avec inscrit·es » / « Sans inscrit·e ». Lit l'annotation nombre_d_inscrits
    de BesoinBenevoleAdmin.get_queryset.
    / With / without sign-ups, from the nombre_d_inscrits annotation.
    """
    title = _("Inscrit·es")
    parameter_name = "inscrits"

    def lookups(self, request, model_admin):
        return [
            ("avec", _("Avec inscrit·es")),
            ("sans", _("Sans inscrit·e")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "avec":
            return queryset.filter(nombre_d_inscrits__gt=0)
        if self.value() == "sans":
            return queryset.filter(nombre_d_inscrits=0)
        return queryset


@admin.register(BesoinBenevole, site=staff_admin_site)
class BesoinBenevoleAdmin(ModelAdmin):
    """
    La page « Besoins » : tous les besoins de tous les plannings (§11.2).
    / The "Needs" page: every need of every planning.

    LOCALISATION : Administration/admin/benevolat.py

    « À venir » par défaut : le passé reste en base (D33). Ajout et modification permis :
    c'est ici qu'on fait une exception à la semaine type. Un besoin modifié qui ne
    correspond plus à sa ligne en est détaché (BesoinBenevole.save) : la ligne ne
    l'écrasera plus.
    / Upcoming by default. Adding and editing allowed: exceptions to the template week.
    """
    list_display = ["jour", "plage", "tache", "planning", "inscrits", "fermeture"]
    list_filter = [
        BesoinsAVenirFilter,
        ("planning", RelatedDropdownFilter),
        ("tache", RelatedDropdownFilter),
        BesoinsAvecInscritsFilter,
    ]
    date_hierarchy = "date"
    ordering = ["date", "heure_debut"]
    list_per_page = 100
    fields = ["planning", "tache", "date", "heure_debut", "heure_fin", "nombre_souhaite"]

    def get_queryset(self, request):
        # Tout ce que lisent les colonnes, en un nombre fixe de requêtes, quel que soit
        # le nombre de besoins affichés.
        # / Everything the columns read, in a fixed number of queries.
        return super().get_queryset(request).select_related(
            "tache", "planning__calendrier",
        ).prefetch_related(
            "planning__calendrier__closed_periods",
        ).annotate(
            nombre_d_inscrits=Count("inscriptions"),
        )

    @admin.display(description=_("Jour"), ordering="date")
    def jour(self, besoin):
        return date_format(besoin.date, "D j F Y")

    @admin.display(description=_("Plage"))
    def plage(self, besoin):
        from booking.benevolat import plage_horaire

        return plage_horaire(besoin)

    @admin.display(description=_("Inscrit·es"), ordering="nombre_d_inscrits")
    def inscrits(self, besoin):
        return f"{besoin.nombre_d_inscrits}/{besoin.nombre_souhaite}"

    @admin.display(description=_("Fermeture"))
    def fermeture(self, besoin):
        libelle_de_fermeture = besoin.planning.libelle_de_fermeture(besoin.date)
        if libelle_de_fermeture is None:
            return "—"
        return _("Fermé : %(libelle)s") % {"libelle": libelle_de_fermeture}

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

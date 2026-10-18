"""
API v2 du bénévolat : tâches, plannings, besoins et inscriptions.
/ Volunteering API v2: tasks, plannings, needs and sign-ups.

LOCALISATION : api_v2/views_benevolat.py
Routes : api_v2/urls.py. Représentations et entrées : api_v2/serializers_benevolat.py.
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§6 bis, D24 — API allégée)

| Route                         | basename          | schema.org     |
|-------------------------------|-------------------|----------------|
| /api/v2/volunteer-tasks/      | volunteertask     | DefinedTerm    |
| /api/v2/volunteer-plannings/  | volunteerplanning | EventSeries    |
| /api/v2/volunteer-needs/      | volunteerneed     | Event          |
| /api/v2/volunteer-signups/    | volunteersignup   | RsvpAction     |

Un seul droit de clé pour les quatre : ExternalApiKey.volunteering (sinon 403).
La clé ne voit que le schéma de son lieu (django-tenants) : un uuid d'un autre lieu = 404.
/ One key right for the four routes; a key only sees its own venue.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status, viewsets
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from booking.benevolat import compte_d_une_personne_inscrite_par_l_equipe
from booking.models import BesoinBenevole, InscriptionBenevole, PlanningBenevole, TacheBenevole
from booking.tasks import envoyer_confirmation_benevole

from .permissions import SemanticApiKeyPermission
from .serializers_benevolat import (
    BesoinEntreeSerializer,
    InscriptionEntreeSerializer,
    PlanningEntreeSerializer,
    TacheEntreeSerializer,
    besoin_en_schema,
    inscription_en_schema,
    planning_en_schema,
    tache_en_schema,
    uuid_ou_rien,
)


def erreurs_du_modele(erreur_de_validation):
    """Les erreurs d'un full_clean(), en réponse 400. / full_clean() errors as a 400."""
    return Response(erreur_de_validation.message_dict, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Tâches → DefinedTerm
# ---------------------------------------------------------------------------

class VolunteerTaskViewSet(viewsets.ViewSet):
    """Le catalogue des tâches du lieu. / The venue's task catalogue."""
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (JSONParser,)
    lookup_field = "uuid"

    def list(self, request):
        taches = TacheBenevole.objects.order_by("name")
        return Response({"results": [tache_en_schema(tache) for tache in taches]})

    def retrieve(self, request, uuid=None):
        tache = get_object_or_404(TacheBenevole, pk=uuid_ou_rien(uuid))
        return Response(tache_en_schema(tache))

    def create(self, request):
        entree = TacheEntreeSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        tache = TacheBenevole.objects.create(
            name=entree.validated_data["name"],
            description=entree.validated_data.get("description", ""),
        )
        return Response(tache_en_schema(tache), status=status.HTTP_201_CREATED)

    def partial_update(self, request, uuid=None):
        tache = get_object_or_404(TacheBenevole, pk=uuid_ou_rien(uuid))
        entree = TacheEntreeSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        if "name" in entree.validated_data:
            tache.name = entree.validated_data["name"]
        if "description" in entree.validated_data:
            tache.description = entree.validated_data["description"]
        tache.save()
        return Response(tache_en_schema(tache))

    def destroy(self, request, uuid=None):
        """
        Une tâche qui sert encore à un besoin ne se supprime pas (PROTECT) : 409.
        / A task still used by a need can't be deleted: 409.
        """
        tache = get_object_or_404(TacheBenevole, pk=uuid_ou_rien(uuid))
        try:
            tache.delete()
        except ProtectedError:
            nombre_de_besoins = tache.besoins.count()
            return Response(
                {"detail": _("Cette tâche sert encore à %(nombre)s besoins.") % {"nombre": nombre_de_besoins}},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Plannings → EventSeries
# ---------------------------------------------------------------------------

def trouver_le_planning(identifiant):
    """Un planning par son uuid OU son slug (comme les pages). / By uuid OR slug."""
    uuid_lu = uuid_ou_rien(identifiant)
    if uuid_lu is not None:
        return PlanningBenevole.objects.filter(pk=uuid_lu).first()
    return PlanningBenevole.objects.filter(slug=identifiant).first()


class VolunteerPlanningViewSet(viewsets.ViewSet):
    """
    Les plannings. Les adhésions requises et le calendrier de fermetures sont en lecture
    seule (API allégée) : ils se règlent dans l'admin.
    / Plannings; memberships and calendar are read-only here.
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (JSONParser,)
    lookup_field = "uuid"
    # Un slug n'est pas un uuid : on accepte les deux dans l'adresse.
    # / A slug is not a uuid: both are accepted in the URL.
    lookup_value_regex = "[^/]+"

    def list(self, request):
        plannings = PlanningBenevole.objects.prefetch_related("adhesions_requises").order_by("-created_at")
        return Response({"results": [planning_en_schema(planning) for planning in plannings]})

    def retrieve(self, request, uuid=None):
        planning = trouver_le_planning(uuid)
        if planning is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(planning_en_schema(planning, avec_les_besoins=True))

    def create(self, request):
        entree = PlanningEntreeSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        # Le slug manquant est refusé par full_clean() (champ obligatoire du modèle).
        # / A missing slug is refused by full_clean().
        planning = PlanningBenevole(**entree.validated_data["champs_du_planning"])
        try:
            planning.full_clean()
        except DjangoValidationError as erreur:
            return erreurs_du_modele(erreur)
        planning.save()
        return Response(planning_en_schema(planning), status=status.HTTP_201_CREATED)

    def partial_update(self, request, uuid=None):
        planning = trouver_le_planning(uuid)
        if planning is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        entree = PlanningEntreeSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        for nom_du_champ, valeur in entree.validated_data["champs_du_planning"].items():
            setattr(planning, nom_du_champ, valeur)
        try:
            planning.full_clean()
        except DjangoValidationError as erreur:
            return erreurs_du_modele(erreur)
        planning.save()
        return Response(planning_en_schema(planning))

    def destroy(self, request, uuid=None):
        """Supprime le planning, ses besoins et leurs inscriptions (CASCADE), sans mail (D17)."""
        planning = trouver_le_planning(uuid)
        if planning is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        planning.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Besoins → Event « Volunteering »
# ---------------------------------------------------------------------------

def besoins_precharges():
    """Les besoins avec ce que lit besoin_en_schema, préchargé. / Needs with prefetches."""
    return BesoinBenevole.objects.select_related("tache", "planning__calendrier").prefetch_related(
        "inscriptions__user", "planning__calendrier__closed_periods",
    )


class VolunteerNeedViewSet(viewsets.ViewSet):
    """
    Les besoins. La liste inclut les besoins passés : l'API sert l'équipe, pas le public.
    Filtres : ?planning=<uuid>, ?task=<uuid>, ?dateFrom=AAAA-MM-JJ, ?dateTo=AAAA-MM-JJ.
    Un besoin créé un jour fermé est accepté ; sa sortie porte « fermeture » (P8).
    / Needs; past ones included. Filters by planning, task and dates.
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (JSONParser,)
    lookup_field = "uuid"

    def list(self, request):
        besoins = besoins_precharges().order_by("date", "heure_debut")
        if request.query_params.get("planning"):
            besoins = besoins.filter(planning_id=uuid_ou_rien(request.query_params["planning"]))
        if request.query_params.get("task"):
            besoins = besoins.filter(tache_id=uuid_ou_rien(request.query_params["task"]))
        if request.query_params.get("dateFrom"):
            besoins = besoins.filter(date__gte=serializers.DateField().run_validation(request.query_params["dateFrom"]))
        if request.query_params.get("dateTo"):
            besoins = besoins.filter(date__lte=serializers.DateField().run_validation(request.query_params["dateTo"]))
        return Response({"results": [besoin_en_schema(besoin) for besoin in besoins]})

    def retrieve(self, request, uuid=None):
        besoin = get_object_or_404(besoins_precharges(), pk=uuid_ou_rien(uuid))
        return Response(besoin_en_schema(besoin))

    def create(self, request):
        entree = BesoinEntreeSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        champs = entree.validated_data["champs_du_besoin"]
        if "planning" not in champs:
            raise serializers.ValidationError({"superEvent": _("Le planning (superEvent) est obligatoire.")})

        besoin = BesoinBenevole(**champs)
        try:
            besoin.full_clean()
        except DjangoValidationError as erreur:
            return erreurs_du_modele(erreur)
        besoin.save()
        return Response(besoin_en_schema(besoins_precharges().get(pk=besoin.pk)), status=status.HTTP_201_CREATED)

    def partial_update(self, request, uuid=None):
        besoin = get_object_or_404(BesoinBenevole, pk=uuid_ou_rien(uuid))
        entree = BesoinEntreeSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        champs = entree.validated_data["champs_du_besoin"]
        # Un besoin ne change pas de planning. / A need doesn't change planning.
        champs.pop("planning", None)
        for nom_du_champ, valeur in champs.items():
            setattr(besoin, nom_du_champ, valeur)
        try:
            besoin.full_clean()
        except DjangoValidationError as erreur:
            return erreurs_du_modele(erreur)
        besoin.save()
        return Response(besoin_en_schema(besoins_precharges().get(pk=besoin.pk)))

    def destroy(self, request, uuid=None):
        """Supprime le besoin et ses inscriptions (CASCADE), sans mail (D17)."""
        besoin = get_object_or_404(BesoinBenevole, pk=uuid_ou_rien(uuid))
        besoin.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Inscriptions → RsvpAction
# ---------------------------------------------------------------------------

def inscriptions_prechargees():
    return InscriptionBenevole.objects.select_related("user", "inscrit_par")


class VolunteerSignupViewSet(viewsets.ViewSet):
    """
    Les inscriptions. Filtres de liste : ?need=<uuid>, ?planning=<uuid>.
    Pas de PATCH : une inscription n'a rien de modifiable.
    / Sign-ups. No PATCH: nothing to edit.
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (JSONParser,)
    lookup_field = "uuid"

    def list(self, request):
        inscriptions = inscriptions_prechargees().order_by("besoin__date", "created_at")
        if request.query_params.get("need"):
            inscriptions = inscriptions.filter(besoin_id=uuid_ou_rien(request.query_params["need"]))
        if request.query_params.get("planning"):
            inscriptions = inscriptions.filter(besoin__planning_id=uuid_ou_rien(request.query_params["planning"]))
        return Response({"results": [inscription_en_schema(inscription) for inscription in inscriptions]})

    def retrieve(self, request, uuid=None):
        inscription = get_object_or_404(inscriptions_prechargees(), pk=uuid_ou_rien(uuid))
        return Response(inscription_en_schema(inscription))

    def create(self, request):
        """
        Inscrit une personne sur un besoin : mêmes règles que « Inscrire quelqu'un » (§5.10).
        / Signs a person up: same rules as the team sign-up.

        FLUX :
        1. Planning publié et besoin pas passé (sinon 400). Pas de contrôle d'adhésion.
        2. Le compte : créé s'il n'existe pas et rattaché au lieu ; prénom et nom écrits
           seulement s'ils sont vides (booking/benevolat.py). S'ils manquent dans le compte
           ET dans la requête : 400, et rien n'est créé (transaction annulée).
        3. get_or_create avec inscrit_par = le compte de la clé (vide si la clé n'en a pas) :
           201 si créée, 200 avec l'inscription existante si rejouée (sans danger).
        4. Mail « L'équipe t'a inscrit·e » (avec le lien « Je ne peux plus venir »),
           seulement à la création, après le commit.
        """
        entree = InscriptionEntreeSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data

        # Le compte de la clé : ExternalApiKey.user, posé par SemanticApiKeyPermission.
        # Il peut être vide. / The key's account, may be empty.
        compte_de_la_cle = request.user if getattr(request.user, "pk", None) else None

        with transaction.atomic():
            personne = compte_d_une_personne_inscrite_par_l_equipe(donnees["email"], donnees["prenom"], donnees["nom"])
            if personne is None:
                raise serializers.ValidationError({"agent": _("Cet email est marqué en erreur : un mail envoyé à cette adresse est revenu.")})
            if not (personne.first_name or "").strip() or not (personne.last_name or "").strip():
                # L'exception annule la transaction : le compte créé à l'instant disparaît.
                # / The exception rolls back the transaction.
                raise serializers.ValidationError({"agent": _("givenName et familyName sont obligatoires : le compte ne les a pas.")})

            inscription, inscription_vient_d_etre_creee = InscriptionBenevole.objects.get_or_create(
                besoin=donnees["besoin"],
                user=personne,
                defaults={"inscrit_par": compte_de_la_cle},
            )

        if inscription_vient_d_etre_creee:
            uuid_de_l_inscription = str(inscription.pk)
            transaction.on_commit(
                lambda: envoyer_confirmation_benevole.delay(uuid_de_l_inscription, par_l_equipe=True)
            )
            code_http = status.HTTP_201_CREATED
        else:
            code_http = status.HTTP_200_OK

        return Response(inscription_en_schema(inscriptions_prechargees().get(pk=inscription.pk)), status=code_http)

    def destroy(self, request, uuid=None):
        """Retire la personne, à tout moment, SANS mail : l'équipe agit, comme en admin (D17)."""
        inscription = get_object_or_404(InscriptionBenevole, pk=uuid_ou_rien(uuid))
        inscription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

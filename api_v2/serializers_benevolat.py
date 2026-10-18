"""
API v2 du bénévolat : les représentations schema.org et la validation des entrées.
/ Volunteering API v2: schema.org representations and input validation.

LOCALISATION : api_v2/serializers_benevolat.py
Utilisé par api_v2/views_benevolat.py.
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§6 bis, D24 — API allégée)

Correspondances schema.org :
- TacheBenevole       → DefinedTerm
- PlanningBenevole    → EventSeries
- BesoinBenevole      → Event, additionalType « Volunteering »
- InscriptionBenevole → RsvpAction

Les SORTIES sont des fonctions qui fabriquent un dict, champ par champ : on lit d'un coup
d'œil ce qui sort. Les ENTRÉES passent par des serializers.Serializer.
/ Outputs are plain dict builders; inputs go through serializers.Serializer.

Les heures : le modèle garde date, heure_debut, heure_fin SANS fuseau (heure locale du
lieu). En sortie, startDate / endDate portent le décalage du lieu (« 2026-10-10T18:00:00+02:00 »).
En entrée, une heure sans décalage est lue en heure locale ; avec un décalage, elle est
convertie dans le fuseau du lieu.
/ Hours are stored without timezone (venue local time).
"""
import datetime
import re
import uuid

from django.db.models import Max, Min
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from BaseBillet.models import Configuration
from booking.benevolat import besoins_a_venir, prenom_public
from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

CONTEXTE_SCHEMA = "https://schema.org"
UNE_DATE_SEULE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def propriete(nom, valeur):
    """Un PropertyValue schema.org. / A schema.org PropertyValue."""
    return {"@type": "PropertyValue", "name": nom, "value": valeur}


def lire_les_proprietes(liste_de_proprietes):
    """
    Les additionalProperty reçus, en dict {nom: valeur}. Une entrée mal formée est ignorée.
    / Incoming additionalProperty as a {name: value} dict.
    """
    proprietes = {}
    if not isinstance(liste_de_proprietes, list):
        return proprietes
    for entree in liste_de_proprietes:
        if isinstance(entree, dict) and entree.get("name"):
            proprietes[entree["name"]] = entree.get("value")
    return proprietes


def uuid_ou_rien(valeur):
    """
    La valeur si c'est un uuid lisible, sinon None : un filtre pk=None ne trouve rien,
    alors qu'un pk mal formé lèverait une ValidationError de Django (500).
    / The value if it parses as a uuid, else None.
    """
    try:
        return uuid.UUID(str(valeur))
    except (ValueError, TypeError, AttributeError):
        return None


def identifiant_recu(valeur):
    """
    Un identifiant reçu seul (« uuid ») ou dans un objet ({"identifier": "uuid"}).
    / An identifier received alone or inside an object.
    """
    if isinstance(valeur, dict):
        return valeur.get("identifier")
    return valeur


# ---------------------------------------------------------------------------
# Sorties / Outputs
# ---------------------------------------------------------------------------

def tache_en_schema(tache):
    return {
        "@context": CONTEXTE_SCHEMA,
        "@type": "DefinedTerm",
        "identifier": str(tache.pk),
        "name": tache.name,
        "description": tache.description,
    }


def besoin_en_schema(besoin):
    """
    Un besoin en schema.org/Event. À appeler sur un besoin dont les inscriptions, la tâche
    et le planning sont préchargés, pour éviter une requête par besoin.
    / A need as schema.org/Event (prefetch sign-ups, task and planning).
    """
    if besoin.est_une_journee():
        date_de_debut = besoin.date.isoformat()
        date_de_fin = None
    else:
        date_de_debut = besoin.debut().isoformat()
        date_de_fin = besoin.fin().isoformat()

    participants = []
    for inscription in sorted(besoin.inscriptions.all(), key=lambda inscription: inscription.created_at):
        participants.append({"@type": "Person", "givenName": prenom_public(inscription.user)})

    libelle_de_fermeture = besoin.planning.libelle_de_fermeture(besoin.date)
    besoin_en_dict = {
        "@context": CONTEXTE_SCHEMA,
        "@type": "Event",
        "additionalType": "Volunteering",
        "identifier": str(besoin.pk),
        "superEvent": {"@type": "EventSeries", "identifier": str(besoin.planning_id), "name": besoin.planning.name},
        "about": {"@type": "DefinedTerm", "identifier": str(besoin.tache_id), "name": besoin.tache.name},
        "startDate": date_de_debut,
        "remainingAttendeeCapacity": besoin.places_libres(),
        "attendee": participants,
        "additionalProperty": [
            propriete("nombreSouhaite", besoin.nombre_souhaite),
            propriete("nombreInscrits", besoin.nombre_inscrits()),
            propriete("renforts", besoin.nombre_de_renforts()),
            propriete("fermeture", str(libelle_de_fermeture) if libelle_de_fermeture else None),
        ],
    }
    if date_de_fin is not None:
        besoin_en_dict["endDate"] = date_de_fin
    return besoin_en_dict


def planning_en_schema(planning, avec_les_besoins=False):
    """
    Un planning en schema.org/EventSeries. startDate / endDate : le premier et le dernier
    jour de ses besoins (absents sans besoin). Les compteurs portent sur les besoins à venir,
    comme l'en-tête de la page publique (D21). subEvent : seulement au retrieve.
    / A planning as schema.org/EventSeries; subEvent only on retrieve.
    """
    bornes = planning.besoins.aggregate(premier_jour=Min("date"), dernier_jour=Max("date"))

    places_couvertes = 0
    places_souhaitees = 0
    renforts = 0
    creneaux_vides = 0
    for besoin in besoins_a_venir(planning):
        places_couvertes += besoin.places_couvertes()
        places_souhaitees += besoin.nombre_souhaite
        renforts += besoin.nombre_de_renforts()
        if besoin.nombre_inscrits() == 0:
            creneaux_vides += 1

    adhesions_requises = []
    for adhesion in planning.adhesions_requises.all():
        adhesions_requises.append(str(adhesion.pk))

    planning_en_dict = {
        "@context": CONTEXTE_SCHEMA,
        "@type": "EventSeries",
        "identifier": str(planning.pk),
        "name": planning.name,
        "description": planning.description,
        "url": f"/booking/benevolat/{planning.slug}/",
        "additionalProperty": [
            propriete("slug", planning.slug),
            propriete("published", planning.published),
            propriete("delaiDesinscriptionHeures", planning.delai_desinscription_heures),
            propriete("requiredMembershipPlans", adhesions_requises),
            propriete("closingCalendar", planning.calendrier_id),
            propriete("placesCouvertes", places_couvertes),
            propriete("placesSouhaitees", places_souhaitees),
            propriete("renforts", renforts),
            propriete("creneauxVides", creneaux_vides),
        ],
    }
    if bornes["premier_jour"] is not None:
        planning_en_dict["startDate"] = bornes["premier_jour"].isoformat()
        planning_en_dict["endDate"] = bornes["dernier_jour"].isoformat()

    if avec_les_besoins:
        besoins = (
            planning.besoins.select_related("tache", "planning__calendrier")
            .prefetch_related("inscriptions__user", "planning__calendrier__closed_periods")
            .order_by("date", "heure_debut")
        )
        planning_en_dict["subEvent"] = [besoin_en_schema(besoin) for besoin in besoins]
    return planning_en_dict


def inscription_en_schema(inscription):
    """
    Une inscription en schema.org/RsvpAction. Ici l'email et le nom sont donnés : la clé
    appartient à l'équipe du lieu, qui voit déjà ces informations dans l'admin.
    / A sign-up as schema.org/RsvpAction (the key belongs to the venue team).
    """
    personne = inscription.user
    inscrit_par = inscription.inscrit_par.email if inscription.inscrit_par_id else None
    rappel = inscription.rappel_envoye_le.isoformat() if inscription.rappel_envoye_le else None
    return {
        "@context": CONTEXTE_SCHEMA,
        "@type": "RsvpAction",
        "identifier": str(inscription.pk),
        "rsvpResponse": "https://schema.org/RsvpResponseYes",
        "object": {"@type": "Event", "identifier": str(inscription.besoin_id)},
        "agent": {
            "@type": "Person",
            "email": personne.email,
            "givenName": personne.first_name or "",
            "familyName": personne.last_name or "",
        },
        "startTime": inscription.created_at.isoformat(),
        "additionalProperty": [
            propriete("inscritPar", inscrit_par),
            propriete("rappelEnvoyeLe", rappel),
        ],
    }


# ---------------------------------------------------------------------------
# Entrées / Inputs
# ---------------------------------------------------------------------------

class TacheEntreeSerializer(serializers.Serializer):
    """Création / PATCH d'une tâche (DefinedTerm). / Task create / PATCH."""
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_name(self, valeur):
        # Le nom de la tâche finit dans le SUJET des mails de confirmation et de rappel :
        # un retour à la ligne y lève BadHeaderError, le mail serait perdu.
        # / The task name ends up in email subjects: no line break.
        if "\n" in valeur or "\r" in valeur:
            raise serializers.ValidationError(_("Une seule ligne, sans retour à la ligne."))
        return valeur


class PlanningEntreeSerializer(serializers.Serializer):
    """
    Création / PATCH d'un planning (EventSeries). Dans additionalProperty : slug,
    published, delaiDesinscriptionHeures. Les adhésions requises et le calendrier de
    fermetures se règlent dans l'admin (API allégée, D24).
    / Planning create / PATCH; memberships and calendar are admin-only.
    """
    name = serializers.CharField(max_length=250)
    description = serializers.CharField(required=False, allow_blank=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, donnees):
        proprietes = lire_les_proprietes(donnees.get("additionalProperty"))
        champs = {}
        if "name" in donnees:
            champs["name"] = donnees["name"]
        if "description" in donnees:
            champs["description"] = donnees["description"]

        if "slug" in proprietes:
            champs["slug"] = serializers.SlugField(max_length=250).run_validation(proprietes["slug"])
        if "published" in proprietes:
            champs["published"] = serializers.BooleanField().run_validation(proprietes["published"])
        if "delaiDesinscriptionHeures" in proprietes:
            champs["delai_desinscription_heures"] = serializers.IntegerField(min_value=0).run_validation(
                proprietes["delaiDesinscriptionHeures"]
            )
        donnees["champs_du_planning"] = champs
        return donnees


def lire_les_dates_du_besoin(texte_du_debut, texte_de_la_fin):
    """
    startDate / endDate reçus → (date, heure_debut, heure_fin), dans le fuseau du lieu.
    / Incoming startDate / endDate → (date, start time, end time), venue timezone.

    - startDate date seule (« 2026-10-03 ») : journée entière ; endDate interdit.
    - startDate avec une heure : endDate obligatoire. Sans décalage = heure locale ; avec
      décalage = converti dans le fuseau du lieu.
    - La fin tombe le jour même (fin après début) ou le lendemain (fin avant début, ex.
      21:00 → 00:00). Début = fin : refusé (24 h, presque toujours une faute de frappe).
    Lève serializers.ValidationError sinon.
    """
    if UNE_DATE_SEULE.match(texte_du_debut or ""):
        if texte_de_la_fin:
            raise serializers.ValidationError({"endDate": _("Pas de endDate pour une journée entière (startDate sans heure).")})
        try:
            return datetime.date.fromisoformat(texte_du_debut), None, None
        except ValueError:
            raise serializers.ValidationError({"startDate": _("Cette date n'existe pas.")})

    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()

    def en_heure_locale(texte, nom_du_champ):
        # parse_datetime lève ValueError sur une date bien formée mais impossible (30 février).
        # / parse_datetime raises ValueError on an impossible date.
        try:
            moment = parse_datetime(texte or "")
        except ValueError:
            raise serializers.ValidationError({nom_du_champ: _("Cette date n'existe pas.")})
        if moment is None:
            raise serializers.ValidationError({nom_du_champ: _("Date et heure attendues, au format ISO 8601.")})
        if moment.tzinfo is None:
            return moment
        return moment.astimezone(fuseau_du_lieu).replace(tzinfo=None)

    debut = en_heure_locale(texte_du_debut, "startDate")
    if not texte_de_la_fin:
        raise serializers.ValidationError({"endDate": _("endDate est obligatoire quand startDate porte une heure.")})
    fin = en_heure_locale(texte_de_la_fin, "endDate")

    ecart_en_jours = (fin.date() - debut.date()).days
    fin_le_jour_meme = ecart_en_jours == 0 and fin.time() > debut.time()
    fin_le_lendemain = ecart_en_jours == 1 and fin.time() < debut.time()
    if not (fin_le_jour_meme or fin_le_lendemain):
        raise serializers.ValidationError({"endDate": _(
            "La fin doit tomber après le début, le jour même ou le lendemain (moins de 24 h)."
        )})
    return debut.date(), debut.time(), fin.time()


class BesoinEntreeSerializer(serializers.Serializer):
    """
    Création / PATCH d'un besoin (Event « Volunteering »).
    superEvent (le planning) et about (la tâche) : un uuid, ou {"identifier": uuid}.
    additionalProperty : nombreSouhaite (≥ 1). Au PATCH, superEvent est ignoré : un besoin
    ne change pas de planning.
    / Need create / PATCH; superEvent is ignored on PATCH.
    """
    superEvent = serializers.JSONField(required=False)
    about = serializers.JSONField()
    startDate = serializers.CharField()
    endDate = serializers.CharField(required=False, allow_blank=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, donnees):
        champs = {}

        if "superEvent" in donnees:
            planning = PlanningBenevole.objects.filter(pk=uuid_ou_rien(identifiant_recu(donnees["superEvent"]))).first()
            if planning is None:
                raise serializers.ValidationError({"superEvent": _("Planning introuvable.")})
            champs["planning"] = planning

        if "about" in donnees:
            tache = TacheBenevole.objects.filter(pk=uuid_ou_rien(identifiant_recu(donnees["about"]))).first()
            if tache is None:
                raise serializers.ValidationError({"about": _("Tâche introuvable.")})
            champs["tache"] = tache

        if "startDate" in donnees:
            une_date, heure_debut, heure_fin = lire_les_dates_du_besoin(donnees["startDate"], donnees.get("endDate"))
            champs["date"] = une_date
            champs["heure_debut"] = heure_debut
            champs["heure_fin"] = heure_fin

        proprietes = lire_les_proprietes(donnees.get("additionalProperty"))
        if "nombreSouhaite" in proprietes:
            champs["nombre_souhaite"] = serializers.IntegerField(min_value=1, max_value=32767).run_validation(
                proprietes["nombreSouhaite"]
            )

        donnees["champs_du_besoin"] = champs
        return donnees


class InscriptionEntreeSerializer(serializers.Serializer):
    """
    Création d'une inscription (RsvpAction) :
    {"object": {"identifier": <besoin>}, "agent": {"email", "givenName", "familyName"}}.
    / Sign-up creation.
    """
    object = serializers.JSONField()
    agent = serializers.DictField()

    def validate(self, donnees):
        besoin = (
            BesoinBenevole.objects.select_related("planning", "tache")
            .filter(pk=uuid_ou_rien(identifiant_recu(donnees["object"])))
            .first()
        )
        if besoin is None:
            raise serializers.ValidationError({"object": _("Besoin introuvable.")})
        if not besoin.planning.published:
            raise serializers.ValidationError({"object": _("Ce planning n'est pas publié.")})
        if besoin.est_passe():
            raise serializers.ValidationError({"object": _("Ce créneau est passé.")})

        agent = donnees["agent"]
        email = serializers.EmailField().run_validation(agent.get("email"))
        prenom = (agent.get("givenName") or "").strip()
        nom = (agent.get("familyName") or "").strip()
        for nom_du_champ, valeur in [("givenName", prenom), ("familyName", nom)]:
            if len(valeur) > 200 or "\n" in valeur or "\r" in valeur:
                raise serializers.ValidationError({"agent": _("%(champ)s : 200 caractères au plus, sur une seule ligne.") % {"champ": nom_du_champ}})

        donnees["besoin"] = besoin
        donnees["email"] = email
        donnees["prenom"] = prenom
        donnees["nom"] = nom
        return donnees

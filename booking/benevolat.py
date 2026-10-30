"""
Calculs du planning des bénévoles : la grille, les couleurs des jours, le compteur.
/ Volunteer planning computations: the grid, the day colours, the counter.

LOCALISATION : booking/benevolat.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.2)

Ce fichier ne rend aucun HTML. Il prépare des dictionnaires simples que les gabarits
de booking/templates/booking/benevolat/ affichent tels quels.
Utilisé par booking/views_benevolat.py.
/ No HTML here: plain dicts for the templates. Used by booking/views_benevolat.py.
"""
import datetime

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, Membership
from booking.models import (
    BesoinBenevole,
    InscriptionBenevole,
    PlanningBenevole,
    libelle_d_une_fermeture,
    periode_fermee_qui_couvre,
)


# ---------------------------------------------------------------------------
# Fonctions pures (sans base de données) / Pure functions (no database)
# ---------------------------------------------------------------------------

def taux_de_remplissage(besoins):
    """
    Le remplissage d'un groupe de besoins, de 0 à 100.
    taux = somme des places couvertes / somme des nombres souhaités.
    Les renforts ne le font jamais dépasser 100.
    / Fill rate of a group of needs, 0 to 100. Extras never push it past 100.

    Sert à la couleur des en-têtes de jours : 0 = rouge, 100 = vert.
    Un groupe vide vaut 100 (rien ne manque).
    / Drives the day header colour. An empty group is 100 (nothing missing).
    """
    total_des_places_souhaitees = 0
    total_des_places_couvertes = 0
    for besoin in besoins:
        total_des_places_souhaitees += besoin.nombre_souhaite
        total_des_places_couvertes += besoin.places_couvertes()

    if total_des_places_souhaitees == 0:
        return 100
    return round(total_des_places_couvertes * 100 / total_des_places_souhaitees)


def prenom_public(user):
    """
    Le prénom affiché sur le planning public. Jamais l'email, jamais le nom de famille.
    Prénom vide (None ou "") : « Bénévole ».
    / The public first name. Never the email or the last name. Empty → "Bénévole".
    """
    if user.first_name and user.first_name.strip():
        return user.first_name.strip()
    return _("Bénévole")


def plage_horaire(besoin):
    """
    « 18h–21h », « 18h30–21h » ou « Journée ».
    Lit les champs sans fuseau (heure locale saisie), jamais debut() ou fin().
    / "18h–21h" or "Journée". Reads the raw local fields, never debut()/fin().
    """
    if besoin.est_une_journee():
        return _("Journée")
    return f"{_heure(besoin.heure_debut)}–{_heure(besoin.heure_fin)}"


def _heure(une_heure):
    """« 18h » ou « 18h30 ». / "18h" or "18h30"."""
    if une_heure.minute == 0:
        return f"{une_heure.hour}h"
    return f"{une_heure.hour}h{une_heure.minute:02d}"


def etat_du_jour(besoins_du_jour):
    """
    Le texte qui dit l'état d'un jour : « 3 places libres », « tout est couvert »,
    suivi de « · +1 en renfort » s'il y a des renforts.
    La couleur ne porte jamais seule l'information : ce texte l'écrit aussi.
    / The written state of a day. Colour never carries the information alone.
    """
    places_libres = 0
    renforts = 0
    for besoin in besoins_du_jour:
        places_libres += besoin.places_libres()
        renforts += besoin.nombre_de_renforts()

    if places_libres:
        texte = ngettext(
            "%(nombre)s place libre", "%(nombre)s places libres", places_libres
        ) % {"nombre": places_libres}
    else:
        texte = _("tout est couvert")

    if renforts:
        texte += " · " + _("+%(nombre)s en renfort") % {"nombre": renforts}

    return {"texte": texte, "places_libres": places_libres, "renforts": renforts}


def lundi_de_la_semaine(une_date):
    """Le lundi de la semaine de ce jour (le jour lui-même si c'est un lundi). / Monday of that week."""
    return une_date - datetime.timedelta(days=une_date.weekday())


def lire_la_semaine_demandee(texte):
    """
    Le paramètre ?semaine=AAAA-MM-JJ de la page publique, en date. None s'il est absent
    ou illisible : la page montre alors la semaine par défaut.
    / The ?semaine= parameter as a date, or None if missing or unreadable.
    """
    if not texte:
        return None
    try:
        return datetime.date.fromisoformat(texte)
    except ValueError:
        return None


def choisir_la_semaine(semaine_demandee, dates_des_besoins_a_venir, lundi_de_cette_semaine):
    """
    Le lundi de la semaine à afficher sur la page publique (§11.1, D28).
    / The Monday of the week to show on the public page.

    - Une semaine demandée, à partir de la semaine en cours : son lundi (un dimanche
      donne le lundi d'avant).
    - Sinon (absente, illisible, ou passée) : la semaine du prochain besoin à venir,
      ou la semaine en cours s'il n'y en a aucun. Le passé n'est jamais affiché (P6).
    / A requested week from the current one: its Monday. Otherwise the week of the next
      upcoming need, or the current week.

    :param semaine_demandee: une date (n'importe quel jour de la semaine) ou None
    :param dates_des_besoins_a_venir: les dates des besoins à venir, triées
    :param lundi_de_cette_semaine: le lundi de la semaine en cours, au fuseau du lieu
    """
    if semaine_demandee is not None:
        lundi_demande = lundi_de_la_semaine(semaine_demandee)
        if lundi_demande >= lundi_de_cette_semaine:
            return lundi_demande

    # Un besoin du dimanche soir qui finit après minuit est encore « à venir » le lundi,
    # mais sa semaine est passée : on cherche le premier besoin de cette semaine ou après.
    # / A Sunday-night need still running on Monday belongs to a past week: skip it.
    for date_du_besoin in dates_des_besoins_a_venir:
        if date_du_besoin >= lundi_de_cette_semaine:
            return lundi_de_la_semaine(date_du_besoin)
    return lundi_de_cette_semaine


def titre_de_la_semaine(lundi):
    """
    « 20 – 26 octobre », « 27 octobre – 2 novembre », ou avec l'année si la semaine
    est à cheval sur deux années.
    / The week title, with the year only when the week spans two years.
    """
    dimanche = lundi + datetime.timedelta(days=6)
    if lundi.month == dimanche.month:
        return f"{lundi.day} – {date_format(dimanche, 'j F')}"
    if lundi.year == dimanche.year:
        return f"{date_format(lundi, 'j F')} – {date_format(dimanche, 'j F')}"
    return f"{date_format(lundi, 'j F Y')} – {date_format(dimanche, 'j F Y')}"


# ---------------------------------------------------------------------------
# Droits / Rights
# ---------------------------------------------------------------------------

def peut_s_inscrire_au_planning(user, planning, maintenant):
    """
    Vrai si cette personne connectée a le droit de s'inscrire sur ce planning (D3).
    - Planning sans adhésion requise : tout compte connecté.
    - Sinon : une adhésion encore valide (deadline >= maintenant) à l'un des produits.
    / True if this logged-in person may sign up (D3).

    Même contrôle que les tarifs réservés aux adhérents de booking
    (booking/booking_engine.py, bloc price.adhesions_obligatoires), sans la branche
    « adhésion achetée dans la même commande », propre au panier.
    / Same check as booking's members-only prices, without the cart branch.
    """
    if not user.is_authenticated:
        return False

    adhesions_requises = list(planning.adhesions_requises.all())
    if not adhesions_requises:
        return True

    # Une adhésion annulée n'ouvre rien, même si sa date de fin est encore à venir.
    # / A canceled membership opens nothing, even with a future deadline.
    return Membership.objects.filter(
        user=user,
        price__product__in=adhesions_requises,
        deadline__gte=maintenant,
    ).exclude(
        status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
    ).exists()


# ---------------------------------------------------------------------------
# Construction de la page / Page building
# ---------------------------------------------------------------------------

def besoins_a_venir(planning, fuseau_du_lieu=None):
    """
    Les besoins pas encore passés du planning, avec leurs inscriptions préchargées.
    Un besoin est passé quand sa FIN est passée (P6) : il reste visible pendant qu'il a lieu.
    / The not-yet-past needs, with sign-ups prefetched. Past = its END is past.

    La fin dépend du fuseau du lieu : le filtre fin se fait en Python. La requête ne
    garde que les besoins d'hier ou après (un besoin d'hier 21h–2h peut durer encore).
    / The end depends on the venue timezone: fine filtering in Python.

    Le fuseau est lu UNE fois et passé à est_passe() : sinon chaque besoin relirait la
    Configuration (un aller-retour au cache par besoin, des centaines par page).
    / The timezone is read ONCE and passed down: otherwise one cache hit per need.
    """
    if fuseau_du_lieu is None:
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui_au_lieu = timezone.now().astimezone(fuseau_du_lieu).date()
    hier_au_lieu = aujourd_hui_au_lieu - datetime.timedelta(days=1)

    besoins_depuis_hier = (
        planning.besoins.filter(date__gte=hier_au_lieu)
        .select_related("tache")
        .prefetch_related("inscriptions__user")
        .order_by("date", "heure_debut", "tache__name")
    )

    besoins_pas_encore_passes = []
    for besoin in besoins_depuis_hier:
        if not besoin.est_passe(fuseau_du_lieu):
            besoins_pas_encore_passes.append(besoin)
    return besoins_pas_encore_passes


def case_du_besoin(besoin, user, user_peut_s_inscrire, maintenant, user_est_admin=False, fuseau_du_lieu=None):
    """
    Tout ce qu'il faut pour afficher un besoin (une « case ») pour cette personne.
    / Everything needed to display one need (a "cell") for this person.

    LOCALISATION : booking/benevolat.py

    Le champ « action » dit quel bouton afficher (spec §5.2, tableau des états) :
    - "connexion"           : anonyme → « Me connecter pour venir »
    - "reserve"             : connectée sans le droit → « Réservé aux adhérent·es »
    - "je_viens"            : besoin pas encore couvert → bouton principal
    - "je_viens_aussi"      : besoin couvert → bouton secondaire (renfort)
    - "me_retirer"          : déjà inscrite, avant le délai
    - "je_ne_peux_plus"     : déjà inscrite, après le délai (l'équipe sera prévenue)
    En plus, pour un·e admin du lieu : « peut_inscrire_quelqu_un » (lien « Inscrire
    quelqu'un », §5.10).
    """
    inscriptions_dans_l_ordre = sorted(besoin.inscriptions.all(), key=lambda inscription: inscription.created_at)

    personnes_affichees = []
    user_est_inscrit = False
    for inscription in inscriptions_dans_l_ordre:
        c_est_moi = user.is_authenticated and inscription.user_id == user.pk
        if c_est_moi:
            user_est_inscrit = True
        personnes_affichees.append({
            "prenom": _("Toi") if c_est_moi else prenom_public(inscription.user),
            "c_est_moi": c_est_moi,
        })
    # « Toi » en premier : on se repère tout de suite.
    # / "You" first: easy to spot.
    personnes_affichees.sort(key=lambda personne: not personne["c_est_moi"])

    nombre_inscrits = len(inscriptions_dans_l_ordre)
    est_couvert = nombre_inscrits >= besoin.nombre_souhaite

    if not user.is_authenticated:
        action = "connexion"
    elif user_est_inscrit:
        if maintenant < besoin.limite_pour_se_retirer_sans_prevenir(fuseau_du_lieu):
            action = "me_retirer"
        else:
            action = "je_ne_peux_plus"
    elif not user_peut_s_inscrire:
        action = "reserve"
    elif est_couvert:
        action = "je_viens_aussi"
    else:
        action = "je_viens"

    places_libres = besoin.places_libres()
    if places_libres:
        description_des_places = ngettext(
            "Il manque %(nombre)s personne", "Il manque %(nombre)s personnes", places_libres
        ) % {"nombre": places_libres}
    else:
        description_des_places = _("Couvert")

    return {
        "besoin": besoin,
        "tache": besoin.tache,
        "plage": plage_horaire(besoin),
        "jour": besoin.date,
        "personnes": personnes_affichees,
        "nombre_inscrits": nombre_inscrits,
        "places_libres_a_afficher": range(places_libres),
        "renforts": besoin.nombre_de_renforts(),
        "est_couvert": est_couvert,
        "user_est_inscrit": user_est_inscrit,
        "action": action,
        "description_des_places": description_des_places,
        "peut_inscrire_quelqu_un": user_est_admin,
    }


def construire_le_planning(planning, user, user_est_admin=False, semaine=None):
    """
    Prépare la zone du planning : le compteur, la navigation par semaine, la grille
    (desktop) et les jours (mobile) d'UNE semaine (§11.1, D28).
    / Builds the planning zone for ONE week: counter, week navigation, grid, mobile days.

    LOCALISATION : booking/benevolat.py

    FLUX :
    1. Charge TOUS les besoins à venir (une requête + préchargements) : le compteur de
       l'en-tête (D21) porte sur le planning entier, pas sur la semaine affichée.
    2. Choisit la semaine à afficher (choisir_la_semaine) et garde ses besoins.
    3. Calcule une « case » par besoin de la semaine pour cette personne (case_du_besoin).
    4. Range les cases par jour (colonnes) et par tâche (lignes).
    / 1. Load all upcoming needs (global counter). 2. Pick the week. 3. One cell per need
      of the week. 4. Arrange by day and task.

    :param user_est_admin: la personne administre ce lieu (lien « Inscrire quelqu'un ») ;
        calculé par la vue avec TenantAdminPermissionWithRequest, la règle de l'admin.
    :param semaine: un jour de la semaine voulue (date), ou None pour la semaine par défaut.
        Après une action sur un besoin, la vue passe la date de ce besoin.
    :return: dict prêt pour booking/benevolat/partials/zone.html
    """
    maintenant = timezone.now()
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    besoins = besoins_a_venir(planning, fuseau_du_lieu)
    user_peut_s_inscrire = peut_s_inscrire_au_planning(user, planning, maintenant)

    # La semaine affichée, et ses besoins.
    # / The displayed week, and its needs.
    aujourd_hui_au_lieu = maintenant.astimezone(fuseau_du_lieu).date()
    lundi_de_cette_semaine = lundi_de_la_semaine(aujourd_hui_au_lieu)
    dates_des_besoins = [besoin.date for besoin in besoins]
    lundi_affiche = choisir_la_semaine(semaine, dates_des_besoins, lundi_de_cette_semaine)
    dimanche_affiche = lundi_affiche + datetime.timedelta(days=6)

    besoins_de_la_semaine = []
    il_y_a_des_besoins_apres_la_semaine = False
    for besoin in besoins:
        if lundi_affiche <= besoin.date <= dimanche_affiche:
            besoins_de_la_semaine.append(besoin)
        elif besoin.date > dimanche_affiche:
            il_y_a_des_besoins_apres_la_semaine = True

    # « Semaine précédente » : absente sur la semaine en cours (le passé n'est pas affiché).
    # « Semaine suivante » : absente s'il n'y a plus aucun besoin après la semaine.
    # / "Previous" hidden on the current week; "next" hidden when nothing comes after.
    semaine_precedente = None
    if lundi_affiche > lundi_de_cette_semaine:
        semaine_precedente = lundi_affiche - datetime.timedelta(days=7)
    semaine_suivante = None
    if il_y_a_des_besoins_apres_la_semaine:
        semaine_suivante = lundi_affiche + datetime.timedelta(days=7)

    cases_par_besoin = {}
    for besoin in besoins_de_la_semaine:
        cases_par_besoin[besoin.pk] = case_du_besoin(
            besoin, user, user_peut_s_inscrire, maintenant,
            user_est_admin=user_est_admin, fuseau_du_lieu=fuseau_du_lieu,
        )

    # Les jours de la semaine qui ont au moins un besoin, dans l'ordre (déjà triés).
    # / Days of the week with at least one need, in order.
    besoins_par_jour = {}
    for besoin in besoins_de_la_semaine:
        besoins_par_jour.setdefault(besoin.date, []).append(besoin)

    jours = []
    for une_date, besoins_du_jour in besoins_par_jour.items():
        etat = etat_du_jour(besoins_du_jour)
        jours.append({
            "date": une_date,
            "remplissage": taux_de_remplissage(besoins_du_jour),
            "etat": etat["texte"],
            "places_libres": etat["places_libres"],
            "cases": [cases_par_besoin[besoin.pk] for besoin in besoins_du_jour],
        })

    # Les tâches qui ont au moins un besoin cette semaine, triées par nom : ce sont les
    # lignes. Chaque ligne a une cellule par jour, vide (« pas besoin ») ou avec ses besoins.
    # / Tasks with at least one need this week are the rows; one cell per day.
    taches = {}
    for besoin in besoins_de_la_semaine:
        taches[besoin.tache_id] = besoin.tache
    taches_triees = sorted(taches.values(), key=lambda tache: tache.name.lower())

    lignes = []
    for tache in taches_triees:
        cellules = []
        for jour in jours:
            cases_de_cette_tache_ce_jour = []
            for case in jour["cases"]:
                if case["tache"].pk == tache.pk:
                    cases_de_cette_tache_ce_jour.append(case)
            cellules.append(cases_de_cette_tache_ce_jour)
        lignes.append({"tache": tache, "cellules": cellules})

    # Compteur de l'en-tête (D21), sur TOUS les besoins à venir.
    # Un créneau vide = un besoin sans aucune inscription.
    # / Header counter (D21), over ALL upcoming needs. Empty slot = no sign-up at all.
    places_couvertes = 0
    places_souhaitees = 0
    renforts = 0
    creneaux_vides = 0
    for besoin in besoins:
        places_couvertes += besoin.places_couvertes()
        places_souhaitees += besoin.nombre_souhaite
        renforts += besoin.nombre_de_renforts()
        if besoin.nombre_inscrits() == 0:
            creneaux_vides += 1

    if places_souhaitees:
        remplissage_global = round(places_couvertes * 100 / places_souhaitees)
    else:
        remplissage_global = 0

    return {
        "planning": planning,
        "jours": jours,
        "lignes": lignes,
        "il_y_a_des_besoins_a_venir": bool(besoins),
        "semaine": {
            "lundi": lundi_affiche,
            "titre": titre_de_la_semaine(lundi_affiche),
            "precedente": semaine_precedente,
            "suivante": semaine_suivante,
        },
        "compteur": {
            "places_couvertes": places_couvertes,
            "places_souhaitees": places_souhaitees,
            "renforts": renforts,
            "creneaux_vides": creneaux_vides,
            "remplissage": remplissage_global,
        },
    }


def plannings_publies_avec_des_besoins_a_venir():
    """
    Les plannings publiés qui ont au moins un besoin pas encore passé : ceux que la
    page liste (/booking/benevolat/) affiche en cartes. Même règle que
    resumes_des_plannings_a_venir sans horizon, sans calculer les cartes.
    / Published plannings with at least one upcoming need: the list page's cards.

    LOCALISATION : booking/benevolat.py
    Appelée par :
    - booking/sitemap.py (PlanningSitemap) : un planning sans besoin à venir est une
      page quasi vide, il n'est pas déclaré ;
    - BaseBillet/sitemap.py (StaticViewSitemap) et BenevolatViewSet.retrieve : la page
      liste n'existe qu'à partir de deux plannings (avec un seul, elle redirige).

    :return: liste de PlanningBenevole
    """
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui_au_lieu = timezone.now().astimezone(fuseau_du_lieu).date()
    hier_au_lieu = aujourd_hui_au_lieu - datetime.timedelta(days=1)

    # Pré-filtre en base (un besoin depuis hier), puis la vraie règle de fin en Python.
    # / Database pre-filter (a need since yesterday), then the real end rule in Python.
    plannings_avec_des_besoins_recents = PlanningBenevole.objects.filter(
        published=True, besoins__date__gte=hier_au_lieu,
    ).distinct().order_by("name")

    plannings_retenus = []
    for planning in plannings_avec_des_besoins_recents:
        if besoins_a_venir(planning, fuseau_du_lieu):
            plannings_retenus.append(planning)
    return plannings_retenus


def resumes_des_plannings_a_venir(nombre_max, horizon_en_jours=None):
    """
    Les cartes « Coups de main » : une par planning publié qui a au moins un besoin à
    venir. Chaque carte porte son nom, sa période, ses créneaux à remplir, ses places
    libres, et ses 5 prochains jours colorés.
    / "Coups de main" cards: one per published planning with an upcoming need.

    LOCALISATION : booking/benevolat.py
    Appelée par :
    - la balise plannings_benevoles_a_venir (pages/templatetags/pages_tags.py) : accueil V2
      et bloc CMS LISTE, avec horizon_en_jours=10 ;
    - newsletter/collecte.py (bloc « On a besoin de vous »), avec horizon_en_jours=10 ;
    - BenevolatViewSet.list (booking/views_benevolat.py), SANS horizon : la page liste du
      menu montre tous les plannings qui ont des besoins à venir.

    `horizon_en_jours` ne s'applique qu'aux plannings « chaque semaine », dont les besoins
    se répètent : on ne compte que les N prochains jours (aujourd'hui compris), et un
    planning sans besoin dans cet horizon n'a pas de carte (un compteur à 0 afficherait
    « tout est couvert », ce qui serait faux). None = pas d'horizon, on compte tout.
    Un planning à dates fixes compte toujours tous ses besoins à venir.
    / horizon_en_jours only applies to weekly plannings; None = no horizon.

    Un « créneau à remplir » est un besoin (une plage horaire d'une tâche) qui a encore
    au moins une place libre. Les places libres comptent les personnes manquantes.
    / A "slot to fill" is a need with at least one free place.

    Tri : le planning dont le prochain besoin est le plus proche d'abord.

    :return: liste de dicts, au plus nombre_max
    """
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui_au_lieu = timezone.now().astimezone(fuseau_du_lieu).date()
    hier_au_lieu = aujourd_hui_au_lieu - datetime.timedelta(days=1)
    # Dernier jour compté : un horizon de 10 jours va d'aujourd'hui à aujourd'hui + 9.
    # / Last counted day: a 10-day horizon runs from today to today + 9.
    dernier_jour_de_l_horizon = None
    if horizon_en_jours is not None:
        dernier_jour_de_l_horizon = aujourd_hui_au_lieu + datetime.timedelta(days=horizon_en_jours - 1)
    # Seulement les plannings qui ont un besoin depuis hier : les plannings terminés
    # depuis longtemps ne coûtent rien à la page d'accueil.
    # / Only plannings with a need since yesterday: old plannings cost nothing.
    plannings_avec_des_besoins_recents = PlanningBenevole.objects.filter(
        published=True, besoins__date__gte=hier_au_lieu,
    ).distinct()

    resumes = []
    for planning in plannings_avec_des_besoins_recents:
        besoins = besoins_a_venir(planning, fuseau_du_lieu)
        if not besoins:
            continue

        # Planning hebdomadaire avec un horizon : ses besoins se répètent sans fin, on ne
        # compte que l'horizon. Sinon : on compte tous ses besoins à venir.
        # / Weekly planning with a horizon: count the horizon only. Otherwise: count all.
        planning_chaque_semaine = planning.type_de_planning == PlanningBenevole.HEBDOMADAIRE
        if planning_chaque_semaine and dernier_jour_de_l_horizon is not None:
            besoins_comptes = []
            for besoin in besoins:
                if besoin.date <= dernier_jour_de_l_horizon:
                    besoins_comptes.append(besoin)
            if not besoins_comptes:
                continue
        else:
            besoins_comptes = besoins

        places_libres = 0
        creneaux_a_remplir = 0
        for besoin in besoins_comptes:
            places_libres_du_besoin = besoin.places_libres()
            places_libres += places_libres_du_besoin
            if places_libres_du_besoin > 0:
                creneaux_a_remplir += 1

        # Les 5 jours colorés viennent des MÊMES besoins que le compteur : un jour
        # hors horizon afficherait des places absentes du total.
        # / The 5 coloured days come from the SAME needs as the counter.
        besoins_par_jour = {}
        for besoin in besoins_comptes:
            besoins_par_jour.setdefault(besoin.date, []).append(besoin)

        cinq_prochains_jours = []
        for une_date, besoins_du_jour in list(besoins_par_jour.items())[:5]:
            cinq_prochains_jours.append({
                "date": une_date,
                "remplissage": taux_de_remplissage(besoins_du_jour),
                "places_libres": etat_du_jour(besoins_du_jour)["places_libres"],
            })

        resumes.append({
            "planning": planning,
            "premier_jour": besoins[0].date,
            "dernier_jour": besoins[-1].date,
            "places_libres": places_libres,
            "creneaux_a_remplir": creneaux_a_remplir,
            "jours": cinq_prochains_jours,
            "prochain_debut": besoins[0].debut(fuseau_du_lieu),
            # Hebdomadaire : « chaque semaine » au lieu de « du … au … », qui glisserait
            # chaque nuit avec l'horizon. / Weekly: "every week" instead of a sliding range.
            "chaque_semaine": planning_chaque_semaine,
        })

    resumes.sort(key=lambda resume: resume["prochain_debut"])
    return resumes[:nombre_max]


def mes_creneaux_a_venir(user):
    """
    Les inscriptions à venir de cette personne, sur tous les plannings du lieu,
    triées par date, avec l'action de retrait à afficher (« Me retirer » avant le
    délai, « Je ne peux plus venir » après : l'équipe sera prévenue).
    / This person's upcoming sign-ups, sorted, with the withdrawal action.

    LOCALISATION : booking/benevolat.py
    Appelée par MyAccount.my_volunteering (BaseBillet/views.py).
    """
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    maintenant = timezone.now()
    hier_au_lieu = maintenant.astimezone(fuseau_du_lieu).date() - datetime.timedelta(days=1)

    inscriptions = (
        # Planning dépublié : ses créneaux disparaissent d'ici comme de la page publique.
        # / Unpublished planning: its slots disappear here too.
        InscriptionBenevole.objects.filter(
            user=user, besoin__date__gte=hier_au_lieu, besoin__planning__published=True,
        )
        .select_related("besoin__tache", "besoin__planning")
        .order_by("besoin__date", "besoin__heure_debut")
    )

    creneaux = []
    for inscription in inscriptions:
        besoin = inscription.besoin
        if besoin.est_passe(fuseau_du_lieu):
            continue
        creneaux.append({
            "besoin": besoin,
            "plage": plage_horaire(besoin),
            "apres_le_delai": maintenant >= besoin.limite_pour_se_retirer_sans_prevenir(fuseau_du_lieu),
        })
    return creneaux


# ---------------------------------------------------------------------------
# Répéter des besoins (§5.7) / Repeat needs
# ---------------------------------------------------------------------------

def cle_d_un_besoin(tache_id, une_date, heure_debut, heure_fin):
    """
    Ce qui rend deux besoins « identiques » pour « Répéter » : même tâche, même jour,
    mêmes heures (dans un même planning). Le nombre souhaité ne compte pas.
    / What makes two needs identical for "Repeat": same task, day and hours.
    """
    return (tache_id, une_date, heure_debut, heure_fin)


def calculer_repetitions(besoins_modele, ecart_en_jours, nombre_de_fois, periodes_fermees, besoins_existants):
    """
    Calcule les copies de la période modèle, SANS rien écrire en base.
    / Computes the copies of the model period, WITHOUT writing anything.

    LOCALISATION : booking/benevolat.py
    Appelée par l'admin (Administration/admin/benevolat.py, PlanningBenevoleAdmin.repeter)
    et, plus tard, par l'API v2 (POST volunteer-plannings/{id}/repeat/).

    Pour chaque besoin du modèle et pour k de 1 à nombre_de_fois :
    nouvelle date = date du modèle + k × ecart_en_jours. Tâche, heures et nombre
    souhaité sont copiés. Les inscriptions ne sont jamais copiées.
    / For each model need and k in 1..nombre_de_fois: new date = date + k × gap.

    Garde-fous :
    - une copie qui tombe un jour fermé est SAUTÉE (pas décalée) ;
    - une copie identique à un besoin existant (ou à une copie déjà prévue) est IGNORÉE :
      on peut relancer l'action sans rien doubler.
    / A copy on a closed day is skipped; a copy identical to an existing need is ignored.

    :param besoins_modele: les besoins de la période modèle (objets avec tache_id, tache,
        date, heure_debut, heure_fin, nombre_souhaite)
    :param ecart_en_jours: N jours, ou N × 7 pour des semaines (>= 1)
    :param nombre_de_fois: combien de copies de la période (>= 1)
    :param periodes_fermees: les ClosedPeriod du calendrier du planning (liste, peut être vide)
    :param besoins_existants: ensemble de clés cle_d_un_besoin() des besoins déjà en base
    :return: dict avec trois listes de dicts {"modele", "date"} :
        - "a_creer"
        - "sautes" (avec en plus "fermeture" : le libellé de la fermeture)
        - "ignores"
    """
    a_creer = []
    sautes = []
    ignores = []
    # Copie : on y ajoute les copies prévues, sans modifier l'ensemble reçu.
    # / Copy: planned copies are added here, the caller's set is untouched.
    cles_deja_prises = set(besoins_existants)

    for numero_de_la_copie in range(1, nombre_de_fois + 1):
        for besoin_modele in besoins_modele:
            nouvelle_date = besoin_modele.date + datetime.timedelta(days=numero_de_la_copie * ecart_en_jours)
            copie = {"modele": besoin_modele, "date": nouvelle_date}

            periode_fermee = periode_fermee_qui_couvre(periodes_fermees, nouvelle_date)
            if periode_fermee is not None:
                copie["fermeture"] = libelle_d_une_fermeture(periode_fermee)
                sautes.append(copie)
                continue

            cle_de_la_copie = cle_d_un_besoin(
                besoin_modele.tache_id, nouvelle_date, besoin_modele.heure_debut, besoin_modele.heure_fin,
            )
            if cle_de_la_copie in cles_deja_prises:
                ignores.append(copie)
                continue

            cles_deja_prises.add(cle_de_la_copie)
            a_creer.append(copie)

    return {"a_creer": a_creer, "sautes": sautes, "ignores": ignores}


# ---------------------------------------------------------------------------
# Semaine type des plannings hebdomadaires (§11.2, D29 à D30)
# / Template week of weekly plannings
# ---------------------------------------------------------------------------

def besoins_de_la_semaine_type(lignes, du, au, periodes_fermees, besoins_existants):
    """
    Calcule les besoins que la semaine type donne entre deux jours, SANS rien écrire.
    Même principe que calculer_repetitions.
    / Computes the needs the template week gives between two days, WITHOUT writing.

    LOCALISATION : booking/benevolat.py

    Pour chaque jour de du à au (compris) et chaque ligne de ce jour de la semaine
    (date.weekday(), 0 = lundi) : une copie avec la date de ce jour.
    - un jour fermé est SAUTÉ ;
    - une copie identique à un besoin existant (cle_d_un_besoin) est IGNORÉE.
    / One copy per day and matching row; closed days skipped; duplicates ignored.

    :param lignes: les LigneDeSemaineType (objets avec jour_de_la_semaine, tache_id,
        heure_debut, heure_fin, nombre_souhaite)
    :param periodes_fermees: les ClosedPeriod du calendrier du planning (liste, peut être vide)
    :param besoins_existants: ensemble de clés cle_d_un_besoin() des besoins déjà en base
    :return: dict avec trois listes de dicts {"ligne", "date"} : "a_creer", "sautes", "ignores"
    """
    a_creer = []
    sautes = []
    ignores = []
    cles_deja_prises = set(besoins_existants)

    jour = du
    while jour <= au:
        for ligne in lignes:
            if ligne.jour_de_la_semaine != jour.weekday():
                continue
            copie = {"ligne": ligne, "date": jour}

            if periode_fermee_qui_couvre(periodes_fermees, jour) is not None:
                sautes.append(copie)
                continue

            cle_de_la_copie = cle_d_un_besoin(ligne.tache_id, jour, ligne.heure_debut, ligne.heure_fin)
            if cle_de_la_copie in cles_deja_prises:
                ignores.append(copie)
                continue

            cles_deja_prises.add(cle_de_la_copie)
            a_creer.append(copie)
        jour += datetime.timedelta(days=1)

    return {"a_creer": a_creer, "sautes": sautes, "ignores": ignores}


def aujourd_hui_au_lieu():
    """
    La date du jour DANS LE FUSEAU DU LIEU : à 22 h UTC, un lieu en UTC+4 est déjà au
    lendemain.
    / Today's date in the venue timezone.
    """
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    return timezone.now().astimezone(fuseau_du_lieu).date()


def creer_des_besoins_pour_ces_lignes(planning, lignes, du, au):
    """
    Crée en base les besoins de ces lignes entre du et au (compris), d'un seul
    bulk_create. Jours fermés sautés, doublons ignorés (besoins_de_la_semaine_type).
    Chaque besoin créé garde le lien vers sa ligne.
    / Creates these rows' needs between du and au, in one bulk_create.

    :return: le nombre de besoins créés
    """
    if du > au or not lignes:
        return 0

    periodes_fermees = []
    if planning.calendrier_id is not None:
        periodes_fermees = list(planning.calendrier.closed_periods.all())

    besoins_existants = set()
    for besoin in planning.besoins.filter(date__gte=du, date__lte=au):
        besoins_existants.add(cle_d_un_besoin(besoin.tache_id, besoin.date, besoin.heure_debut, besoin.heure_fin))

    calcul = besoins_de_la_semaine_type(lignes, du, au, periodes_fermees, besoins_existants)

    nouveaux_besoins = []
    for copie in calcul["a_creer"]:
        ligne = copie["ligne"]
        nouveaux_besoins.append(BesoinBenevole(
            planning=planning,
            tache_id=ligne.tache_id,
            date=copie["date"],
            heure_debut=ligne.heure_debut,
            heure_fin=ligne.heure_fin,
            nombre_souhaite=ligne.nombre_souhaite,
            ligne_de_semaine_type=ligne,
        ))
    BesoinBenevole.objects.bulk_create(nouveaux_besoins)
    return len(nouveaux_besoins)


def creer_les_besoins_de_la_semaine_type(planning):
    """
    Ouvre les semaines à venir d'un planning hebdomadaire ACTIF : crée les besoins de sa
    semaine type qui manquent dans la fenêtre.
    / Opens the coming weeks of an ACTIVE weekly planning: creates the missing needs.

    LOCALISATION : booking/benevolat.py
    Appelée à l'enregistrement de la fiche (Administration/admin/benevolat.py,
    PlanningBenevoleAdmin.save_related) et chaque nuit (booking/tasks.py,
    creer_les_besoins_des_semaines_types).

    Planning ponctuel ou inactif (published faux) : rien. Réactivé, il reprend à partir
    du jour même : les jours où il était inactif ne sont pas rattrapés.
    / One-off or inactive planning: nothing. Reactivated: resumes from today.

    Fenêtre :
    - du = le plus tard entre aujourd'hui (au lieu) et le lendemain de besoins_crees_jusqu_au ;
    - au = aujourd'hui + horizon_en_semaines.
    Fenêtre vide (du > au) : rien à faire. Sinon besoins_crees_jusqu_au passe à au, qui
    est forcément après l'ancienne valeur (du > ancienne valeur et au >= du) : il ne
    recule jamais. Ce qui est avant n'est jamais recréé : un besoin supprimé à la main
    reste supprimé. Les jours fermés du calendrier du planning sont sautés.
    / Window [du, au]; besoins_crees_jusqu_au moves to au and never goes back.

    INDISPENSABLE : le verrou (select_for_update) sur le planning. L'enregistrement de la
    fiche et la tâche de nuit peuvent tomber ensemble (3 h UTC = 7 h à La Réunion) : la
    seconde attend la première, relit besoins_crees_jusqu_au, et ne trouve plus rien à
    créer. Pas de contrainte d'unicité possible : les heures vides (journée) la rendraient
    inopérante (Django 4.2 n'a pas nulls_distinct).
    / The lock makes a simultaneous second call wait, then find nothing to create.

    :return: le nombre de besoins créés
    """
    with transaction.atomic():
        planning = PlanningBenevole.objects.select_for_update().get(pk=planning.pk)
        if planning.type_de_planning != PlanningBenevole.HEBDOMADAIRE or not planning.published:
            return 0

        aujourd_hui = aujourd_hui_au_lieu()
        du = aujourd_hui
        if planning.besoins_crees_jusqu_au is not None:
            du = max(du, planning.besoins_crees_jusqu_au + datetime.timedelta(days=1))
        au = aujourd_hui + datetime.timedelta(weeks=planning.horizon_en_semaines)
        if du > au:
            return 0

        nombre_de_besoins_crees = creer_des_besoins_pour_ces_lignes(
            planning, list(planning.semaine_type.all()), du, au,
        )
        planning.besoins_crees_jusqu_au = au
        planning.save(update_fields=["besoins_crees_jusqu_au"])
        return nombre_de_besoins_crees


def appliquer_la_semaine_type_modifiee(planning, besoins_des_lignes_supprimees, lignes_modifiees,
                                       lignes_qui_changent_de_jour, lignes_ajoutees):
    """
    Répercute une semaine type modifiée sur les besoins FUTURS (D30), puis ouvre les
    semaines manquantes. Appelée par l'admin APRÈS l'enregistrement des lignes.
    / Applies an edited template week to FUTURE needs (D30), then opens missing weeks.

    LOCALISATION : booking/benevolat.py
    Appelée par Administration/admin/benevolat.py (PlanningBenevoleAdmin.save_related).

    Règle : un besoin qui a des inscrits ne bouge JAMAIS. On le compte, l'admin le dit.
    - Ligne supprimée : ses besoins futurs sans inscrit sont supprimés.
    - Ligne modifiée : ses besoins futurs sans inscrit prennent les nouvelles valeurs ;
      ceux qui ne tombent plus le bon jour de la semaine (la ligne a changé de jour) sont
      supprimés.
    - Ligne ajoutée, ou qui change de jour : ses besoins sont créés d'aujourd'hui à
      besoins_crees_jusqu_au (doublons ignorés), si le planning est actif. La suite vient
      de creer_les_besoins_de_la_semaine_type.
    Les besoins manuels (sans ligne) ne sont jamais touchés.
    / Needs with sign-ups never move. Manual needs are never touched.

    :param besoins_des_lignes_supprimees: les uuid des besoins des lignes supprimées, lus
        AVANT la suppression : après, SET_NULL efface le lien vers la ligne.
    :param lignes_modifiees: les LigneDeSemaineType modifiées (déjà enregistrées)
    :param lignes_qui_changent_de_jour: parmi elles, celles dont le jour a changé
    :param lignes_ajoutees: les LigneDeSemaineType nouvelles (déjà enregistrées)
    :return: dict {"crees", "mis_a_jour", "supprimes", "avec_inscrits"}
    """
    bilan = {"crees": 0, "mis_a_jour": 0, "supprimes": 0, "avec_inscrits": 0}

    with transaction.atomic():
        # Même verrou que la tâche de nuit. / Same lock as the nightly task.
        planning = PlanningBenevole.objects.select_for_update().get(pk=planning.pk)
        aujourd_hui = aujourd_hui_au_lieu()

        # 1. Lignes supprimées / Deleted rows
        besoins_futurs_des_lignes_supprimees = BesoinBenevole.objects.filter(
            pk__in=besoins_des_lignes_supprimees, date__gte=aujourd_hui,
        )
        bilan["avec_inscrits"] += besoins_futurs_des_lignes_supprimees.filter(
            inscriptions__isnull=False,
        ).distinct().count()
        # Candidats à la suppression : ceux qui ont des inscrits sont écartés à l'étape de
        # la suppression (filtre « sans inscrit » plus bas).
        # / Deletion candidates: those with sign-ups are filtered out at delete time.
        uuids_a_supprimer = list(besoins_futurs_des_lignes_supprimees.values_list("pk", flat=True))

        # 2. Lignes modifiées / Edited rows
        for ligne in lignes_modifiees:
            besoins_futurs_de_la_ligne = ligne.besoins.filter(date__gte=aujourd_hui)
            bilan["avec_inscrits"] += besoins_futurs_de_la_ligne.filter(inscriptions__isnull=False).distinct().count()

            uuids_a_mettre_a_jour = []
            for besoin in besoins_futurs_de_la_ligne.filter(inscriptions__isnull=True):
                if besoin.date.weekday() != ligne.jour_de_la_semaine:
                    uuids_a_supprimer.append(besoin.pk)
                else:
                    uuids_a_mettre_a_jour.append(besoin.pk)

            # update() et pas save() : save() détacherait le besoin de sa ligne.
            # / update(), not save(): save() would detach the need from its row.
            bilan["mis_a_jour"] += BesoinBenevole.objects.filter(pk__in=uuids_a_mettre_a_jour).update(
                tache_id=ligne.tache_id,
                heure_debut=ligne.heure_debut,
                heure_fin=ligne.heure_fin,
                nombre_souhaite=ligne.nombre_souhaite,
            )

        # INDISPENSABLE : le filtre « sans inscrit » est posé ICI, au moment de supprimer.
        # Un besoin qui a des inscrits n'est jamais supprimé (ses inscriptions partiraient
        # en cascade), même si une inscription arrive pendant l'enregistrement.
        # / The "no sign-up" filter is applied HERE: a need with sign-ups is never deleted.
        bilan["supprimes"], _detail = BesoinBenevole.objects.filter(
            pk__in=uuids_a_supprimer, inscriptions__isnull=True,
        ).delete()

        # 3. Lignes ajoutées ou changées de jour : jusqu'à la fenêtre déjà ouverte.
        # Un planning inactif ne crée rien.
        # / New rows or rows on a new day: up to the already open window. Inactive: nothing.
        lignes_a_creer = list(lignes_ajoutees) + list(lignes_qui_changent_de_jour)
        ouvert_jusqu_au = planning.besoins_crees_jusqu_au
        planning_actif_et_hebdomadaire = (
            planning.type_de_planning == PlanningBenevole.HEBDOMADAIRE and planning.published
        )
        if planning_actif_et_hebdomadaire and ouvert_jusqu_au is not None and lignes_a_creer:
            bilan["crees"] += creer_des_besoins_pour_ces_lignes(planning, lignes_a_creer, aujourd_hui, ouvert_jusqu_au)

        # 4. Les semaines pas encore ouvertes. / Weeks not yet open.
        bilan["crees"] += creer_les_besoins_de_la_semaine_type(planning)

    return bilan


# ---------------------------------------------------------------------------
# Se retirer, et le lien « Je ne peux plus venir » des mails (§5.4, §5.9)
# / Withdrawing, and the "I can't come anymore" email link
# ---------------------------------------------------------------------------

SEL_DU_LIEN_DE_DESISTEMENT = "benevolat-desistement"


def jeton_de_desistement(inscription):
    """
    Le jeton signé du lien « Je ne peux plus venir » : /booking/benevolat/desistement/<jeton>/.
    / The signed token of the "I can't come anymore" link.

    INDISPENSABLE : on signe l'UUID, jamais un entier. La SECRET_KEY est commune à tous
    les lieux : un entier signé, rejoué sur un autre lieu, y désignerait l'inscription de
    quelqu'un d'autre. Un uuid n'y désigne rien.
    Pas de durée de validité dans le jeton : « expiré » = le besoin est passé.
    / Sign the UUID, never an integer: the SECRET_KEY is shared by all venues.
    """
    return signing.dumps(str(inscription.pk), salt=SEL_DU_LIEN_DE_DESISTEMENT)


def inscription_du_jeton(jeton):
    """
    L'inscription désignée par ce jeton, ou None : jeton faux ou modifié, inscription
    déjà supprimée, ou jeton venu d'un autre lieu (son uuid n'existe pas ici).
    / The sign-up of this token, or None.
    """
    try:
        uuid_de_l_inscription = signing.loads(jeton, salt=SEL_DU_LIEN_DE_DESISTEMENT)
    except signing.BadSignature:
        return None

    try:
        return InscriptionBenevole.objects.select_related(
            "user", "besoin__tache", "besoin__planning",
        ).get(pk=uuid_de_l_inscription)
    except (InscriptionBenevole.DoesNotExist, ValidationError, ValueError):
        return None


def retirer_une_inscription(inscription, nom_pour_l_equipe):
    """
    Supprime l'inscription, et prévient l'équipe si c'est un désistement tardif.
    / Deletes the sign-up, and warns the team on a late withdrawal.

    LOCALISATION : booking/benevolat.py
    Appelée par booking/views_benevolat.py : retirer (bouton du site) et desistement
    (lien du mail). Un seul mécanisme pour les deux.

    L'équipe est prévenue (mail à Configuration.email, après le commit) seulement si :
    - on est après le délai de retrait (debut() - delai_desinscription_heures) ;
    - ET la personne était inscrite AVANT ce délai : l'équipe ne comptait pas sur un
      renfort de dernière minute, et ça empêche une boucle de mails.
    / The team is warned only after the deadline AND if the sign-up predates it.

    :param nom_pour_l_equipe: « Prénom Nom » (ou l'email) de la personne
    :return: True si l'équipe est prévenue
    """
    # Import local : booking/tasks.py importe ce module dans ses fonctions.
    # / Local import: booking/tasks.py imports this module inside its functions.
    from booking.tasks import prevenir_l_equipe_d_un_desistement

    besoin = inscription.besoin
    limite = besoin.limite_pour_se_retirer_sans_prevenir()
    apres_le_delai = timezone.now() >= limite
    etait_inscrite_avant_le_delai = inscription.created_at < limite

    # Supprimer PAR LA BASE et compter : deux retraits simultanés (double clic sur le
    # formulaire du mail, lien et bouton en même temps) chargent la même inscription ;
    # un seul la supprime vraiment, et un seul doit prévenir l'équipe.
    # / Delete through the DB and count: only the request that really deleted warns.
    nombre_supprime, _detail = InscriptionBenevole.objects.filter(pk=inscription.pk).delete()
    prevenir_l_equipe = nombre_supprime > 0 and apres_le_delai and etait_inscrite_avant_le_delai

    if prevenir_l_equipe:
        uuid_du_besoin = str(besoin.pk)
        transaction.on_commit(
            lambda: prevenir_l_equipe_d_un_desistement.delay(uuid_du_besoin, nom_pour_l_equipe)
        )
    return prevenir_l_equipe


# ---------------------------------------------------------------------------
# Inscription par l'équipe (§5.10) et par l'API (§6 bis)
# / Sign-up by the team and by the API
# ---------------------------------------------------------------------------

def compte_d_une_personne_inscrite_par_l_equipe(email, prenom, nom):
    """
    Le compte de la personne que l'équipe (ou une clé API) inscrit : créé s'il n'existe
    pas, et rattaché au lieu, sans mail de connexion (compte inactif, sans mot de passe).
    / The account of the person the team (or an API key) signs up.

    LOCALISATION : booking/benevolat.py
    Appelée par booking/views_benevolat.py (inscrire_une_personne) et
    api_v2/views_benevolat.py (VolunteerSignupViewSet.create).

    Prénom et nom ne sont écrits QUE s'ils sont vides dans le compte : le compte est
    partagé entre les lieux, on ne réécrit pas le nom qu'une personne a choisi.
    Un prénom ou un nom vide (ou None) reçu ici n'écrit rien.
    / First and last name are written ONLY if empty in the account.

    :return: le compte, ou None si l'email est marqué en erreur (get_or_create_user)
    """
    # get_or_create_user rattache le compte au lieu AVANT de tester email_error : on
    # annule ce rattachement si le compte est refusé.
    # / get_or_create_user attaches the account BEFORE checking email_error: roll back.
    with transaction.atomic():
        compte = get_or_create_user(email, send_mail=False)
        if compte is None:
            transaction.set_rollback(True)
            return None

        champs_a_enregistrer = []
        if not (compte.first_name or "").strip() and (prenom or "").strip():
            compte.first_name = prenom.strip()
            champs_a_enregistrer.append("first_name")
        if not (compte.last_name or "").strip() and (nom or "").strip():
            compte.last_name = nom.strip()
            champs_a_enregistrer.append("last_name")
        if champs_a_enregistrer:
            compte.save(update_fields=champs_a_enregistrer)
    return compte

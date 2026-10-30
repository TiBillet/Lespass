"""
Vues du planning des bénévoles : la page publique, s'inscrire, se retirer.
/ Volunteer planning views: public page, sign up, withdraw.

LOCALISATION : booking/views_benevolat.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.2 à §5.4, §6)

Routes (booking/urls.py, préfixe /booking/) :
- GET  benevolat/                        → list     : les plannings à venir (menu du site)
- GET  benevolat/<slug>/                 → retrieve : la page du planning
- POST benevolat/besoin/<uuid>/inscrire/ → inscrire : « Je viens » / « Je viens aussi »
- POST benevolat/besoin/<uuid>/retirer/  → retirer  : « Me retirer » / « Je ne peux plus venir »
- POST benevolat/<slug>/lettre/          → lettre   : inscription à la lettre d'information
- GET/POST benevolat/desistement/<jeton>/ → desistement : le lien « Je ne peux plus venir » des mails
- GET/POST benevolat/besoin/<uuid>/inscrire-une-personne/ → inscrire_une_personne (équipe, §5.10)
- GET  benevolat/besoin/<uuid>/chercher-une-personne/?q= → chercher_une_personne (équipe, §5.10)

FONCTIONNEMENT HTMX :
Chaque bouton d'un besoin poste en htmx et la réponse remplace TOUTE la zone du
planning (#benevolat-planning : compteur, grille desktop, jours mobiles), en outerHTML.
Pourquoi pas la case seule : chaque besoin est affiché deux fois (grille desktop et
liste mobile), et l'en-tête du jour, la barre des jours et le compteur changent aussi.
Re-rendre la zone garde tout juste en une seule réponse, sans swap hors bande
(htmx 1.9 gère mal un <th> hors bande).
/ Every need button posts with htmx and the response replaces the WHOLE planning zone.

La zone montre UNE semaine (§11.1, D28) : ?semaine=AAAA-MM-JJ sur la page, et, après
une action, la semaine du besoin touché. Les liens « semaine précédente / suivante »
rechargent la zone seule (en-tête HX-Target: benevolat-planning).
/ The zone shows ONE week: ?semaine= on the page, the need's week after an action.

La fenêtre « Comment on t'appelle ? » (prénom ou nom manquant, D18) est un <dialog>
de planning.html. La réponse y est redirigée par l'en-tête HX-Retarget, et
l'événement ouvrirModaleBenevolat l'ouvre (HX-Trigger-After-Settle).
/ The name dialog is reached with HX-Retarget, opened by an HX-Trigger event.
"""
import json
import logging

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, serializers, viewsets
from rest_framework.authentication import CSRFCheck

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import HumanUser
from BaseBillet.models import GhostConfig
from BaseBillet.tasks import send_to_ghost_email
from BaseBillet.views import get_context
from booking.benevolat import (
    compte_d_une_personne_inscrite_par_l_equipe,
    construire_le_planning,
    inscription_du_jeton,
    lire_la_semaine_demandee,
    peut_s_inscrire_au_planning,
    plage_horaire,
    plannings_publies_avec_des_besoins_a_venir,
    resumes_des_plannings_a_venir,
    retirer_une_inscription,
)
from booking.models import BesoinBenevole, InscriptionBenevole, PlanningBenevole
from booking.tasks import envoyer_confirmation_benevole
from booking.views import texte_brut_d_un_texte_riche

logger = logging.getLogger(__name__)


def champ_est_vide(valeur):
    """None, "" ou des espaces seulement. / None, "" or whitespace only."""
    return valeur is None or not valeur.strip()


class NomDuBenevoleSerializer(serializers.Serializer):
    """
    Valide la fenêtre « Comment on t'appelle ? ».
    / Validates the "What's your name?" dialog.

    LOCALISATION : booking/views_benevolat.py

    Un champ VIDE dans le compte doit être fourni. Un champ déjà rempli dans le compte
    est ignoré s'il est envoyé : la fenêtre ne réécrit jamais un nom existant.
    Le contexte porte la liste des champs à demander : context["champs_manquants"].
    / An empty account field must be given; a filled one is ignored if sent.
    """
    prenom = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)
    nom = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, donnees):
        champs_manquants = self.context["champs_manquants"]
        erreurs = {}
        if "prenom" in champs_manquants and champ_est_vide(donnees.get("prenom")):
            erreurs["prenom"] = _("Écris ton prénom (ou un surnom).")
        if "nom" in champs_manquants and champ_est_vide(donnees.get("nom")):
            erreurs["nom"] = _("Écris ton nom.")
        # Pas de saut de ligne : le nom finit dans le sujet du mail à l'équipe, et un
        # sujet qui en contient lève BadHeaderError (le mail serait perdu).
        # / No line break: the name ends up in an email subject (BadHeaderError).
        refuser_les_retours_a_la_ligne(donnees, ["prenom", "nom"], erreurs)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return donnees


def champs_du_nom_manquants(user):
    """
    Les champs du nom vides dans le compte : une liste parmi ["prenom", "nom"].
    / The empty name fields of the account.
    """
    champs_manquants = []
    if champ_est_vide(user.first_name):
        champs_manquants.append("prenom")
    if champ_est_vide(user.last_name):
        champs_manquants.append("nom")
    return champs_manquants


def reponse_session_expiree():
    """
    403 avec un toast : sans lui, htmx n'affiche rien et le clic semble sans effet
    (session expirée, page ouverte dans un autre onglet).
    / 403 with a toast, otherwise the click looks like it did nothing.
    """
    reponse = HttpResponse(status=403)
    reponse["HX-Trigger"] = json.dumps({
        "appToast": {"level": "error", "text": str(_("Connecte-toi pour continuer."))},
        # Ouvre le panneau de connexion (écouteur dans planning.html).
        # / Opens the login panel (listener in planning.html).
        "ouvrirLaConnexion": True,
    })
    return reponse


def nom_pour_l_equipe(user):
    """
    « Prénom Nom » pour l'équipe du lieu, ou l'email si les deux sont vides.
    / "First Last" for the venue team, or the email if both are empty.
    """
    morceaux_du_nom = []
    if not champ_est_vide(user.first_name):
        morceaux_du_nom.append(user.first_name.strip())
    if not champ_est_vide(user.last_name):
        morceaux_du_nom.append(user.last_name.strip())
    if morceaux_du_nom:
        return " ".join(morceaux_du_nom)
    return user.email


def refuser_les_retours_a_la_ligne(donnees, noms_des_champs, erreurs):
    """
    Ajoute une erreur pour chaque champ qui contient un retour à la ligne : le nom finit
    dans le sujet d'un mail, et un sujet qui en contient lève BadHeaderError.
    / Adds an error for each field with a line break (it ends up in an email subject).
    """
    for nom_du_champ in noms_des_champs:
        valeur = donnees.get(nom_du_champ) or ""
        if "\n" in valeur or "\r" in valeur:
            erreurs[nom_du_champ] = _("Une seule ligne, sans retour à la ligne.")


class InscriptionParLEquipeSerializer(serializers.Serializer):
    """
    « Inscrire quelqu'un » (§5.10) : soit une personne trouvée par la recherche (user),
    soit une personne nouvelle (email, prénom et nom, les trois obligatoires).
    / Either a found person (user), or a new one (email, first and last name).

    LOCALISATION : booking/views_benevolat.py

    INDISPENSABLE : le pk reçu est revérifié dans HumanUser.objects, qui ne contient que
    les comptes humains rattachés AU LIEU. Un pk forcé vers le compte d'un autre lieu est
    refusé, même si le bouton n'est jamais affiché pour lui.
    / The posted pk is re-checked in HumanUser.objects (this venue's people only).
    """
    user = serializers.UUIDField(required=False)
    email = serializers.EmailField(
        required=False,
        error_messages={"invalid": _("Cette adresse email ne semble pas valide.")},
    )
    prenom = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)
    nom = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, donnees):
        if donnees.get("user"):
            personne_du_lieu = HumanUser.objects.filter(pk=donnees["user"]).first()
            if personne_du_lieu is None:
                raise serializers.ValidationError({"user": _("Cette personne n'est pas connue du lieu.")})
            donnees["personne"] = personne_du_lieu
            return donnees

        erreurs = {}
        if not donnees.get("email"):
            erreurs["email"] = _("Écris son adresse email.")
        if champ_est_vide(donnees.get("prenom")):
            erreurs["prenom"] = _("Écris son prénom.")
        if champ_est_vide(donnees.get("nom")):
            erreurs["nom"] = _("Écris son nom.")
        refuser_les_retours_a_la_ligne(donnees, ["prenom", "nom"], erreurs)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return donnees


def jeton_csrf_valide(request):
    """
    Vérifie le jeton CSRF d'un POST, même pour une personne non connectée.
    / Checks a POST's CSRF token, even for an anonymous visitor.

    INDISPENSABLE : les vues DRF sont exemptées du CSRF, et SessionAuthentication ne le
    revérifie que pour une personne CONNECTÉE. Un POST anonyme passerait donc sans jeton.
    Même vérification que DRF (rest_framework.authentication.CSRFCheck).
    / DRF views are CSRF-exempt and only re-check for logged-in users.
    """
    def ne_rien_faire(requete):
        return None

    verificateur = CSRFCheck(ne_rien_faire)
    requete_django = request._request
    verificateur.process_request(requete_django)
    refus = verificateur.process_view(requete_django, None, (), {})
    return refus is None


def user_est_admin_du_lieu(request):
    """
    Vrai si la personne connectée administre ce lieu. Même règle que l'admin du projet
    (TenantAdminPermissionWithRequest) : superuser, ou admin du lieu actif et humain.
    / Same rule as the project admin: superuser, or an active human admin of the venue.
    """
    return TenantAdminPermissionWithRequest(request)


class EmailDeLaLettreSerializer(serializers.Serializer):
    """Le champ email du bloc « Pas dispo cette fois ? » (§5.8). / Newsletter email field."""
    email = serializers.EmailField(
        error_messages={
            "required": _("Écris ton adresse email."),
            "blank": _("Écris ton adresse email."),
            "invalid": _("Cette adresse email ne semble pas valide."),
        },
    )


def lettre_d_information_active():
    """
    Vrai si le Ghost du lieu est configuré (adresse et clé renseignées).
    ghost_key est chiffrée : on teste sa présence, on ne la déchiffre pas.
    La variable newsletter_active des autres pages est vraie aussi avec Brevo seul,
    alors que send_to_ghost_email ne parle qu'à Ghost : on ne la réutilise pas.
    / True if the venue's Ghost is configured. Not newsletter_active (true with Brevo only).
    """
    ghost_config = GhostConfig.get_solo()
    return bool(ghost_config.ghost_url) and bool(ghost_config.ghost_key)


class BenevolatViewSet(viewsets.ViewSet):
    """
    La page publique d'un planning, et les actions sur ses besoins.
    / A planning's public page, and the actions on its needs.

    LOCALISATION : booking/views_benevolat.py

    AllowAny, puis un contrôle explicite dans chaque action : la page est publique
    (prénoms visibles même sans compte, D2), s'inscrire et se retirer exigent une session.
    / AllowAny, then an explicit check in each action.
    """
    permission_classes = [permissions.AllowAny]

    # ------------------------------------------------------------------
    # Réponses communes / Shared responses
    # ------------------------------------------------------------------

    def _reponse_zone(self, request, planning, semaine, toast_texte=None, toast_niveau="success",
                      fermer_la_fenetre=False, status=200):
        """
        Rend la zone du planning (compteur + grille + jours mobiles) à jour,
        avec un toast facultatif (appToast, BaseBillet/templates/htmx/components/panier_scripts.html).
        / Renders the up-to-date planning zone, with an optional toast.

        :param semaine: la date du besoin touché : la zone montre sa semaine. Une semaine
            déjà passée retombe sur la semaine par défaut (choisir_la_semaine).
        """
        context = construire_le_planning(
            planning, request.user, user_est_admin=user_est_admin_du_lieu(request), semaine=semaine,
        )
        reponse = render(request, "booking/benevolat/partials/zone.html", context, status=status)

        if toast_texte:
            reponse["HX-Trigger"] = json.dumps({
                "appToast": {"level": toast_niveau, "text": str(toast_texte)},
            })
        if fermer_la_fenetre:
            reponse["HX-Trigger-After-Settle"] = json.dumps({"fermerModaleBenevolat": True})
        return reponse

    def _reponse_fenetre_du_nom(self, request, besoin, champs_manquants, erreurs=None, status=200):
        """
        Rend le contenu de la fenêtre « Comment on t'appelle ? » et l'ouvre.
        HX-Retarget envoie la réponse dans le <dialog> au lieu de la zone du planning.
        / Renders the name dialog content and opens it, via HX-Retarget.
        """
        context = {
            "besoin": besoin,
            "demander_le_prenom": "prenom" in champs_manquants,
            "demander_le_nom": "nom" in champs_manquants,
            "erreurs": erreurs or {},
            "valeurs": request.POST,
        }
        reponse = render(request, "booking/benevolat/partials/fenetre_nom.html", context, status=status)
        reponse["HX-Retarget"] = "#benevolat-modale-contenu"
        reponse["HX-Reswap"] = "innerHTML"
        reponse["HX-Trigger-After-Settle"] = json.dumps({"ouvrirModaleBenevolat": True})
        return reponse

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def list(self, request):
        """
        GET /booking/benevolat/ : les plannings publiés qui ont des besoins à venir,
        en cartes (les mêmes que le bloc d'accueil « Coups de main »). C'est la page de
        l'entrée « Bénévolat » du menu du site (BaseBillet/views.py, get_context).
        / The upcoming plannings, as cards; target of the site menu entry.

        Un seul planning à venir : il n'y a rien à choisir, on ouvre directement sa page.
        / Only one upcoming planning: nothing to choose, open its page directly.
        """
        plannings_a_venir = resumes_des_plannings_a_venir(50)

        il_y_a_un_seul_planning = len(plannings_a_venir) == 1
        if il_y_a_un_seul_planning:
            le_seul_planning = plannings_a_venir[0]["planning"]
            return redirect("benevolat-planning", slug=le_seul_planning.slug)

        context = get_context(request)
        context["plannings"] = plannings_a_venir

        # Texte de partage et des moteurs (meta description, og, twitter) : le texte
        # d'introduction de la page en texte brut (texte_brut_d_un_texte_riche),
        # coupé à 20 mots, sinon la phrase affichée par défaut sous le titre (liste.html).
        # / Sharing and search text: the intro text as plain text, else the default sentence.
        config = context["config"]
        introduction_en_texte_brut = texte_brut_d_un_texte_riche(config.description_benevolat_page)
        description_de_la_page_benevolat = Truncator(introduction_en_texte_brut).words(20)
        if not description_de_la_page_benevolat:
            description_de_la_page_benevolat = _(
                "Les coups de main dont le lieu a besoin. Choisis un planning, puis une case : c'est noté."
            )
        context["description_de_la_page_benevolat"] = description_de_la_page_benevolat
        return render(request, "booking/benevolat/liste.html", context)

    def retrieve(self, request, slug=None):
        """
        GET /booking/benevolat/<slug>/?semaine=AAAA-MM-JJ : la page publique du planning
        (§5.2), une semaine à la fois (§11.1).
        Un planning non publié n'existe pas pour le public (404).
        / The planning public page, one week at a time. Unpublished = 404.

        Les liens « semaine précédente / suivante » de la zone font un hx-get qui cible
        #benevolat-planning : on ne rend alors que la zone. Toute autre requête (lien
        ouvert à la main, retour arrière que htmx refait sans HX-Target) reçoit la page.
        / Week links target #benevolat-planning: render the zone only. Anything else
        gets the full page.
        """
        planning = get_object_or_404(
            PlanningBenevole.objects.prefetch_related("adhesions_requises"),
            slug=slug,
            published=True,
        )
        semaine_demandee = lire_la_semaine_demandee(request.GET.get("semaine"))
        zone_du_planning = construire_le_planning(
            planning, request.user, user_est_admin=user_est_admin_du_lieu(request), semaine=semaine_demandee,
        )

        requete_de_la_zone_seule = request.headers.get("HX-Target") == "benevolat-planning"
        if requete_de_la_zone_seule:
            return render(request, "booking/benevolat/partials/zone.html", zone_du_planning)

        context = get_context(request)
        context.update(zone_du_planning)
        context["adhesions_requises"] = list(planning.adhesions_requises.all())
        context["lettre_active"] = lettre_d_information_active()

        # Texte de partage et des moteurs (meta description, og, twitter) : la
        # présentation du planning coupée à 20 mots, sinon la phrase de la page liste.
        # La présentation est du texte simple (rendu |linebreaks) : pas de balises.
        # / Sharing and search text: the planning presentation, 20 words, else the list sentence.
        description_du_planning = Truncator(" ".join(planning.description.split())).words(20)
        if not description_du_planning:
            description_du_planning = _(
                "Les coups de main dont le lieu a besoin. Choisis un planning, puis une case : c'est noté."
            )
        context["description_du_planning"] = description_du_planning

        # Le fil d'Ariane passe par la page liste seulement si elle existe : avec un
        # seul planning à venir, /booking/benevolat/ redirige vers ce planning.
        # / The breadcrumb goes through the list only when it is a real page.
        context["plusieurs_plannings_a_venir"] = len(plannings_publies_avec_des_besoins_a_venir()) > 1
        return render(request, "booking/benevolat/planning.html", context)

    def inscrire(self, request, pk=None):
        """
        POST /booking/benevolat/besoin/<uuid>/inscrire/ : « Je viens » (§5.3).
        / Sign up for a need.

        FLUX :
        1. Session obligatoire (403 sinon).
        2. Planning publié (404 sinon), besoin pas passé et droit d'accès (422 sinon).
           Pas de contrôle du nombre d'inscrits : on peut venir en renfort (D7).
        3. Prénom ou nom vide dans le compte (D18) :
           - premier clic : on ouvre la fenêtre, rien n'est inscrit ;
           - envoi de la fenêtre (champ caché « fenetre_nom ») : on valide, on enregistre
             les champs manquants dans le compte, puis on continue.
        4. get_or_create : un double clic ne crée qu'une inscription (contrainte d'unicité).
        5. Mail de confirmation après le commit, seulement si l'inscription est neuve.
        6. Réponse : la zone du planning à jour + toast.
        """
        if not request.user.is_authenticated:
            return reponse_session_expiree()

        besoin = get_object_or_404(
            BesoinBenevole.objects.select_related("planning", "tache"),
            pk=pk,
            planning__published=True,
        )
        planning = besoin.planning

        # Le formulaire de la fenêtre du nom poste ici avec fenetre_nom=1. Si la réponse
        # est un refus, la fenêtre doit se fermer : la zone se met à jour derrière elle.
        # / The name dialog posts with fenetre_nom=1; a refusal must close it.
        vient_de_la_fenetre = request.POST.get("fenetre_nom") == "1"

        if besoin.est_passe():
            return self._reponse_zone(
                request, planning, besoin.date, toast_texte=_("Ce créneau est passé."), toast_niveau="error",
                fermer_la_fenetre=vient_de_la_fenetre, status=422,
            )

        if not peut_s_inscrire_au_planning(request.user, planning, timezone.now()):
            return self._reponse_zone(
                request, planning, besoin.date,
                toast_texte=_("Ce planning est réservé aux adhérent·es."), toast_niveau="error",
                fermer_la_fenetre=vient_de_la_fenetre, status=422,
            )

        champs_manquants = champs_du_nom_manquants(request.user)

        if champs_manquants and not vient_de_la_fenetre:
            return self._reponse_fenetre_du_nom(request, besoin, champs_manquants)

        if champs_manquants and vient_de_la_fenetre:
            serializer = NomDuBenevoleSerializer(
                data=request.POST, context={"champs_manquants": champs_manquants},
            )
            if not serializer.is_valid():
                erreurs = {}
                for nom_du_champ, messages_d_erreur in serializer.errors.items():
                    erreurs[nom_du_champ] = messages_d_erreur[0]
                return self._reponse_fenetre_du_nom(
                    request, besoin, champs_manquants, erreurs=erreurs, status=422,
                )

            # Seuls les champs vides du compte sont écrits. Le compte est partagé entre
            # les lieux (AuthBillet en SHARED_APPS) : c'est voulu, c'est le même compte.
            # / Only the empty account fields are written.
            champs_a_enregistrer = []
            if "prenom" in champs_manquants:
                request.user.first_name = serializer.validated_data["prenom"]
                champs_a_enregistrer.append("first_name")
            if "nom" in champs_manquants:
                request.user.last_name = serializer.validated_data["nom"]
                champs_a_enregistrer.append("last_name")
            request.user.save(update_fields=champs_a_enregistrer)

        # get_or_create crée la ligne dans un point de sauvegarde. Si un second clic
        # simultané a déjà créé la même ligne, la contrainte d'unicité lève une
        # IntegrityError : get_or_create la rattrape et relit la ligne existante.
        # / get_or_create catches the IntegrityError of a simultaneous double click.
        inscription, inscription_vient_d_etre_creee = InscriptionBenevole.objects.get_or_create(
            besoin=besoin,
            user=request.user,
        )

        if inscription_vient_d_etre_creee:
            uuid_de_l_inscription = str(inscription.pk)
            transaction.on_commit(lambda: envoyer_confirmation_benevole.delay(uuid_de_l_inscription))

        return self._reponse_zone(
            request, planning, besoin.date,
            toast_texte=_("C'est noté, merci ! Un mail de confirmation arrive."),
            fermer_la_fenetre=vient_de_la_fenetre,
        )

    def _reponse_du_retrait(self, request, besoin, toast_texte=None, toast_niveau="success", status=200):
        """
        La réponse d'un retrait dépend de la page d'où il vient :
        - la page du planning : la zone du planning à jour ;
        - « Mes créneaux » (champ depuis=mes_creneaux) : une réponse vide, que la ligne du
          créneau remplace (elle disparaît), avec le toast.
        / The page of origin picks the response: planning zone, or an empty body that
        replaces the "My shifts" row.
        """
        vient_de_mes_creneaux = request.POST.get("depuis") == "mes_creneaux"
        if not vient_de_mes_creneaux:
            return self._reponse_zone(
                request, besoin.planning, besoin.date,
                toast_texte=toast_texte, toast_niveau=toast_niveau, status=status,
            )

        reponse = HttpResponse("", status=status)
        if toast_texte:
            reponse["HX-Trigger"] = json.dumps({
                "appToast": {"level": toast_niveau, "text": str(toast_texte)},
            })
        return reponse

    def retirer(self, request, pk=None):
        """
        POST /booking/benevolat/besoin/<uuid>/retirer/ : « Me retirer » (§5.4).
        Appelée depuis la page du planning ou depuis « Mes créneaux » (§5.5).
        / Withdraw from a need, from the planning page or from "My shifts".

        - Avant le délai (debut() - delai_desinscription_heures) : retrait silencieux.
        - Après le délai : le retrait marche aussi, et l'équipe est prévenue par mail (P10).
        - Besoin passé : refusé (422).
        On ne supprime que l'inscription de la personne connectée.
        / Only the logged-in person's own sign-up is deleted.
        """
        if not request.user.is_authenticated:
            return reponse_session_expiree()

        besoin = get_object_or_404(
            BesoinBenevole.objects.select_related("planning", "tache"),
            pk=pk,
            planning__published=True,
        )
        if besoin.est_passe():
            return self._reponse_du_retrait(
                request, besoin, toast_texte=_("Ce créneau est passé."), toast_niveau="error", status=422,
            )

        inscription_de_la_personne = InscriptionBenevole.objects.filter(
            besoin=besoin, user=request.user,
        ).first()
        if inscription_de_la_personne is None:
            # Déjà retirée (double clic, autre onglet) : on montre l'état réel.
            # / Already withdrawn: show the real state.
            return self._reponse_du_retrait(request, besoin)

        # Même mécanisme que le lien du mail (desistement) : booking/benevolat.py.
        # / Same mechanism as the email link.
        l_equipe_est_prevenue = retirer_une_inscription(
            inscription_de_la_personne, nom_pour_l_equipe(request.user),
        )
        if l_equipe_est_prevenue:
            return self._reponse_du_retrait(
                request, besoin, toast_texte=_("C'est noté. L'équipe est prévenue, merci de l'avoir dit."),
            )

        return self._reponse_du_retrait(request, besoin, toast_texte=_("Tu n'es plus sur ce créneau."))

    def lettre(self, request, slug=None):
        """
        POST /booking/benevolat/<slug>/lettre/ : « Je m'inscris à la lettre d'information » (§5.8).
        / Subscribe to the venue newsletter from the planning page.

        Ouvert à tout le monde, connecté·e ou non (D13) : même chemin que la case
        « newsletter » des formulaires, send_to_ghost_email, avec l'étiquette Ghost
        « Bénévolat » en plus. Aucun compte TiBillet n'est créé : seul un membre Ghost l'est.
        Limite connue et acceptée (D13) : n'importe qui peut abonner l'email d'une autre
        personne.
        / Open to anyone (D13). No TiBillet account is created, only a Ghost member.

        Réponse : le bloc de la lettre (partials/lettre.html), avec le message de réussite,
        ou en 422 avec l'erreur de saisie.
        """
        planning = get_object_or_404(PlanningBenevole, slug=slug, published=True)
        if not jeton_csrf_valide(request):
            return HttpResponse(status=403)
        if not lettre_d_information_active():
            return HttpResponse(status=404)

        serializer = EmailDeLaLettreSerializer(data=request.POST)
        if not serializer.is_valid():
            context = {
                "planning": planning,
                "erreur": serializer.errors["email"][0],
                "email_saisi": request.POST.get("email", ""),
            }
            return render(request, "booking/benevolat/partials/lettre.html", context, status=422)

        email = serializer.validated_data["email"]
        nom = ""
        if request.user.is_authenticated:
            nom = nom_pour_l_equipe(request.user)
            if nom == request.user.email:
                nom = ""
        send_to_ghost_email.delay(email, nom, etiquettes_en_plus=["Bénévolat"])

        context = {"planning": planning, "email_inscrit": email}
        return render(request, "booking/benevolat/partials/lettre.html", context)

    # ------------------------------------------------------------------
    # Le lien « Je ne peux plus venir » des mails (§5.9)
    # ------------------------------------------------------------------

    def desistement(self, request, jeton=None):
        """
        GET/POST /booking/benevolat/desistement/<jeton>/ : le lien des mails de confirmation
        et de rappel. Marche sans être connecté·e : le jeton signé est la preuve.
        / The email link. Works without login: the signed token is the proof.

        - GET = une page de confirmation, JAMAIS une suppression : les antivirus et les
          messageries ouvrent souvent les liens des mails tout seuls.
        - POST (formulaire avec {% csrf_token %}) = le retrait, même après le délai.
          Après le délai, l'équipe est prévenue (même règle que « Me retirer »).
        - Jeton faux, d'un autre lieu, inscription déjà supprimée, planning dépublié ou
          besoin passé : « Ce lien ne marche plus » (jamais d'erreur 500).
        / GET shows a confirmation; POST withdraws; a dead link gets a friendly page.
        """
        inscription = inscription_du_jeton(jeton)
        lien_valide = (
            inscription is not None
            and inscription.besoin.planning.published
            and not inscription.besoin.est_passe()
        )

        context = get_context(request)
        context["lien_valide"] = lien_valide
        if not lien_valide:
            return render(request, "booking/benevolat/desistement.html", context)

        besoin = inscription.besoin
        context["besoin"] = besoin
        context["plage"] = plage_horaire(besoin)

        if request.method == "POST":
            if not jeton_csrf_valide(request):
                # La page a été ouverte il y a longtemps, ou les cookies sont bloqués :
                # on la ré-affiche avec un message, au lieu d'une page blanche.
                # / Stale page or blocked cookies: show it again with a message.
                context["page_perimee"] = True
                return render(request, "booking/benevolat/desistement.html", context, status=403)
            context["equipe_prevenue"] = retirer_une_inscription(inscription, nom_pour_l_equipe(inscription.user))
            context["retrait_fait"] = True

        return render(request, "booking/benevolat/desistement.html", context)

    # ------------------------------------------------------------------
    # Inscrire quelqu'un à sa place (§5.10) — équipe du lieu seulement
    # ------------------------------------------------------------------

    def _reponse_fenetre_de_l_equipe(self, request, besoin, erreurs=None, montrer_la_creation=False, status=200):
        """
        Le contenu de la fenêtre « Inscrire quelqu'un », envoyé dans le <dialog> par
        HX-Retarget, et ouvert par ouvrirModaleBenevolat (même mécanisme que la fenêtre du nom).
        / The "Sign someone up" dialog content, same mechanism as the name dialog.
        """
        context = {
            "besoin": besoin,
            "plage": plage_horaire(besoin),
            "erreurs": erreurs or {},
            "valeurs": request.POST,
            "montrer_la_creation": montrer_la_creation,
        }
        reponse = render(request, "booking/benevolat/partials/inscrire_une_personne.html", context, status=status)
        reponse["HX-Retarget"] = "#benevolat-modale-contenu"
        reponse["HX-Reswap"] = "innerHTML"
        reponse["HX-Trigger-After-Settle"] = json.dumps({"ouvrirModaleBenevolat": True})
        return reponse

    def inscrire_une_personne(self, request, pk=None):
        """
        GET  /booking/benevolat/besoin/<uuid>/inscrire-une-personne/ : la fenêtre.
        POST : l'inscription d'une personne trouvée (user) ou nouvelle (email, prénom, nom).
        / GET: the dialog. POST: sign up a found or a new person.

        FLUX DU POST :
        1. Admin du lieu, revérifié ici (403 sinon) : cacher le lien ne protège rien.
        2. Planning publié (404), besoin pas passé (422). PAS de contrôle d'adhésion :
           l'équipe décide qui elle inscrit.
        3. Personne nouvelle : compte_d_une_personne_inscrite_par_l_equipe (booking/benevolat.py)
           la rattache au lieu (compte inactif sans mot de passe) et n'écrit prénom et nom
           que s'ils sont vides. None si l'email est marqué en erreur.
        4. get_or_create avec inscrit_par = l'admin ; mail de confirmation « L'équipe t'a
           inscrit·e », avec le lien de désistement signé, seulement si l'inscription est neuve.
        Limite assumée (comme D13) : un·e admin peut rattacher n'importe quel email au lieu
        et lui faire envoyer ce mail.
        """
        if not user_est_admin_du_lieu(request):
            return HttpResponse(status=403)

        besoin = get_object_or_404(
            BesoinBenevole.objects.select_related("planning", "tache"),
            pk=pk,
            planning__published=True,
        )

        if request.method == "GET":
            return self._reponse_fenetre_de_l_equipe(request, besoin)

        if besoin.est_passe():
            return self._reponse_zone(
                request, besoin.planning, besoin.date, toast_texte=_("Ce créneau est passé."), toast_niveau="error",
                fermer_la_fenetre=True, status=422,
            )

        serializer = InscriptionParLEquipeSerializer(data=request.POST)
        if not serializer.is_valid():
            erreurs = {}
            for nom_du_champ, messages_d_erreur in serializer.errors.items():
                erreurs[nom_du_champ] = messages_d_erreur[0]
            montrer_la_creation = "user" not in request.POST
            return self._reponse_fenetre_de_l_equipe(
                request, besoin, erreurs=erreurs, montrer_la_creation=montrer_la_creation, status=422,
            )

        personne = serializer.validated_data.get("personne")
        if personne is None:
            personne = compte_d_une_personne_inscrite_par_l_equipe(
                serializer.validated_data["email"],
                serializer.validated_data["prenom"],
                serializer.validated_data["nom"],
            )
            if personne is None:
                return self._reponse_fenetre_de_l_equipe(
                    request, besoin,
                    erreurs={"email": _("Cet email ne fonctionne pas : un mail envoyé à cette adresse est revenu en erreur.")},
                    montrer_la_creation=True, status=422,
                )

        inscription, inscription_vient_d_etre_creee = InscriptionBenevole.objects.get_or_create(
            besoin=besoin,
            user=personne,
            defaults={"inscrit_par": request.user},
        )

        if inscription_vient_d_etre_creee:
            uuid_de_l_inscription = str(inscription.pk)
            transaction.on_commit(
                lambda: envoyer_confirmation_benevole.delay(uuid_de_l_inscription, par_l_equipe=True)
            )
            toast_texte = _("%(nom)s (%(email)s) est inscrit·e.") % {
                "nom": nom_pour_l_equipe(personne), "email": personne.email,
            }
        else:
            toast_texte = _("%(nom)s (%(email)s) était déjà inscrit·e.") % {
                "nom": nom_pour_l_equipe(personne), "email": personne.email,
            }

        return self._reponse_zone(
            request, besoin.planning, besoin.date, toast_texte=toast_texte, fermer_la_fenetre=True,
        )

    def chercher_une_personne(self, request, pk=None):
        """
        GET /booking/benevolat/besoin/<uuid>/chercher-une-personne/?q= : les résultats de la
        recherche de la fenêtre « Inscrire quelqu'un ».
        / Search results of the "Sign someone up" dialog.

        INDISPENSABLE : la recherche porte sur HumanUser.objects, qui ne renvoie que les
        comptes humains rattachés au lieu (client_achat). Les comptes des autres lieux ne
        sortent jamais, même en tapant leur email exact.
        Au moins 2 caractères ; 10 résultats au plus, triés par nom puis prénom.
        / HumanUser.objects only holds this venue's people.
        """
        if not user_est_admin_du_lieu(request):
            return HttpResponse(status=403)

        besoin = get_object_or_404(BesoinBenevole, pk=pk, planning__published=True)
        texte_cherche = (request.GET.get("q") or "").strip()

        texte_trop_court = len(texte_cherche) < 2
        personnes = []
        if not texte_trop_court:
            personnes = list(
                HumanUser.objects.filter(
                    Q(first_name__icontains=texte_cherche)
                    | Q(last_name__icontains=texte_cherche)
                    | Q(email__icontains=texte_cherche)
                ).order_by("last_name", "first_name")[:10]
            )

        pk_des_inscrits = set(besoin.inscriptions.values_list("user_id", flat=True))
        resultats = []
        for personne in personnes:
            resultats.append({
                "personne": personne,
                "nom_affiche": nom_pour_l_equipe(personne),
                "deja_inscrite": personne.pk in pk_des_inscrits,
            })

        context = {
            "besoin": besoin,
            "resultats": resultats,
            "texte_trop_court": texte_trop_court,
        }
        return render(request, "booking/benevolat/partials/resultats_personnes.html", context)

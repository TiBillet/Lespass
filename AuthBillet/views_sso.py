"""
Vues du guichet de connexion commun à tous les lieux (SSO).
/ Views of the login desk shared by all venues (SSO).

LOCALISATION : AuthBillet/views_sso.py
Routes : TiBillet/urls_public.py (schéma `public` seulement).
Gabarits : AuthBillet/templates/sso/

LES TROIS ROUTES :
- GET  /sso/?lieu=<domaine>&state=<state> : la page du guichet.
  Personne déjà connectée sur le guichet → ticket et retour immédiat au lieu.
  Sinon → étape 1 (email).
- POST /sso/code/ : étape 1 → envoie un code à 6 chiffres → étape 2.
- POST /sso/code/verifier/ : étape 2 → vérifie le code, finalise le compte,
  connecte sur le guichet, renvoie vers le lieu avec un ticket.
/ GET /sso/ shows the desk (or redirects at once if already logged in),
POST /sso/code/ sends a code, POST /sso/code/verifier/ checks it.

RIEN N'EST GARDÉ DANS LA SESSION DU GUICHET : `lieu` et `state` voyagent dans
des champs cachés des formulaires. Le guichet revérifie `lieu` à chaque requête.
Deux onglets ouverts pour deux lieux ne se mélangent pas.
/ Nothing is stored in the desk session: lieu and state travel in hidden
fields, and lieu is checked again on every request.

RÉPONSES HTMX : toujours 200 avec le partiel, le message d'erreur dedans.
htmx ne remplace pas le contenu d'une réponse 4xx. Jamais de Http404.
/ htmx answers are always 200 with the partial (htmx ignores 4xx bodies).

Spec : TECH_DOC/SESSIONS/OTP/CHANTIER-02-connexion-par-code-guichet.md (§5.3, §5.4).
"""

import logging
from urllib.parse import urlencode

from django.contrib.auth import login
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import HttpResponseClientRedirect
from django_tenants.utils import tenant_context
from rest_framework import serializers

from AuthBillet.connexion_par_code import (
    envoyer_un_code_de_connexion,
    verifier_le_code_de_connexion,
)
from AuthBillet.models import TibilletUser
from AuthBillet.sso import fabriquer_un_ticket, trouver_le_lieu_du_domaine
from AuthBillet.utils import get_client_ip, get_or_create_user
from BaseBillet.models import Configuration, Reservation
from BaseBillet.validators import LoginEmailValidator

logger = logging.getLogger(__name__)


# Le projet n'a qu'un backend d'authentification. L'écrire évite une erreur
# le jour où on en ajoute un autre (login() exige alors le backend).
# / Explicit backend: login() would fail if a second backend were added.
BACKEND_DE_CONNEXION = "django.contrib.auth.backends.ModelBackend"

# La page du guichet prend l'habillage du lieu qui envoie la personne : un
# gabarit par skin (pages.ConfigurationSite.skin). Un skin absent de ce
# dictionnaire, ou un lieu inconnu, prend l'habillage V2 (le skin par défaut).
# / The desk page takes the look of the sending venue: one template per skin.
GABARIT_DU_GUICHET_PAR_SKIN = {
    "V2": "sso/guichet_V2.html",
    "reunion": "sso/guichet_reunion.html",
    "faire_festival": "sso/guichet_faire_festival.html",
}
GABARIT_DU_GUICHET_PAR_DEFAUT = "sso/guichet_V2.html"
PARTIEL_ETAPE_EMAIL = "sso/partials/etape_email.html"
PARTIEL_ETAPE_CODE = "sso/partials/etape_code.html"
PARTIEL_ERREUR = "sso/partials/erreur.html"
PARTIEL_CONSENTEMENT = "sso/partials/etape_consentement.html"

# Message de l'étape 2 pour chaque réponse de verifier_le_code_de_connexion.
# / Step 2 message for each answer of verifier_le_code_de_connexion.
MESSAGE_CODE_INCORRECT = _("Code incorrect. Vérifiez le code reçu par mail.")
MESSAGES_D_ERREUR_DU_CODE = {
    "faux": MESSAGE_CODE_INCORRECT,
    "bloque": _("Trop d'essais. Demandez un nouveau code."),
    "expire": _("Ce code a expiré. Demandez un nouveau code."),
}


# --- Validation des données reçues / Validation of received data ---


class ParametresDuLieuSerializer(serializers.Serializer):
    """
    Les deux paramètres qui accompagnent la personne d'un bout à l'autre du
    guichet : le domaine du lieu et le `state` posé par le lieu.
    / The two parameters carried through the whole desk: venue domain and state.

    `lieu` : un domaine fait au plus 253 caractères.
    `state` : `secrets.token_urlsafe(32)` côté lieu, soit 43 caractères.
    Le guichet ne le lit pas : il le rend au lieu, qui le compare.
    / lieu: a domain is at most 253 chars. state: opaque for the desk.
    """

    lieu = serializers.CharField(max_length=253)
    state = serializers.CharField(max_length=128)


class CodeSaisiSerializer(serializers.Serializer):
    """
    Étape 2 : l'email (champ caché) et le code tapé (6 chiffres).
    Les paramètres du lieu sont validés à part, par ParametresDuLieuSerializer.
    / Step 2: email (hidden field) and typed code. Venue parameters are
    validated separately.
    """

    email = serializers.EmailField()
    code = serializers.RegexField(regex=r"^\d{6}$")


# --- Petites fonctions de la vue / Small view helpers ---


def lire_l_habillage_du_lieu(lieu, domaine_du_lieu: str) -> dict:
    """
    Ce qu'il faut pour habiller le guichet aux couleurs du lieu.
    / What the desk needs to wear the venue's look.

    Lu dans le tenant_context du lieu : le guichet tourne sur le schéma
    `public`, où Configuration et ConfigurationSite n'existent pas.

    Les adresses sont ABSOLUES, sur le domaine du lieu : le guichet est sur un
    autre domaine, un lien relatif mènerait au guichet. Le logo est servi par
    le lieu, comme sur ses propres pages.
    / Read in the venue's tenant_context. URLs are absolute, on the venue domain.

    :return: dict avec skin, nom_du_lieu, url_du_lieu, url_du_logo ("" sans logo)
    """
    from pages.models import ConfigurationSite

    with tenant_context(lieu):
        configuration_du_lieu = Configuration.get_solo()
        configuration_du_site = ConfigurationSite.get_solo()

        url_du_logo = ""
        if configuration_du_lieu.logo:
            url_du_logo = f"https://{domaine_du_lieu}{configuration_du_lieu.logo.med.url}"

        return {
            "skin": configuration_du_site.skin,
            "nom_du_lieu": configuration_du_lieu.organisation,
            "url_du_lieu": f"https://{domaine_du_lieu}/",
            "url_du_logo": url_du_logo,
        }


def le_compte_connait_deja_le_lieu(user, lieu) -> bool:
    """
    Le lieu connaît-il déjà ce compte ?
    / Does the venue already know this account?

    `client_achat` liste les lieux qui ont déjà le compte : connexion acceptée sur
    ce lieu (connexion_retour l'ajoute), achat, adhésion, caisse, admin...
    La table est sur le schéma `public` (AuthBillet est une app partagée) : le
    guichet la lit sans tenant_context.
    / client_achat lists the venues that already have the account. Shared table.
    """
    return user.client_achat.filter(pk=lieu.pk).exists()


def choisir_le_gabarit_du_guichet(habillage) -> str:
    """
    Le gabarit de page du guichet pour cet habillage (un par skin).
    / The desk page template for this look (one per skin).

    :param habillage: dict de lire_l_habillage_du_lieu, ou None (lieu inconnu)
    """
    if habillage is None:
        return GABARIT_DU_GUICHET_PAR_DEFAUT

    skin_du_lieu = habillage["skin"]
    if skin_du_lieu in GABARIT_DU_GUICHET_PAR_SKIN:
        return GABARIT_DU_GUICHET_PAR_SKIN[skin_du_lieu]
    return GABARIT_DU_GUICHET_PAR_DEFAUT


def rendre_la_page_d_erreur(request, habillage=None):
    """
    Page « Lien de connexion invalide », habillée si le lieu est connu.
    / "Invalid login link" page, with the venue look when the venue is known.
    """
    contexte = {"partiel": PARTIEL_ERREUR, "habillage": habillage}
    return render(request, choisir_le_gabarit_du_guichet(habillage), context=contexte)


def fabriquer_l_url_de_retour_vers_le_lieu(
    domaine_du_lieu: str, ticket: str, state: str
) -> str:
    """
    URL de retour vers le lieu, construite par le guichet lui-même.
    / Return URL to the venue, built by the desk itself.

    Le guichet ne reçoit jamais une URL complète : seulement un domaine, déjà
    vérifié par trouver_le_lieu_du_domaine. Toujours `https://` : en dev aussi,
    traefik sert `https://*.tibillet.localhost`.
    / Only a checked domain is received, never a full URL. Always https.
    """
    parametres_du_retour = urlencode({"ticket": ticket, "state": state})
    return f"https://{domaine_du_lieu}/connexion/retour/?{parametres_du_retour}"


def fabriquer_le_lien_changer_d_adresse(domaine_du_lieu: str, state: str) -> str:
    """
    Lien « Changer d'adresse » : la page du guichet, à l'étape 1.
    / "Change address" link: the desk page, back to step 1.
    """
    parametres_du_lien = urlencode({"lieu": domaine_du_lieu, "state": state})
    return f"/sso/?{parametres_du_lien}"


def rendre_l_etape_email(request, domaine_du_lieu, state, email="", erreur_email=""):
    """Partiel de l'étape 1. / Step 1 partial."""
    contexte = {
        "lieu": domaine_du_lieu,
        "state": state,
        "email": email,
        "erreur_email": erreur_email,
    }
    return render(request, PARTIEL_ETAPE_EMAIL, context=contexte)


def rendre_l_etape_code(
    request, domaine_du_lieu, state, email, etat_de_l_envoi="", erreur_code=""
):
    """
    Partiel de l'étape 2.
    / Step 2 partial.

    :param etat_de_l_envoi: "envoye", "attendre", ou "" (pas d'envoi à annoncer)
    :param erreur_code: message d'erreur du code, ou ""
    """
    contexte = {
        "lieu": domaine_du_lieu,
        "state": state,
        "email": email,
        "etat_de_l_envoi": etat_de_l_envoi,
        "erreur_code": erreur_code,
        "lien_changer_d_adresse": fabriquer_le_lien_changer_d_adresse(
            domaine_du_lieu, state
        ),
    }
    return render(request, PARTIEL_ETAPE_CODE, context=contexte)


def finaliser_le_compte(email: str, lieu):
    """
    Après un bon code : trouve ou crée le compte, et l'active si besoin.
    / After a correct code: finds or creates the account, activates it if needed.

    LOCALISATION : AuthBillet/views_sso.py

    TOURNE DANS `tenant_context(lieu)` :
    - le compte créé est rattaché au lieu (`client_achat`, `client_source`),
      pas au schéma `public` ;
    - la machine à états (BaseBillet/signals.py) valide les anciennes
      réservations gratuites `F` de CE lieu. Sur `public`, elle ne fait rien.
    / Runs in the venue context: account attached to the venue, and the state
    machine validates the venue's old free reservations.

    FLUX :
    1. Un compte non humain (terminal, compte technique) a cet email → refus.
    2. Compte trouvé ou créé (get_or_create_user, sans mail).
    3. Compte pas encore activé : anciennes réservations `F` d'événements
       passés annulées, puis activation par `user.save()`.

    :return: (user, avertissement). user = None si le compte est refusé.
        avertissement = message à afficher sur le lieu, ou "".
    """
    with tenant_context(lieu):
        # 1. Compte non humain. Sans ce contrôle, get_or_create_user cherche un
        # compte humain, n'en trouve pas, tente une création, et l'unicité de
        # l'email lève une IntegrityError (500).
        # / Non-human account: refused, otherwise get_or_create_user crashes
        # on the email unique constraint.
        un_compte_non_humain_a_cet_email = (
            TibilletUser.objects.filter(email=email)
            .exclude(espece=TibilletUser.TYPE_HUM)
            .exists()
        )
        if un_compte_non_humain_a_cet_email:
            logger.warning(
                f"SSO : un compte non humain a l'email {email}, connexion refusée."
            )
            return None, ""

        # 2. Le compte. get_or_create_user renvoie None quand le compte a
        # `email_error=True`. Or le code vient d'arriver dans cette boîte :
        # l'adresse marche. On efface l'erreur et on recommence.
        # get_or_create_user rattache aussi le compte au lieu (client_achat).
        # / None means email_error=True; the code just arrived, so the address
        # works: clear the flag and retry. Also attaches the venue.
        #
        # RÈGLE : on garde TOUJOURS l'instance TibilletUser renvoyée par
        # get_or_create_user, jamais un proxy (HumanUser, SuperHumanUser).
        # Avec un proxy, le pre_save de la machine à états part avec un autre
        # nom de modèle (pre_save_signal_status lit sender.__name__) et
        # l'activation ne valide plus les anciennes réservations.
        # / RULE: always the TibilletUser instance, never a proxy model: the
        # state machine keys on sender.__name__.
        user = get_or_create_user(email, send_mail=False)
        if user is None:
            TibilletUser.objects.filter(email=email).update(email_error=False)
            user = get_or_create_user(email, send_mail=False)

        avertissement = ""
        compte_deja_active = user.is_active and user.email_valid
        if not compte_deja_active:
            # 3.1 Les anciennes réservations gratuites en attente, pour un
            # événement déjà passé, sont annulées. Sinon l'activation enverrait
            # les billets d'un événement terminé : l'activateur ne regarde pas
            # la date. `.update()` ne passe pas par la machine à états : c'est
            # voulu, « F → annulée » n'a pas de transition.
            # / Old pending free reservations of past events are cancelled
            # first (update() bypasses the state machine on purpose).
            Reservation.objects.filter(
                user_commande=user,
                status=Reservation.FREERES,
                event__datetime__lt=timezone.now(),
            ).update(status=Reservation.CANCELED)

            # 3.2 Activation. `save()` et pas `.update()` : seul save() lance la
            # machine à états, qui valide les autres réservations `F` du lieu.
            # / save(), not update(): only save() runs the state machine.
            user.is_active = True
            user.email_valid = True
            user.save()

            # 3.3 La machine à états pose ce message quand une ancienne
            # réservation gratuite n'a pas pu être validée (événement complet).
            # / Set by the state machine when an old free reservation was cancelled.
            avertissement = getattr(user, "message_reservation_annulee", "") or ""

    return user, avertissement


# --- Les vues / The views ---


@require_GET
def guichet(request):
    """
    GET /sso/?lieu=<domaine>&state=<state> : la page du guichet.
    / GET /sso/: the desk page.

    - `lieu` inconnu (ou paramètres absents) → page « Lien de connexion invalide ».
    - Personne déjà connectée sur le guichet, compte humain → ticket et retour
      immédiat au lieu. Le compte est forcément activé : le ModelBackend ne
      rend pas de session à un compte non activé.
    - Sinon → page « Connexion à <nom du lieu> », étape 1.
    / Unknown venue → error page. Already logged in → ticket and redirect.
    Otherwise → step 1.
    """
    parametres = ParametresDuLieuSerializer(data=request.GET)
    if not parametres.is_valid():
        return rendre_la_page_d_erreur(request)

    domaine_du_lieu = parametres.validated_data["lieu"]
    state = parametres.validated_data["state"]
    lieu = trouver_le_lieu_du_domaine(domaine_du_lieu)
    if lieu is None:
        logger.warning(f"SSO : guichet appelé avec un lieu inconnu : {domaine_du_lieu}")
        return rendre_la_page_d_erreur(request)

    if request.user.is_authenticated:
        # Une session de terminal ou de compte technique ne donne jamais de ticket.
        # / A terminal or technical session never gets a ticket.
        if request.user.espece != TibilletUser.TYPE_HUM:
            return rendre_la_page_d_erreur(
                request, lire_l_habillage_du_lieu(lieu, domaine_du_lieu)
            )

        # Lieu déjà connu du compte : ticket tout de suite, sans rien demander.
        # / Venue already knows the account: ticket at once.
        if le_compte_connait_deja_le_lieu(request.user, lieu):
            ticket = fabriquer_un_ticket(request.user, domaine_du_lieu)
            url_de_retour = fabriquer_l_url_de_retour_vers_le_lieu(
                domaine_du_lieu, ticket, state
            )
            return HttpResponseRedirect(url_de_retour)

        # Première visite sur ce lieu : on demande l'accord avant de lui donner
        # l'identité de la personne. Sans cet écran, n'importe quel lieu (l'ouverture
        # d'un lieu est libre) pourrait récupérer l'email et le nom de toute personne
        # déjà connectée au guichet, juste en lui faisant suivre un lien.
        # / First visit on this venue: ask before sharing the identity. Without
        # this step, any venue could harvest the identity of logged-in people.
        habillage = lire_l_habillage_du_lieu(lieu, domaine_du_lieu)
        contexte = {
            "partiel": PARTIEL_CONSENTEMENT,
            "habillage": habillage,
            "lieu": domaine_du_lieu,
            "state": state,
            "email": request.user.email,
        }
        return render(request, choisir_le_gabarit_du_guichet(habillage), context=contexte)

    habillage = lire_l_habillage_du_lieu(lieu, domaine_du_lieu)
    contexte = {
        "partiel": PARTIEL_ETAPE_EMAIL,
        "habillage": habillage,
        "lieu": domaine_du_lieu,
        "state": state,
        "email": "",
        "erreur_email": "",
    }
    return render(request, choisir_le_gabarit_du_guichet(habillage), context=contexte)


@require_POST
def envoyer_le_code(request):
    """
    POST /sso/code/ : étape 1 (et « Recevoir un nouveau code » de l'étape 2).
    / POST /sso/code/: step 1 (and "send a new code" from step 2).

    Envoie un code à 6 chiffres. NE CRÉE NI COMPTE NI PORTEFEUILLE : le compte
    n'est créé qu'après le bon code. Ainsi, la réponse est la même que le
    compte existe ou non.
    / Sends a code. Creates neither account nor wallet: same answer whether
    the account exists or not.

    Le service est appelé SANS tenant_context : ses clés et ses plafonds
    vivent sur le guichet, tous lieux confondus. Le service programme le mail
    lui-même dans le contexte du lieu (nom du lieu dans le mail).
    / Service called WITHOUT tenant_context: limits count all venues together.
    """
    parametres = ParametresDuLieuSerializer(data=request.POST)
    if not parametres.is_valid():
        return render(request, PARTIEL_ERREUR)

    domaine_du_lieu = parametres.validated_data["lieu"]
    state = parametres.validated_data["state"]
    lieu = trouver_le_lieu_du_domaine(domaine_du_lieu)
    if lieu is None:
        return render(request, PARTIEL_ERREUR)

    validateur_de_l_email = LoginEmailValidator(data=request.POST)
    if not validateur_de_l_email.is_valid():
        return rendre_l_etape_email(
            request,
            domaine_du_lieu,
            state,
            email=request.POST.get("email", ""),
            erreur_email=_("Adresse email invalide."),
        )

    email = validateur_de_l_email.validated_data["email"].strip().lower()
    resultat_de_l_envoi = envoyer_un_code_de_connexion(
        email,
        get_client_ip(request),
        get_language(),
        lieu,
    )

    # Refus pendant un renvoi (« Recevoir un nouveau code », champ caché `renvoi`) :
    # on reste à l'étape du code. Le dernier code reçu reste valable 10 minutes,
    # la personne doit encore pouvoir le taper.
    # / Refused during a resend: stay on the code step, the last code still works.
    demande_venue_de_l_etape_code = request.POST.get("renvoi") == "1"
    if resultat_de_l_envoi == "trop_de_demandes" and demande_venue_de_l_etape_code:
        return rendre_l_etape_code(
            request,
            domaine_du_lieu,
            state,
            email,
            erreur_code=_("Trop de demandes. Le dernier code reçu reste valable 10 minutes."),
        )

    if resultat_de_l_envoi == "trop_de_demandes":
        return rendre_l_etape_email(
            request,
            domaine_du_lieu,
            state,
            email=email,
            erreur_email=_("Trop de demandes. Réessayez un peu plus tard."),
        )

    # "envoye" ou "attendre" (un code est parti il y a moins d'une minute).
    # / "envoye" or "attendre" (a code left less than a minute ago).
    return rendre_l_etape_code(
        request,
        domaine_du_lieu,
        state,
        email,
        etat_de_l_envoi=resultat_de_l_envoi,
    )


@require_POST
def verifier_le_code(request):
    """
    POST /sso/code/verifier/ : étape 2.
    / POST /sso/code/verifier/: step 2.

    FLUX :
    1. Les serializers valident lieu, state, email et code (6 chiffres).
    2. Le service vérifie le code (sans tenant_context, sur le guichet).
    3. Bon code → finalisation du compte dans le contexte du lieu.
    4. login() sur le guichet (hors du contexte du lieu).
    5. Redirection htmx vers le lieu, avec le ticket.
    / Validate, check the code, finalize the account in the venue context,
    log in on the desk, redirect to the venue with a ticket.
    """
    parametres = ParametresDuLieuSerializer(data=request.POST)
    if not parametres.is_valid():
        return render(request, PARTIEL_ERREUR)

    domaine_du_lieu = parametres.validated_data["lieu"]
    state = parametres.validated_data["state"]
    lieu = trouver_le_lieu_du_domaine(domaine_du_lieu)
    if lieu is None:
        return render(request, PARTIEL_ERREUR)

    # 1. Un code qui n'a pas 6 chiffres est un code faux.
    # / 1. A code without 6 digits is a wrong code.
    code_saisi_valide = CodeSaisiSerializer(data=request.POST)
    if not code_saisi_valide.is_valid():
        return rendre_l_etape_code(
            request,
            domaine_du_lieu,
            state,
            request.POST.get("email", "").strip().lower(),
            erreur_code=MESSAGE_CODE_INCORRECT,
        )

    email = code_saisi_valide.validated_data["email"].strip().lower()
    code_saisi = code_saisi_valide.validated_data["code"]

    # 2. Vérification du code, sur le guichet (sans tenant_context).
    # / 2. Code check, on the desk.
    resultat_de_la_verification = verifier_le_code_de_connexion(email, code_saisi)
    if resultat_de_la_verification != "ok":
        return rendre_l_etape_code(
            request,
            domaine_du_lieu,
            state,
            email,
            erreur_code=MESSAGES_D_ERREUR_DU_CODE[resultat_de_la_verification],
        )

    # 3. Finalisation du compte, dans le contexte du lieu.
    # Un compte non humain reçoit le même message qu'un code faux.
    # / 3. Account finalization in the venue context. Non-human = "wrong code".
    user, avertissement = finaliser_le_compte(email, lieu)
    if user is None:
        return rendre_l_etape_code(
            request,
            domaine_du_lieu,
            state,
            email,
            erreur_code=MESSAGE_CODE_INCORRECT,
        )

    # 4. Connexion sur le guichet. Au prochain lieu, GET /sso/ donnera un
    # ticket sans redemander de code.
    # / 4. Log in on the desk: the next venue gets a ticket without a code.
    login(request, user, backend=BACKEND_DE_CONNEXION)

    # 5. Retour vers le lieu. Le message éventuel (ancienne réservation annulée)
    # voyage dans le ticket : c'est le lieu qui l'affiche.
    # / 5. Back to the venue; the optional warning travels in the ticket.
    ticket = fabriquer_un_ticket(user, domaine_du_lieu, avertissement)
    url_de_retour = fabriquer_l_url_de_retour_vers_le_lieu(
        domaine_du_lieu, ticket, state
    )
    return HttpResponseClientRedirect(url_de_retour)


@require_POST
def continuer_vers_le_lieu(request):
    """
    POST /sso/continuer/ : la personne, déjà connectée au guichet, accepte d'entrer
    sur un lieu qu'elle visite pour la première fois.
    / POST /sso/continuer/: the logged-in person agrees to enter a new venue.

    Affiché par guichet() (partiel etape_consentement.html). Le lieu sera ajouté à
    `client_achat` par connexion_retour : les visites suivantes passent sans écran.
    / Shown by guichet(). connexion_retour then adds the venue to client_achat.

    Refus (page d'erreur, pas de ticket) : paramètres invalides, lieu inconnu,
    personne non connectée, ou compte non humain.
    / Refused: bad parameters, unknown venue, not logged in, or non-human account.
    """
    parametres = ParametresDuLieuSerializer(data=request.POST)
    if not parametres.is_valid():
        return render(request, PARTIEL_ERREUR)

    domaine_du_lieu = parametres.validated_data["lieu"]
    state = parametres.validated_data["state"]
    lieu = trouver_le_lieu_du_domaine(domaine_du_lieu)
    if lieu is None:
        return render(request, PARTIEL_ERREUR)

    personne_connectee_et_humaine = (
        request.user.is_authenticated
        and request.user.espece == TibilletUser.TYPE_HUM
    )
    if not personne_connectee_et_humaine:
        return render(request, PARTIEL_ERREUR)

    ticket = fabriquer_un_ticket(request.user, domaine_du_lieu)
    url_de_retour = fabriquer_l_url_de_retour_vers_le_lieu(
        domaine_du_lieu, ticket, state
    )
    # Bouton htmx : HX-Redirect. Sans JavaScript : redirection classique.
    # / htmx button: HX-Redirect. Without JavaScript: plain redirect.
    if request.headers.get("HX-Request") == "true":
        return HttpResponseClientRedirect(url_de_retour)
    return HttpResponseRedirect(url_de_retour)

"""
Vues du wizard d'onboarding.
/ Onboarding wizard views.

LOCALISATION: onboard/views.py

ViewSet DRF explicite (`viewsets.ViewSet`, PAS `ModelViewSet`) : chaque
etape du wizard est une `@action` explicite. Cf. djc / FALC guidelines
du projet.

Etapes (Tasks 10 a 15 du plan `TECH_DOC/SESSIONS/ONBOARD/02-implementation-plan.md`) :
  - identity     (Task 10) — formulaire complet : email + CGU + invitation + OTP send
  - verify       (Task 11) — saisie de l'OTP (placeholder pour l'instant)
  - place        (Task 12) — adresse + GPS (placeholder pour l'instant)
  - descriptions (Task 13) — texte long + logo (placeholder pour l'instant)
  - events       (Task 14) — brouillons d'events (placeholder pour l'instant)
  - launch       (Task 15) — declenche la creation async (placeholder pour l'instant)

Helpers de session : `_get_or_none_wc`, `_set_session_wc`, `_clear_session_wc`
encapsulent la clef `onboard_wc_uuid` pour ne pas la dupliquer dans chaque
step. `_redirect_to_current_step` factorise la redirection vers la step
courante d'un brouillon, via la table `STEP_TO_URL_NAME`.

/ Explicit DRF `ViewSet` (NOT `ModelViewSet`) : each wizard step is its
own `@action`. Session helpers wrap the `onboard_wc_uuid` key. Steps 11-15
are placeholders (Task 10 only implements `identity`).
"""

import logging

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.throttling import AnonRateThrottle

from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)


# Clef de session unique pour le wizard : on stocke l'UUID du brouillon
# WaitingConfiguration (vit dans le schema `meta`, partage entre ROOT et
# tenants). Volontairement courte mais prefixee `onboard_` pour eviter
# toute collision avec d'autres apps qui pourraient utiliser la session.
# / Single session key for the wizard: stores the UUID of the
# WaitingConfiguration draft (living in the `meta` schema, shared across
# ROOT and tenants). Short but prefixed with `onboard_` to avoid collisions
# with other apps using the session.
SESSION_KEY = "onboard_wc_uuid"


# Rate-limit anti-spam sur identity POST : 5 creations de WC par minute
# par IP. Friction ZERO pour un user normal (qui POST 1 fois identity).
# Bloque silencieusement (HTTP 429) un bot single-IP qui itere vite.
# `rate` declare directement sur la classe car le projet n'a pas active
# `DEFAULT_THROTTLE_RATES` dans REST_FRAMEWORK (cf. settings.py:300-310).
# `allow_request` filtre : on n'applique le throttle qu'au POST. Sans
# ca un user qui refresh la page (GET) consommerait son quota et
# resterait bloque apres 5 GET innocents.
# / Anti-spam rate-limit on identity POST: 5 WC/min/IP. ZERO friction
# for normal users (who POST identity once). Silently blocks (429) a
# single-IP bot iterating fast. `allow_request` filter: throttle only
# POST (a refresh of GET shouldn't burn the user's quota).
class IdentityPostRateThrottle(AnonRateThrottle):
    """5 POST/minute/IP — anti-spam creation WC + envoi OTP."""

    rate = "5/minute"
    # `scope` doit etre unique pour ne pas partager le compteur DRF avec
    # d'autres throttles (ex: WidgetReverseGeocodeRateThrottle si re-introduit).
    # / Unique `scope` to avoid sharing the DRF counter with other throttles.
    scope = "onboard_identity_post"

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


# Table de routage des steps : `WaitingConfiguration.current_step` (chaine
# parmi `STEP_IDENTITY`, ...) -> nom d'URL Django (`onboard-identity`, ...).
# Permet de centraliser la correspondance pour `redirect()` et faciliter
# les futurs renommages. Lecture : `STEP_TO_URL_NAME[wc.current_step]`.
# / Step routing table: `WaitingConfiguration.current_step` -> Django URL
# name. Centralised mapping for `redirect()`, easy to refactor.
STEP_TO_URL_NAME = {
    WaitingConfiguration.STEP_IDENTITY: "onboard-identity",
    WaitingConfiguration.STEP_VERIFY: "onboard-verify",
    WaitingConfiguration.STEP_PLACE: "onboard-place",
    WaitingConfiguration.STEP_DESCRIPTIONS: "onboard-descriptions",
    WaitingConfiguration.STEP_EVENTS: "onboard-events",
    WaitingConfiguration.STEP_LAUNCH: "onboard-launch",
}


def _get_or_none_wc(request):
    """
    Lit l'UUID du brouillon dans la session et renvoie l'instance
    WaitingConfiguration associee, ou None si pas de brouillon en session
    ou si l'UUID ne correspond a aucun enregistrement.
    / Read the draft UUID from the session and return the matching
    WaitingConfiguration instance, or None if no draft is in session or
    the UUID doesn't match any row.

    PIEGE : WaitingConfiguration vit dans le schema `meta`, pas dans le
    schema courant. On force `schema_context("meta")` avant la requete.
    / PITFALL: WaitingConfiguration lives in the `meta` schema, not the
    current one. We force `schema_context("meta")` before the query.
    """
    wc_uuid = request.session.get(SESSION_KEY)
    if not wc_uuid:
        return None
    with schema_context("meta"):
        try:
            return WaitingConfiguration.objects.get(uuid=wc_uuid)
        except WaitingConfiguration.DoesNotExist:
            # Brouillon supprime entre-temps (purge cron, admin manuel, etc.).
            # / Draft removed in the meantime (cron purge, manual admin, etc.).
            return None


def _set_session_wc(request, wc):
    """
    Stocke l'UUID du brouillon dans la session courante.
    / Store the draft UUID in the current session.
    """
    request.session[SESSION_KEY] = str(wc.uuid)
    request.session.modified = True


def _clear_session_wc(request):
    """
    Retire l'UUID du brouillon de la session courante (sans erreur si absent).
    / Remove the draft UUID from the current session (no error if missing).
    """
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


def _redirect_to_current_step(request, wc):
    """
    Renvoie un `redirect` HTTP vers l'URL nommee de la step courante du
    brouillon `wc`. Si `wc.current_step` n'est pas dans la table (donnees
    incoherentes), on tombe par defaut sur `onboard-identity`.
    / Return an HTTP redirect to the URL name of `wc.current_step`. If the
    step value is not in the table (inconsistent data), fall back to
    `onboard-identity`.
    """
    url_name = STEP_TO_URL_NAME.get(wc.current_step, "onboard-identity")
    return redirect(url_name)


def _get_confirmed_wc_or_redirect(request):
    """
    Garde de session pour les vues "navigationnelles" du wizard (steps
    place / descriptions / events GET / launch GET).

    Verifie 3 conditions :
      1. Un brouillon est present en session.
      2. L'email du brouillon a ete confirme par OTP (`email_confirmed`).
      3. L'utilisateur Django est `is_authenticated` (login fait au moment
         du verify success — defense en profondeur en cas de logout
         silencieux entre 2 steps).

    Si OK -> retourne `(wc, None)`. Si KO -> retourne
    `(None, redirect("onboard-identity"))` : l'utilisateur ne doit pas
    pouvoir sauter l'OTP ni se "deconnecter" en cours de wizard sans
    refaire la verification.

    Usage attendu dans une action :
        wc, redirect_response = _get_confirmed_wc_or_redirect(request)
        if redirect_response is not None:
            return redirect_response
        # ... suite de la vue, `wc` est garanti non-None et confirme.

    / Session guard for navigational wizard views. Three checks:
      1. Draft in session.
      2. Email confirmed by OTP.
      3. Django user is authenticated (login set at verify success —
         defense in depth in case of silent logout between steps).
    Returns `(wc, None)` if OK; otherwise `(None, redirect("onboard-identity"))`.
    """
    wc = _get_or_none_wc(request)
    if wc is None or not wc.email_confirmed:
        return None, redirect("onboard-identity")
    if not request.user.is_authenticated:
        # Logout silencieux entre 2 steps (cookie expire, admin force_logout,
        # nettoyage manuel). On force la re-verification : retour identity
        # qui re-creera un WC + OTP.
        # / Silent logout between 2 steps. Force re-verification.
        return None, redirect("onboard-identity")
    return wc, None


def _get_confirmed_wc_or_404(request):
    """
    Variante du garde precedent pour les actions HTMX (events add /
    remove, etc.) ou un `redirect` n'aurait pas de sens cote client
    (HTMX ne suit pas les 302 vers une page complete proprement). On
    renvoie `(None, HttpResponse(status=404))` qui se traduit cote
    navigateur par une erreur HTMX visible.

    Memes 3 conditions que `_get_confirmed_wc_or_redirect` (WC en session
    + email_confirmed + user authentifie).

    / Same as `_get_confirmed_wc_or_redirect` but for HTMX actions:
    returns a 404 response instead of a redirect.
    """
    wc = _get_or_none_wc(request)
    if wc is None or not wc.email_confirmed:
        return None, HttpResponse(status=404)
    if not request.user.is_authenticated:
        return None, HttpResponse(status=404)
    return wc, None


# Cooldown anti-spam entre 2 envois d'OTP pour le meme brouillon. Mesure
# COMPLEMENTAIRE au rate-limit IP existant (3/h/IP via `cache.add(key)`) :
# le rate-limit IP empeche un attaquant de spammer la plateforme entiere,
# le cooldown WC empeche un user de double-cliquer "Renvoyer".
# / Anti-spam cooldown between two OTP sends for the same draft.
# Complements the existing per-IP rate-limit (3/h): the cooldown prevents
# the user from double-clicking "Resend".
OTP_RESEND_COOLDOWN_SECONDS = 60


def _generate_and_send_otp_for_wc(wc, is_resend=False):
    """
    Genere un nouvel OTP, le persiste sur le brouillon `wc` (schema
    `meta`), et enqueue l'envoi par email via Celery.

    Cette fonction est appelee a 2 endroits :
      1. `identity` POST : envoi automatique apres creation du brouillon
         (sauf branche `skip_otp` user authentifie). `is_resend=False`.
      2. `resend_otp` action : sur clic explicite "Renvoyer le code" par
         l'utilisateur. `is_resend=True` (incremente `otp_resend_count`
         pour l'audit).

    Champs mis a jour :
      - otp_hash, otp_expires_at : nouveau code (l'ancien est invalide).
      - otp_attempts : reset 0 (nouveau quota de 5 tentatives).
      - otp_sent_at : timestamp now (sert au cooldown 60s).
      - otp_resend_count : +1 si `is_resend=True` uniquement.

    Effets de bord :
      - Update DB dans le schema `meta`.
      - Enqueue `onboard_otp_mailer.delay()` (Celery, async).

    / Generates a fresh OTP, persists it on the draft `wc`, and enqueues
    the email send via Celery. Called both from `identity` POST (auto-send
    after draft creation, `is_resend=False`) and from `resend_otp` (user
    click, `is_resend=True` increments `otp_resend_count` for audit).
    """
    # Imports locaux : evitent les dependances circulaires au chargement
    # du module `views` (services et tasks importent indirectement views).
    # / Local imports: avoid circular dependencies at module load time.
    from django.utils import timezone

    from onboard.services import generate_otp
    from onboard.tasks import onboard_otp_mailer

    otp_clair, otp_hash, expires_at = generate_otp()
    sent_at = timezone.now()

    update_fields = {
        "otp_hash": otp_hash,
        "otp_expires_at": expires_at,
        "otp_attempts": 0,
        "otp_sent_at": sent_at,
    }
    if is_resend:
        # Incremente uniquement sur resend explicite : le premier envoi
        # (depuis identity POST) n'est pas un "resend" et ne doit pas
        # gonfler le compteur d'audit.
        # / Increment only on explicit resend.
        update_fields["otp_resend_count"] = wc.otp_resend_count + 1

    with schema_context("meta"):
        WaitingConfiguration.objects.filter(uuid=wc.uuid).update(**update_fields)

    onboard_otp_mailer.delay(wc_uuid=str(wc.uuid), otp_clair=otp_clair)
    return sent_at


def _finalize_otp_success(request, wc):
    """
    Finalise une verification OTP reussie : avance le brouillon, cree/active
    le TibilletUser, et logue l'utilisateur dans la session Django.

    Appele a 2 endroits dans `verify` POST :
      1. Branche DEBUG (bypass : tout code 6 chiffres accepte en dev local).
      2. Branche prod (apres `verify_otp(saisie, wc.otp_hash)` OK).

    Les deux branches doivent faire EXACTEMENT le meme travail post-succes,
    sinon le user ne sera pas authentifie sur la step suivante et le garde
    `_get_confirmed_wc_or_redirect` le renverra a `onboard-identity`.
    C'est le bug qui a motive cette factorisation (DEBUG bypass faisait
    update WC + get_or_create_user mais sautait l'activation et `login()`).

    Etapes :
      - Update WC en schema `meta` : `email_confirmed=True`,
        `current_step=PLACE`, purge OTP (`otp_hash=""`, `otp_expires_at=None`).
      - get_or_create_user(wc.email) : idempotent, cree si absent.
      - Si retour None (cas `email_error` sur user existant) -> on retourne
        None pour signaler l'echec a l'appelant qui rendra son template.
      - Force `email_valid=True` (preuve OTP) + `is_active=True` (les
        nouveaux users sortent inactifs de get_or_create_user).
      - `login(request, user, backend=...)` : pose le cookie session auth.

    / Finalise a successful OTP verification: advance the draft, create/
    activate the TibilletUser, and log the user in via Django session.
    Called from both DEBUG-bypass and prod branches of `verify` POST.
    Both branches must do the SAME post-success work, otherwise the user
    won't be authenticated on the next step and `_get_confirmed_wc_or_redirect`
    will send them back to `onboard-identity`.

    Returns the user object on success, or `None` on failure (caller
    renders its own 422 template).
    """
    # Imports locaux : evite la dependance circulaire au chargement du
    # module et le cout d'import sur les requetes qui ne passent pas par
    # ici. / Local imports to avoid circular dep + load cost.
    from django.contrib.auth import login

    from AuthBillet.utils import get_or_create_user

    # 1. Avance du brouillon. Atomique via `.update()` (pas besoin de re-fetch).
    # / 1. Advance the draft. Atomic via `.update()` (no re-fetch).
    with schema_context("meta"):
        WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_PLACE,
            otp_hash="",
            otp_expires_at=None,
        )

    # 2. Cree ou recupere le user (idempotent). `send_mail=False` car la
    # confirmation email est deja faite via l'OTP.
    # / 2. Create-or-get user (idempotent). `send_mail=False` since OTP
    # already confirmed the email.
    user = get_or_create_user(wc.email, send_mail=False)
    if user is None:
        # Cas extreme : `email_error` positionne sur un user existant.
        # On signale l'echec a l'appelant.
        # / Edge case: `email_error` set on existing user — signal failure.
        return None

    # 3. Force `email_valid` + `is_active`. `get_or_create_user` cree les
    # users avec `is_active=False` par defaut ; sans activation, certains
    # backends refuseraient l'auth. `update_fields` evite les writes inutiles.
    # / 3. Force email_valid + is_active. `update_fields` scopes the write.
    update_fields = []
    if not user.email_valid:
        user.email_valid = True
        update_fields.append("email_valid")
    if not user.is_active:
        user.is_active = True
        update_fields.append("is_active")
    if update_fields:
        user.save(update_fields=update_fields)

    # 4. Login Django : pose le cookie session auth. Backend explicite car
    # le projet a plusieurs AUTHENTICATION_BACKENDS et `login()` l'exige
    # sans `authenticate()` prealable.
    # / 4. Django login: set auth session cookie. Explicit backend required
    # because the project has several AUTHENTICATION_BACKENDS and `login()`
    # needs one when called without a prior `authenticate()`.
    login(
        request, user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    return user


# --- SSO transitoire tenant -> ROOT --------------------------------------
# Quand un utilisateur deja authentifie sur un tenant est redirige vers le
# wizard servi par ROOT (cf. `_redirect_to_root_if_tenant`), on perd la
# session cross-domain (cookie scope au domaine du tenant). Pour eviter de
# lui redemander OTP / login a froid, on lui forge un token tres court qui
# transporte son identite jusqu'a ROOT.
#
# Securite (durcissement vs `TibilletUser.get_connect_token` qui sert pour
# les magic-link mail) :
#   - Scope explicite `onboard_sso:` dans le payload signe : un token vole
#     ailleurs (mail de connexion) ne marche PAS ici, et inversement.
#   - TTL court (`ONBOARD_SSO_TTL_SECONDS`) : 120s suffit pour un redirect
#     HTTP automatique, vs 72h pour le mail de connexion.
#   - One-shot via Redis : `cache.add()` est atomique ; une 2e tentative
#     avec le meme token (rejeu, capture) est refusee.
#   - Cle Redis derivee d'un SHA256 du token : on ne stocke jamais le
#     token brut en cache pour eviter sa fuite en cas de dump Redis.
#
# Le token transite en query string `?sso=<token>` lors du 302 ; sur ROOT,
# `dispatch()` le consomme immediatement et fait un 2e 302 vers le meme
# path SANS le param, pour nettoyer l'URL (history navigateur, Referer).
#
# / Transient SSO from tenant to ROOT. We mint a short-lived signed token
# when the user is authenticated on a tenant and we redirect to ROOT, so
# they don't have to re-OTP. Hardened vs the mail magic-link token:
# explicit `onboard_sso:` scope, 120s TTL, one-shot via Redis (cache.add),
# Redis key derived from SHA256 of the token (never the raw value).
ONBOARD_SSO_SCOPE = "onboard_sso"
ONBOARD_SSO_TTL_SECONDS = 120
ONBOARD_SSO_QUERY_PARAM = "sso"


def _hash_for_cache(token):
    """
    Renvoie un SHA256 hex du token, utilise comme cle Redis. On ne stocke
    jamais le token brut en cache.
    / Returns the token's SHA256 (hex), used as Redis key. We never store
    the raw token in the cache.
    """
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_onboard_sso_token(user):
    """
    Forge un token SSO signe et scope, lie a `user.pk`.

    Format : `urlsafe_base64( TimestampSigner().sign("onboard_sso:<pk>") )`.
    Le scope `onboard_sso:` est inclus DANS le payload signe — un token
    forge sans la `SECRET_KEY` Django est impossible, et un token venant
    d'un autre scope (mail magic-link) ne passe pas le check de scope.

    SECURITE : on ne genere un token QUE pour un user humain
    (`espece == TYPE_HUM`). Un terminal (POS, borne) ou un android n'a
    aucune raison de creer un tenant via le wizard. Retourne `None` si
    l'utilisateur n'est pas humain — l'appelant decide quoi faire (en
    pratique : ne pas ajouter le param `sso` au redirect).

    Le timestamp est embarque par `TimestampSigner` (verifie via `max_age`
    au moment du `unsign`), donc pas besoin de le serialiser nous-memes.

    / Mint a signed, scoped SSO token bound to `user.pk`. Format:
    `urlsafe_base64(TimestampSigner.sign("onboard_sso:<pk>"))`. The scope
    is part of the signed payload, preventing cross-scope reuse.
    SECURITY: only mint a token for human users (`espece == TYPE_HUM`).
    Terminals (POS) and android terminals have no business creating a
    tenant via the wizard. Returns `None` if user is not human.
    """
    from AuthBillet.models import TibilletUser
    from django.core.signing import TimestampSigner
    from django.utils.http import urlsafe_base64_encode

    # Garde 1 — type d'utilisateur. Un terminal compromis ne doit pas
    # pouvoir creer un tenant en se faisant passer pour un humain via SSO.
    # / Guard 1 — user type. A compromised terminal must not be able to
    # create a tenant by SSO-ing as a human.
    if getattr(user, "espece", None) != TibilletUser.TYPE_HUM:
        logger.warning(
            "Onboard SSO: refus de generer un token pour user pk=%s "
            "(espece=%s, attendu=HU).",
            getattr(user, "pk", None),
            getattr(user, "espece", "?"),
        )
        return None

    signer = TimestampSigner()
    payload = f"{ONBOARD_SSO_SCOPE}:{user.pk}"
    signed = signer.sign(payload)
    return urlsafe_base64_encode(signed.encode("utf-8"))


def _consume_onboard_sso_token(token):
    """
    Verifie le token SSO et renvoie l'instance `TibilletUser` cible, ou
    `None` en cas d'echec (signature, expiration, scope incorrect, user
    introuvable, deja consomme).

    Quatre garde-fous :
      1. `signer.unsign(..., max_age=120)` -> rejette signature invalide
         ET expiration > 120s.
      2. Scope : le payload demuxe doit commencer par `onboard_sso:`.
         Un token magic-link mail (scope different) est refuse.
      3. One-shot : `cache.add(redis_key, 1, timeout=120)` est atomique ;
         si la cle existe deja, c'est un rejeu, on refuse.
      4. User : on charge `User.objects.get(pk=user_pk)`. Si supprime
         entre-temps, on refuse.

    / Verifies the SSO token and returns the matching `TibilletUser`, or
    `None` on any failure (signature, expiry, wrong scope, missing user,
    already-consumed). Four guards: TimestampSigner with max_age=120s,
    scope check, atomic one-shot via cache.add(), user existence check.
    """
    # Imports locaux : on n'a besoin d'eux que sur le chemin SSO.
    # / Local imports: only needed on the SSO path.
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
    from django.utils.http import urlsafe_base64_decode

    if not token:
        return None

    # Decode base64 -> string signe.
    # / Decode base64 -> signed string.
    try:
        signed = urlsafe_base64_decode(token).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        logger.info("Onboard SSO: token base64 invalide.")
        return None

    # Verifie signature + TTL.
    # / Verify signature + TTL.
    signer = TimestampSigner()
    try:
        payload = signer.unsign(signed, max_age=ONBOARD_SSO_TTL_SECONDS)
    except SignatureExpired:
        logger.info("Onboard SSO: token expire (TTL %ss).", ONBOARD_SSO_TTL_SECONDS)
        return None
    except BadSignature:
        logger.warning("Onboard SSO: signature invalide (tentative de forge ?).")
        return None

    # Verifie scope : le payload doit commencer par `onboard_sso:`. Sans
    # ce check, un token magic-link mail (scope different) pourrait servir.
    # / Scope check: payload must start with `onboard_sso:`. Without this,
    # a mail magic-link token (different scope) could be reused.
    prefix = f"{ONBOARD_SSO_SCOPE}:"
    if not payload.startswith(prefix):
        logger.warning(
            "Onboard SSO: scope invalide (payload='%s', attendu='%s*').",
            payload[:30], prefix,
        )
        return None

    user_pk_str = payload[len(prefix):]
    if not user_pk_str:
        logger.warning("Onboard SSO: pk vide dans le payload.")
        return None

    # One-shot via cache.add() — atomique entre workers. Si la cle existe
    # deja, c'est un rejeu (replay attack ou refresh trop tardif).
    # / Atomic one-shot via cache.add(). Existing key = replay attempt.
    cache_key = f"onboard:sso:consumed:{_hash_for_cache(token)}"
    got_lock = cache.add(cache_key, "1", timeout=ONBOARD_SSO_TTL_SECONDS)
    if not got_lock:
        logger.warning(
            "Onboard SSO: token deja consomme (rejeu user_pk=%s).",
            user_pk_str,
        )
        return None

    # Charge l'utilisateur. Si supprime entre-temps : refuse.
    # / Load the user. If deleted in the meantime: refuse.
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_pk_str)
    except (User.DoesNotExist, ValueError):
        logger.warning("Onboard SSO: user pk=%s introuvable.", user_pk_str)
        return None

    # Garde 5 — type d'utilisateur (defense en profondeur). Si jamais un
    # terminal a reussi a forger / capturer un token humain et que la
    # garde cote `_generate_onboard_sso_token` est buggee, on bloque ici
    # aussi. Le wizard ne sert qu'a creer un tenant, ce n'est jamais un
    # terminal qui le fait.
    # / Guard 5 — user type (defense in depth). Even if the generation-time
    # guard were buggy and a terminal got a human token, we block here.
    # Only humans create tenants via the wizard.
    from AuthBillet.models import TibilletUser

    if user.espece != TibilletUser.TYPE_HUM:
        logger.warning(
            "Onboard SSO: refus de consommer un token pour user pk=%s "
            "(espece=%s, attendu=HU).",
            user.pk, user.espece,
        )
        return None

    return user


def _consume_sso_in_request_if_present(request):
    """
    Sur ROOT, si la query string contient `?sso=<token>` :
      - consomme le token et logue l'utilisateur via Django session ;
      - retourne un `HttpResponseRedirect` vers le meme path mais SANS le
        param `sso` (URL propre dans l'history navigateur et le Referer).

    Renvoie `None` si :
      - pas de `sso=` en query (cas nominal) ;
      - token invalide (logge le motif, mais ne bloque pas le wizard :
        l'utilisateur sera juste considere comme anonyme).

    / On ROOT, if the query string contains `?sso=<token>`: consume +
    Django login, then return a 302 to the same path WITHOUT the `sso`
    param (clean URL). Returns `None` if no `sso=` or invalid token (we
    log the reason but don't block the wizard — user just stays anonymous).
    """
    token = request.GET.get(ONBOARD_SSO_QUERY_PARAM, "").strip()
    if not token:
        return None

    user = _consume_onboard_sso_token(token)
    if user is None:
        # Token invalide / expire / rejeu : on ne bloque pas, on retire
        # juste le param de l'URL pour ne pas le re-tenter en boucle.
        # / Invalid/expired/replayed token: don't block, just strip the
        # param to avoid retrying it in a loop.
        return _redirect_stripping_sso_param(request)

    # Login Django : backend explicite (cf. _finalize_otp_success).
    # / Django login: explicit backend (cf. _finalize_otp_success).
    from django.contrib.auth import login

    login(
        request, user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    logger.info(
        "Onboard SSO: user pk=%s logue via token transitoire (tenant -> ROOT).",
        user.pk,
    )
    return _redirect_stripping_sso_param(request)


def _redirect_stripping_sso_param(request):
    """
    Renvoie un 302 vers le path courant, query string nettoyee du param
    `sso`. Si la query string devient vide, on supprime aussi le `?`.

    / Returns a 302 to the current path with the `sso` param stripped.
    """
    from django.http import HttpResponseRedirect

    # `request.GET` est un QueryDict immuable ; on en fait une copie mutable.
    # / `request.GET` is immutable; copy it to mutate.
    params_copies = request.GET.copy()
    params_copies.pop(ONBOARD_SSO_QUERY_PARAM, None)
    suffix = f"?{params_copies.urlencode()}" if params_copies else ""
    target = f"{request.path}{suffix}"
    return HttpResponseRedirect(target)


def _redirect_to_root_if_tenant(request):
    """
    Si l'utilisateur accede au wizard depuis un tenant (subdomain d'un lieu),
    on le renvoie vers le meme path sur le tenant ROOT (tibillet.org).

    Pourquoi : le wizard `base_wizard.html` etend `seo/base.html`, dont la
    navbar est codee pour le contexte ROOT (Explorer / Documentation / logo
    TiBillet). Sur un tenant, on heritait de cette navbar ROOT au lieu de
    celle du lieu — incoherent visuellement. Choix mainteneur 2026-05-16 :
    plutot que de fabriquer un base wizard double-skin (ROOT/tenant), on
    redirige tout simplement vers ROOT. Le wizard vit toujours sur le meme
    domaine, et le bouton "Creer son espace" des footers tenant pointe en
    fait vers la meme experience.

    Renvoie `None` si on est deja sur ROOT (schema `public`), sinon un
    `HttpResponseRedirect` vers `https://<root_domain><path_complet>`.
    Le path complet est preserve (identity / verify / ...) ainsi que la
    query string (`?invite=<code>`) pour ne pas casser les invitations.

    / If the user reaches the wizard from a tenant (venue subdomain), we
    redirect to the same path on the ROOT tenant (tibillet.org).
    Reason: `base_wizard.html` extends `seo/base.html` whose navbar is
    hardcoded for the ROOT context. On a tenant, we'd inherit the ROOT
    navbar instead of the venue's — visually inconsistent. Maintainer
    choice 2026-05-16: simpler to redirect than to build a dual-skin base.
    Returns `None` if already on ROOT (`public` schema), otherwise an
    `HttpResponseRedirect` preserving full path + query string.
    """
    # Import local : evite de charger django.db.connection au top du module.
    # / Local import: avoid loading django.db.connection at module top.
    from django.db import connection
    from django.http import HttpResponseRedirect

    if connection.schema_name == "public":
        # Deja sur ROOT, rien a faire. / Already on ROOT, nothing to do.
        return None

    # Recupere le domaine primary du tenant ROOT. Le Client ROOT vit dans
    # SHARED_APPS, donc visible depuis n'importe quel schema, mais on force
    # le contexte `public` par defense en profondeur (au cas ou le futur).
    # / Lookup ROOT tenant's primary domain. SHARED_APPS so visible from
    # anywhere, but we still scope to `public` for defense in depth.
    from Customers.models import Client

    with schema_context("public"):
        try:
            root = Client.objects.get(categorie=Client.ROOT)
        except Client.DoesNotExist:
            # Cas d'installation incomplete : pas de fallback possible, on
            # laisse le wizard se charger sur le tenant courant (skin
            # incoherent mais au moins l'utilisateur peut avancer).
            # / Incomplete install: no fallback, let the wizard load on the
            # current tenant (inconsistent skin but at least the user can
            # proceed).
            logger.warning(
                "No ROOT tenant found (Client.ROOT). Wizard will load on "
                "current tenant '%s' with inconsistent skin.",
                connection.schema_name,
            )
            return None
        root_domain = root.get_primary_domain().domain

    # Construit la query string cible : on conserve TOUS les params actuels
    # (ex: `?invite=abc`) et on injecte `?sso=<token>` si l'utilisateur est
    # authentifie. Cela permet de transporter son identite cross-domain
    # sans qu'il refasse OTP / login.
    # / Build the target query string: keep all current params (e.g.
    # `?invite=abc`) and add `?sso=<token>` if the user is authenticated.
    # This transports identity cross-domain without re-OTP / re-login.
    params_pour_root = request.GET.copy()
    if request.user.is_authenticated:
        # Token a TTL court (120s), one-shot, scope `onboard_sso:`. Cf.
        # `_generate_onboard_sso_token` pour le detail securite.
        # `_generate_onboard_sso_token` retourne `None` si l'utilisateur
        # n'est pas humain (terminal POS, android) : dans ce cas on ne
        # met pas de param `sso` -> l'utilisateur arrivera anonyme sur
        # ROOT et devra refaire le flow d'identite + OTP (normal).
        # / Short-TTL (120s), one-shot, scoped token. Returns None for
        # non-human users (terminals) — in which case we skip the param
        # and the user lands anonymous on ROOT.
        token = _generate_onboard_sso_token(request.user)
        if token is not None:
            params_pour_root[ONBOARD_SSO_QUERY_PARAM] = token
            logger.info(
                "Onboard: user authenticated on tenant '%s', issuing SSO "
                "token for ROOT redirect.",
                connection.schema_name,
            )

    query_string = params_pour_root.urlencode()
    suffix = f"?{query_string}" if query_string else ""
    target_url = f"https://{root_domain}{request.path}{suffix}"
    logger.info(
        "Onboard: redirecting from tenant '%s' to ROOT.",
        connection.schema_name,
    )
    return HttpResponseRedirect(target_url)


class OnboardViewSet(viewsets.ViewSet):
    """
    Wizard d'onboarding en 6 etapes pour creer un nouveau tenant.

    Routing tenant -> ROOT (decision mainteneur 2026-05-16) : le wizard
    est techniquement SHARED (URLs branchees dans urls_public ET dans les
    schemas tenants), mais on ne le SERT que depuis ROOT. Si un utilisateur
    arrive depuis un tenant (lien footer "Creer son espace"), `dispatch()`
    le redirige vers le meme path sur `https://<root_domain>/onboard/...`.
    Cf. helper `_redirect_to_root_if_tenant`.

    / 6-step onboarding wizard. Tenant -> ROOT routing (maintainer choice
    2026-05-16): the wizard is technically SHARED but only SERVED from ROOT.
    A user landing from a tenant is redirected to the same path on ROOT
    via `dispatch()`. See `_redirect_to_root_if_tenant` helper.
    """

    # Le wizard est public : pas d'authentification requise pour commencer
    # un brouillon. L'utilisateur s'authentifiera via l'OTP en step 2.
    # / The wizard is public: no auth required to start a draft. The user
    # authenticates via the OTP at step 2.
    permission_classes = [permissions.AllowAny]

    def dispatch(self, request, *args, **kwargs):
        """
        Garde commune a toutes les actions du ViewSet.

        Sequence :
          1. Sur ROOT, si la query contient `?sso=<token>`, on consomme le
             token, on logue l'utilisateur, puis 302 vers le meme path
             SANS le param `sso` (nettoie l'URL navigateur). Cf.
             `_consume_sso_in_request_if_present`.
          2. Sur un tenant, on redirige vers ROOT (avec un token SSO en
             query string si l'utilisateur etait deja authentifie). Cf.
             `_redirect_to_root_if_tenant`.
          3. Sinon, on laisse passer vers l'action demandee.

        / Common guard. Order matters:
          1. On ROOT with `?sso=<token>`: consume + login + clean redirect.
          2. On tenant: redirect to ROOT (with SSO if authenticated).
          3. Otherwise pass through.
        """
        # 1. Consommation du token SSO si present (uniquement sur ROOT,
        # le helper retourne None si pas de param `sso=`).
        # / 1. Consume SSO token if present (only on ROOT — returns None
        # if no `sso=` param).
        sso_redirect = _consume_sso_in_request_if_present(request)
        if sso_redirect is not None:
            return sso_redirect

        # 2. Redirect tenant -> ROOT si on n'est pas deja sur ROOT.
        # / 2. Redirect tenant -> ROOT if we're not already on ROOT.
        redirect_to_root = _redirect_to_root_if_tenant(request)
        if redirect_to_root is not None:
            return redirect_to_root

        return super().dispatch(request, *args, **kwargs)

    # ------------------------------------------------------------------
    # Root : redirige vers la step courante (Task 9 + refactor Task 10).
    # / Root: redirect to current step (Task 9 + Task 10 refactor).
    # ------------------------------------------------------------------

    def root(self, request):
        """
        GET `/onboard/` — point d'entree du wizard.

        Comportement :
          - Pas de brouillon en session -> redirige vers `onboard-identity`.
          - Brouillon en session -> redirige vers `onboard-<wc.current_step>`
            via la table `STEP_TO_URL_NAME`.

        / GET `/onboard/` — wizard entry point.
          - No draft in session -> redirect to `onboard-identity`.
          - Draft in session -> redirect to `onboard-<wc.current_step>`
            via the `STEP_TO_URL_NAME` table.
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            logger.debug("Onboard root hit without draft in session, -> identity.")
            return redirect("onboard-identity")

        logger.debug(
            "Onboard root hit with draft uuid=%s step=%s",
            wc.uuid, wc.current_step,
        )
        return _redirect_to_current_step(request, wc)

    # ------------------------------------------------------------------
    # Helper interne pour les placeholders des steps 11-15.
    # / Internal helper for placeholders of steps 11-15.
    # ------------------------------------------------------------------

    def _placeholder(self, request, step_name, todo_task):
        """
        Reponse HTML minimale pour une step pas encore implementee.
        Utilise un `data-testid="onboard-step-<step>-placeholder"` pour
        que les tests automatises distinguent un placeholder d'un vrai
        rendu. / Minimal HTML response for not-yet-implemented steps.
        Uses a `data-testid` so automated tests can tell apart a
        placeholder from a real render.
        """
        html = (
            f'<!doctype html><html><body>'
            f'<h1 data-testid="onboard-step-{step_name}-placeholder">'
            f'Step {step_name} &mdash; TODO {todo_task}'
            f'</h1></body></html>'
        )
        return HttpResponse(html)

    # ------------------------------------------------------------------
    # Step 1 — Identity (Task 10).
    # ------------------------------------------------------------------

    def get_throttles(self):
        """
        Throttle dynamique selon `self.action`.

        Nécessaire car le ViewSet est expose via `OnboardViewSet.as_view(
        {"post": "identity"})` direct dans `urls.py` (pas via DefaultRouter
        ni via le routing automatique de `@action`). Du coup l'argument
        `throttle_classes=[...]` du decorateur `@action` est ignore par
        DRF (il n'est consulte que par le routing auto).

        On override `get_throttles()` pour restaurer ce comportement.
        Pour l'instant : seul `identity` a un throttle (anti-spam creation
        WC). Ajouter ici si d'autres actions ont besoin.

        / Dynamic throttle by `self.action`. Required because the ViewSet
        is exposed via direct `as_view({"post": "identity"})` in urls.py
        (not via DefaultRouter or `@action` auto-routing). DRF only reads
        the `@action` `throttle_classes` argument from auto-routing.
        Override `get_throttles()` to restore the behavior.
        """
        if getattr(self, "action", None) == "identity":
            return [IdentityPostRateThrottle()]
        return super().get_throttles()

    @action(detail=False, methods=["GET", "POST"], url_path="identity")
    def identity(self, request):
        """
        GET  `/onboard/identity/` -> rend le formulaire d'identite.
        POST `/onboard/identity/` -> valide, cree le brouillon, declenche
        l'envoi de l'OTP, et redirige vers la step suivante :
          - `onboard-place` si l'utilisateur est deja authentifie + email
            verifie (skip OTP),
          - `onboard-verify` sinon.

        Code d'invitation optionnel via `?invite=<code>` :
          - Si valide -> attache l'invitation au WC.
          - Si invalide -> ignore silencieusement (l'utilisateur continue
            sans invitation, pas d'erreur visible).

        / GET `/onboard/identity/` -> renders the identity form.
        POST `/onboard/identity/` -> validates, creates the draft, sends
        the OTP, and redirects to the next step:
          - `onboard-place` if user already authenticated + email verified
            (skip OTP),
          - `onboard-verify` otherwise.

        Optional invitation code via `?invite=<code>`:
          - Valid -> attach the invitation to the WC.
          - Invalid -> silently ignored.
        """
        wc = _get_or_none_wc(request)

        # Lecture eventuelle d'un code d'invitation en query string.
        # / Optionally read invitation code from query string.
        invite_code = request.GET.get("invite", "").strip()
        invitation = None
        if invite_code:
            # Import local : evite de charger onboard.models au top du
            # module si l'utilisateur n'utilise pas d'invitation.
            # / Local import: avoid loading onboard.models at module-top
            # if no invitation is used.
            from onboard.models import OnboardInvitation
            invitation = OnboardInvitation.objects.filter(
                code=invite_code,
            ).first()
            if invitation and not invitation.is_valid():
                # Invitation expiree ou deja utilisee : on ignore silencieusement.
                # / Expired or already-used invitation: silently ignored.
                invitation = None

        if request.method == "GET":
            initial = {}
            # Priorite 1 : pre-remplit depuis le brouillon en session (cas
            # resume / retour en arriere). / Priority 1: pre-fill from
            # the in-session draft (resume / back nav).
            if wc:
                initial = {
                    "email": wc.email,
                    "first_name": wc.first_name,
                    "last_name": wc.last_name,
                    "name": wc.organisation,
                    "dns_choice": wc.dns_choice,
                }
            # Priorite 2 : si l'utilisateur est deja authentifie (cas user
            # qui reviennt sur le wizard apres avoir deja un compte TiBillet),
            # on pre-remplit email/first_name/last_name depuis son profil
            # SANS ecraser un eventuel brouillon (priorite 1 garde le focus).
            # Si email_valid + email matchant, le `skip_otp` du POST
            # bypassera la verification — l'utilisateur ne re-tape pas l'OTP.
            # / Priority 2: if the user is already authenticated, pre-fill
            # email/first_name/last_name from their profile WITHOUT
            # overwriting an existing draft. If email_valid + matching email,
            # the POST `skip_otp` branch will bypass verification.
            if request.user.is_authenticated and not wc:
                initial.setdefault("email", request.user.email)
                initial.setdefault(
                    "first_name", getattr(request.user, "first_name", "") or "",
                )
                initial.setdefault(
                    "last_name", getattr(request.user, "last_name", "") or "",
                )
            return render(request, "onboard/steps/01_identity.html", {
                "step": "identity",
                "initial": initial,
                "invitation": invitation,
            })

        # === POST ===
        # Imports locaux pour eviter une dependance circulaire au chargement
        # de l'app onboard. / Local imports to avoid circular import.
        from onboard.serializers import OnboardIdentitySerializer

        serializer = OnboardIdentitySerializer(data=request.data)
        if not serializer.is_valid():
            # 422 + re-rendu du formulaire avec les erreurs et les valeurs saisies.
            # / 422 + re-render the form with errors and submitted values.
            # `request.data` est un QueryDict immuable ; on en fait un dict
            # mutable pour pouvoir le passer comme `initial`.
            # / `request.data` is an immutable QueryDict; convert to a
            # mutable dict to pass as `initial`.
            initial_from_post = {
                key: request.data.get(key, "")
                for key in (
                    "email", "first_name", "last_name", "name", "dns_choice",
                )
            }
            return render(request, "onboard/steps/01_identity.html", {
                "step": "identity",
                "errors": serializer.errors,
                "initial": initial_from_post,
                "invitation": invitation,
            }, status=422)

        data = serializer.validated_data

        # Cas user authentifie + email_valid + memes emails : on saute l'OTP.
        # / Authenticated user + verified email + matching addresses -> skip OTP.
        skip_otp = (
            request.user.is_authenticated
            and getattr(request.user, "email_valid", False)
            and request.user.email.lower() == data["email"].lower()
        )

        # Persistance du brouillon dans le schema `meta`.
        # / Persist the draft in the `meta` schema.
        with schema_context("meta"):
            wc = WaitingConfiguration.objects.create(
                organisation=data["name"],
                email=data["email"],
                dns_choice=data["dns_choice"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                # `phone` est obligatoire dans le modele historique. On le
                # laisse vide ici (sera saisi plus tard) — le champ accepte
                # max_length=20 mais pas blank=True. En l'absence de
                # contrainte DB stricte (CharField), une chaine vide passe.
                # / `phone` is required by the legacy model; we leave it
                # empty (filled later). CharField without NOT NULL
                # constraint accepts an empty string.
                phone="",
                email_confirmed=skip_otp,
                current_step=(
                    WaitingConfiguration.STEP_PLACE if skip_otp
                    else WaitingConfiguration.STEP_VERIFY
                ),
                invitation=invitation,
            )

        # Envoi automatique de l'OTP (refacto 2026-05-15) : auparavant,
        # l'OTP n'etait envoye que sur clic explicite "Recevoir le code"
        # cote step Verify. Friction UX inutile : l'utilisateur arrivait
        # sur Verify, regardait sa boite mail vide, devait revenir cliquer
        # un bouton, attendre. Slack / Linear / Stripe envoient l'OTP des
        # la validation de l'email — on s'aligne. Le bouton "Renvoyer"
        # reste, avec cooldown 60s + rate-limit IP 3/h (cf. resend_otp).
        # On skip si l'utilisateur est deja authentifie + email valide
        # (branche `skip_otp` ci-dessus) — il sera redirige direct vers
        # Place sans passer par Verify.
        # / Auto-send OTP (refactor 2026-05-15): used to require an
        # explicit "Receive code" click on Verify — pointless friction.
        # Now sent here, right after draft creation. The "Resend" button
        # stays, with 60s cooldown + 3/h IP rate-limit (cf. resend_otp).
        # Skipped on the `skip_otp` branch (auth user, redirected to Place).
        if not skip_otp:
            _generate_and_send_otp_for_wc(wc, is_resend=False)

        _set_session_wc(request, wc)
        return redirect(
            "onboard-place" if skip_otp else "onboard-verify",
        )

    # ------------------------------------------------------------------
    # Placeholders pour les steps 11-15 (a remplacer dans leurs tasks).
    # / Placeholders for steps 11-15 (to be replaced in their tasks).
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Step 2 — Verify OTP (Task 11).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["GET", "POST"], url_path="verify")
    def verify(self, request):
        """
        GET  `/onboard/verify/` -> rend le formulaire de saisie OTP.
        POST `/onboard/verify/` -> verifie le code, met a jour le brouillon,
        et redirige vers `onboard-place`.

        Securite :
          - Apres 5 tentatives ratees -> compte verrouille (status 422).
          - OTP expire (otp_expires_at < now) -> 422 + message "code expire".
          - OTP errone -> incremente `otp_attempts` + 422.
          - OTP correct -> `email_confirmed=True`, purge `otp_hash`, et
            cree le `TibilletUser` si absent (`get_or_create_user`).

        / GET `/onboard/verify/` -> renders OTP entry form.
        POST `/onboard/verify/` -> verifies the code, updates the draft,
        redirects to `onboard-place`.

        Security:
          - After 5 failed attempts -> account locked (status 422).
          - Expired OTP -> 422 + "expired" message.
          - Wrong OTP -> increments `otp_attempts` + 422.
          - Correct OTP -> `email_confirmed=True`, purges `otp_hash`, and
            creates the `TibilletUser` if absent.
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            # Pas de brouillon en session : on renvoie vers la step 1.
            # / No draft in session: redirect to step 1.
            return redirect("onboard-identity")

        if request.method == "GET":
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                # `has_pending_otp` permet au template d'adapter le label :
                # "Recevoir le code" si pas encore envoye, "Renvoyer" sinon.
                # / Lets the template adapt the label: "Receive the code"
                # before any send, "Resend" afterwards.
                "has_pending_otp": bool(wc.otp_hash),
            })

        # === POST ===
        # Imports locaux pour eviter une dependance circulaire au chargement
        # de l'app onboard. / Local imports to avoid circular import.
        from django.conf import settings
        from django.utils import timezone

        from onboard.serializers import OnboardVerifySerializer
        from onboard.services import verify_otp

        # Bypass DEBUG (feedback mainteneur 2026-05-15) : en mode dev local
        # on n'a pas toujours de worker Celery actif pour envoyer l'OTP par
        # email. On accepte donc tout code 6 chiffres saisi sans verifier.
        # Le user peut donc avancer dans le wizard sans dependance Celery.
        # En prod (DEBUG=False), le check OTP normal s'applique.
        # / DEBUG bypass (maintainer feedback 2026-05-15): local dev may
        # not have a running Celery worker to send OTP emails. We accept
        # any 6-digit code without verifying. The user can thus progress
        # in the wizard without a Celery dependency. In prod (DEBUG=False)
        # the regular OTP check applies.
        if settings.DEBUG:
            serializer = OnboardVerifySerializer(data=request.data)
            if not serializer.is_valid():
                return render(request, "onboard/steps/02_verify.html", {
                    "step": "verify",
                    "email": wc.email,
                    "has_pending_otp": bool(wc.otp_hash),
                    "errors": serializer.errors,
                }, status=422)
            logger.warning(
                "DEBUG: OTP check bypassed for WC %s (settings.DEBUG=True)",
                wc.uuid,
            )
            # Meme finalisation que la branche prod (helper partage) : update
            # WC + creation/activation user + login Django. Sans login() ici,
            # `place` GET redirigeait vers identity car le garde
            # `_get_confirmed_wc_or_redirect` exige `request.user.is_authenticated`.
            # / Same post-success finalisation as the prod branch (shared
            # helper): update WC + create/activate user + Django login.
            # Without login() here, `place` GET would redirect to identity
            # because `_get_confirmed_wc_or_redirect` requires authentication.
            user = _finalize_otp_success(request, wc)
            if user is None:
                return render(request, "onboard/steps/02_verify.html", {
                    "step": "verify",
                    "email": wc.email,
                    "has_pending_otp": bool(wc.otp_hash),
                    "errors": {"otp": [_("Email error on user account.")]},
                }, status=422)
            return redirect("onboard-place")

        serializer = OnboardVerifySerializer(data=request.data)
        if not serializer.is_valid():
            # Format invalide (pas 6 chiffres) -> 422 + re-rendu avec erreurs.
            # / Invalid format (not 6 digits) -> 422 + re-render with errors.
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": serializer.errors,
            }, status=422)

        # Verrou apres 5 tentatives ratees (anti brute-force).
        # / Lock after 5 failed attempts (anti brute-force).
        if wc.otp_attempts >= 5:
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": {"otp": [_(
                    "Account locked: too many wrong attempts."
                )]},
                "locked": True,
            }, status=422)

        # Pas encore de code genere : l'user a saisi un code sans avoir
        # clique "Recevoir le code" (Mod 1 — OTP envoye seulement sur clic).
        # / No code generated yet: the user submitted before clicking
        # "Receive the code" (Mod 1 — OTP sent only on explicit click).
        if not wc.otp_hash:
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": {"otp": [_(
                    "No code requested yet. Click \"Receive the code\" first."
                )]},
            }, status=422)

        # OTP expire : sortie immediate, pas d'incrementation d'attempts.
        # / Expired OTP: immediate exit, no attempt increment.
        if wc.otp_expires_at is None or wc.otp_expires_at < timezone.now():
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": {"otp": [_("OTP expired. Please request a new code.")]},
            }, status=422)

        # Verification du code : on hash le saisi et on compare au hash stocke.
        # / Verify the code: hash the input and compare to the stored hash.
        if not verify_otp(serializer.validated_data["otp"], wc.otp_hash):
            # Code incorrect : incrementation atomique via .update() pour
            # eviter les race conditions (deux requetes simultanees).
            # / Wrong code: atomic increment via .update() to avoid races.
            with schema_context("meta"):
                WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                    otp_attempts=wc.otp_attempts + 1,
                )
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": {"otp": [_("Wrong code.")]},
            }, status=422)

        # === Succes ===
        # Finalisation : update WC + creation/activation user + login Django.
        # Helper partage avec la branche DEBUG pour garantir un comportement
        # identique (sinon le garde `_get_confirmed_wc_or_redirect` de la
        # step suivante echoue et l'utilisateur est renvoye sur identity).
        # / Post-success finalisation: update WC + create/activate user +
        # Django login. Shared helper with the DEBUG branch to guarantee
        # identical behaviour (otherwise `_get_confirmed_wc_or_redirect`
        # of the next step fails and the user is sent back to identity).
        user = _finalize_otp_success(request, wc)
        if user is None:
            # Cas extreme : email_error sur un user existant (cf. utils.py).
            # On bloque ici plutot qu'au step suivant. / Edge case: email_error
            # on existing user — block here rather than next step.
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
                "has_pending_otp": bool(wc.otp_hash),
                "errors": {"otp": [_("Email error on user account.")]},
            }, status=422)

        return redirect("onboard-place")

    # ------------------------------------------------------------------
    # Step 2bis — Resend OTP (Task 11).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["POST"], url_path="resend-otp")
    def resend_otp(self, request):
        """
        POST `/onboard/resend-otp/` — regenere un OTP et le renvoie par mail.

        Rate-limit Redis : max 3 envois par heure par IP. Au dela, on
        renvoie un partial HTMX 429 ("trop d'envois, reessayer plus tard").

        Cote brouillon : on regenere `otp_hash` + `otp_expires_at`, on
        remet `otp_attempts=0` (l'utilisateur a un nouveau quota) et on
        incremente `otp_resend_count` (audit).

        / POST `/onboard/resend-otp/` — regenerates an OTP and re-sends it.

        Redis rate-limit: max 3 sends per hour per IP. Beyond that, we
        return a 429 HTMX partial ("too many sends, try later").

        Draft-side: regenerate `otp_hash` + `otp_expires_at`, reset
        `otp_attempts=0` (fresh quota for the user), and bump
        `otp_resend_count` (audit).
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            # Pas de brouillon en session : 404 (l'utilisateur doit recommencer).
            # / No draft in session: 404 (user must restart).
            return HttpResponse(status=404)

        # Imports locaux : evite la dependance circulaire et le cout au
        # chargement du module. / Local imports: avoid circular dep + load cost.
        from django.core.cache import cache
        from django.utils import timezone

        from AuthBillet.utils import get_client_ip

        # Garde 1 — Cooldown WC : empeche un user de spammer "Renvoyer"
        # sur le meme brouillon (ex. double-clic accidentel ou refresh).
        # 60s entre 2 envois pour le meme WC. Independant du rate-limit IP.
        # / Guard 1 — WC cooldown: prevents the user from spamming "Resend"
        # on the same draft. 60s between two sends for the same WC.
        if wc.otp_sent_at is not None:
            seconds_since_last_send = (
                timezone.now() - wc.otp_sent_at
            ).total_seconds()
            if seconds_since_last_send < OTP_RESEND_COOLDOWN_SECONDS:
                seconds_remaining = int(
                    OTP_RESEND_COOLDOWN_SECONDS - seconds_since_last_send,
                )
                return render(
                    request,
                    "onboard/partials/resend_cooldown.html",
                    {"seconds_remaining": seconds_remaining},
                    status=429,
                )

        # Garde 2 — Rate-limit Redis par vraie IP client. On utilise
        # `get_client_ip` qui lit `HTTP_X_FORWARDED_FOR` derriere le proxy
        # (Traefik/nginx). Sans ca, `REMOTE_ADDR` brut serait l'IP du proxy
        # et tous les utilisateurs partageraient le meme bucket — un seul
        # attaquant pourrait bloquer les renvois OTP de toute la plateforme.
        # TTL 1h, compteur incremente a chaque demande.
        # / Guard 2 — Per-real-IP Redis rate-limit. Uses `get_client_ip`
        # (X-Forwarded-For aware) so all users don't share the proxy IP
        # bucket. 1h TTL.
        ip = get_client_ip(request) or "unknown"
        cache_key = f"onboard:resend:{ip}"
        count = cache.get(cache_key, 0)
        if count >= 3:
            return render(
                request, "onboard/partials/resend_blocked.html", status=429,
            )
        # cache.set avec TTL 3600s : la fenetre se renouvelle automatiquement.
        # / cache.set with 3600s TTL: window auto-renews.
        cache.set(cache_key, count + 1, 3600)

        # Generation + envoi via le helper partage avec `identity` POST.
        # `is_resend=True` -> incremente `otp_resend_count` pour l'audit.
        # / Generate + send via the helper shared with `identity` POST.
        # `is_resend=True` -> increments `otp_resend_count` for audit.
        _generate_and_send_otp_for_wc(wc, is_resend=True)
        return render(request, "onboard/partials/resend_sent.html")

    # ------------------------------------------------------------------
    # Step 3 — Place (Task 12).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["GET", "POST"], url_path="place")
    def place(self, request):
        """
        GET  `/onboard/place/` -> rend le formulaire d'adresse + GPS.
        POST `/onboard/place/` -> valide, met a jour le brouillon, et
        redirige vers `onboard-descriptions`.

        Pre-requis : brouillon en session ET `email_confirmed=True`. Sinon
        -> redirection silencieuse vers `onboard-identity` (l'utilisateur
        ne doit pas pouvoir contourner la verification OTP).

        Champs persistes en cas de succes :
          street_address, postal_code, address_locality, address_country,
          latitude, longitude, current_step="descriptions".

        NOTE : `short_description` est desormais saisi sur la step suivante
        ("Presentation") avec la `long_description` et le logo
        (feedback mainteneur 2026-05-14).

        / GET `/onboard/place/` -> renders the address + GPS form.
        POST `/onboard/place/` -> validates, updates the draft, redirects
        to `onboard-descriptions`.

        NOTE: `short_description` is now collected on the next step
        ("Presentation") alongside the long description and the logo.

        Prerequisite: draft in session AND `email_confirmed=True`. Otherwise
        -> silent redirect to `onboard-identity` (user must not bypass OTP).
        """
        wc, redirect_response = _get_confirmed_wc_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        if request.method == "GET":
            return render(request, "onboard/steps/03_place.html", {
                "step": "place", "wc": wc,
            })

        # === POST ===
        # Import local pour eviter une dependance circulaire au chargement
        # de l'app onboard. / Local import to avoid circular import.
        from onboard.serializers import OnboardPlaceSerializer

        serializer = OnboardPlaceSerializer(data=request.data)
        # Whitelist explicite des champs renvoyes au template en cas d'erreur.
        # On evite `request.data.dict()` qui n'est pas portable (MultiValueDict
        # vs dict simple selon le parser DRF).
        # / Explicit whitelist of fields echoed back to the template on
        # error. We avoid `request.data.dict()` which isn't portable across
        # DRF parsers (MultiValueDict vs plain dict).
        initial = {
            key: request.data.get(key, "")
            for key in (
                "street_address", "postal_code", "address_locality",
                "address_country",
                "place_latitude", "place_longitude", "place_adresse",
            )
        }
        if not serializer.is_valid():
            # 422 + re-rendu du formulaire avec les erreurs et les valeurs saisies.
            # / 422 + re-render the form with errors and submitted values.
            return render(request, "onboard/steps/03_place.html", {
                "step": "place", "wc": wc,
                "errors": serializer.errors, "initial": initial,
            }, status=422)

        data = serializer.validated_data
        # Persistance dans le schema `meta` via `.update()` atomique (pas
        # besoin de re-fetch). / Persist in the `meta` schema via atomic
        # `.update()` (no re-fetch needed).
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                street_address=data["street_address"],
                postal_code=data["postal_code"],
                address_locality=data["address_locality"],
                address_country=data["address_country"],
                latitude=data["place_latitude"],   # nouveau nom prefixe widget
                longitude=data["place_longitude"], # idem
                current_step=WaitingConfiguration.STEP_DESCRIPTIONS,
            )
        return redirect("onboard-descriptions")

    # ------------------------------------------------------------------
    # Step 4 — Descriptions + logo (Task 13).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["GET", "POST"], url_path="descriptions")
    def descriptions(self, request):
        """
        GET  `/onboard/descriptions/` -> rend le formulaire "Presentation"
        (description courte + description longue + upload logo).
        POST `/onboard/descriptions/` -> valide, met a jour le brouillon,
        et redirige vers `onboard-events`.

        Pre-requis : brouillon en session ET `email_confirmed=True`. Sinon
        -> redirection silencieuse vers `onboard-identity` (l'utilisateur
        ne doit pas pouvoir contourner la verification OTP).

        Champs persistes en cas de succes :
          short_description (obligatoire), long_description (optionnel),
          logo (optionnel), current_step="events".

        NOTE : `short_description` etait initialement saisi sur la step
        "Place" mais a ete deplace ici (feedback mainteneur 2026-05-14)
        pour regrouper toutes les descriptions sur une meme page
        "Presentation".

        PIEGE : `logo` est un `StdImageField`. On NE peut PAS utiliser
        `.update(logo=...)` (QuerySet.update bypass `save()` et ne genere
        donc pas les variations StdImage). On doit charger l'instance,
        affecter l'attribut, puis appeler `wc.save()` pour declencher la
        generation des variations (med, hdr, fhd, thumbnail).

        / GET `/onboard/descriptions/` -> renders the "Presentation" form
        (short description + long description + logo upload).
        POST `/onboard/descriptions/` -> validates, updates the draft,
        redirects to `onboard-events`.

        Prerequisite: draft in session AND `email_confirmed=True`. Otherwise
        -> silent redirect to `onboard-identity`.

        Persisted fields on success:
          short_description (required), long_description (optional),
          logo (optional), current_step="events".

        NOTE: `short_description` was initially collected on the "Place"
        step but moved here so all descriptions live on the same page.

        PITFALL: `logo` is a `StdImageField`. We MUST NOT use
        `.update(logo=...)` (QuerySet.update bypasses `save()` and skips
        StdImage variations generation). Instead, load the instance, set
        the attribute, then call `wc.save()` to trigger variations
        generation (med, hdr, fhd, thumbnail).
        """
        wc, redirect_response = _get_confirmed_wc_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        if request.method == "GET":
            return render(request, "onboard/steps/04_descriptions.html", {
                "step": "descriptions", "wc": wc,
            })

        # === POST ===
        # Import local pour eviter une dependance circulaire au chargement
        # de l'app onboard. / Local import to avoid circular import.
        from onboard.serializers import OnboardDescriptionsSerializer

        # `request.data` contient files + form fields grace au MultiPartParser
        # par defaut de DRF (active automatiquement avec `enctype="multipart/form-data"`).
        # / `request.data` exposes files + form fields thanks to DRF's
        # MultiPartParser (auto-activated with `enctype="multipart/form-data"`).
        serializer = OnboardDescriptionsSerializer(data=request.data)
        if not serializer.is_valid():
            # 422 + re-rendu du formulaire avec les erreurs.
            # On ne re-injecte pas le fichier `logo` dans `initial` (un
            # input type=file ne peut pas etre pre-rempli en HTML), mais
            # on re-injecte la description longue pour ne pas la perdre.
            # / 422 + re-render with errors. We don't echo the file back
            # (HTML file inputs cannot be pre-filled), but we keep the
            # long description so the user doesn't lose their text.
            return render(request, "onboard/steps/04_descriptions.html", {
                "step": "descriptions", "wc": wc,
                "errors": serializer.errors,
                "initial": {
                    "short_description": request.data.get("short_description", ""),
                    "long_description": request.data.get("long_description", ""),
                },
            }, status=422)

        data = serializer.validated_data

        # Persistance dans le schema `meta`. On utilise `instance.save()`
        # (pas `.update()`) pour declencher la generation des variations
        # StdImage du logo. / Persist in the `meta` schema via
        # `instance.save()` (NOT `.update()`) to trigger StdImage
        # variations generation for the logo.
        #
        # NOTE 2026-05-16 : la step "Evenements" a ete masquee du parcours
        # par defaut (decision mainteneur — wizard trop long). On passe
        # directement `current_step=LAUNCH` et on enqueue la task de
        # creation tenant ici (au lieu d'attendre le POST de la step
        # events). Le code et les routes `events_*` restent en place pour
        # un usage futur ; on peut revenir au flow d'origine en remettant
        # `STEP_EVENTS` + `redirect("onboard-events")`.
        # / NOTE 2026-05-16: the "Events" step is hidden from the default
        # flow (wizard was too long). We jump straight to LAUNCH and
        # enqueue tenant creation here (previously in `events` POST). The
        # `events_*` routes are kept in code for future reuse.
        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            # short_description : obligatoire dans le serializer, toujours
            # present dans validated_data. / short_description: required by
            # the serializer, always present in validated_data.
            wc_db.short_description = data["short_description"]
            # long_description : optionnel. La cle existe dans validated_data
            # quand le user a saisi quelque chose ; sinon CharField renvoie ""
            # (allow_blank=True). On peut donc assigner sans condition.
            # / long_description: optional. CharField returns "" when blank
            # (allow_blank=True), so assigning unconditionally is safe.
            wc_db.long_description = data.get("long_description", "") or ""
            # `logo` est optionnel (allow_null=True dans le serializer).
            # Si absent du POST, `validated_data` ne contient pas la cle.
            # On ne touche au champ que si l'utilisateur a uploade.
            # / `logo` is optional (allow_null=True). If absent from POST,
            # `validated_data` won't have the key. Only assign when uploaded.
            if "logo" in data and data["logo"] is not None:
                wc_db.logo = data["logo"]
            wc_db.current_step = WaitingConfiguration.STEP_LAUNCH
            wc_db.save()

        # Enqueue la task asynchrone qui cree le tenant final. On passe
        # `wc_uuid` en str (Celery serialise mal les UUID en JSON par defaut).
        # Idempotent : la task verifie `wc.tenant_id is None` au demarrage.
        # / Enqueue the async task creating the final tenant. We pass
        # `wc_uuid` as str. Idempotent: the task checks `wc.tenant_id is None`.
        from onboard.tasks import create_tenant_from_draft

        create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))
        return redirect("onboard-launch")

    # ------------------------------------------------------------------
    # Step 5 — Events drafts (Task 14).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["GET", "POST"], url_path="events")
    def events(self, request):
        """
        GET  `/onboard/events/` -> rend le formulaire des brouillons d'event
        (liste deja saisie + sous-form HTMX pour ajouter un event).
        POST `/onboard/events/` -> FINALISE la collecte : on passe la step
        a "launch", on enqueue la task asynchrone `create_tenant_from_draft`,
        et on redirige vers `onboard-launch`. Le contenu du POST n'est pas
        relu (la liste est deja construite via `events_add` / `events_remove`).

        Pre-requis : brouillon en session ET `email_confirmed=True`. Sinon
        -> redirection silencieuse vers `onboard-identity` (l'utilisateur
        ne doit pas pouvoir contourner la verification OTP).

        Choix : pas d'event obligatoire. L'utilisateur peut tres bien lancer
        son tenant sans event pre-renseigne (la liste reste vide). La step
        sert juste a permettre la pre-saisie d'events qui seront recrees
        par `create_tenant_from_draft`.

        / GET `/onboard/events/` -> renders the event drafts form (existing
        list + HTMX sub-form to add one).
        POST `/onboard/events/` -> FINALIZE: advance step to "launch",
        enqueue the async `create_tenant_from_draft` task, redirect to
        `onboard-launch`. The POST body isn't read (the list is built via
        `events_add` / `events_remove`).

        Prerequisite: draft in session AND `email_confirmed=True`. Otherwise
        -> silent redirect to `onboard-identity`.

        Choice: no event is required. The user can launch with an empty list.
        """
        wc, redirect_response = _get_confirmed_wc_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        if request.method == "GET":
            # `events_draft` est un JSONField default=list. On force `or []`
            # par defense (si la valeur a ete remise a None par une migration
            # ou un override admin). / `events_draft` is a JSONField with
            # default=list. We force `or []` defensively (in case it was
            # nulled by a migration or admin override).
            return render(request, "onboard/steps/05_events.html", {
                "step": "events", "wc": wc,
                "events": wc.events_draft or [],
            })

        # === POST -> finalisation ===
        # Import local pour eviter la dependance circulaire au chargement
        # de l'app onboard. / Local import to avoid circular import.
        from onboard.tasks import create_tenant_from_draft

        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                current_step=WaitingConfiguration.STEP_LAUNCH,
            )

        # Enqueue la task asynchrone qui cree le tenant final. On passe
        # `wc_uuid` en str (Celery serialise mal les UUID en JSON par defaut).
        # / Enqueue the async task creating the final tenant. We pass
        # `wc_uuid` as str (Celery serializes UUIDs poorly by default).
        create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))

        return redirect("onboard-launch")

    @action(detail=False, methods=["POST"], url_path="events/add")
    def events_add(self, request):
        """
        POST `/onboard/events/add/` -> ajoute un brouillon d'event dans
        `wc.events_draft` (liste JSON). Renvoie le partial HTMX
        `events_list.html` qui represente la liste mise a jour.

        Champs attendus dans le POST : `name`, `datetime` (ISO datetime-local),
        `description` (optionnel). Validation via `OnboardEventDraftSerializer`.

        En cas d'erreur de validation : on re-rend `events_list.html` avec
        la liste actuelle inchangee + les erreurs affichees dans
        `aria-live="polite"`. Le sous-form (`event_row_form.html`) inclus
        a part dans le template parent gere son propre re-rendu via une
        autre cible HTMX, donc ici on garde la cible "liste" simple.

        / POST `/onboard/events/add/` -> append an event draft to
        `wc.events_draft` (JSON list). Returns the `events_list.html` HTMX
        partial with the updated list.

        Expected POST fields: `name`, `datetime`, `description` (optional).
        Validation via `OnboardEventDraftSerializer`.
        """
        wc, error_response = _get_confirmed_wc_or_404(request)
        if error_response is not None:
            # Pas de session : 404. HTMX recevra une erreur visible cote
            # client. / No session: 404. HTMX will show an error.
            return error_response

        # Import local pour eviter la dependance circulaire au chargement
        # de l'app onboard. / Local import to avoid circular import.
        from onboard.serializers import OnboardEventDraftSerializer

        # Whitelist explicite des champs : `request.data.dict()` n'est pas
        # portable selon le parser DRF (MultiValueDict vs dict). On ne lit
        # que ce qu'on attend. `image` est gere a part car il s'agit d'un
        # fichier uploade (present dans `request.FILES` cote Django, expose
        # par `request.data` cote DRF via le MultiPartParser).
        # / Explicit field whitelist: `request.data.dict()` isn't portable
        # across DRF parsers. Read only what we expect. `image` is a file
        # upload (DRF surfaces it through `request.data` via MultiPartParser).
        payload = {
            key: request.data.get(key, "")
            for key in ("name", "datetime", "description")
        }
        # Image : on ne l'injecte que si presente (sinon le serializer
        # recevrait une chaine vide "" qui ferait planter ImageField).
        # / Image: only inject when present (otherwise ImageField would
        # choke on an empty string "").
        uploaded_image = request.data.get("image")
        if uploaded_image:
            payload["image"] = uploaded_image
        serializer = OnboardEventDraftSerializer(data=payload)

        if not serializer.is_valid():
            # Erreurs : on re-rend la liste inchangee + erreurs dans le
            # template (affichage aria-live). / Errors: re-render the
            # unchanged list + errors in the template (aria-live region).
            return render(request, "onboard/partials/events_list.html", {
                "events": wc.events_draft or [],
                "errors": serializer.errors,
                "initial": payload,
            })

        data = serializer.validated_data

        # === Persistance optionnelle de l'image via `default_storage` ===
        # On stocke le fichier sous `onboard_drafts/<wc_uuid>/events/<uuid4>.<ext>`
        # pour eviter les collisions et empecher l'utilisateur de deviner
        # l'URL d'un fichier appartenant a un autre brouillon.
        # On garde le chemin RELATIF (utilisable par `default_storage.url()`
        # et compatible S3/etc. en prod) dans le JSONField `events_draft`.
        # / Optional image persistence via `default_storage`. Path layout
        # `onboard_drafts/<wc_uuid>/events/<uuid4>.<ext>` avoids collisions
        # and prevents users from guessing other drafts' file URLs. The
        # RELATIVE path (usable by `default_storage.url()` and S3-friendly)
        # is stored in the `events_draft` JSONField.
        image_path = None
        image_file = data.get("image")
        if image_file is not None:
            import os
            import uuid as uuid_module

            from django.core.files.storage import default_storage

            # Extraction de l'extension d'origine, lowercased.
            # ImageField a deja valide qu'il s'agit d'une image et le
            # serializer impose une whitelist (jpeg/png/webp), donc on
            # peut faire confiance a l'extension (fallback `.bin` en defense).
            # / Extract original extension, lowercased. ImageField validated
            # the file is an image and the serializer enforces a whitelist,
            # so the extension is trustworthy (`.bin` defensive fallback).
            _, ext = os.path.splitext(image_file.name or "")
            ext = (ext or ".bin").lower()
            target_relpath = (
                f"onboard_drafts/{wc.uuid}/events/"
                f"{uuid_module.uuid4().hex}{ext}"
            )
            # `default_storage.save()` renvoie le path effectivement utilise
            # (peut differer si collision improbable -> suffix auto).
            # / `default_storage.save()` returns the actually-used path
            # (may differ in case of unlikely collision -> auto-suffix).
            image_path = default_storage.save(target_relpath, image_file)

        # PIEGE JSONField : `DateTimeField` renvoie un `datetime` python.
        # JSON ne sait pas serialiser un datetime tel quel — on stocke en
        # ISO 8601 (string) via `.isoformat()`. Au reload, on peut reparser
        # avec `datetime.fromisoformat()` si on veut le manipuler.
        # / JSONField pitfall: `DateTimeField` returns a python `datetime`.
        # JSON cannot serialize it as-is — store as ISO 8601 string via
        # `.isoformat()`. Reparse with `datetime.fromisoformat()` if needed.
        new_event = {
            "name": data["name"],
            "datetime": data["datetime"].isoformat(),
            "description": data.get("description", ""),
        }
        # `image` n'apparait dans le dict que si l'utilisateur en a uploade
        # une (cf. plan : pas de cle quand absente, pas de placeholder).
        # / `image` only appears in the dict when uploaded (no placeholder
        # key when absent, per the plan).
        if image_path:
            new_event["image"] = image_path

        # Append + persist atomique. On recharge la liste depuis la DB pour
        # eviter d'ecraser un ajout concurrent (peu probable mais propre).
        # / Atomic append + persist. Reload the list from DB to avoid
        # overwriting a concurrent add (unlikely but cleaner).
        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            current_list = wc_db.events_draft or []
            updated_list = current_list + [new_event]
            wc_db.events_draft = updated_list
            wc_db.save(update_fields=["events_draft"])

        return render(request, "onboard/partials/events_list.html", {
            "events": updated_list,
        })

    @action(
        detail=False, methods=["POST"],
        url_path=r"events/(?P<idx>\d+)/remove",
    )
    def events_remove(self, request, idx=None):
        """
        POST `/onboard/events/<idx>/remove/` -> retire l'event a l'index
        `idx` de `wc.events_draft`. Renvoie le partial HTMX
        `events_list.html` avec la liste mise a jour.

        Si `idx` est hors-bornes ou la liste vide -> renvoie la liste
        actuelle (idempotent, pas d'erreur). / If `idx` is out of range or
        the list is empty -> return the current list (idempotent, no error).

        NOTE : on utilise `url_path` avec une regex DRF (`(?P<idx>\d+)`)
        plutot que `path("<int:idx>", ...)` cote `urls.py`. C'est plus
        consistant avec les autres actions du ViewSet qui exposent toutes
        leur path via `url_path`. La regex DRF est bien supportee par
        `as_view()`. / We use a DRF regex `url_path` instead of `<int:idx>`
        in `urls.py` to stay consistent with other ViewSet actions whose
        path is declared via `url_path`. DRF regex is supported by
        `as_view()`.
        """
        wc, error_response = _get_confirmed_wc_or_404(request)
        if error_response is not None:
            return error_response

        # Conversion explicite : `idx` arrive en str via le routeur DRF.
        # / Explicit cast: `idx` comes as str from the DRF router.
        try:
            index = int(idx)
        except (TypeError, ValueError):
            # Si jamais la regex est contournee : on rend la liste inchangee.
            # / If somehow the regex is bypassed: render unchanged list.
            return render(request, "onboard/partials/events_list.html", {
                "events": wc.events_draft or [],
            })

        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            current_list = wc_db.events_draft or []
            if 0 <= index < len(current_list):
                # On capture le chemin image AVANT le pop pour pouvoir
                # supprimer le fichier orphelin apres la persistance.
                # / Capture the image path BEFORE popping so we can delete
                # the orphan file after persisting the new list.
                removed_event = current_list[index]
                image_path = removed_event.get("image") if isinstance(
                    removed_event, dict,
                ) else None

                # Pop par index : retire l'event a la position demandee.
                # / Pop by index: remove the event at the given position.
                updated_list = current_list[:index] + current_list[index + 1:]
                wc_db.events_draft = updated_list
                wc_db.save(update_fields=["events_draft"])

                # Nettoyage du fichier image associe via `default_storage`
                # (compatible S3/etc.). On reste defensif : la suppression
                # ne doit pas faire echouer la requete si le fichier a
                # deja disparu (cas reload manuel, purge concurrente).
                # / Clean up the associated image file via `default_storage`
                # (S3-friendly). Stay defensive: failing to delete must not
                # break the request (file already gone, concurrent purge, ...).
                if image_path:
                    from django.core.files.storage import default_storage

                    try:
                        if default_storage.exists(image_path):
                            default_storage.delete(image_path)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning(
                            "events_remove: failed to delete image %s: %s",
                            image_path, exc,
                        )
            else:
                # Out of bounds : on renvoie la liste actuelle sans toucher
                # a la DB. / Out of bounds: return current list, don't touch DB.
                updated_list = current_list

        return render(request, "onboard/partials/events_list.html", {
            "events": updated_list,
        })

    # ------------------------------------------------------------------
    # Step 6 — Launch + status polling + retry (Task 15).
    # ------------------------------------------------------------------

    @action(detail=False, methods=["GET", "POST"], url_path="launch")
    def launch(self, request):
        """
        GET `/onboard/launch/` -> rend la page de lancement.

        La page contient :
          - le recapitulatif des choix de l'utilisateur,
          - une mention du carrousel d'inspirations (Task 19 finalisera),
          - un container `#status` qui poll `/onboard/launch/status/`
            toutes les 2 secondes via HTMX.

        Pre-requis : brouillon en session ET `email_confirmed=True`. Sinon
        -> redirection silencieuse vers `onboard-identity` (l'utilisateur
        ne doit pas pouvoir contourner la verification OTP).

        Cette vue NE declenche PAS la task `create_tenant_from_draft` :
        la step 5 (events finalize, POST `/onboard/events/`) l'a deja
        enqueuee. `launch` est purement un ecran d'attente / suivi.

        / GET `/onboard/launch/` -> renders the launch page.

        The page contains:
          - recap of user choices,
          - mention of the inspiration carousel (Task 19),
          - `#status` container polling `/onboard/launch/status/` every
            2 seconds via HTMX.

        Prerequisite: draft in session AND `email_confirmed=True`.
        Otherwise -> silent redirect to `onboard-identity`.

        This view does NOT enqueue `create_tenant_from_draft`: step 5
        (events finalize, POST `/onboard/events/`) already did. `launch`
        is purely a status / waiting screen.
        """
        wc, redirect_response = _get_confirmed_wc_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        # `events_draft` est un JSONField default=list. On force `or []` par
        # defense (cas None apres migration ou override admin).
        # / `events_draft` is a JSONField with default=list. Force `or []`
        # defensively (None case after migration or admin override).
        events_count = len(wc.events_draft or [])

        # Mod 4 (feedback mainteneur 2026-05-15) : chaque chargement de la
        # page launch (re-)enqueue la task de creation tenant tant qu'elle
        # n'a pas reussi. La task est idempotente via un claim Redis
        # (`onboard:create_tenant_claim:<uuid>`, TTL 5min), donc un double
        # appel est safe. Cela rend le wizard plus robuste : si Celery
        # avait perdu le message ou si l'utilisateur recharge apres avoir
        # vu une erreur, on relance proprement.
        # On stocke le timestamp de demarrage du polling dans la session
        # pour que `launch_status` puisse calculer le timeout 5min (Mod 5).
        # / Mod 4 (maintainer feedback): every load of launch (re-)enqueues
        # the creation task until success. The task is idempotent via a
        # Redis claim, so double-calls are safe. Also store the polling
        # start time in session for the 5-min timeout (Mod 5).
        if wc.tenant_id is None and not wc.error_message:
            from django.utils import timezone
            from onboard.tasks import create_tenant_from_draft
            create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))
            # On (re)initialise le timestamp de polling seulement si
            # absent : un refresh ne reset pas la fenetre des 5 min.
            # / Init polling timestamp only if missing: a refresh does
            # not reset the 5-min window.
            if "onboard_polling_started_at" not in request.session:
                request.session["onboard_polling_started_at"] = timezone.now().isoformat()
                request.session.modified = True

        return render(request, "onboard/steps/06_launch.html", {
            "step": "launch",
            "wc": wc,
            "events_count": events_count,
        })

    @action(detail=False, methods=["GET"], url_path="launch/status")
    def launch_status(self, request):
        """
        GET `/onboard/launch/status/` -> partial HTMX d'etat (polled 2s).

        Lit le brouillon en session, le re-charge depuis le schema `meta`
        (refresh_from_db) pour avoir les derniers champs ecrits par la
        task Celery `create_tenant_from_draft`, puis selectionne un des
        trois partiels selon l'etat :

          - `wc.error_message` non vide -> `status_error.html` (polling
            s'arrete, bouton "Réessayer" propose).
          - `wc.tenant_id` non null -> `status_done.html` (polling
            s'arrete, lien vers l'admin du nouveau tenant).
          - Sinon -> `status_progress.html` (polling continue).

        Pre-requis : brouillon en session. Sans WC en session, on renvoie
        404 (la page parente fera reapparaitre le wizard a l'identity).

        / GET `/onboard/launch/status/` -> HTMX status partial (polled 2s).

        Reads the session draft, refreshes from the `meta` schema (to see
        the latest fields written by the Celery task
        `create_tenant_from_draft`), then picks one of three partials:

          - non-empty `wc.error_message` -> `status_error.html` (polling
            stops, retry button shown).
          - non-null `wc.tenant_id` -> `status_done.html` (polling stops,
            admin link shown).
          - Otherwise -> `status_progress.html` (polling continues).

        Prerequisite: draft in session. Without WC, returns 404.
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            # Pas de brouillon : 404 (HTMX recevra une erreur, la page
            # parente affichera son etat initial).
            # / No draft: 404 (HTMX will show an error; parent page falls
            # back to its initial state).
            return HttpResponse(status=404)

        # Refresh from DB : la task Celery a pu ecrire `tenant`,
        # `error_message`, etc. depuis le dernier render. On force le
        # schema `meta` (WaitingConfiguration y vit).
        # / Refresh from DB: the Celery task may have written `tenant` or
        # `error_message` since the last render. Force `meta` schema
        # (WaitingConfiguration lives there).
        with schema_context("meta"):
            wc.refresh_from_db()

        # === Cas 1 : erreur ===
        # Priorite sur `tenant_id` car la task peut, dans de rares cas,
        # ecrire les deux (erreur post-creation). On preferera afficher
        # l'erreur pour que l'utilisateur en soit informe.
        # / Case 1: error. Priority over `tenant_id` since the task may
        # rarely write both (post-creation error). Show the error so the
        # user knows.
        if wc.error_message:
            return render(request, "onboard/partials/status_error.html", {
                "wc": wc,
            })

        # === Cas 2 : tenant cree ===
        if wc.tenant_id is not None:
            # `get_primary_domain()` peut renvoyer None si aucun Domain
            # primaire n'est positionne — on tombe alors sur une string
            # vide pour eviter un AttributeError.
            # / `get_primary_domain()` may return None if no primary
            # Domain is set — fall back to empty string to avoid an
            # AttributeError.
            primary = wc.tenant.get_primary_domain()
            domain = primary.domain if primary else ""
            admin_url = f"https://{domain}/admin/" if domain else "/admin/"
            return render(request, "onboard/partials/status_done.html", {
                "wc": wc,
                "domain": domain,
                "admin_url": admin_url,
            })

        # === Cas 3 : timeout polling (5 min) ===
        # Mod 5 (feedback mainteneur 2026-05-15) : le polling ne doit JAMAIS
        # tourner indefiniment. On limite a 5 minutes a partir du premier
        # chargement de `/onboard/launch/`. Au-dela, on affiche un partial
        # "timeout" avec un bouton "Réessayer" (qui re-enqueue + reset le
        # timer via launch_retry). Cela evite qu'un onglet oublie n'envoie
        # des requetes pendant des heures.
        # / Mod 5 (maintainer feedback): polling must NEVER run forever.
        # Cap at 5 minutes from the first load of `/onboard/launch/`.
        # Past that, show a "timeout" partial with a retry button.
        from datetime import timedelta
        from django.utils import timezone
        from datetime import datetime as _datetime
        started_iso = request.session.get("onboard_polling_started_at")
        if started_iso:
            try:
                started_at = _datetime.fromisoformat(started_iso)
            except (TypeError, ValueError):
                # Session corrompue : on reset.
                # / Session corrupted: reset.
                started_at = timezone.now()
                request.session["onboard_polling_started_at"] = started_at.isoformat()
                request.session.modified = True
            if timezone.now() - started_at > timedelta(minutes=5):
                return render(
                    request, "onboard/partials/status_timeout.html", {"wc": wc},
                )

        # === Cas 4 : creation en cours (polling continue) ===
        return render(request, "onboard/partials/status_progress.html")

    @action(detail=False, methods=["POST"], url_path="launch/retry")
    def launch_retry(self, request):
        """
        POST `/onboard/launch/retry/` -> reset l'erreur + re-enqueue.

        Comportement :
          1. Reset `wc.error_message=""` dans le schema `meta`.
          2. Re-enqueue `create_tenant_from_draft.delay(wc_uuid=str(uuid))`.
          3. Retourne le partial `status_progress.html` pour relancer le
             polling cote HTMX.

        Si pas de WC en session : 404.

        / POST `/onboard/launch/retry/` -> reset error + re-enqueue.

        Behavior:
          1. Reset `wc.error_message=""` in the `meta` schema.
          2. Re-enqueue `create_tenant_from_draft.delay(...)`.
          3. Return the `status_progress.html` partial to restart HTMX
             polling.

        Without WC in session: 404.
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            return HttpResponse(status=404)

        # Import local : evite de charger les tasks Celery au top du
        # module (qui tirent BaseBillet.models, donc plus de monde).
        # / Local import: avoid loading Celery tasks at module top
        # (they pull BaseBillet.models, hence more code).
        from django.utils import timezone

        from onboard.tasks import create_tenant_from_draft

        # Reset atomique via `.update()` (pas de re-fetch necessaire).
        # / Atomic reset via `.update()` (no re-fetch needed).
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                error_message="",
            )

        # Mod 5 : reset le timer de polling pour qu'on n'expire pas
        # immediatement apres un retry (sinon le user verrait
        # status_timeout des le clic).
        # / Mod 5: reset polling timer so a retry doesn't immediately
        # show status_timeout.
        request.session["onboard_polling_started_at"] = timezone.now().isoformat()
        request.session.modified = True

        create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))
        return render(request, "onboard/partials/status_progress.html")

    # ------------------------------------------------------------------
    # Magic link de reprise du wizard (Task 15).
    # / Wizard resume magic link (Task 15).
    # ------------------------------------------------------------------

    @action(
        detail=False, methods=["GET"],
        url_path=r"resume/(?P<signed>[^/]+)",
    )
    def resume(self, request, signed=None):
        """
        GET `/onboard/resume/<signed>/` -> magic link de reprise du wizard.

        `<signed>` est une chaine produite par `TimestampSigner().sign(uuid)`
        (cf. Task 6 / mail "OTP" + Task 19 final). Si la signature est
        valide ET datant de moins de 7 jours, on remet l'UUID en session
        et on redirige vers la step courante du brouillon.

        Si la signature est invalide ou expiree, on rend
        `resume_invalid.html` avec un statut 400 (lien casse).

        / GET `/onboard/resume/<signed>/` -> wizard resume magic link.

        `<signed>` is a string produced by `TimestampSigner().sign(uuid)`.
        If the signature is valid AND less than 7 days old, we re-set the
        UUID in session and redirect to the draft's current step.

        If invalid or expired, render `resume_invalid.html` with status
        400 (broken link).
        """
        # Import local : `signing` n'est pas utilise ailleurs dans ce
        # module. / Local import: `signing` isn't used elsewhere here.
        from django.core import signing

        signer = signing.TimestampSigner()
        try:
            # max_age en secondes : 7 jours = 7 * 24 * 3600.
            # / max_age in seconds: 7 days = 7 * 24 * 3600.
            wc_uuid_str = signer.unsign(signed, max_age=7 * 24 * 3600)
        except (signing.BadSignature, signing.SignatureExpired):
            # Signature cassee ou trop vieille : on rend le partial
            # d'erreur dedie avec status 400.
            # / Broken or too-old signature: render the dedicated error
            # partial with status 400.
            return render(
                request, "onboard/partials/resume_invalid.html",
                status=400,
            )

        # Verifie que le brouillon existe encore (purge cron peut l'avoir
        # supprime). / Check the draft still exists (cron purge may have
        # removed it).
        with schema_context("meta"):
            try:
                wc = WaitingConfiguration.objects.get(uuid=wc_uuid_str)
            except WaitingConfiguration.DoesNotExist:
                return render(
                    request, "onboard/partials/resume_invalid.html",
                    status=400,
                )

            # Revocation du magic link : si le brouillon est deja finalise
            # (tenant cree), on N'expose PAS le wizard en mode "reprise".
            # L'utilisateur va plutot vers le status / l'admin du tenant.
            # Cela evite qu'un ancien email "tu as un brouillon en cours"
            # ne reactive un draft deja finalise (apparence trompeuse).
            # / Magic link revocation: if the draft is already finalised
            # (tenant created), do NOT expose the wizard in "resume" mode.
            # Sends the user to the launch/status page instead. Prevents
            # stale "you have a draft in progress" emails from reactivating
            # an already-finalised draft (misleading UX).
            if wc.tenant_id is not None:
                _set_session_wc(request, wc)
                return redirect("onboard-launch")

        # Remet l'UUID en session et redirige vers la step courante.
        # / Re-set UUID in session and redirect to current step.
        _set_session_wc(request, wc)
        return _redirect_to_current_step(request, wc)

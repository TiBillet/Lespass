"""
Vues reservees aux tests E2E Playwright. Chargees uniquement si settings.DEBUG=True.
/ Views reserved for Playwright E2E tests. Loaded only if settings.DEBUG=True.

LOCALISATION : AuthBillet/views_test_only.py

Ce fichier contient des endpoints de test qui contournent le flow UI normal
pour accelerer les fixtures Playwright. Ils sont triple-gates pour empecher
toute exposition en production :

1. settings.DEBUG doit valoir True
2. La variable d'environnement E2E_TEST_TOKEN doit etre definie
3. Le header X-Test-Token de la requete doit matcher cette variable
   (comparaison en temps constant pour eviter les attaques temporelles)

Si une condition manque, l'endpoint repond 404 sans fuiter d'information.

/ This file contains test endpoints that bypass the normal UI flow to speed up
Playwright fixtures. They are triple-gated to prevent any prod exposure:

1. settings.DEBUG must be True
2. The E2E_TEST_TOKEN env var must be set
3. The X-Test-Token request header must match that var (constant-time compare
   to prevent timing attacks)

If any condition is missing, the endpoint returns 404 without leaking info.

BRANCHEMENT : voir AuthBillet/urls.py, section `if settings.DEBUG:`.
/ WIRING: see AuthBillet/urls.py, `if settings.DEBUG:` section.
"""

import hmac
import os

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


# --- Garde-fous communs / Shared gates ---


def _silent_404():
    """
    Renvoie une 404 minimale pour eviter de fuiter l'existence de l'endpoint.
    / Returns a minimal 404 to avoid leaking endpoint existence.
    """
    return JsonResponse({"detail": "Not Found"}, status=404)


def _request_is_authorized(request):
    """
    Verifie les 3 garde-fous (DEBUG, token env, header match).
    / Check the 3 gates (DEBUG, env token, header match).

    Retourne True si et seulement si les 3 conditions sont vraies.
    / Returns True if and only if all 3 conditions hold.
    """
    # Garde-fou 1 : DEBUG obligatoire / Gate 1: DEBUG required
    debug_is_on = settings.DEBUG
    if not debug_is_on:
        return False

    # Garde-fou 2 : le token doit etre configure cote serveur
    # / Gate 2: token must be configured on server side
    expected_token = os.environ.get("E2E_TEST_TOKEN", "")
    if not expected_token:
        return False

    # Garde-fou 3 : comparaison constant-time du header contre la valeur d'env
    # hmac.compare_digest protege contre les attaques temporelles
    # / Gate 3: constant-time compare of header vs env value
    # hmac.compare_digest protects against timing attacks
    provided_token = request.headers.get("X-Test-Token", "")
    tokens_match = hmac.compare_digest(provided_token, expected_token)
    if not tokens_match:
        return False

    return True


# --- Endpoint : force_login / Endpoint: force_login ---


@csrf_exempt
@require_http_methods(["POST"])
def force_login_for_e2e(request):
    """
    Cree une session authentifiee pour un utilisateur donne, sans passer par le
    flow UI (pas de click, pas de navigation, pas de lien TEST MODE).
    / Create an authenticated session for a given user, without the UI flow
    (no click, no navigation, no TEST MODE link).

    LOCALISATION : AuthBillet/views_test_only.py

    FLUX :
    1. Verifie les 3 garde-fous (DEBUG + token env + header)
    2. Recoit `email` dans le body POST
    3. Cherche l'utilisateur dans le tenant courant (schema actif)
    4. Appelle django.contrib.auth.login() qui cree la session et pose le cookie
    5. Renvoie le session_key et le nom du cookie pour injection cote Playwright

    / FLOW:
    1. Check the 3 gates (DEBUG + env token + header)
    2. Receive `email` in POST body
    3. Find the user in the current tenant (active schema)
    4. Call django.contrib.auth.login() to create session and set cookie
    5. Return session_key and cookie name for Playwright-side injection

    DEPENDANCES / DEPENDENCIES :
    - settings.DEBUG (TiBillet/settings.py)
    - os.environ["E2E_TEST_TOKEN"] (.env)
    - get_user_model() → AuthBillet.TibilletUser

    USAGE E2E / E2E USAGE :
        POST /api/user/__test_only__/force_login/
        Headers: X-Test-Token: <token>
        Body:    email=<user_email>

        Reponse JSON :
        {
            "sessionid": "<session_key>",
            "session_cookie_name": "sessionid",
            "user_email": "<email>"
        }

    :param request: HttpRequest avec header X-Test-Token et POST email
    :return: JsonResponse avec session_key, ou 404/400 selon echec
    """
    # Etape 1 : garde-fous / Step 1: gates
    if not _request_is_authorized(request):
        return _silent_404()

    # Etape 2 : recupere l'email depuis le POST / Step 2: get email from POST
    email_utilisateur = request.POST.get("email", "").strip()
    if not email_utilisateur:
        return JsonResponse({"detail": "email required"}, status=400)

    # Etape 3 : cherche le user dans le tenant courant
    # La vue est montee dans urls_tenants.py donc connection.tenant est actif
    # / Step 3: find the user in the current tenant
    # View is mounted in urls_tenants.py so connection.tenant is active
    user_model = get_user_model()
    try:
        user_a_connecter = user_model.objects.get(email__iexact=email_utilisateur)
    except user_model.DoesNotExist:
        return JsonResponse({"detail": "user not found"}, status=404)

    # Etape 4 : force le login
    # login() cree une session, la sauvegarde, et pose le cookie sur la reponse
    # / Step 4: force login
    # login() creates a session, saves it, and sets the cookie on the response
    login(request, user_a_connecter)

    # Etape 5 : retourne le session_key pour injection Playwright
    # request.session.session_key est dispo apres login() (appel implicite a save())
    # / Step 5: return session_key for Playwright injection
    # request.session.session_key is available after login() (implicit save())
    session_key = request.session.session_key

    return JsonResponse({
        "sessionid": session_key,
        "session_cookie_name": settings.SESSION_COOKIE_NAME,
        "user_email": user_a_connecter.email,
    })

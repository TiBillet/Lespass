"""
Garde central des sessions terminal.
/ Central guard for terminal sessions.

LOCALISATION : AuthBillet/middleware.py

Un terminal materiel (borne kiosk, caisse LaBoutik, tireuse) est authentifie via
le bridge (/laboutik/auth/bridge/ fait un login Django complet) : il obtient une
session normale et pourrait donc atteindre toutes les vues « humaines » protegees
par IsAuthenticated (mon compte, agenda, transfert de session cross-tenant, etc.).

Ce middleware restreint les sessions terminal (espece = TE) aux seules URLs de
leur interface, et renvoie tout autre chemin vers l'interface du terminal.
Les humains (espece = HU) et les requetes anonymes ne sont JAMAIS touches
(court-circuit immediat).

/ A hardware terminal is authenticated via the bridge (full Django login) and
gets a normal session, so it could reach every human view guarded only by
IsAuthenticated. This middleware restricts terminal sessions (espece = TE) to
their own interface URLs and redirects any other path to the terminal's home.
Humans and anonymous requests are never affected.

POSITION : doit etre APRES AuthenticationMiddleware (lit request.user) ET APRES
HtmxMiddleware (lit request.htmx). / Must run AFTER AuthenticationMiddleware and
HtmxMiddleware.
"""
from django.shortcuts import redirect
from django_htmx.http import HttpResponseClientRedirect

from AuthBillet.models import TibilletUser


# Prefixes d'URL autorises pour une session terminal (espece = TE).
# Un terminal ne doit voir que son interface + les assets. La garde specifique de
# chaque interface (IsKioskTerminal, HasLaBoutikTerminalAccess...) fait le tri fin
# du role : un terminal KI qui tenterait /laboutik/ passe ici mais sera refuse par
# la garde de la caisse. Pas de fuite.
# / URL prefixes allowed for a terminal session. Fine-grained role filtering is
# still done by each interface's own permission.
PREFIXES_AUTORISES_TERMINAL = (
    "/kiosk/",
    "/laboutik/",
    "/controlvanne/",
    "/static/",
    "/media/",
    "/admin/logout",
)

# Interface d'accueil par role de terminal (cible de la redirection).
# / Home interface per terminal role (redirect target).
ACCUEIL_PAR_ROLE = {
    TibilletUser.ROLE_KIOSQUE: "/kiosk/",
    TibilletUser.ROLE_LABOUTIK: "/laboutik/caisse/",
    TibilletUser.ROLE_TIREUSE: "/controlvanne/kiosk/",
}


class TerminalSessionGuardMiddleware:
    """Restreint les sessions terminal a leur interface. / Restrict terminal sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        # On ne restreint que les terminaux authentifies. Tout le reste (humains,
        # anonymes) passe sans surcout. / Only authenticated terminals are guarded.
        est_un_terminal = (
            user is not None
            and user.is_authenticated
            and getattr(user, "espece", None) == TibilletUser.TYPE_TERM
        )
        if est_un_terminal:
            chemin = request.path
            if not chemin.startswith(PREFIXES_AUTORISES_TERMINAL):
                # Renvoie le terminal vers son interface, selon son role.
                # / Send the terminal back to its own interface, per role.
                accueil = ACCUEIL_PAR_ROLE.get(
                    getattr(user, "terminal_role", None), "/kiosk/"
                )
                # Garde anti-boucle : ne pas rediriger vers le chemin courant.
                # / Anti-loop guard: never redirect to the current path.
                if chemin != accueil:
                    if getattr(request, "htmx", False):
                        return HttpResponseClientRedirect(accueil)
                    return redirect(accueil)

        return self.get_response(request)

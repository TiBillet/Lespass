"""
Middleware de protection du cache HTTP pour les réponses bi-formes HTMX.
/ HTTP cache protection middleware for the HTMX dual-body responses.

LOCALISATION : BaseBillet/middleware.py

Contexte : la quasi-totalité des vues publiques rendent DEUX corps différents
sur la MÊME URL selon le header HX-Request (page complète via shell.html, ou
fragment via headless.html — cf. get_context). Sans les en-têtes posés ici,
tout cache HTTP (navigateur, proxy, CDN) indexe uniquement par URL et peut
servir un fragment nu à une navigation normale (page sans CSS) ou une page
complète à un swap HTMX.
/ Context: most public views render TWO different bodies on the SAME URL
depending on the HX-Request header (full page via shell.html, or fragment via
headless.html). Without the headers set here, any HTTP cache indexes by URL
only and can serve a bare fragment to a normal navigation (unstyled page) or
a full page to an HTMX swap.

Deux mesures, volontairement globales (un oubli par-vue serait invisible en
dev, où rien n'est mis en cache, et ne casserait qu'en production) :
/ Two measures, deliberately global (a per-view omission would be invisible in
dev, where nothing is cached, and would only break in production):

1. `Vary: HX-Request` sur toutes les réponses : demande aux caches d'indexer
   par URL + valeur du header HX-Request → les deux variantes sont stockées
   séparément et chacun reçoit la bonne.
   / Asks caches to index by URL + HX-Request header value.

2. `Cache-Control` explicite sur le HTML dynamique (si la vue n'en a pas déjà
   posé un) : `private, no-store` pour un utilisateur connecté (jamais stocké,
   nulle part), `no-cache` sinon (stockable mais revalidation obligatoire
   avant chaque réutilisation — comportement identique à aujourd'hui, mais
   déclaré contractuellement).
   / Explicit Cache-Control on dynamic HTML (when the view did not set one):
   `private, no-store` for authenticated users, `no-cache` otherwise.
"""
from django.utils.cache import patch_vary_headers


class ProtectionCacheHtmxMiddleware:
    """
    Pose Vary: HX-Request partout + un Cache-Control par défaut sur le HTML.
    / Sets Vary: HX-Request everywhere + a default Cache-Control on HTML.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # patch_vary_headers AJOUTE HX-Request à la liste Vary existante
        # (Cookie, Accept-Language…), il n'écrase rien.
        # / patch_vary_headers APPENDS HX-Request to the existing Vary list.
        patch_vary_headers(response, ("HX-Request",))

        # Cache-Control par défaut, uniquement sur le HTML et uniquement si la
        # vue n'a pas déjà exprimé sa propre politique.
        # / Default Cache-Control, HTML only, and only when the view did not
        # already express its own policy.
        type_de_contenu = response.get("Content-Type", "")
        if type_de_contenu.startswith("text/html") and not response.has_header("Cache-Control"):
            utilisateur = getattr(request, "user", None)
            if utilisateur is not None and utilisateur.is_authenticated:
                # Contenu personnel (tirelire, billets…) : jamais stocké,
                # ni par un CDN ni sur le disque d'un poste partagé.
                # / Personal content: never stored, not by a CDN nor on a
                # shared computer's disk.
                response["Cache-Control"] = "private, no-store"
            else:
                # Public : stockable, mais revalidation obligatoire avant
                # chaque réutilisation. / Public: storable, but must be
                # revalidated before each reuse.
                response["Cache-Control"] = "no-cache"

        return response

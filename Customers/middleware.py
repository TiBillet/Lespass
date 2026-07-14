"""
Middleware de domaine canonique pour le multi-tenant.
/ Canonical domain middleware for the multi-tenant setup.

LOCALISATION : Customers/middleware.py

Ce middleware assure la CANONICALISATION DE DOMAINE.

Chaque tenant peut avoir plusieurs domaines (ex : le ROOT TiBillet répond sur
tibillet.coop, tibillet.re, tibillet.org). Un seul est marqué principal
(`is_primary=True`). Toute requête GET/HEAD arrivant sur un domaine secondaire
est redirigée vers le domaine principal, en conservant chemin et query string
(cas « tibillet.org → tibillet.coop »).
/ Domain canonicalization: redirect GET/HEAD requests landing on a secondary
domain to the tenant's primary domain, keeping path and query string.

NOTE : le rattrapage des anciens liens de doc Docusaurus v2 (redirection vers
documentation_v3) a été retiré — ces chemins renvoient désormais un 404 normal.
/ NOTE: the legacy Docusaurus v2 docs redirect was removed — those paths now 404.

PLACEMENT : juste APRÈS `TenantMainMiddleware` dans settings.MIDDLEWARE, pour que
`connection.tenant` soit déjà résolu.
/ Placement: right AFTER TenantMainMiddleware so `connection.tenant` is set.

PRÉREQUIS : les domaines secondaires doivent être enregistrés comme `Domain` du
tenant (sinon TenantMainMiddleware renvoie 404 avant d'arriver ici).
/ PREREQUISITE: secondary domains must be registered as `Domain` rows.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect


class CanonicalDomainRedirectMiddleware:
    """
    Redirige les requêtes GET/HEAD vers le domaine principal du tenant courant.
    / Redirects GET/HEAD requests to the current tenant's primary domain.
    """

    # Durée de cache du domaine principal par tenant (il change très rarement).
    # / Cache duration for a tenant's primary domain (rarely changes).
    DUREE_CACHE_SECONDES = 3600

    # 302 (temporaire) pendant la phase de transition multi-domaine.
    # Les <link rel="canonical"> des pages SEO gèrent déjà la déduplication pour
    # Google, donc le coût SEO d'un 302 temporaire est faible. Passer à True
    # (301 permanent) UNE FOIS la config des domaines figée et validée : meilleure
    # consolidation du référencement, mais mise en cache DURABLE par les navigateurs
    # (difficile à corriger si un domaine principal est mal configuré).
    # / 302 (temporary) during the multi-domain transition. SEO canonical tags
    # already dedupe for Google, so a temporary 302 costs little. Switch to True
    # (permanent 301) ONCE the domain config is frozen and validated.
    REDIRECTION_PERMANENTE = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Canonicalisation de domaine (ex : tibillet.org → tibillet.coop).
        # / Domain canonicalization (e.g. tibillet.org → tibillet.coop).
        redirection = self._redirection_canonique(request)
        if redirection is not None:
            return redirection
        return self.get_response(request)

    def _redirection_canonique(self, request):
        # En contexte de test, on ne redirige jamais : APIClient utilise l'hôte
        # « testserver » qui n'est pas le domaine principal et déclencherait des
        # 301 intempestifs cassant les tests.
        # / In tests, never redirect: APIClient uses the "testserver" host which
        # would trigger spurious 301s and break the test suite.
        if getattr(settings, "TEST", False):
            return None

        # On ne redirige que les méthodes sûres (GET/HEAD).
        # Surtout JAMAIS de POST : cela casserait les webhooks Stripe et l'envoi
        # de formulaires (le corps de la requête serait perdu).
        # / Only redirect safe methods. NEVER POST: it would break Stripe
        # webhooks and form submissions (the request body would be lost).
        if request.method not in ("GET", "HEAD"):
            return None

        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            return None

        # Hôte demandé, sans le port (utile en développement).
        # / Requested host, without the port (useful in development).
        hote = request.get_host().split(":")[0]

        # En développement local et en test, on ne redirige pas.
        # / Do not redirect in local development or tests.
        if hote == "localhost" or hote == "testserver" or hote.endswith(".localhost"):
            return None

        # On ne redirige pas les endpoints API : un 301 cross-domaine pourrait
        # faire perdre les en-têtes (Authorization, CORS) à certains clients.
        # Les intégrations API utilisent le domaine de leur choix.
        # / Do not redirect API endpoints: a cross-domain 301 may drop headers
        # (Authorization, CORS) for some clients. API clients pick their domain.
        if request.path.startswith("/api/"):
            return None

        domaine_principal = self._domaine_principal(tenant)

        # Rien à faire si pas de domaine principal connu ou si on y est déjà.
        # / Nothing to do if no known primary domain or already on it.
        if not domaine_principal or hote == domaine_principal:
            return None

        # Reconstruit l'URL sur le domaine principal (chemin + query conservés).
        # request.scheme est fiable ici grâce à SECURE_PROXY_SSL_HEADER (Traefik).
        # / Rebuild the URL on the primary domain (path + query preserved).
        url_cible = f"{request.scheme}://{domaine_principal}{request.get_full_path()}"
        classe_reponse = (
            HttpResponsePermanentRedirect if self.REDIRECTION_PERMANENTE else HttpResponseRedirect
        )
        return classe_reponse(url_cible)

    def _domaine_principal(self, tenant):
        """
        Retourne le domaine principal du tenant (chaîne) ou None.
        Met le résultat en cache pour éviter une requête DB à chaque requête HTTP.
        / Returns the tenant's primary domain (string) or None, cached to avoid
        a DB query on every HTTP request.
        """
        schema = getattr(tenant, "schema_name", None)
        if not schema:
            return None

        cle_cache = f"canonical_primary_domain:{schema}"

        # Lecture du cache PROTÉGÉE : si le backend (Memcached) est indisponible,
        # on ne doit JAMAIS faire planter le front. On retombe sur la DB.
        # Sans ça, une panne Memcached provoquerait des 500 sur toutes les pages GET.
        # / Guarded cache read: if the backend (Memcached) is down, never crash the
        # front. Fall back to the DB. Otherwise a Memcached outage would 500 every GET.
        try:
            domaine = cache.get(cle_cache)
        except Exception:
            domaine = None

        if domaine is None:
            # get_primary_domain() peut renvoyer None (aucun primaire) ou lever
            # une exception si la config est incohérente : on protège l'accès.
            # / get_primary_domain() may return None or raise on bad config.
            try:
                primaire = tenant.get_primary_domain()
            except Exception:
                primaire = None
            # On met en cache une chaîne (jamais None) pour distinguer
            # « pas encore calculé » de « calculé mais vide ».
            # / Cache a string (never None) to tell "not computed" from "empty".
            domaine = primaire.domain if primaire else ""
            # Écriture du cache protégée de la même manière (panne backend tolérée).
            # / Guarded cache write, same reasoning (backend outage tolerated).
            try:
                cache.set(cle_cache, domaine, self.DUREE_CACHE_SECONDES)
            except Exception:
                pass

        return domaine or None

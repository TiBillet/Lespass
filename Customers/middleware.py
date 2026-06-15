"""
Middleware de domaine canonique pour le multi-tenant.
/ Canonical domain middleware for the multi-tenant setup.

LOCALISATION : Customers/middleware.py

Ce middleware fait DEUX choses, dans cet ordre :

1. RATTRAPAGE DES ANCIENS LIENS DE DOC (Docusaurus v2).
   L'ancienne documentation (Docusaurus) était servie sur tibillet.org avec des
   chemins comme /docs/..., /fr/..., /en/..., /roadmap/, /search/, /cgucgv/.
   Ces chemins n'existent plus dans Lespass : on les redirige vers la nouvelle
   doc (documentation_v3 sur tibillet.github.io). Uniquement sur le tenant ROOT
   (schema public), car c'est là qu'atterrissent les liens tibillet.org/.coop.
   / Catch old Docusaurus v2 links (/docs, /fr, /en, /roadmap, /search, /cgucgv)
   and redirect them to documentation_v3. ROOT tenant (public schema) only.

2. DOMAINE CANONIQUE.
   Chaque tenant peut avoir plusieurs domaines (ex : le ROOT TiBillet répond sur
   tibillet.coop, tibillet.re, tibillet.org). Un seul est marqué principal
   (`is_primary=True`). Toute requête GET/HEAD arrivant sur un domaine secondaire
   est redirigée vers le domaine principal, en conservant chemin et query string
   (cas « tibillet.org → tibillet.coop »).
   / Redirect GET/HEAD requests landing on a secondary domain to the tenant's
   primary domain, keeping path and query string.

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


# Racine de la nouvelle documentation (documentation_v3 sur GitHub Pages).
# / Root of the new documentation (documentation_v3 on GitHub Pages).
URL_DOC_V3 = "https://tibillet.github.io/documentation_v3/"

# Page de démonstration des modules dans la doc v3.
# URLs vérifiées (HTTP 200) le 2026-06-02 sur tibillet.github.io.
# / Module demonstration page in the v3 docs. URLs checked (HTTP 200) on 2026-06-02.
URL_DOC_V3_DEMO = (
    "https://tibillet.github.io/documentation_v3/"
    "les-bases-et-valeurs-tibillet/demonstration-des-differents-modules/"
)

# Page CGU / CGV dans la doc v3.
# / Terms and conditions (CGU/CGV) page in the v3 docs.
URL_DOC_V3_CGU = (
    "https://tibillet.github.io/documentation_v3/"
    "les-bases-et-valeurs-tibillet/aspects-legaux-et-reglementaires/cgu-cgv/"
)

# Anciens chemins Docusaurus v2 qui ont un équivalent PRÉCIS dans la doc v3.
# Les clés sont normalisées : sans slash final, en minuscules.
# / Old Docusaurus v2 paths with a PRECISE v3 equivalent. Keys are normalized:
# no trailing slash, lowercase.
REDIRECTIONS_DOC_EXACTES = {
    "/docs/presentation/demonstration": URL_DOC_V3_DEMO,
    "/fr/docs/presentation/demonstration": URL_DOC_V3_DEMO,
    "/cgucgv": URL_DOC_V3_CGU,
    "/fr/cgucgv": URL_DOC_V3_CGU,
}

# Préfixes hérités du Docusaurus v2 sans équivalent précis : tout ce qui commence
# par l'un d'eux retombe sur la racine de la doc v3. Ces préfixes n'existent PAS
# comme routes Lespass (pas d'i18n_patterns, donc /fr et /en sont libres).
# / Legacy Docusaurus v2 prefixes with no precise mapping: anything starting with
# one of these falls back to the v3 docs homepage. None of these are Lespass
# routes (no i18n_patterns, so /fr and /en are free).
PREFIXES_DOC_HERITES = ("/docs", "/fr", "/en", "/roadmap", "/search")


def url_doc_v3_pour_chemin_herite(chemin_demande):
    """
    Retourne l'URL de la doc v3 correspondant à un ancien chemin Docusaurus v2,
    ou None si le chemin n'est pas un ancien chemin de doc.
    / Return the v3 docs URL matching an old Docusaurus v2 path, or None.

    LOCALISATION : Customers/middleware.py

    Logique :
    1. On normalise le chemin (sans slash final, en minuscules).
    2. Si c'est un chemin connu avec équivalent précis (démo, CGU) → URL précise.
    3. Sinon, si le chemin commence par un préfixe hérité → racine de la doc v3.
    4. Sinon → None (ce n'est pas un ancien lien de doc, on ne touche à rien).
    / 1. Normalize. 2. Exact match (demo, CGU). 3. Legacy prefix → v3 homepage.
    4. Otherwise None.

    Fonction PURE (ne lit ni request ni connection) : facile à tester unitairement.
    / PURE function (reads neither request nor connection): easy to unit-test.
    """
    # On enlève le slash final et on passe en minuscules pour comparer.
    # / Strip trailing slash and lowercase for comparison.
    chemin = chemin_demande.rstrip("/").lower()

    # La racine "" est la home Lespass, jamais la doc.
    # / The "" root is the Lespass home, never the docs.
    if chemin == "":
        return None

    # Correspondance précise (page de démonstration, CGU/CGV).
    # / Precise match (demonstration page, CGU/CGV).
    if chemin in REDIRECTIONS_DOC_EXACTES:
        return REDIRECTIONS_DOC_EXACTES[chemin]

    # Préfixe hérité sans équivalent précis → racine de la doc v3.
    # On teste l'égalité exacte (ex : /fr) ET le préfixe suivi d'un slash
    # (ex : /fr/docs/...) pour ne pas attraper /french par erreur.
    # / Legacy prefix without precise mapping → v3 homepage. Match exact (/fr)
    # AND prefix followed by a slash (/fr/docs/...) to avoid catching /french.
    for prefixe in PREFIXES_DOC_HERITES:
        if chemin == prefixe or chemin.startswith(prefixe + "/"):
            return URL_DOC_V3

    # Ce n'est pas un ancien chemin de doc.
    # / Not an old docs path.
    return None


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
        # 1. Anciens liens de la doc Docusaurus v2 → doc v3.
        #    Prioritaire : on quitte carrément le domaine pour github.io, donc
        #    inutile de passer par la redirection canonique org→coop ensuite.
        # / 1. Old Docusaurus v2 links → v3 docs. Checked first: we leave the
        #    domain for github.io, so no point running the canonical redirect.
        redirection_doc = self._redirection_doc_heritee(request)
        if redirection_doc is not None:
            return redirection_doc

        # 2. Domaine canonique (ex : tibillet.org → tibillet.coop).
        # / 2. Canonical domain (e.g. tibillet.org → tibillet.coop).
        redirection = self._redirection_canonique(request)
        if redirection is not None:
            return redirection
        return self.get_response(request)

    def _redirection_doc_heritee(self, request):
        """
        Redirige les anciens chemins de la doc Docusaurus v2 vers la doc v3.
        Retourne une réponse de redirection (302) ou None.
        / Redirect old Docusaurus v2 docs paths to the v3 docs. Returns a 302
        response or None.

        Uniquement sur le tenant ROOT (schema public) : c'est là qu'arrivent les
        liens tibillet.org / tibillet.coop. Les sous-domaines des tenants ne sont
        donc jamais affectés (zéro risque de collision avec leurs routes).
        / ROOT tenant (public schema) only: that's where tibillet.org/.coop links
        land. Tenant subdomains are never affected (no route collision risk).
        """
        # En test, on ne redirige jamais (même raison que la redirection
        # canonique : l'hôte « testserver » fausserait tout).
        # / In tests, never redirect (same reason as the canonical redirect).
        if getattr(settings, "TEST", False):
            return None

        # Méthodes sûres seulement (GET/HEAD) — jamais de POST.
        # / Safe methods only (GET/HEAD) — never POST.
        if request.method not in ("GET", "HEAD"):
            return None

        # Uniquement sur le ROOT public.
        # / ROOT public schema only.
        tenant = getattr(connection, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", None) != "public":
            return None

        # La logique de correspondance est dans la fonction pure (testable).
        # / The matching logic lives in the pure function (testable).
        url_cible = url_doc_v3_pour_chemin_herite(request.path)
        if not url_cible:
            return None

        # 302 temporaire : la table de redirection n'est pas encore figée
        # (cohérent avec REDIRECTION_PERMANENTE de la redirection canonique).
        # / 302 temporary: the redirect table isn't frozen yet (consistent with
        # the canonical redirect's REDIRECTION_PERMANENTE).
        return HttpResponseRedirect(url_cible)

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

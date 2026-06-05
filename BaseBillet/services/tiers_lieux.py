"""
Client pour l'API publique du recensement national des Tiers-Lieux.
/ Client for the public national Tiers-Lieux directory API.

LOCALISATION : BaseBillet/services/tiers_lieux.py

Doc API : https://api.tiers-lieux.fr/

On l'utilise dans le wizard de proposition d'évènement (étape 1) : quand le
visiteur cherche un lieu et qu'aucune adresse locale ne correspond, on interroge
ce recensement pour lui proposer une fiche déjà connue au niveau national.
/ Used in the event proposal wizard (step 1): when no local address matches, we
query this national directory to suggest an already-known place.

RÈGLE IMPORTANTE : ce module ne lève JAMAIS d'exception vers l'appelant. Si l'API
externe est lente, en panne, ou répond mal, on renvoie une liste vide. Le wizard
ne doit jamais casser à cause d'un service tiers.
/ KEY RULE: this module NEVER raises to the caller. On any failure, return [].
The wizard must never break because of a third-party service.
"""

import hashlib
import logging

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Adresse de base de l'API publique. / Public API base URL.
TIERS_LIEUX_API_BASE = "https://api.tiers-lieux.fr"

# Délai maximum d'attente d'une réponse, en secondes. Court exprès : on préfère
# ne rien proposer plutôt que de faire patienter le visiteur.
# / Max wait for a response, in seconds. Deliberately short.
TIMEOUT_SECONDES = 4

# Durée de mise en cache d'une recherche, en secondes (1 heure). La donnée est
# nationale et publique : la même pour tous les tenants. La clé de cache n'est
# donc PAS préfixée par le tenant (exception assumée à la règle multi-tenant).
# / Search cache duration, in seconds (1 hour). National public data, identical
# for every tenant: the cache key is intentionally NOT tenant-scoped.
CACHE_TTL = 3600

# En-tête poli pour identifier l'appelant auprès de l'API.
# / Polite header to identify the caller to the API.
USER_AGENT = "TiBillet-Lespass (https://tibillet.coop)"


def _cle_de_cache(terme, limite):
    """
    Construit une clé de cache memcached valide à partir du terme de recherche.
    / Build a valid memcached cache key from the search term.

    Le terme vient de l'utilisateur : il peut contenir des espaces, des accents,
    des caractères interdits par memcached. On le passe donc dans un hash md5
    pour obtenir une clé courte et sûre.
    / The term is user input (spaces, accents, forbidden chars): we md5-hash it
    to get a short, safe key.
    """
    terme_normalise = (terme or "").strip().lower()
    empreinte = hashlib.md5(terme_normalise.encode("utf-8")).hexdigest()
    return f"tierslieux:search:{empreinte}:{limite}"


def _texte_ou_vide(valeur):
    """Renvoie une chaîne nettoyée, jamais None. / Return a clean string, never None."""
    if valeur is None:
        return ""
    return str(valeur).strip()


def _construire_rue(adresse_complete, code_postal, ville):
    """
    Déduit la rue à partir de l'adresse complète du recensement.
    / Derive the street from the directory's full address.

    L'API renvoie une `adresse_nationale` qui mélange rue + code postal + ville
    (ex : "Avenue de Bourbon 97434 Saint-Paul"). On retire le code postal et la
    ville pour ne garder que la rue. Si on n'y arrive pas, on renvoie l'adresse
    complète telle quelle : l'utilisateur validera/corrigera de toute façon.
    / The API returns `adresse_nationale` mixing street + zip + city. We strip
    the zip and city to keep only the street. On failure, return the full address
    (the user validates/edits anyway).
    """
    rue = _texte_ou_vide(adresse_complete)
    code_postal = _texte_ou_vide(code_postal)
    ville = _texte_ou_vide(ville)

    if code_postal:
        rue = rue.replace(code_postal, "")
    if ville:
        rue = rue.replace(ville, "")
    # On nettoie les espaces et virgules en trop laissés par les remplacements.
    # / Clean up leftover spaces/commas from the replacements.
    return rue.strip(" ,").strip()


def _normaliser_fiche(hit):
    """
    Transforme une fiche brute de l'API en un dict aux champs de notre PostalAddress.
    / Map a raw API record to a dict matching our PostalAddress fields.

    LOCALISATION : BaseBillet/services/tiers_lieux.py

    On ne garde que ce dont le wizard a besoin pour pré-remplir un nouveau lieu.
    / We keep only what the wizard needs to pre-fill a new place.
    """
    code_postal = _texte_ou_vide(hit.get("adresse_nationale_cp"))
    ville = _texte_ou_vide(hit.get("adresse_nationale_ville"))
    adresse_complete = _texte_ou_vide(hit.get("adresse_nationale"))

    return {
        "name": _texte_ou_vide(hit.get("nom_tiers_lieu")),
        "street_address": _construire_rue(adresse_complete, code_postal, ville),
        "postal_code": code_postal,
        "locality": ville,
        "region": _texte_ou_vide(hit.get("adresse_nationale_region")),
        "country": "France",
        "latitude": hit.get("adresse_nationale_lat"),
        "longitude": hit.get("adresse_nationale_lon"),
        "identifiant_national": _texte_ou_vide(hit.get("Identifiant_national")),
    }


def rechercher_tiers_lieux(terme, limite=5):
    """
    Cherche des tiers-lieux par nom / ville / code postal dans le recensement national.
    / Search tiers-lieux by name / city / zip in the national directory.

    LOCALISATION : BaseBillet/services/tiers_lieux.py

    Appelé par : EventWizard.search_tierslieux (BaseBillet/views.py).
    / Called by: EventWizard.search_tierslieux.

    FLUX / FLOW :
    1. Cherche d'abord en cache (mémoire partagée, 1h).
    2. Si absent : appelle GET {base}/search?q={terme}&limit={limite} (timeout 4s).
    3. Normalise chaque fiche vers nos champs PostalAddress.
    4. Met en cache et renvoie.
    En cas d'erreur (timeout, réseau, JSON invalide) : renvoie [] et journalise.

    :param terme: texte de recherche (nom, ville, code postal)
    :param limite: nombre maximum de fiches (défaut 5)
    :return: liste de dicts normalisés (vide si rien trouvé ou si erreur)
    """
    terme_propre = (terme or "").strip()
    if not terme_propre:
        return []

    cle = _cle_de_cache(terme_propre, limite)
    resultats_en_cache = cache.get(cle)
    if resultats_en_cache is not None:
        return resultats_en_cache

    try:
        reponse = requests.get(
            f"{TIERS_LIEUX_API_BASE}/search",
            params={"q": terme_propre, "limit": limite},
            timeout=TIMEOUT_SECONDES,
            headers={"User-Agent": USER_AGENT},
        )
        reponse.raise_for_status()
        donnees = reponse.json()
    except (requests.RequestException, ValueError) as erreur:
        # On ne propage jamais l'erreur : le wizard continue sans suggestion.
        # / Never propagate: the wizard keeps working without a suggestion.
        logger.warning("Recherche Tiers-Lieux échouée pour '%s' : %s", terme_propre, erreur)
        return []

    # L'API renvoie {"hits": [...]}. On normalise chaque fiche.
    # / The API returns {"hits": [...]}. Normalize each record.
    fiches_brutes = donnees.get("hits", []) if isinstance(donnees, dict) else []
    fiches_normalisees = [_normaliser_fiche(fiche) for fiche in fiches_brutes]

    cache.set(cle, fiches_normalisees, CACHE_TTL)
    return fiches_normalisees

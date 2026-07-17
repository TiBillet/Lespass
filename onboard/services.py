"""
Services synchrones de l'app onboard.
/ Synchronous helpers for the onboard app.

LOCALISATION: onboard/services.py

NOTE : on hash les OTP avec django.contrib.auth.hashers (PBKDF2-SHA256 par
defaut), pas avec bcrypt. Le plan initial mentionnait bcrypt, mais la lib
n'est pas installee sur cette branche. PBKDF2 + TTL 10min + compteur
`otp_attempts` offrent une securite equivalente pour un code 6 chiffres
court-vivant.
/ NOTE: we hash OTPs with Django's password hashers (PBKDF2-SHA256), not
bcrypt. bcrypt isn't installed on this branch. PBKDF2 + 10min TTL + attempt
counter is equivalent security for a short-lived 6-digit code.
"""

import hashlib
import logging
import os
import secrets
from datetime import timedelta

import requests

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils.translation import get_language
from django.utils import timezone


# Logger module-level pour tracer les erreurs reseau Nominatim.
# / Module-level logger to trace Nominatim network errors.
logger = logging.getLogger(__name__)


# === OTP ===
# Duree de vie d'un OTP : 10 minutes.
# / OTP time-to-live: 10 minutes.
OTP_TTL = timedelta(minutes=10)


def generate_otp():
    """
    Genere un code OTP a 6 chiffres et son hash PBKDF2.
    Renvoie (otp_clair, otp_hash, expires_at).
    Le clair doit etre envoye dans le mail ; seul le hash est stocke en DB.
    / Generate a 6-digit OTP + its PBKDF2 hash.
    Returns (otp_clair, otp_hash, expires_at).
    Plain code goes in the email; only the hash is persisted.
    """
    # secrets.randbelow donne un int uniforme dans [0, 1_000_000).
    # zfill 6 garantit l'affichage avec zeros en tete (ex: "000042").
    # / secrets.randbelow yields a uniform int in [0, 1_000_000).
    # zfill 6 pads with leading zeros (e.g. "000042").
    otp_clair = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = make_password(otp_clair)
    expires_at = timezone.now() + OTP_TTL
    return otp_clair, otp_hash, expires_at


def verify_otp(saisi, otp_hash):
    """
    Verifie un code OTP saisi contre le hash PBKDF2 stocke.
    Retour : True si match, False sinon (y compris si hash vide).
    / Verify a submitted OTP against the stored PBKDF2 hash.
    Returns True on match, False otherwise (including empty hash).
    """
    # Garde-fous : pas de hash ou pas de saisie -> echec immediat.
    # / Guard clauses: missing hash or input -> immediate failure.
    if not otp_hash:
        return False
    if not saisi:
        return False
    try:
        return check_password(saisi, otp_hash)
    except (ValueError, TypeError):
        # Format de hash invalide / Invalid hash format.
        return False


# === Geocode Nominatim ===
# Proxy serveur vers Nominatim (OpenStreetMap) avec cache Redis 24h.
# / Server-side proxy to Nominatim (OpenStreetMap) with 24h Redis cache.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "TiBillet-Onboard/1.0 (contact@tibillet.re)"
NOMINATIM_TIMEOUT = 5  # secondes / seconds
GEOCODE_CACHE_TTL = 24 * 60 * 60  # 24h en secondes / 24h in seconds


def _geocode_cache_key(query, lang):
    """
    Construit une cle de cache Redis courte et deterministe a partir d'une
    query + une langue (SHA256 tronque). On inclut la langue dans la cle
    parce que Nominatim renvoie des `display_name` differents selon la
    langue demandee (ex: "Brussels" en EN vs "Bruxelles" en FR).

    / Build a short deterministic Redis cache key from a query + language
    (truncated SHA256). Language is part of the key because Nominatim
    returns localized `display_name` values per language (e.g. "Brussels"
    EN vs "Bruxelles" FR).
    """
    # SHA256 pour rester court et eviter les caracteres exotiques.
    # / SHA256 for short key and no exotic chars.
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"onboard:geocode:{lang}:{h[:32]}"


def _get_user_language():
    """
    Retourne le code langue ISO 2 lettres a passer a Nominatim
    (`accept-language=...`). On lit la langue active de Django via
    `get_language()` (mise par `LocaleMiddleware`) et on tronque la
    region pour ne garder que la langue : "fr-fr" / "fr-FR" -> "fr".
    Defaut "fr" si aucune langue n'est detectee.

    / Returns the 2-letter ISO language code for Nominatim
    (`accept-language=...`). Reads Django's active language via
    `get_language()` (set by `LocaleMiddleware`) and strips the region:
    "fr-fr" / "fr-FR" -> "fr". Falls back to "fr" if none.
    """
    lang_complete = get_language() or "fr"
    return lang_complete.split("-")[0].lower()


def geocode(query):
    """
    Resout une adresse texte vers un dict {latitude, longitude, display_name}
    via Nominatim. Cache Redis 24h sur le hash de la query.
    Retourne None si query trop courte, pas de resultat, timeout, ou erreur
    reseau. Toutes les erreurs sont logguees en warning (pas d'exception
    propagee vers l'appelant).
    / Resolve a text address to a {latitude, longitude, display_name} dict
    via Nominatim. Redis-cached 24h via the query hash.
    Returns None on too-short query, no result, timeout, or network error.
    All errors are logged at warning level (no exception is propagated).
    """
    # Garde-fou : query vide ou trop courte -> on n'appelle pas Nominatim.
    # / Guard: empty or too-short query -> don't call Nominatim.
    if not query or len(query.strip()) < 3:
        return None

    # Langue active de l'utilisateur (mise par `LocaleMiddleware`). Sert
    # a localiser les `display_name` retournes par Nominatim (ex: noms de
    # villes etrangeres traduits) ET a separer le cache par langue.
    # / Active user language (set by `LocaleMiddleware`). Used both to
    # localize Nominatim `display_name` values (e.g. translated foreign
    # city names) AND to namespace the cache per language.
    user_language = _get_user_language()

    cache_key = _geocode_cache_key(query, user_language)
    cached = cache.get(cache_key)
    if cached is not None:
        # `cached` peut etre un dict OU le sentinel "no-result".
        # / `cached` may be a dict OR the "no-result" sentinel.
        return cached if cached != "no-result" else None

    # On tronque la query dans les logs pour eviter de stocker des PII
    # completes (adresses precises) en clair. La cle de cache, elle, reste
    # construite sur la query complete pour ne pas degrader le hit-rate.
    # / Truncate query in logs to avoid storing full PII (precise addresses)
    # in plain text. The cache key is built from the full query to preserve
    # hit-rate.
    truncated = query[:40] + ("..." if len(query) > 40 else "")

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                # `accept-language` : demande explicitement les noms de
                # lieux dans la langue de l'utilisateur. Sans ce param,
                # Nominatim renvoie souvent des noms en anglais ou en
                # langue d'origine non latinisee.
                # / `accept-language`: explicitly asks for place names in
                # the user's language. Without it, Nominatim often returns
                # English or untranslated original-script names.
                "accept-language": user_language,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        # Timeout, DNS, connexion refusee, etc. -> on log et on renvoie None.
        # / Timeout, DNS, connection refused, etc. -> log and return None.
        logger.warning("Nominatim error for query %r : %s", truncated, exc)
        return None

    if response.status_code != 200:
        logger.warning("Nominatim status %d for %r", response.status_code, truncated)
        return None

    results = response.json()
    if not results:
        # On cache aussi les "pas de resultat" pour ne pas re-frapper Nominatim
        # a chaque saisie d'une adresse inexistante.
        # / Cache no-result too so we don't hammer Nominatim on every
        # attempt with a non-existent address.
        cache.set(cache_key, "no-result", GEOCODE_CACHE_TTL)
        return None

    first = results[0]
    payload = {
        "latitude": float(first["lat"]),
        "longitude": float(first["lon"]),
        "display_name": first.get("display_name", ""),
    }
    cache.set(cache_key, payload, GEOCODE_CACHE_TTL)
    return payload


# Suffixes de domaine "preferes" : s'ils sont presents dans la liste derivee de
# l'environnement, on les remonte en tete (le 1er suffixe = choix par defaut du
# formulaire d'onboarding). L'ordre ici est l'ordre de priorite : tibillet.coop
# passe avant tibillet.localhost. Feedback mainteneur 2026-07-17 : tibillet.coop
# doit rester le choix par defaut meme s'il est declare dans ADDITIONAL_DOMAINS
# (et non dans DOMAIN).
# / "Preferred" domain suffixes: if present in the env-derived list, they are
# moved to the front (1st suffix = default choice in the onboarding form).
SUFFIXES_DNS_PREFERES = ("tibillet.coop", "tibillet.localhost")


def dns_suffixes_disponibles():
    """
    Liste ordonnee des suffixes de domaine proposes a la creation d'un tenant.
    / Ordered list of domain suffixes offered when creating a tenant.

    LOCALISATION : onboard/services.py

    Source de verite unique, derivee de l'environnement :
      - `DOMAIN` : le domaine wildcard principal (ex. tibillet.coop en prod,
        tibillet.localhost en dev).
      - `ADDITIONAL_DOMAINS` : domaines additionnels du modele SaaS multi-domaine,
        separes par des virgules (ex. "tibillet.re,tibillet.coop").
    Les doublons sont retires en gardant le 1er ordre d'apparition, puis les
    suffixes de `SUFFIXES_DNS_PREFERES` sont remontes en tete. Le 1er element
    est le choix par defaut du formulaire.

    / Single source of truth, derived from the environment (DOMAIN +
    ADDITIONAL_DOMAINS). Duplicates removed, preferred suffixes moved to the
    front. The 1st element is the form's default choice.
    """
    # 1. Le domaine principal en premier, puis les domaines additionnels.
    #    / Main domain first, then the additional domains.
    suffixes = []
    domaine_principal = os.environ.get("DOMAIN", "").strip()
    if domaine_principal:
        suffixes.append(domaine_principal)

    domaines_additionnels = os.environ.get("ADDITIONAL_DOMAINS", "")
    for domaine in domaines_additionnels.split(","):
        domaine_nettoye = domaine.strip()
        if domaine_nettoye and domaine_nettoye not in suffixes:
            suffixes.append(domaine_nettoye)

    # 2. Repli minimal si l'environnement est vide (ne doit pas arriver en prod,
    #    mais garantit une liste non vide pour le formulaire et la validation).
    #    / Minimal fallback if the env is empty (guarantees a non-empty list).
    if not suffixes:
        suffixes = ["tibillet.localhost"]

    # 3. On remonte les suffixes preferes en tete, dans l'ordre de priorite.
    #    On insere du moins prioritaire au plus prioritaire pour que le 1er de
    #    SUFFIXES_DNS_PREFERES finisse en tete de liste.
    #    / Move preferred suffixes to the front, least-priority first so the
    #    first preferred one ends up at index 0.
    for suffixe_prefere in reversed(SUFFIXES_DNS_PREFERES):
        if suffixe_prefere in suffixes:
            suffixes.remove(suffixe_prefere)
            suffixes.insert(0, suffixe_prefere)

    return suffixes

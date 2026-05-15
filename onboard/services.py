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
import secrets
from datetime import timedelta

import requests

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
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
NOMINATIM_USER_AGENT = "TiBillet-Onboard/1.0 (contact@tibillet.coop)"
NOMINATIM_TIMEOUT = 5  # secondes / seconds
GEOCODE_CACHE_TTL = 24 * 60 * 60  # 24h en secondes / 24h in seconds


def _geocode_cache_key(query):
    """
    Construit une cle de cache Redis courte et deterministe a partir d'une
    query (SHA256 tronque). Evite les caracteres exotiques dans la cle.
    / Build a short deterministic Redis cache key from a query
    (truncated SHA256). Avoids exotic chars in the key.
    """
    # SHA256 pour rester court et eviter les caracteres exotiques.
    # / SHA256 for short key and no exotic chars.
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"onboard:geocode:{h[:32]}"


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

    cache_key = _geocode_cache_key(query)
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
            params={"q": query, "format": "json", "limit": 1},
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

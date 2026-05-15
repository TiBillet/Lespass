"""
Services de géocodage côté serveur (proxy Nominatim avec cache Redis).
/ Server-side geocoding services (Nominatim proxy with Redis cache).

LOCALISATION: BaseBillet/services_geocode.py

Mutualisable hors widget : tout formulaire ayant besoin de géocodage
serveur (forward ou reverse) peut consommer ces fonctions. La forward
existe encore dans `onboard/services.py::geocode` pour l'instant — sera
déplacée ici quand un 2e consommateur réel apparaîtra.

/ Reusable beyond the widget: any form needing server-side geocoding
(forward or reverse) can call these functions. Forward still lives in
`onboard/services.py::geocode` — to be moved here when a 2nd real
consumer appears.
"""

import hashlib
import logging

import requests

from django.core.cache import cache
from django.utils.translation import get_language

logger = logging.getLogger(__name__)


# Politique d'usage Nominatim : User-Agent identifiable, max 1 req/s par IP.
# / Nominatim usage policy: identifiable User-Agent, max 1 req/s per IP.
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "TiBillet-Widget/1.0 (contact@tibillet.coop)"
NOMINATIM_TIMEOUT = 5  # secondes / seconds
GEOCODE_CACHE_TTL = 24 * 60 * 60  # 24h en secondes / 24h in seconds


def _construire_cle_cache_reverse(latitude, longitude, lang):
    """
    Cle de cache deterministe pour le reverse geocode. On arrondit les
    coordonnees a 5 decimales (precision ~1.1m) pour augmenter le hit
    rate sur les drags successifs au meme endroit. La langue est dans
    la cle parce que Nominatim renvoie des `display_name` localises.
    / Deterministic cache key. Coords rounded to 5 decimals (~1.1m
    precision) to boost hit rate on successive drags at the same spot.
    Language is in the key because Nominatim returns localized names.
    """
    latitude_arrondie = round(latitude, 5)
    longitude_arrondie = round(longitude, 5)
    raw = f"{latitude_arrondie}:{longitude_arrondie}:{lang}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"widget:geocode-reverse:{h[:32]}"


def _resoudre_langue_utilisateur(lang_explicite=None):
    """
    Renvoie le code langue ISO 2 lettres a passer a Nominatim. Si
    `lang_explicite` est fourni on l'utilise, sinon on lit la langue
    active via `get_language()` (mise par `LocaleMiddleware`). Defaut
    "fr" si aucune langue n'est detectee.
    / Returns 2-letter ISO language code. Falls back to active Django
    language, then to "fr".
    """
    if lang_explicite:
        return lang_explicite.split("-")[0].lower()
    lang_complete = get_language() or "fr"
    return lang_complete.split("-")[0].lower()


def reverse_geocode(latitude, longitude, lang=None):
    """
    Géocodage inverse : (latitude, longitude) -> dict avec :
      - "display_name" : adresse complète formatée par Nominatim.
      - "address" : dict structuré (road, house_number, postcode, city, country, ...).

    Cache Redis 24h sur (lat arrondi 5 décimales, lng arrondi 5 décimales, lang).
    Renvoie `{"display_name": "", "address": {}}` si Nominatim KO
    (timeout, status non-200) — pas d'exception propagée.

    / Reverse geocoding. 24h Redis cache on rounded coords + lang.
    Returns empty payload on Nominatim error (no exception propagated).
    """
    langue_effective = _resoudre_langue_utilisateur(lang)
    cle_cache = _construire_cle_cache_reverse(latitude, longitude, langue_effective)

    payload_en_cache = cache.get(cle_cache)
    if payload_en_cache is not None:
        return payload_en_cache

    try:
        reponse = requests.get(
            NOMINATIM_REVERSE_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "addressdetails": 1,
                "accept-language": langue_effective,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Nominatim reverse error for (%s, %s): %s",
            latitude, longitude, exc,
        )
        # Pas de cache negatif : un timeout transitoire ne doit pas masquer
        # le retour de Nominatim au prochain essai. Trade-off : si Nominatim
        # est down longtemps, on rappelle a chaque drag (limite par notre
        # throttle 1/s/IP cote endpoint).
        # / No negative cache: a transient timeout shouldn't hide Nominatim's
        # recovery on the next attempt. Trade-off: long outage = repeated
        # outgoing calls (limited by our 1/s/IP endpoint throttle).
        return {"display_name": "", "address": {}}

    if reponse.status_code != 200:
        logger.warning(
            "Nominatim reverse status %d for (%s, %s)",
            reponse.status_code, latitude, longitude,
        )
        # Pas de cache negatif : voir commentaire dans le bloc except plus
        # haut. Un 429 / 503 peut etre transitoire.
        # / No negative cache: see except block above. 429 / 503 may be transient.
        return {"display_name": "", "address": {}}

    donnees_json = reponse.json()
    payload = {
        "display_name": donnees_json.get("display_name", ""),
        "address": donnees_json.get("address", {}) or {},
    }
    cache.set(cle_cache, payload, GEOCODE_CACHE_TTL)
    return payload

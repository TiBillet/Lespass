"""
Expose la cle MapTiler a tous les gabarits, ou une cle vide si MapTiler refuse
de servir les tuiles.
/ Exposes the MapTiler key to every template, or an empty key when MapTiler
refuses to serve tiles.

LOCALISATION : TiBillet/maptiler.py

Les cartes du projet vivent dans des apps differentes (pages, seo, widgets
d'adresse inclus par onboard et par le wizard d'evenement). Sans context
processor, chaque vue qui rend une carte devrait penser a passer la cle : la
premiere oubliee affiche une carte au repli sans que personne ne s'en apercoive.
/ The project's maps live in different apps. Without a context processor every
view rendering a map would have to remember to pass the key; the first one
forgotten would silently render the fallback basemap.

La cle est PUBLIQUE par nature : elle part dans le HTML et MapTiler la restreint
par domaine. Il n'y a donc rien a proteger ici.
/ The key is PUBLIC by design: it ships in the HTML and MapTiler restricts it by
domain. There is nothing to protect here.

Le gabarit la pose dans un data-* et le JS la lit — cf. static/cartes/tb_fond_de_carte.js.
Une cle vide fait prendre au JS le fond OSM France HOT, sans cle.
/ The template puts it in a data-* and the JS reads it. An empty key makes the
JS use the keyless OSM France HOT basemap.

REPLI QUOTA : quand le quota gratuit est epuise (ou la cle refusee), MapTiler
repond 403/429 AVEC une image PNG valide (« Invalid key »). Le navigateur
affiche cette image comme une tuile normale : le JS ne voit aucune erreur et ne
peut pas basculer seul. C'est donc le serveur qui sonde MapTiler et retient le
resultat dans le cache :
  - MapTiler OK  -> on expose la cle, on resonde dans DUREE_CACHE_MAPTILER_OK ;
  - MapTiler KO  -> on expose une cle vide pendant DUREE_CACHE_MAPTILER_KO ;
  - reseau en panne pendant la sonde -> on expose la cle, rien n'est retenu.
/ QUOTA FALLBACK: when the quota is used up, MapTiler answers 403/429 WITH a
valid PNG image. The browser shows it as a normal tile, so the JS cannot switch
by itself. The server probes MapTiler and keeps the result in the cache.

APPELE PAR / CALLED BY :
  - TiBillet/settings.py (context processor maptiler_context)
  - BaseBillet/templatetags/tibitags.py (tag {% maptiler_key %})
  - BaseBillet/views.py (get_context, vue reseau)
  - seo/views.py (explorer du ROOT)
"""

import logging
import os

import requests
from django.conf import settings
from django.core.cache import cache
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# Cle du cache qui retient l'etat de MapTiler : "ok" ou "ko".
# / Cache key holding the MapTiler state: "ok" or "ko".
CLE_CACHE_ETAT_MAPTILER = "maptiler:etat_du_service"

# Duree de vie du resultat de la sonde, en secondes.
# OK : 1 h, pour voir un quota qui tombe en cours de journee.
# KO : 24 h, pour ne pas resonder un service qu'on sait refuse.
# / Lifetime of the probe result, in seconds.
DUREE_CACHE_MAPTILER_OK = 60 * 60
DUREE_CACHE_MAPTILER_KO = 60 * 60 * 24

# La sonde tourne pendant le rendu d'une page : elle doit rester courte.
# / The probe runs while a page renders: it must stay short.
DELAI_MAX_SONDE_SECONDES = 2

# Une seule tuile du style utilise par tb_fond_de_carte.js.
# / A single tile of the style used by tb_fond_de_carte.js.
URL_TUILE_DE_SONDE = "https://api.maptiler.com/maps/dataviz-v4/0/0/0.png"


def sonder_maptiler(cle_maptiler):
    """
    Demande une tuile a MapTiler et dit si le service accepte la cle.
    / Asks MapTiler for one tile and tells whether the service accepts the key.

    On envoie le domaine racine en Referer et en Origin : la cle est restreinte
    par domaine dans le dashboard MapTiler. Sans ces en-tetes, MapTiler repond
    403 et la carte basculerait sur OSM alors que le service marche.
    / The root domain is sent as Referer and Origin: the key is restricted by
    domain in the MapTiler dashboard. Without them MapTiler answers 403.

    :param cle_maptiler: la cle MapTiler (str, non vide)
    :return: "ok", "ko", ou None si le reseau n'a pas repondu
    """
    domaine_racine = f"https://{os.environ.get('DOMAIN', 'tibillet.coop')}"
    try:
        reponse = requests.get(
            URL_TUILE_DE_SONDE,
            params={"key": cle_maptiler},
            headers={
                "Referer": f"{domaine_racine}/",
                "Origin": domaine_racine,
            },
            timeout=DELAI_MAX_SONDE_SECONDES,
        )
    except requests.RequestException as erreur_reseau:
        logger.warning(f"Sonde MapTiler sans reponse : {erreur_reseau}")
        return None

    if reponse.ok:
        return "ok"

    logger.warning(
        f"MapTiler refuse les tuiles (HTTP {reponse.status_code}) : "
        f"repli OSM France HOT pendant {DUREE_CACHE_MAPTILER_KO} s"
    )
    return "ko"


def cle_maptiler_a_exposer():
    """
    Renvoie la cle MapTiler a poser dans le HTML, ou une chaine vide si
    MapTiler refuse les tuiles.
    / Returns the MapTiler key to put in the HTML, or an empty string when
    MapTiler refuses tiles.

    Le cache est lu et ecrit dans le schema public : le cache du projet
    prefixe chaque cle par le schema du tenant (KEY_FUNCTION de django-tenants).
    Sans schema_context, chaque lieu ferait sa propre sonde et epuiserait le
    quota que ce repli doit justement proteger.
    / The cache is read and written in the public schema: the project cache
    prefixes each key with the tenant schema. Without schema_context every venue
    would probe on its own and burn the quota this fallback protects.

    :return: la cle (str) ou "" (str)
    """
    cle_maptiler = settings.MAPTILER_KEY
    if not cle_maptiler:
        return ""

    with schema_context("public"):
        etat_du_service = cache.get(CLE_CACHE_ETAT_MAPTILER)

        if etat_du_service is None:
            etat_du_service = sonder_maptiler(cle_maptiler)

            if etat_du_service == "ok":
                cache.set(
                    CLE_CACHE_ETAT_MAPTILER, "ok", DUREE_CACHE_MAPTILER_OK
                )
            if etat_du_service == "ko":
                cache.set(
                    CLE_CACHE_ETAT_MAPTILER, "ko", DUREE_CACHE_MAPTILER_KO
                )

    if etat_du_service == "ko":
        return ""
    return cle_maptiler


def maptiler_context(request):
    """
    Ajoute `maptiler_key` au contexte de tous les gabarits.
    / Adds `maptiler_key` to every template context.

    Chaine vide si la variable d'environnement MAPTILER_KEY est absente, ou si
    MapTiler refuse les tuiles : le JS bascule alors sur le fond de carte de repli.
    / Empty string when MAPTILER_KEY is unset or MapTiler refuses tiles: the JS
    then uses the fallback basemap.
    """
    return {"maptiler_key": cle_maptiler_a_exposer()}

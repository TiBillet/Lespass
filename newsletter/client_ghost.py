"""
Client de l'Admin API de Ghost.
/ Ghost Admin API client.

LOCALISATION : newsletter/client_ghost.py

Ce module ne connait NI les evenements NI TiBillet. Il sait seulement forger un
jeton d'authentification et deposer un brouillon de post dans une instance Ghost.
/ This module knows NOTHING about events or TiBillet. It only forges an auth token
and drops a draft post into a Ghost instance.

POURQUOI DU HTML ET PAS DU LEXICAL (le point contre-intuitif) :
Le contenu d'un post Ghost est stocke en Lexical (JSON avec des cartes typees), mais
ce format n'est PAS documente. En revanche, le convertisseur `?source=html` de Ghost
reconstruit ses cartes natives a partir des conventions de balisage `kg-*` : c'est le
chemin documente et supporte. Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md §4.
/ Ghost stores Lexical (undocumented). The `?source=html` converter rebuilds native
cards from `kg-*` markup: that's the documented path.
"""

import datetime
import logging

import jwt
import requests

logger = logging.getLogger(__name__)

# Ghost refuse tout jeton dont la duree de vie depasse 5 minutes.
# / Ghost rejects any token living longer than 5 minutes.
DUREE_DE_VIE_DU_TOKEN_EN_SECONDES = 5 * 60

# Au-dela, on considere l'instance Ghost injoignable.
# / Past this, we consider the Ghost instance unreachable.
DELAI_MAX_DE_REPONSE_EN_SECONDES = 15


class ErreurGhost(Exception):
    """Erreur generique de dialogue avec Ghost. / Generic Ghost dialogue error."""


class GhostInjoignable(ErreurGhost):
    """L'instance ne repond pas : DNS, connexion refusee, timeout."""


class GhostCleRefusee(ErreurGhost):
    """Ghost a refuse la cle Admin API (401 / 403)."""


class GhostReponseInattendue(ErreurGhost):
    """Ghost a repondu, mais pas ce qu'on attendait (500, corps illisible...)."""


def forger_token_ghost(cle_admin_ghost):
    """
    Fabrique le jeton JWT court attendu par l'Admin API de Ghost.
    / Build the short-lived JWT expected by the Ghost Admin API.

    LOCALISATION : newsletter/client_ghost.py

    La cle Admin a la forme "<identifiant hexa>:<secret hexa>".
    L'identifiant part dans le header (champ `kid`), le secret sert a signer,
    apres avoir ete decode depuis l'hexadecimal vers des octets bruts.
    / The Admin key looks like "<hex id>:<hex secret>".

    :param cle_admin_ghost: la cle Admin API, en clair (str)
    :return: le jeton JWT signe (str)
    """
    # Une cle mal formee (pas de ":", secret non hexadecimal) leverait une ValueError
    # brute, hors de la hierarchie ErreurGhost : l'admin ferait alors un 500 au lieu
    # d'afficher un message. On la convertit en GhostCleRefusee, qui est bien ce dont
    # il s'agit.
    # / A malformed key would raise a bare ValueError, outside the ErreurGhost hierarchy,
    # turning into a 500 in the admin. Convert it to GhostCleRefusee.
    try:
        identifiant_de_la_cle, secret_hexadecimal = cle_admin_ghost.split(":")
        secret_en_octets = bytes.fromhex(secret_hexadecimal)
    except ValueError as erreur_de_forme:
        raise GhostCleRefusee(
            f"La cle Admin API est mal formee. Elle doit avoir la forme "
            f"'<identifiant>:<secret hexadecimal>'. ({erreur_de_forme})"
        )

    instant_present = int(datetime.datetime.now().timestamp())

    entete_du_jeton = {
        "alg": "HS256",
        "typ": "JWT",
        "kid": identifiant_de_la_cle,
    }
    charge_utile_du_jeton = {
        "iat": instant_present,
        "exp": instant_present + DUREE_DE_VIE_DU_TOKEN_EN_SECONDES,
        "aud": "/admin/",
    }

    # Le secret est stocke en hexadecimal : Ghost signe avec les OCTETS, pas la chaine.
    # C'est pour cela que `secret_en_octets` est decode plus haut, dans le try.
    # / The secret is hex-encoded: Ghost signs with the raw BYTES, not the string.
    return jwt.encode(
        charge_utile_du_jeton,
        secret_en_octets,
        algorithm="HS256",
        headers=entete_du_jeton,
    )


def tester_la_connexion(url_instance_ghost, cle_admin_ghost):
    """
    Verifie que l'URL et la cle Admin API repondent. NE MODIFIE RIEN dans Ghost.
    / Check that the URL and Admin key work. CHANGES NOTHING in Ghost.

    LOCALISATION : newsletter/client_ghost.py

    On interroge l'endpoint des membres avec `limit=1` : c'est le plus leger, et il exige
    une authentification valide. Si Ghost repond 200, l'URL et la cle sont bonnes.
    / We query the members endpoint with limit=1: the lightest call that still requires
    valid authentication.

    :param url_instance_ghost: l'URL de l'instance
    :param cle_admin_ghost: la cle Admin API en clair
    :return: None si tout va bien
    :raises GhostInjoignable, GhostCleRefusee, GhostReponseInattendue
    """
    url_nettoyee = url_instance_ghost.rstrip("/")
    entetes = {"Authorization": f"Ghost {forger_token_ghost(cle_admin_ghost)}"}

    try:
        reponse = requests.get(
            f"{url_nettoyee}/ghost/api/admin/members/",
            params={"limit": 1},
            headers=entetes,
            timeout=DELAI_MAX_DE_REPONSE_EN_SECONDES,
        )
    except requests.exceptions.RequestException as erreur_reseau:
        raise GhostInjoignable(f"Instance Ghost injoignable : {erreur_reseau}")

    if reponse.status_code in (401, 403):
        raise GhostCleRefusee(
            f"Ghost a refuse la cle Admin API (HTTP {reponse.status_code})."
        )

    if not reponse.ok:
        raise GhostReponseInattendue(
            f"Ghost a repondu HTTP {reponse.status_code} : {reponse.text[:300]}"
        )


def creer_brouillon(url_instance_ghost, cle_admin_ghost, titre, contenu_html):
    """
    Depose un BROUILLON de post dans Ghost et renvoie son URL d'edition.
    / Drop a DRAFT post into Ghost and return its edit URL.

    LOCALISATION : newsletter/client_ghost.py

    Le post est cree avec status="draft". Il n'est JAMAIS publie, JAMAIS envoye par
    email. L'envoi reste un geste humain, dans l'interface de Ghost.
    / The post is created with status="draft". Never published, never emailed.

    :param url_instance_ghost: l'URL de l'instance (ex: https://ghost.exemple.coop)
    :param cle_admin_ghost: la cle Admin API en clair
    :param titre: le titre du brouillon
    :param contenu_html: le corps, en HTML semantique aux conventions kg-*
    :return: l'URL d'edition du brouillon dans Ghost (str)
    :raises GhostInjoignable, GhostCleRefusee, GhostReponseInattendue
    """
    # URLField accepte un slash final : sans ce nettoyage on produirait //ghost/api/...
    # / URLField allows a trailing slash: without this we'd emit //ghost/api/...
    url_nettoyee = url_instance_ghost.rstrip("/")

    url_de_creation = f"{url_nettoyee}/ghost/api/admin/posts/?source=html"

    # On n'envoie DELIBEREMENT aucun en-tete `Accept-Version`.
    #
    # Ghost s'en sert pour epingler une version d'API. Ce serait une bonne idee sur une
    # instance unique — mais ici, CHAQUE TENANT heberge SON PROPRE Ghost, avec SA propre
    # version. Epingler "v6.0" ferait refuser la requete chez un tenant reste en Ghost 5 ;
    # epingler "v5.0" cassera le jour ou Ghost retirera la compatibilite v5.
    # Sans l'en-tete, chaque instance repond avec sa version courante (verifie : une
    # instance 6.52 renvoie Content-Version: v6.52). Notre usage (creer un brouillon)
    # est stable d'une version majeure a l'autre.
    # / DELIBERATELY no `Accept-Version` header: each tenant self-hosts its own Ghost, at
    # its own version. Pinning any version would break tenants on a different major.
    entetes = {
        "Authorization": f"Ghost {forger_token_ghost(cle_admin_ghost)}",
    }

    corps_de_la_requete = {
        "posts": [
            {
                "title": titre,
                "html": contenu_html,
                # NON NEGOCIABLE : on ne publie jamais, on ne poste qu'un brouillon.
                # / NON-NEGOTIABLE: we never publish, we only post a draft.
                "status": "draft",
            }
        ]
    }

    try:
        reponse = requests.post(
            url_de_creation,
            json=corps_de_la_requete,
            headers=entetes,
            timeout=DELAI_MAX_DE_REPONSE_EN_SECONDES,
        )
    except requests.exceptions.RequestException as erreur_reseau:
        logger.warning(
            f"creer_brouillon : Ghost injoignable sur {url_nettoyee} — {erreur_reseau}"
        )
        raise GhostInjoignable(f"Instance Ghost injoignable : {erreur_reseau}")

    if reponse.status_code in (401, 403):
        raise GhostCleRefusee(
            f"Ghost a refuse la cle Admin API (HTTP {reponse.status_code})."
        )

    # On exige un 201, PAS un "2xx quelconque". C'est une protection contre une panne
    # muette : si l'URL configuree est en http:// et que le reverse-proxy force le https
    # par une redirection 301, `requests` suit la redirection en TRANSFORMANT LE POST EN
    # GET. Ghost repond alors 200 avec la LISTE de ses posts existants. Avec un simple
    # `reponse.ok`, on lirait posts[0].id et on renverrait l'URL d'edition d'un article
    # DEJA EXISTANT, sans avoir rien cree, et sans le moindre signal d'erreur.
    # La creation d'un post repond 201 : on n'accepte que ca.
    # / We require a 201, NOT "any 2xx". Guard against a silent failure: on an http:// URL
    # behind an HTTPS-forcing 301, `requests` follows the redirect and TURNS THE POST INTO
    # A GET. Ghost then answers 200 with the LIST of existing posts, and we would return
    # an existing post's edit URL having created nothing. Creation answers 201.
    CODE_ATTENDU_A_LA_CREATION = 201
    if reponse.status_code != CODE_ATTENDU_A_LA_CREATION:
        raise GhostReponseInattendue(
            f"Ghost a repondu HTTP {reponse.status_code} au lieu de "
            f"{CODE_ATTENDU_A_LA_CREATION} : {reponse.text[:300]}"
        )

    try:
        identifiant_du_post = reponse.json()["posts"][0]["id"]
    except (ValueError, KeyError, IndexError) as erreur_de_lecture:
        raise GhostReponseInattendue(
            f"Reponse de Ghost illisible : {erreur_de_lecture} — {reponse.text[:300]}"
        )

    return f"{url_nettoyee}/ghost/#/editor/post/{identifiant_du_post}"

"""
Guichet de connexion commun à tous les lieux (SSO) : le ticket de connexion.
/ Login desk shared by all venues (SSO): the login ticket.

LOCALISATION : AuthBillet/sso.py

LE PARCOURS :
1. Le lieu B envoie la personne au guichet (domaine du schéma `public`).
2. Le guichet vérifie l'email de la personne (code à 6 chiffres), ou voit
   qu'elle est déjà connectée chez lui.
3. Le guichet fabrique un TICKET et renvoie la personne vers
   `https://<domaine de B>/connexion/retour/?ticket=...`.
4. Le lieu B lit le ticket, puis ouvre SA propre session.
/ The venue sends the user to the desk, the desk proves the email, makes a
ticket, and the venue reads it and opens its own session.

LE TICKET :
Une chaîne signée par `django.core.signing` (sel "AuthBillet.sso.ticket").
Elle contient : `compte` (pk du compte), `lieu` (domaine du lieu de
destination), `unique` (nombre au hasard, pour l'usage unique) et, si besoin,
`avertissement` (message à afficher sur le lieu).
Le ticket ne contient aucune session : seulement « c'est le compte n°X, pour le
lieu B ».
/ A signed string: account pk, destination venue domain, a random nonce,
an optional warning. It carries no session.

Ces fonctions ne connaissent ni la requête ni les gabarits.
/ These functions know neither the request nor the templates.

Spec : TECH_DOC/SESSIONS/TODO/AUTH-connexion-par-code-achat-connecte.md (§3.3, §5.2).
"""

import logging
import secrets

from django.core import signing
from django.core.cache import caches
from django_tenants.utils import get_public_schema_name

from AuthBillet.models import TibilletUser
from Customers.models import Client, Domain

logger = logging.getLogger(__name__)


# Sel de la signature. Un autre sel (lien magique, onboarding...) donne une
# autre signature : un jeton d'une autre fonction ne passe jamais pour un ticket.
# / Signing salt: a token signed for another purpose never reads as a ticket.
SEL_DU_TICKET = "AuthBillet.sso.ticket"

# Durée de vie d'un ticket. Il ne sert qu'à traverser deux redirections.
# / Ticket lifetime: it only has to survive two redirects.
DUREE_DE_VIE_DU_TICKET_EN_SECONDES = 60

# Durée de la clé « ticket déjà servi ». Plus longue que la vie du ticket :
# la clé doit exister tant que le ticket est encore valable.
# / Lifetime of the "ticket already used" key: longer than the ticket itself.
DUREE_DE_LA_CLE_D_USAGE_UNIQUE_EN_SECONDES = 120


def domaine_du_guichet() -> str:
    """
    Domaine principal du tenant `public` : là où vit le guichet.
    / Primary domain of the `public` tenant: where the login desk lives.

    `tibillet.coop` en production, `tibillet.localhost` en dev.
    Lu en base à chaque appel (une requête par clic sur « Se connecter ») :
    pas de cache à invalider.
    / Read from the database on each call: no cache to invalidate.
    """
    tenant_public = Client.objects.get(schema_name=get_public_schema_name())
    domaine_principal = tenant_public.get_primary_domain()
    return domaine_principal.domain


def trouver_le_lieu_du_domaine(domaine: str):
    """
    Le lieu (tenant) qui possède ce domaine. None si le domaine est inconnu,
    ou s'il appartient au tenant `public`.
    / The venue (tenant) owning this domain. None if unknown or `public`.

    C'est la garde contre la redirection ouverte : le guichet ne renvoie un
    ticket que vers un domaine qu'il connaît. Il construit lui-même l'URL de
    retour à partir de ce domaine ; il ne reçoit jamais une URL complète.
    / Guard against open redirects: tickets only go to known venue domains.

    :param domaine: le domaine reçu dans `lieu=` / domain received in `lieu=`
    :return: Customers.Client, ou None
    """
    domaine_connu = (
        Domain.objects.select_related("tenant")
        .filter(domain=domaine)
        .exclude(tenant__schema_name=get_public_schema_name())
        .first()
    )
    if domaine_connu is None:
        return None
    return domaine_connu.tenant


def fabriquer_un_ticket(user, domaine_du_lieu: str, avertissement: str = "") -> str:
    """
    Fabrique le ticket signé qui prouve au lieu que la personne est connectée.
    / Makes the signed ticket proving to the venue that the user is logged in.

    Refuse un compte non humain (terminal de caisse, compte technique) : ces
    comptes ne doivent jamais ouvrir de session sur un lieu par le guichet.
    L'appelant vérifie le type de compte AVANT : ici, c'est le dernier filet.
    / Refuses non-human accounts (ValueError). The caller checks first.

    :param user: le compte (TibilletUser) / the account
    :param domaine_du_lieu: le domaine du lieu de destination, tel que reçu
        dans `lieu=` / destination venue domain, as received in `lieu=`
    :param avertissement: message facultatif à afficher sur le lieu
        / optional message to show on the venue
    :return: le ticket (chaîne signée) / the signed ticket
    """
    if user.espece != TibilletUser.TYPE_HUM:
        raise ValueError(
            f"SSO : refus de fabriquer un ticket pour le compte {user.pk} "
            f"(espece={user.espece}, attendu {TibilletUser.TYPE_HUM})."
        )

    contenu_du_ticket = {
        "compte": str(user.pk),
        "lieu": domaine_du_lieu,
        "unique": secrets.token_hex(16),
    }
    # `str()` : le message peut être une traduction paresseuse, que la
    # signature (JSON) ne sait pas écrire.
    # / str(): the message may be a lazy translation, not JSON-serializable.
    if avertissement:
        contenu_du_ticket["avertissement"] = str(avertissement)

    return signing.dumps(contenu_du_ticket, salt=SEL_DU_TICKET)


def lire_un_ticket(ticket: str, domaine_attendu: str):
    """
    Lit un ticket reçu par le lieu. Renvoie son contenu, ou None.
    / Reads a ticket received by the venue. Returns its content, or None.

    LOCALISATION : AuthBillet/sso.py

    None si le ticket :
    - est faux ou modifié (signature) ;
    - a plus de 60 secondes ;
    - est prévu pour un autre lieu ;
    - a déjà servi une fois.
    / None if forged, older than 60 s, meant for another venue, or already used.

    :param ticket: le ticket reçu dans `ticket=` / the received ticket
    :param domaine_attendu: `request.tenant.domain_url` du lieu, jamais
        `request.get_host()` (qui garde le port)
        / the venue's request.tenant.domain_url, never get_host()
    :return: dict (`compte`, `lieu`, `unique`, `avertissement` facultatif), ou None
    """
    # `SignatureExpired` est une sorte de `BadSignature` : un seul except suffit.
    # / SignatureExpired is a subclass of BadSignature.
    try:
        contenu_du_ticket = signing.loads(
            ticket,
            salt=SEL_DU_TICKET,
            max_age=DUREE_DE_VIE_DU_TICKET_EN_SECONDES,
        )
    except signing.BadSignature:
        logger.info("SSO : ticket refusé (signature fausse ou ticket expiré).")
        return None

    # Le ticket porte le domaine du lieu de destination. Sans ce contrôle, un
    # ticket prévu pour le lieu B pourrait servir sur le lieu C.
    # Ce contrôle passe AVANT l'usage unique : un ticket présenté au mauvais
    # lieu n'est pas consommé.
    # / A ticket for venue B must not open a session on venue C. Checked
    # before the one-time lock, so a misdirected ticket is not consumed.
    if contenu_du_ticket.get("lieu") != domaine_attendu:
        logger.warning(
            f"SSO : ticket prévu pour {contenu_du_ticket.get('lieu')}, "
            f"présenté sur {domaine_attendu}."
        )
        return None

    # Usage unique. `add` ne pose la clé que si elle n'existe pas encore : il
    # renvoie False pour un ticket déjà servi.
    # `caches["verrous"]` et pas le cache par défaut : en panne de memcached,
    # le cache par défaut renverrait False, et tous les tickets seraient
    # refusés comme des rejeux, en silence. L'alias "verrous" lève une
    # exception : la panne arrive dans Sentry.
    # / One-time use through caches["verrous"]: an outage raises instead of
    # silently refusing every ticket as a replay.
    cle_du_ticket_servi = f"sso_ticket_utilise:{contenu_du_ticket['unique']}"
    premiere_utilisation = caches["verrous"].add(
        cle_du_ticket_servi,
        1,
        DUREE_DE_LA_CLE_D_USAGE_UNIQUE_EN_SECONDES,
    )
    if not premiere_utilisation:
        logger.warning(
            f"SSO : ticket déjà servi (rejeu), compte {contenu_du_ticket.get('compte')}."
        )
        return None

    return contenu_du_ticket

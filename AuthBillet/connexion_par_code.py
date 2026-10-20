"""
Connexion par code à 6 chiffres envoyé par mail : envoi et vérification du code.
/ Login by 6-digit emailed code: sending and checking the code.

LOCALISATION : AuthBillet/connexion_par_code.py

Ce service ne connaît ni la requête ni les gabarits. Il garde l'empreinte du
code et les compteurs dans le cache Django (memcached).
/ This service knows neither the request nor the templates. It keeps the code
fingerprint and the counters in the Django cache (memcached).

OÙ IL TOURNE :
L'appelant (le guichet de connexion, schéma `public`) lance ces fonctions SANS
`tenant_context`. `django_tenants.cache.make_key` préfixe chaque clé du cache
par le schéma courant : les clés sont donc posées sur `public`. Ainsi, les
plafonds comptent tous les lieux ensemble. Comptés par lieu, ils seraient
multipliés par le nombre de lieux.
Seul le `.delay()` du mail tourne dans `tenant_context(lieu)` : la tâche
Celery hérite du lieu, et le mail porte le nom du lieu.
/ Called WITHOUT tenant_context (keys live on `public`, limits count all venues
together). Only the mail `.delay()` runs inside tenant_context(venue).

CLÉS DU CACHE (<e> = 32 premiers caractères du SHA-256 de l'email) :
- login_code:<e>:empreinte            empreinte du code        600 s
- login_code:<e>:essais               compteur d'essais        600 s
- login_code:<e>:dernier_envoi        1 (cache "verrous")       60 s
- login_code:<e>:envois_de_l_heure    compteur d'envois       3600 s
- login_code_ip:<ip>:demandes_des_10_min  compteur par IP      600 s

Spec : TECH_DOC/SESSIONS/TODO/AUTH-connexion-par-code-achat-connecte.md (§5.1).
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache, caches
from django_tenants.utils import tenant_context

from AuthBillet.otp_service import (
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    generer_code_otp,
    hash_code_otp,
    verifier_code_otp,
)

logger = logging.getLogger(__name__)


# Nombre maximum de codes envoyés à un même email en une heure.
# 10 plutôt que 5 : une personne dont le mail arrive dans les indésirables
# reclique plusieurs fois.
# / Max codes sent to one email per hour.
CODES_PAR_HEURE_ET_PAR_EMAIL = 10
DUREE_D_UNE_HEURE_EN_SECONDES = 3600

# Durée de la tranche du plafond par IP. Le nombre permis est dans
# settings.CONNEXION_CODE_PLAFOND_IP_10_MIN.
# / Length of the per-IP window. The allowed count is in settings.
DUREE_DE_LA_TRANCHE_IP_EN_SECONDES = 600


def cle_cache(email: str, suffixe: str) -> str:
    """
    Clé de cache d'un email, pour un suffixe donné (empreinte, essais...).
    / Cache key of an email, for a given suffix.

    Sert au service ET au test E2E, qui remplace l'empreinte par celle d'un code
    connu. Ne jamais recopier cette construction à la main ailleurs.
    / Used by the service AND the E2E test. Never rebuild it by hand.

    L'email est normalisé ici aussi (strip + lower) : la même adresse tapée avec
    une majuscule ou un espace donne la même clé.
    On garde 32 caractères du SHA-256 de l'email, pas l'email lui-même :
    memcached refuse les clés de plus de 250 caractères et certains caractères.
    / The email is normalized here too. We keep 32 chars of its SHA-256:
    memcached rejects long keys and some characters.
    """
    email_normalise = email.strip().lower()
    empreinte_de_l_email = hashlib.sha256(email_normalise.encode("utf-8")).hexdigest()[
        :32
    ]
    return f"login_code:{empreinte_de_l_email}:{suffixe}"


def cle_cache_ip(adresse_ip: str) -> str:
    """
    Clé de cache du compteur de demandes d'une adresse IP.
    / Cache key of an IP address request counter.
    """
    return f"login_code_ip:{adresse_ip}:demandes_des_10_min"


def augmenter_un_compteur(cle: str, duree_de_vie_en_secondes: int) -> int:
    """
    Ajoute 1 à un compteur du cache et renvoie la nouvelle valeur.
    / Adds 1 to a cache counter and returns the new value.

    Le compteur doit tenir face à deux requêtes arrivées en même temps.
    `cache.add` (crée la clé seulement si elle n'existe pas) et `cache.incr`
    sont atomiques dans memcached. L'appelant décide TOUJOURS sur la valeur
    renvoyée ici, jamais sur un `get` suivi d'une comparaison : entre les deux,
    une autre requête aurait pu compter.
    / add + incr are atomic in memcached. Callers decide on the returned value,
    never on a get-then-compare.

    Si la clé expire entre `add` et `incr`, `incr` lève ValueError : on recrée
    le compteur à 1.
    En panne de memcached (cache par défaut, `ignore_exc`), `incr` lève aussi
    ValueError et le compteur vaut toujours 1 : les plafonds sont suspendus le
    temps de la panne. C'est accepté.
    / If the key expired in between, incr raises ValueError: restart at 1.
    During a memcached outage limits are suspended (accepted).
    """
    cache.add(cle, 0, duree_de_vie_en_secondes)
    try:
        nouvelle_valeur = cache.incr(cle)
    except ValueError:
        cache.add(cle, 1, duree_de_vie_en_secondes)
        nouvelle_valeur = 1
    return nouvelle_valeur


def envoyer_un_code_de_connexion(email: str, adresse_ip, langue: str, lieu) -> str:
    """
    Vérifie les plafonds, fabrique un code, garde son empreinte en cache,
    et programme le mail dans le contexte du lieu.
    / Checks limits, makes a code, caches its fingerprint, schedules the email
    in the venue context.

    LOCALISATION : AuthBillet/connexion_par_code.py

    FLUX :
    1. Plafond par IP (si l'IP est connue).
    2. Délai de 60 s entre deux envois au même email.
    3. Plafond de 10 codes par heure et par email.
    4. Nouveau code : il remplace l'ancien, le compteur d'essais repart à 0.
    5. `.delay()` du mail dans `tenant_context(lieu)`.

    :param email: email tapé par la personne / typed email
    :param adresse_ip: AuthBillet.utils.get_client_ip(request), ou None / client IP or None
    :param langue: get_language() de la requête / request language
    :param lieu: le tenant (Customers.Client) d'où vient la personne / venue tenant
    :return: "envoye", "attendre" (moins de 60 s) ou "trop_de_demandes"
    """
    # Import local : BaseBillet.tasks charge Stripe, Fedow, weasyprint...
    # au chargement du module. Même choix que otp_service.envoyer_email_otp.
    # / Local import: BaseBillet.tasks pulls heavy deps at load time.
    from BaseBillet.tasks import code_de_connexion_celery_mailer

    email_normalise = email.strip().lower()

    # 1. Plafond par adresse IP, tous lieux confondus.
    # Il ne protège pas les personnes (c'est le rôle du plafond par email).
    # Il freine un script qui enverrait des codes à des milliers d'adresses
    # depuis une seule IP. Une IP inconnue (None, en dev local) n'est pas comptée.
    # / Per-IP limit: slows down a naive mass-mailing script. Unknown IP = not counted.
    if adresse_ip is not None:
        plafond_ip = settings.CONNEXION_CODE_PLAFOND_IP_10_MIN
        nombre_de_demandes_de_l_ip = augmenter_un_compteur(
            cle_cache_ip(adresse_ip),
            DUREE_DE_LA_TRANCHE_IP_EN_SECONDES,
        )
        if nombre_de_demandes_de_l_ip > plafond_ip:
            # Une seule ligne par tranche de 10 minutes : la première demande
            # refusée. Le journal sert à distinguer un festival bloqué d'une attaque.
            # / One log line per window: the first refused request.
            if nombre_de_demandes_de_l_ip == plafond_ip + 1:
                logger.warning(
                    f"Connexion par code : l'adresse IP {adresse_ip} a atteint le plafond "
                    f"de {plafond_ip} demandes en 10 minutes."
                )
            return "trop_de_demandes"

    # 2. Délai entre deux envois au même email.
    # `caches["verrous"]` et pas le cache par défaut : en panne de memcached,
    # le cache par défaut renverrait False (comme si la clé était prise), et la
    # personne lirait « Un code vient de partir » pour toujours. L'alias
    # "verrous" lève une exception : la panne arrive dans Sentry.
    # / The "verrous" alias raises on outage instead of looking like "key taken".
    cache_des_verrous = caches["verrous"]
    premier_envoi_de_la_minute = cache_des_verrous.add(
        cle_cache(email_normalise, "dernier_envoi"),
        1,
        OTP_RESEND_COOLDOWN_SECONDS,
    )
    if not premier_envoi_de_la_minute:
        return "attendre"

    # 3. Plafond par email : 10 codes par heure.
    # Il est compté APRÈS le délai de 60 s : un double clic ne consomme pas le quota.
    # / Per-email limit, counted AFTER the 60 s delay: a double click costs nothing.
    nombre_d_envois_de_l_heure = augmenter_un_compteur(
        cle_cache(email_normalise, "envois_de_l_heure"),
        DUREE_D_UNE_HEURE_EN_SECONDES,
    )
    if nombre_d_envois_de_l_heure > CODES_PAR_HEURE_ET_PAR_EMAIL:
        return "trop_de_demandes"

    # 4. Nouveau code. Il remplace l'ancien : nouvelle empreinte, et le
    # compteur d'essais repart à 0.
    # / New code replaces the old one: new fingerprint, attempts back to 0.
    code = generer_code_otp()
    cache.set(
        cle_cache(email_normalise, "empreinte"), hash_code_otp(code), OTP_TTL_SECONDS
    )
    cache.set(cle_cache(email_normalise, "essais"), 0, OTP_TTL_SECONDS)

    # En DEBUG seulement, le code est écrit dans le journal du serveur.
    # C'est la seule fonction qui voit le code : ni la vue ni la tâche mail
    # ne le journalisent.
    # / DEBUG only: the code is logged here, and nowhere else.
    if settings.DEBUG:
        logger.info(
            f"Connexion par code (DEBUG) : code pour {email_normalise} : {code}"
        )

    # 5. Le mail part dans le contexte du lieu : la tâche Celery hérite du
    # schéma (TenantAwareCeleryApp) et lit le nom du lieu dans sa Configuration.
    # / The email is scheduled in the venue context: the task inherits the schema.
    with tenant_context(lieu):
        code_de_connexion_celery_mailer.delay(email_normalise, code, langue)

    return "envoye"


def verifier_le_code_de_connexion(email: str, code_saisi: str) -> str:
    """
    Vérifie le code tapé par la personne.
    / Checks the code typed by the user.

    LOCALISATION : AuthBillet/connexion_par_code.py

    FLUX :
    1. Pas d'empreinte en cache → "expire" (code trop vieux, déjà servi, ou
       jamais demandé).
    2. Un essai de plus est compté AVANT de comparer le code.
    3. Plus de 5 essais → "bloque".
    4. Code juste → on efface l'empreinte : le code ne sert qu'une fois.
    5. Code faux → "faux", ou "bloque" si c'était le dernier essai permis.

    :return: "ok", "faux", "expire" ou "bloque"
    """
    cle_de_l_empreinte = cle_cache(email, "empreinte")
    cle_des_essais = cle_cache(email, "essais")

    empreinte_du_code = cache.get(cle_de_l_empreinte)
    if empreinte_du_code is None:
        return "expire"

    # L'essai est compté AVANT la comparaison, sur la valeur renvoyée par incr :
    # deux requêtes simultanées ne peuvent pas passer toutes les deux sur le
    # même dernier essai.
    # / Count the attempt BEFORE comparing, on the value returned by incr.
    numero_de_l_essai = augmenter_un_compteur(cle_des_essais, OTP_TTL_SECONDS)
    if numero_de_l_essai > OTP_MAX_ATTEMPTS:
        return "bloque"

    code_est_juste = verifier_code_otp(code_saisi, empreinte_du_code)
    if code_est_juste:
        # Usage unique. `cache.delete` renvoie True seulement pour la requête
        # qui a vraiment effacé la clé : si deux requêtes arrivent en même
        # temps avec le bon code, une seule obtient "ok".
        # / One-time use: only the request that really deleted the key gets "ok".
        empreinte_effacee_par_cette_requete = cache.delete(cle_de_l_empreinte)
        cache.delete(cle_des_essais)
        if not empreinte_effacee_par_cette_requete:
            return "expire"
        return "ok"

    # Le dernier essai permis était faux : la personne doit demander un nouveau code.
    # / The last allowed attempt was wrong: a new code is needed.
    if numero_de_l_essai >= OTP_MAX_ATTEMPTS:
        return "bloque"
    return "faux"

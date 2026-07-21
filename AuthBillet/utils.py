import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction

from AuthBillet.models import TibilletUser
from BaseBillet.tasks import connexion_celery_mailer

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Retourne l'adresse IP du visiteur, telle que le proxy l'a etablie.
    / Returns the visitor's IP address, as established by the proxy.

    LOCALISATION : AuthBillet/utils.py

    L'ORDRE DES SOURCES EST UN CHOIX DE SECURITE, NE PAS L'INVERSER.

    `X-Real-IP` est lu EN PREMIER parce que nginx l'IMPOSE : il vaut le
    `$remote_addr` reconstruit par le module `real_ip` (cf. nginx_prod), qui
    remonte la chaine `X-Forwarded-For` par la DROITE en ignorant les
    intermediaires de confiance. C'est donc la seule valeur que le client ne
    controle pas.

    `X-Forwarded-For` ne sert qu'en REPLI, et on y prend le dernier element.
    Cet en-tete s'ecrit en AJOUTANT A DROITE : son element de GAUCHE est celui
    que le client a envoye lui-meme, donc entierement forgeable. Le lire
    reviendrait a laisser n'importe qui choisir son identite.

    Ce que cela protege : cette fonction sert d'identifiant de limitation de
    debit (throttle DRF de l'identification, plafond de renvoi d'OTP dans
    `onboard/views.py`). Prendre une valeur forgeable permettrait a la fois de
    contourner ces plafonds — une IP differente a chaque requete — et de bloquer
    une victime en remplissant le compteur associe a SON adresse.

    / SOURCE ORDER IS A SECURITY CHOICE, DO NOT SWAP IT. `X-Real-IP` comes first
    because nginx SETS it from the `real_ip`-rebuilt `$remote_addr`, which walks
    `X-Forwarded-For` from the RIGHT skipping trusted hops — the client cannot
    control it. `X-Forwarded-For` is a fallback only, and we take its LAST entry:
    the header appends on the right, so its leftmost value is client-supplied.
    This function identifies clients for rate limiting (DRF throttle, OTP resend
    cap), so a forgeable value would both bypass the caps and let an attacker
    lock out a victim by filling their counter.

    :param request: l'objet Request Django
    :return: l'adresse IP (str), ou None si aucune source n'est disponible
    """
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip.strip()

    # Repli : le dernier maillon de la chaine, ajoute par le proxy le plus
    # proche de nous — et non le premier, qui vient du client.
    # / Fallback: the last hop, added by the nearest proxy — not the first,
    # which comes from the client.
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[-1].strip()

    return request.META.get('REMOTE_ADDR')



def sender_mail_connect(email, subject_mail=None, next_url=None):
    # Mail de confirmation de création de compte
    try :
        base_url = connection.tenant.get_primary_domain().domain
    except AttributeError :
        # get_primary_domain plante lors des tests unitaires python :
        base_url = "lespass.tibillet.localhost"

    try:
        logger.info(f"sender_mail_connect : {email} - {base_url}")
        # On attend le COMMIT avant d'envoyer la tache Celery.
        # Sinon, quand l'user est cree dans une transaction (ex: creation
        # via l'admin Django, dont les vues changeform sont atomic), le
        # worker Celery peut lire l'user AVANT le COMMIT depuis sa propre
        # connexion et planter sur "TibilletUser DoesNotExist".
        # Hors transaction (vues publiques en autocommit), on_commit execute
        # le callback immediatement : aucun changement de comportement.
        # / Defer the Celery dispatch until after COMMIT, so the worker never
        #   reads the user before it is committed (admin changeform = atomic).
        #   Outside a transaction (public views), the callback runs immediately.
        transaction.on_commit(
            lambda: connexion_celery_mailer.delay(
                email, f"https://{base_url}", subject_mail, next_url=next_url
            )
        )
    except Exception as e:
        logger.error(f"validate_email_and_return_user erreur pour récuperer config : {email} - {base_url} : {e}")


def get_or_create_user(email: str,
                       password=None,
                       set_active=False,
                       send_mail=True,
                       force_mail=False,
                       next_url=None,
                       ) -> "TibilletUser" or None:
    """
    If user not created, set it inactive.
    Only the mail validation can set active the user.

    :param email: email
    :param password: str
    :return:
    """

    User: "TibilletUser" = get_user_model()
    email = email.lower()
    user, created = User.objects.get_or_create(
        email=email,
        username=email,
        espece=TibilletUser.TYPE_HUM
    )

    try :
        if not connection.tenant in user.client_achat.all():
            user.client_achat.add(connection.tenant)
    except (AttributeError, ValidationError):
        pass # Fake tenant, on pass
    except Exception as e:
        raise e

    if created:
        if password:
            user.set_password(password)

        user.is_active = bool(set_active)
        user.client_achat.add(connection.tenant)
        user.client_source = connection.tenant
        user.save()

        if bool(send_mail):
            logger.info(f"created & bool(send_mail) == {send_mail}, -> sender_mail_connect({user.email})")
            sender_mail_connect(user.email, next_url=next_url)


    else:
        if user.email_error:
            logger.info("utilisateur n'a pas un email valide")
            return None

        if force_mail:
            sender_mail_connect(user.email, next_url=next_url)
        elif user.email_valid == False:
            # L'utilisateur n'a pas encore validé son email
            # On relance le mail de validation.
            if bool(send_mail):
                logger.info("utilisateur est inactif, il n'a pas encore validé son mail, on lance le mail de validation")
                sender_mail_connect(user.email, next_url=next_url)

    return user




import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection

from AuthBillet.models import TibilletUser
from BaseBillet.tasks import connexion_celery_mailer

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    x_real_ip = request.META.get('HTTP_X_REAL_IP')

    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    elif x_real_ip:
        ip = x_real_ip
    else:
        ip = request.META.get('REMOTE_ADDR')

    return ip



def sender_mail_connect(email, subject_mail=None):
    # Mail de confirmation de création de compte
    try :
        base_url = connection.tenant.get_primary_domain().domain
    except AttributeError :
        # get_primary_domain plante lors des tests unitaires python :
        base_url = "lespass.tibillet.localhost"

    try:
        logger.info(f"sender_mail_connect : {email} - {base_url}")
        connexion_celery_mailer.delay(email, f"https://{base_url}", subject_mail)
        # connexion_celery_mailer(email, f"https://{base_url}", subject_mail)
    except Exception as e:
        logger.error(f"validate_email_and_return_user erreur pour récuperer config : {email} - {base_url} : {e}")


def get_or_create_user(email: str,
                       password=None,
                       set_active=False,
                       send_mail=True,
                       force_mail=False,
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
            sender_mail_connect(user.email)


    else:
        if user.email_error:
            logger.info("utilisateur n'a pas un email valide")
            return None

        if force_mail:
            sender_mail_connect(user.email)
        elif user.email_valid == False:
            # L'utilisateur n'a pas encore validé son email
            # On relance le mail de validation.
            if bool(send_mail):
                logger.info("utilisateur est inactif, il n'a pas encore validé son mail, on lance le mail de validation")
                sender_mail_connect(user.email)

    return user




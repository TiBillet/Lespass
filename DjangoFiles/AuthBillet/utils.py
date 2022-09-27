import logging

from django.contrib.auth import get_user_model
from django.db import connection

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
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
    # Si la billetterie est active, on envoie le mail de confirmation
    base_url = connection.tenant.get_primary_domain().domain
    try:
        logger.info(f"sender_mail_connect : {email} - {base_url}")
        connexion_celery_mailer.delay(email, f"https://{base_url}", subject_mail)

    except Exception as e:
        logger.error(f"validate_email_and_return_user erreur pour récuperer config : {email} - {base_url} : {e}")


def get_or_create_user(email, password=None, set_active=False, send_mail=True):
    """
    If user not created, set it inactive.
    Only the mail validation can set active the user.

    :param email: email
    :param password: str
    :return:
    """

    User: TibilletUser = get_user_model()
    user, created = User.objects.get_or_create(
        email=email,
        username=email,
        espece=TibilletUser.TYPE_HUM
    )

    if created :
        if password:
            user.set_password(password)

        user.is_active = bool(set_active)

        user.client_achat.add(connection.tenant)
        user.save()

        if bool(send_mail) :
            sender_mail_connect(user.email)

        return user

    else:
        if user.email_error:
            return False
        return user


################################# MAC ADRESS SERIALIZER #################################


import re
from rest_framework.fields import Field
from django.core.validators import RegexValidator
from django.utils.translation import ugettext_lazy as _

class MacAdressField(Field):
    MAX_STRING_LENGTH = 17
    default_error_messages = {
        'invalid': _("Not a mac address")
    }
    MAC_GROUPS = 6
    MAC_DELIMITER = ':'
    MAC_RE = re.compile("([0-9a-f]{2})" +
                        ("\%s([0-9a-f]{2})" % MAC_DELIMITER) * (MAC_GROUPS - 1),
                        flags=re.IGNORECASE)

    def __init__(self, **kwargs):
        super(MacAdressField, self).__init__(**kwargs)
        self.validators.append(
            RegexValidator(self.MAC_RE, message=self.error_messages['invalid']))


    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value

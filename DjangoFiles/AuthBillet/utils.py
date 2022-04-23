from django.contrib.auth import get_user_model
from django.db import connection

from AuthBillet.models import TibilletUser
from BaseBillet.tasks import connexion_celery_mailer


def validate_email_and_return_user(email, password=None, subject_mail=None):
    User: TibilletUser = get_user_model()
    user, created = User.objects.get_or_create(
        email=email,
        username=email,
        espece=TibilletUser.TYPE_HUM
    )

    base_url = connection.tenant.get_primary_domain().domain

    if not created:
        if user.is_active:
            task = connexion_celery_mailer.delay(user.email, f"https://{base_url}", subject_mail)
            return user
        else:
            if user.email_error:
                return False
            else:
                task = connexion_celery_mailer.delay(user.email, f"https://{base_url}", subject_mail)
                return user
    else:
        if password:
            user.set_password(password)

        user.is_active = False

        user.client_achat.add(connection.tenant)
        user.save()
        task = connexion_celery_mailer.delay(user.email, f"https://{base_url}")

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

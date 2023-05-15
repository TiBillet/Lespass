import logging
import typing

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework_api_key.models import APIKey, AbstractAPIKey
from rest_framework_api_key.permissions import BaseHasAPIKey, KeyParser

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration, ExternalApiKey
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


def user_apikey_valid(view):
    # En string : On vérifie que view.basename == url.basename
    # exemple dans DjangoFiles/ApiBillet/urls.py
    # router.register(r'events', api_view.EventsViewSet, basename='event')
    # On peut aussi faire action = view.action -> create ? Pas utile pour l'instant.
    try :
        key = view.request.META["HTTP_AUTHORIZATION"].split()[1]
        api_key = APIKey.objects.get_from_key(key)
        tenant_apikey = get_object_or_404(ExternalApiKey, key=api_key)

        ip = get_client_ip(view.request)

        logger.info(
            f"is_apikey_valid : "
            f"ip request : {ip} - ip apikey : {tenant_apikey.ip} - "
            f"basename : {view.basename} : {tenant_apikey.api_permissions().get(view.basename)} - "
            f"permission : {tenant_apikey.api_permissions()}"
        )

        if all([
            ip == tenant_apikey.ip,
            tenant_apikey.api_permissions().get(view.basename)
        ]):
            return tenant_apikey.user

    except:
        return False



def sender_mail_connect(email, subject_mail=None):
    # Si la billetterie est active, on envoie le mail de confirmation
    base_url = connection.tenant.get_primary_domain().domain
    try:
        logger.info(f"sender_mail_connect : {email} - {base_url}")
        connexion_celery_mailer.delay(email, f"https://{base_url}", subject_mail)

    except Exception as e:
        logger.error(f"validate_email_and_return_user erreur pour récuperer config : {email} - {base_url} : {e}")


def get_or_create_user(email,
                       password=None,
                       set_active=False,
                       send_mail=True,
                       force_mail=False
                       ) -> TibilletUser or None:
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

    if created:
        if password:
            user.set_password(password)

        user.is_active = bool(set_active)

        user.client_achat.add(connection.tenant)
        user.client_source = connection.tenant
        user.save()

        if bool(send_mail):
            sender_mail_connect(user.email)


    else:
        if user.email_error:
            logger.info("utilisateur n'a pas un email valide")
            return None

        if force_mail:
            sender_mail_connect(user.email)
        elif user.is_active == False:
            # Si l'utilisateur est inactif, il n'a pas encore validé son mail
            # Si la demande vient après la création, on relance le mail de validation.
            if bool(send_mail):
                logger.info("utilisateur est inactif, il n'a pas encore validé son mail, on lance le mail de validation")
                sender_mail_connect(user.email)

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

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

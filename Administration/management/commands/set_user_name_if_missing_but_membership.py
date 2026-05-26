from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q
from django_tenants.utils import get_tenant_model, tenant_context
import logging
import argparse

from Customers.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Récupère tout les utilisateurs qui n'ont pas de prénom et/ou nom de famille et leur en ajoute un depuis une potentiel adhésion sur tout les tenants (hors ROOT)."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = """
Va chercher tout les utilisateurs sans prénom ou nom de famille dans tout les tenants.
Pour chaque utilisateur, on vérifie si il a une adhésion, si oui on lui assigne le prénom/nom de l'adhésion à la place de celui qu'il lui manque.


Exemple d'utilisation :
python manage.py set_user_name_if_missing_but_membership 

Via Docker :
docker exec lespass_django poetry run python manage.py set_user_name_if_missing_but_membership
        """


    def handle(self, *args, **options):

        # Get all the tenants except ROOT
        TenantModel = get_tenant_model()
        tenants = TenantModel.objects.exclude(categorie=Client.ROOT)

        for tenant in tenants:
            # Use the tenant contexte
            with tenant_context(tenant):

                # Get all the users without first name or last name
                User = get_user_model()
                users_without_name = User.objects.filter(
                    Q(first_name__exact="") |
                    Q(first_name__isnull=True) |
                    Q(last_name__exact="") |
                    Q(last_name__isnull=True)
                )
                # Get the count of user without first or last name
                users_without_name_count = users_without_name.count()
                logger.info(f"=== TENANT : {tenant.name} - User without name : {users_without_name_count} === ")

                for user in users_without_name:
                    # Get the user's last membership
                    membership = user.memberships.first()

                    # Check if the user has a membership and is missing its first or last name
                    if membership and (not user.first_name or not user.last_name):
                        first_name = membership.first_name if not user.first_name else user.first_name
                        last_name = membership.last_name if not user.last_name else user.last_name

                        # Get the user as a queryset to update
                        user = User.objects.filter(pk=user.pk)
                        user.update(first_name=first_name, last_name=last_name)
                        users_without_name_count-=1
                        logger.info(f"=== UPDATED : {user[0].email} === ")

                logger.info(f"=== IN TENANT : {tenant.name} - there is still {users_without_name_count} user(s) without name  === ")

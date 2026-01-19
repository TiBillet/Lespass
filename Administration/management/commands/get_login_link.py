from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django_tenants.utils import get_tenant_model, tenant_context
from BaseBillet.tasks import forge_connexion_url
import logging
import argparse

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Génère un lien de connexion (token) pour un utilisateur sur un tenant spécifique."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = """
Génère un lien de connexion (token) pour un utilisateur sur un tenant spécifique.
Le lien généré est identique à celui envoyé par email lors d'une demande de connexion.

Exemple d'utilisation :
python manage.py get_login_link user@example.com mytenant

Via Docker :
docker exec lespass_django poetry run python manage.py get_login_link user@example.com mytenant
        """
        parser.add_argument('email', type=str, help="L'email de l'utilisateur")
        parser.add_argument('schema_name', type=str, help="Le schema_name du tenant")

    def handle(self, *args, **options):
        email = options['email'].strip()
        schema_name = options['schema_name']

        TenantModel = get_tenant_model()
        try:
            tenant = TenantModel.objects.get(schema_name=schema_name)
        except TenantModel.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tenant avec le schema_name '{schema_name}' non trouvé."))
            return

        with tenant_context(tenant):
            User = get_user_model()
            try:
                # On essaie d'abord en minuscule comme dans le reste du projet
                user = User.objects.get(email=email.lower())
            except User.DoesNotExist:
                # Si pas trouvé, on essaie tel quel
                try:
                    user = User.objects.get(email=email)
                except User.DoesNotExist:
                    self.stderr.write(self.style.ERROR(
                        f"Utilisateur avec l'email '{email}' non trouvé sur le tenant '{schema_name}'."))
                    return

            try:
                domain = tenant.get_primary_domain().domain
                base_url = f"https://{domain}"
            except Exception:
                # Fallback si pas de domaine défini ou erreur
                base_url = "https://tibillet.org"
                self.stdout.write(self.style.WARNING(
                    "Pas de domaine primaire trouvé, utilisation de https://tibillet.org par défaut."))

            connexion_url = forge_connexion_url(user, base_url)
            self.stdout.write(connexion_url)

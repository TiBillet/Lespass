# Migration de donnees : cree une page d'accueil par defaut (app pages) pour
# chaque tenant existant, reproduisant la home historique.
# / Data migration: create a default home page (pages app) for each existing
# tenant, reproducing the historical home.

from django.db import connection, migrations


def creer_page_accueil_par_defaut(apps, schema_editor):
    """
    Cree la page d'accueil par defaut sur le schema tenant courant.
    / Create the default home page on the current tenant schema.

    Cette migration BaseBillet ne s'execute que sur les schemas tenant
    (BaseBillet est en TENANT_APPS uniquement). On garde un garde sur le schema
    public par securite. Idempotent : le service ne fait rien si une page
    d'accueil existe deja.
    / This BaseBillet migration only runs on tenant schemas (BaseBillet is in
    TENANT_APPS only). We guard the public schema for safety. Idempotent: the
    service does nothing if a home page already exists.
    """
    if connection.schema_name == "public":
        return

    Page = apps.get_model("pages", "Page")
    Bloc = apps.get_model("pages", "Bloc")
    Configuration = apps.get_model("BaseBillet", "Configuration")

    config = Configuration.objects.first()
    if config is None:
        return

    # Le service prend les classes en parametres et utilise des chaines pour
    # type_bloc : compatible avec les modeles historiques de migration.
    # / The service takes the model classes as params and uses strings for
    # type_bloc: compatible with historical migration models.
    from pages.services import construire_page_accueil

    page = construire_page_accueil(Page, Bloc, config)
    if page is not None:
        print(f"  -> [{connection.schema_name}] page d'accueil par defaut creee")


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0221_remove_configuration_skin'),
        # La page d'accueil utilise les modeles de l'app pages.
        # / The home page uses the pages app models.
        ('pages', '0003_configurationsite'),
    ]

    operations = [
        migrations.RunPython(
            creer_page_accueil_par_defaut,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

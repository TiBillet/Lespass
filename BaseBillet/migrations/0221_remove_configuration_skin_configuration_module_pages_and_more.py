# Migration UNIQUE de la branche main-pages (squash du 2026-07-05).
# Remplace les anciennes 0220_configuration_module_pages -> 0225 (jamais
# deployees en production, qui s'arrete a 0220_lignearticle_idempotency_key).
# Schema : module_pages + externalapikey.page + retrait de Configuration.skin.
# Donnees (RunPython, pour les tenants EXISTANTS de production) :
#   1. copie Configuration.skin -> pages.ConfigurationSite AVANT le RemoveField
#      (sinon les tenants faire_festival perdraient leur skin) ;
#   2. creation de la page d'accueil par defaut (HERO/PARAGRAPHE/CTA) via
#      pages.services.construire_page_accueil, idempotente, dans la LANGUE du
#      tenant (translation.override — sans lui, les libelles CTA seraient
#      graves en anglais, locale du worker).
# / Single migration of the main-pages branch (2026-07-05 squash). Replaces the
# never-deployed 0220..0225. Schema: module_pages + externalapikey.page + drop
# Configuration.skin. Data (for EXISTING production tenants): 1. copy skin to
# pages.ConfigurationSite BEFORE the RemoveField; 2. create the default home
# page (idempotent) in the tenant's language (translation.override).

from django.db import connection, migrations, models


def copier_skin_vers_configuration_site(apps, schema_editor):
    """
    Copie Configuration.skin vers le singleton pages.ConfigurationSite.
    / Copies Configuration.skin into the pages.ConfigurationSite singleton.

    Cette migration BaseBillet ne s'execute que sur les schemas tenant
    (BaseBillet est en TENANT_APPS uniquement), donc Configuration et
    ConfigurationSite existent toutes deux ici. On garde tout de meme un garde
    sur le schema public par securite.
    / This BaseBillet migration only runs on tenant schemas (BaseBillet is in
    TENANT_APPS only), so both Configuration and ConfigurationSite exist here.
    We still guard against the public schema for safety.
    """
    if connection.schema_name == "public":
        return

    Configuration = apps.get_model("BaseBillet", "Configuration")
    ConfigurationSite = apps.get_model("pages", "ConfigurationSite")

    configuration = Configuration.objects.first()
    if configuration is None:
        return

    skin_actuel = getattr(configuration, "skin", None)

    # Defensif : si le champ skin n'existe plus (re-execution apres RemoveField),
    # on NE TOUCHE PAS au singleton, sinon on l'ecraserait avec une valeur par
    # defaut et on perdrait le skin reel du tenant.
    # / Defensive: if the skin field is gone (re-run after RemoveField), DO NOT
    # touch the singleton, otherwise we'd overwrite it with a default and lose
    # the tenant's real skin.
    if not skin_actuel:
        return

    # Le singleton django-solo utilise l'id 1. On cree ou met a jour la ligne.
    # / The django-solo singleton uses id 1. We create or update the row.
    ConfigurationSite.objects.update_or_create(
        id=1,
        defaults={"skin": skin_actuel},
    )
    print(f"  -> [{connection.schema_name}] skin '{skin_actuel}' copie vers ConfigurationSite")


def creer_home_par_defaut(apps, schema_editor):
    """
    Cree la home par defaut (HERO/PARAGRAPHE/CTA) sur le schema tenant courant,
    si absente. Idempotente et non destructive : construire_page_accueil ne
    fait rien si une page d'accueil (est_accueil=True) existe deja.
    / Create the default home (HERO/PARAGRAPH/CTA) on the current tenant
    schema, if missing. Idempotent and non-destructive.
    """
    if connection.schema_name == "public":
        return

    Page = apps.get_model("pages", "Page")
    Bloc = apps.get_model("pages", "Bloc")
    Configuration = apps.get_model("BaseBillet", "Configuration")

    config = Configuration.objects.first()
    if config is None:
        # Tenant sans Configuration : rien a faire.
        # / Tenant without a Configuration: nothing to do.
        return

    # Le service prend les classes en parametres et utilise des chaines pour
    # type_bloc : compatible avec les modeles historiques de migration.
    # description_longue=None -> le service retombe sur config.long_description
    # (comportement voulu pour les tenants existants).
    # / The service takes the model classes as params and uses strings for
    # type_bloc (migration-safe). description_longue=None -> falls back to
    # config.long_description (intended for existing tenants).
    from pages.services import construire_page_accueil

    # IMPORTANT : les libelles CTA sont figes en base via gettext() (non lazy).
    # migrate_schemas tourne dans un processus SANS langue activee (locale du
    # worker, souvent anglaise) : sans override, un tenant francais recevrait
    # des boutons "Calendar"/"Subscriptions" graves en anglais. On active donc
    # explicitement la langue du tenant le temps de l'appel.
    # / CTA labels are frozen in DB via gettext() (not lazy). migrate_schemas
    # runs without any activated language: explicitly activate the tenant's
    # language around the call.
    from django.utils import translation

    with translation.override(config.language or "fr"):
        page = construire_page_accueil(Page, Bloc, config)
    if page is not None:
        print(f"  -> [{connection.schema_name}] home par defaut creee (HERO/PARAGRAPHE/CTA)")


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0220_lignearticle_idempotency_key_and_more'),
        # Les RunPython utilisent pages.ConfigurationSite/Page/Bloc : les tables
        # doivent exister. / The RunPython ops use the pages models: their
        # tables must exist first.
        ('pages', '0001_initial'),
    ]

    operations = [
        # 1. Copier le skin AVANT de retirer le champ (donnees prod).
        # / 1. Copy the skin BEFORE removing the field (prod data).
        migrations.RunPython(
            copier_skin_vers_configuration_site,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='configuration',
            name='skin',
        ),
        migrations.AddField(
            model_name='configuration',
            name='module_pages',
            field=models.BooleanField(default=True, verbose_name='Module pages / site web'),
        ),
        migrations.AddField(
            model_name='externalapikey',
            name='page',
            field=models.BooleanField(default=False, verbose_name='Pages / Site web'),
        ),
        # 2. Home par defaut pour les tenants existants (idempotente).
        # / 2. Default home for existing tenants (idempotent).
        migrations.RunPython(
            creer_home_par_defaut,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

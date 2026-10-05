"""
Migration de données : le skin du lieu passe dans `pages.ConfigurationSite`, et la page
d'accueil par défaut est créée.
/ Data migration: the venue's skin moves into `pages.ConfigurationSite`, and the default
home page is created.

LOCALISATION : BaseBillet/migrations/0225_copier_le_skin_et_creer_la_page_d_accueil.py

ORDRE IMPÉRATIF / MANDATORY ORDER :
1. `pages 0001_initial` crée les tables de `pages` (dépendance ci-dessous) ;
2. cette migration copie `Configuration.skin` puis crée la page d'accueil ;
3. `BaseBillet 0226` retire le champ `skin`.
/ 1. pages tables exist; 2. this migration copies the skin and creates the home page;
3. BaseBillet 0226 removes the `skin` field.

Elle porte les données des lieux EXISTANTS de production. Sur un lieu neuf, il n'y a
pas encore de `Configuration` : elle ne fait rien.
/ It carries the data of EXISTING production venues. On a new venue there is no
Configuration yet: it does nothing.

Code repris de l'ancienne `BaseBillet/0222_categorieproduct_module_pages_reprise_du_skin`.
/ Code taken from the former BaseBillet 0222 migration.
"""

from django.db import connection, migrations


def copier_skin_vers_configuration_site(apps, schema_editor):
    """
    Copie Configuration.skin vers le singleton pages.ConfigurationSite.
    / Copies Configuration.skin into the pages.ConfigurationSite singleton.

    Cette migration BaseBillet ne s'exécute que sur les schémas de lieu
    (BaseBillet est en TENANT_APPS uniquement), donc Configuration et
    ConfigurationSite existent toutes deux ici. On garde tout de même une garde
    sur le schéma public par sécurité.
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

    # Défensif : si le champ skin n'existe plus (réexécution après RemoveField),
    # on NE TOUCHE PAS au singleton, sinon on l'écraserait avec une valeur par
    # défaut et on perdrait le skin réel du lieu.
    # / Defensive: if the skin field is gone (re-run after RemoveField), DO NOT
    # touch the singleton, otherwise we would overwrite it with a default and lose
    # the venue's real skin.
    if not skin_actuel:
        return

    # Le singleton django-solo utilise l'id 1. On crée ou met à jour la ligne.
    # / The django-solo singleton uses id 1. We create or update the row.
    ConfigurationSite.objects.update_or_create(
        id=1,
        defaults={"skin": skin_actuel},
    )
    print(f"  -> [{connection.schema_name}] skin '{skin_actuel}' copie vers ConfigurationSite")


def creer_home_par_defaut(apps, schema_editor):
    """
    Crée la page d'accueil par défaut (HERO/PARAGRAPHE/CTA) sur le schéma de lieu
    courant, si elle manque. Idempotente et non destructive : construire_page_accueil
    ne fait rien si une page d'accueil (est_accueil=True) existe déjà.
    / Creates the default home (HERO/PARAGRAPH/CTA) on the current tenant
    schema, if missing. Idempotent and non-destructive.
    """
    if connection.schema_name == "public":
        return

    Page = apps.get_model("pages", "Page")
    Bloc = apps.get_model("pages", "Bloc")
    Configuration = apps.get_model("BaseBillet", "Configuration")

    config = Configuration.objects.first()
    if config is None:
        # Lieu sans Configuration : rien à faire.
        # / Venue without a Configuration: nothing to do.
        return

    # Le service prend les classes en paramètres et utilise des chaînes pour
    # type_bloc : compatible avec les modèles historiques de migration.
    # description_longue=None -> le service retombe sur config.long_description
    # (comportement voulu pour les lieux existants).
    # / The service takes the model classes as params and uses strings for
    # type_bloc (migration-safe). description_longue=None -> falls back to
    # config.long_description (intended for existing venues).
    from pages.services import construire_page_accueil

    # IMPORTANT : les libellés des boutons sont figés en base via gettext() (non lazy).
    # migrate_schemas tourne dans un processus SANS langue activée (langue du
    # worker, souvent l'anglais) : sans override, un lieu francophone recevrait
    # des boutons "Calendar"/"Subscriptions" gravés en anglais. On active donc
    # explicitement la langue du lieu le temps de l'appel.
    # / CTA labels are frozen in DB via gettext() (not lazy). migrate_schemas
    # runs without any activated language: explicitly activate the venue's
    # language around the call.
    from django.utils import translation

    with translation.override(config.language or "fr"):
        page = construire_page_accueil(Page, Bloc, config)
    if page is not None:
        print(f"  -> [{connection.schema_name}] home par defaut creee (HERO/PARAGRAPHE/CTA)")


class Migration(migrations.Migration):

    dependencies = [
        ("BaseBillet", "0224_liens_caisse_fedow_et_montants_des_ventes"),
        # Les fonctions utilisent pages.ConfigurationSite/Page/Bloc : les tables
        # doivent exister.
        # / The functions use the pages models: their tables must exist first.
        ("pages", "0001_initial"),
    ]

    operations = [
        # 1. Copier le skin AVANT de retirer le champ (0226).
        # / 1. Copy the skin BEFORE removing the field (0226).
        migrations.RunPython(
            copier_skin_vers_configuration_site,
            reverse_code=migrations.RunPython.noop,
        ),
        # 2. Page d'accueil par défaut pour les lieux existants (idempotente).
        # / 2. Default home page for existing venues (idempotent).
        migrations.RunPython(
            creer_home_par_defaut,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

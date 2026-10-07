"""
Passe en moteur `v2` un lieu qui utilise deja un module V2.
/ Switches to the `v2` engine a venue that already uses a V2 module.

LOCALISATION : BaseBillet/migrations/0227_moteur_v2_si_un_module_v2_est_actif.py

Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §4.2.

`Customers 0006` a mis tous les lieux existants en `legacy`. Mais un lieu dont la
`Configuration` a deja un module V2 allume (caisse, monnaie locale, kiosk, tireuse)
utilise deja le moteur V2 : le laisser en `legacy` lui fermerait sa caisse et ses
monnaies. Cette migration, jouee dans le schema de chaque lieu, le passe en `v2`.
/ A venue with a V2 module on already uses V2: it goes v2.

`migrate_schemas` migre `public` d'abord, puis chaque lieu : `Customers 0006` est donc
deja passee quand cette migration tourne. La table `Customers_client` (schema public) est
atteinte par le `search_path` du lieu (lieu, puis public).
/ public is migrated first; Customers_client is reached through the search_path.

Elle n'ecrit que par `update()` : pas de `save()`, pas de signal, aucun appel reseau.
Rejouee, elle ne change rien.
/ update() only: no save, no signal, no network call. Replaying changes nothing.
"""

from django.db import connection, migrations

# Les drapeaux de `Configuration` qui font d'un lieu un lieu V2. `module_inventaire`
# (stock des articles) n'est pas monetaire : il n'en fait pas partie.
# / The Configuration flags that make a venue a V2 venue (inventory is not one).
DRAPEAUX_DES_MODULES_V2 = [
    "module_caisse",
    "module_monnaie_locale",
    "module_kiosk",
    "module_tireuse",
]


def passer_en_v2_si_un_module_v2_est_actif(apps, schema_editor):
    """
    Passe en `v2` le `Client` du schema courant si un module V2 est allume dans sa
    `Configuration`. Sinon, le lieu reste `legacy`.
    / Sets the current schema's Client to v2 if a V2 module is on.

    FLUX :
    1. schema public : rien a faire (pas de Configuration ici) ;
    2. pas de Configuration (lieu neuf) : rien a faire, son `Client` est deja `v2` ;
    3. aucun module V2 allume : rien a faire, le lieu reste `legacy` ;
    4. sinon : `update()` du `Client` dont le `schema_name` est le schema courant.
       La ligne n'est imprimee que si l'`update()` a touche une ligne : un schema sans
       `Client` (comme le modele des tests, `test_modele`) n'imprime rien.
    """
    schema_courant = connection.schema_name
    schema_est_public = schema_courant == "public"
    if schema_est_public:
        return

    # Modele historique : on lit la ligne par objects.first(), pas par get_solo().
    # / Historical model: read the row with objects.first(), not get_solo().
    Configuration = apps.get_model("BaseBillet", "Configuration")
    configuration_du_lieu = Configuration.objects.first()
    if configuration_du_lieu is None:
        return

    un_module_v2_est_allume = False
    for nom_du_drapeau in DRAPEAUX_DES_MODULES_V2:
        if getattr(configuration_du_lieu, nom_du_drapeau):
            un_module_v2_est_allume = True

    if not un_module_v2_est_allume:
        return

    # Pas de save() : le modele historique n'a pas TenantMixin.save.
    # / No save(): the historical model has no TenantMixin.save.
    Client = apps.get_model("Customers", "Client")
    nombre_de_lieux_passes_en_v2 = Client.objects.filter(
        schema_name=schema_courant,
    ).update(
        moteur_monnaie="v2",
    )

    if nombre_de_lieux_passes_en_v2 == 1:
        print(f"  -> [{schema_courant}] moteur v2 (module V2 actif)")


class Migration(migrations.Migration):
    dependencies = [
        ("BaseBillet", "0226_retirer_le_skin_de_la_configuration"),
        ("Customers", "0006_moteur_de_monnaie"),
    ]

    operations = [
        migrations.RunPython(
            passer_en_v2_si_un_module_v2_est_actif,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

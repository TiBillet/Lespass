"""
Migration de données : chaque lieu a la ligne de sa configuration LaBoutik et sa clé
d'empreinte, en base.
/ Data migration: every venue has its LaBoutik configuration row and its fingerprint
key, in the database.

LOCALISATION : laboutik/migrations/0016_cle_d_empreinte_toujours_en_base.py

POURQUOI
La clé d'empreinte (HMAC) scelle chaque vente réglée. Elle vit dans
`LaboutikConfiguration.hmac_key`, un singleton django-solo mis en cache (memcached).
Sans cette migration, la ligne n'est créée qu'au premier `get_solo()`. Si cette
première création a lieu dans une transaction annulée ensuite, le cache garde un objet
que la base n'a pas (tests/PIEGES.md 9.86). Avec la ligne et la clé déjà en base, la
première vente n'a rien à créer.
/ Without this migration, the row is created at the first get_solo(); inside a rolled
back transaction, the cache keeps an object the database does not have.

laboutik est une application de lieu : la migration tourne dans chaque schéma de lieu
existant, et à la création de chaque nouveau lieu. Elle ne fait rien dans le schéma
public (la table n'y existe pas).
/ Tenant app: runs in every venue schema and at each venue creation; nothing in public.

Une clé existante ne change JAMAIS : changer la clé casserait la vérification des
empreintes déjà écrites. Inverse : rien (la ligne et la clé restent).
/ An existing key NEVER changes. Reverse: nothing.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-H-1-ter.md (point 8).
"""

import secrets

from django.db import connection, migrations

# L'identifiant de la ligne unique de django-solo (`SingletonModel.singleton_instance_id`).
# / The django-solo single row id.
IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON = 1


def creer_la_configuration_et_sa_cle(apps, schema_editor):
    """
    Crée la ligne de `LaboutikConfiguration` si elle manque, et sa clé d'empreinte si
    elle est vide. Même génération et même chiffrement que
    `LaboutikConfiguration.get_or_create_hmac_key` : 32 octets en hexadécimal,
    chiffrés Fernet. N'utilise pas `schema_editor`.
    / Creates the row if missing and its key if empty (same generation and encryption
    as get_or_create_hmac_key). Does not use schema_editor.
    """
    # Le schéma public n'a pas la table : on ne fait rien.
    # / The public schema has no such table: do nothing.
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    from root_billet.utils import fernet_encrypt

    LaboutikConfiguration = apps.get_model("laboutik", "LaboutikConfiguration")
    configuration_du_lieu, _ligne_creee = LaboutikConfiguration.objects.get_or_create(
        pk=IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON
    )

    cle_deja_presente = bool(configuration_du_lieu.hmac_key)
    if cle_deja_presente:
        return

    nouvelle_cle = secrets.token_hex(32)
    LaboutikConfiguration.objects.filter(
        pk=IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON
    ).update(hmac_key=fernet_encrypt(nouvelle_cle))
    print(f"  -> [{schema_courant}] clé d'empreinte du lieu créée")


class Migration(migrations.Migration):
    dependencies = [
        ("laboutik", "0015_impression_vers_la_cloture_unique"),
    ]

    operations = [
        migrations.RunPython(
            creer_la_configuration_et_sa_cle,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

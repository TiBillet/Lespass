"""
Migration de données : les impressions de tickets Z perdent leur lien vers l'ancienne
clôture de caisse (`laboutik.ClotureCaisse`).
/ Data migration: Z ticket prints lose their link to the old register closure.

LOCALISATION : laboutik/migrations/0014_vider_le_lien_de_cloture_des_impressions.py

La migration suivante (0015) fait pointer `ImpressionLog.cloture` vers la clôture
unique du lieu (`comptabilite.ClotureCaisse`). Les valeurs existantes pointent vers
d'anciennes clôtures, qui n'existent pas dans la nouvelle table : elles sont remises
à vide ici (base de dev seulement, perte acceptée). Deux migrations SÉPARÉES : jamais
de DML et de DDL dans la même (tests/PIEGES.md 9.113).
/ The next migration retargets the FK; existing values are emptied here first. DML and
DDL are never mixed in one migration.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2.1).
"""

from django.db import connection, migrations


def vider_le_lien_de_cloture_des_impressions(apps, schema_editor):
    """
    Remet à vide le lien de clôture de toutes les impressions du lieu.
    / Empties the closure link of every print of the venue.

    `ImpressionLog` est une TENANT_APP : sa table n'existe pas dans le schéma public.
    On ne fait rien dans public.
    / ImpressionLog is a TENANT_APP: nothing to do in the public schema.
    """
    schema_courant = connection.schema_name
    schema_est_public = schema_courant == "public"
    if schema_est_public:
        return

    ImpressionLog = apps.get_model("laboutik", "ImpressionLog")
    nombre_d_impressions_videes = ImpressionLog.objects.filter(
        cloture__isnull=False
    ).update(cloture=None)

    if nombre_d_impressions_videes:
        print(
            f"  -> [{schema_courant}] "
            f"{nombre_d_impressions_videes} impression(s) de Z sans lien de clôture"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0013_ranger_les_crowds_dans_le_financement_participatif'),
    ]

    operations = [
        migrations.RunPython(
            vider_le_lien_de_cloture_des_impressions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

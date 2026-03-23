"""
Migration de donnees + schema : refonte typage comportement PointDeVente.
/ Data + schema migration: refactor PointDeVente comportement typing.

Supprime les comportements ADHESION ('A'), CASHLESS ('C') et KIOSK ('K').
Tous les PV existants passent a DIRECT ('D').
Ajoute AVANCE ('V') pour le mode commande restaurant (reserve, pas code).

/ Removes ADHESION ('A'), CASHLESS ('C') and KIOSK ('K') behaviors.
All existing POS are migrated to DIRECT ('D').
Adds AVANCE ('V') for restaurant order mode (reserved, not coded yet).
"""
from django.db import connection, migrations, models


def convertir_comportements_vers_direct(apps, schema_editor):
    """
    Convertit tous les PV non-DIRECT vers DIRECT.
    / Converts all non-DIRECT POS to DIRECT.

    Protection schema public : la table PointDeVente est dans TENANT_APPS,
    elle n'existe pas dans le schema public.
    / Public schema guard: PointDeVente is in TENANT_APPS,
    the table does not exist in the public schema.
    """
    schema_est_public = (connection.schema_name == 'public')
    if schema_est_public:
        return

    PointDeVente = apps.get_model('laboutik', 'PointDeVente')
    nombre_modifies = PointDeVente.objects.exclude(comportement='D').update(comportement='D')
    if nombre_modifies:
        print(f"  -> [{connection.schema_name}] {nombre_modifies} PV migre(s) vers DIRECT")


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0003_laboutikconfiguration'),
    ]

    operations = [
        # 1. Data migration : tous les PV → DIRECT
        migrations.RunPython(
            convertir_comportements_vers_direct,
            reverse_code=migrations.RunPython.noop,
        ),
        # 2. Schema : reduire les choix a DIRECT + AVANCE
        migrations.AlterField(
            model_name='pointdevente',
            name='comportement',
            field=models.CharField(
                choices=[('D', 'Direct'), ('V', 'Advanced')],
                default='D',
                help_text='Operating mode: Direct (standard counter sale) or Advanced (restaurant order mode).',
                max_length=1,
                verbose_name='Behavior',
            ),
        ),
    ]

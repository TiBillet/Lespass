"""
Migration schema : restaurer les types de point de vente.
/ Schema migration: restore point of sale types.

Ajoute ADHESION ('A'), CASHLESS ('C') et BILLETTERIE ('T') aux choix.
Le type determine le chargement automatique des articles, pas le contenu exclusif.
Les articles du M2M products sont toujours charges en plus.

/ Adds ADHESION ('A'), CASHLESS ('C') and BILLETTERIE ('T') to choices.
The type determines automatic article loading, not exclusive content.
M2M products are always loaded in addition.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0004_refonte_typage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pointdevente',
            name='comportement',
            field=models.CharField(
                choices=[
                    ('D', 'Direct'),
                    ('A', 'Memberships'),
                    ('C', 'Cashless'),
                    ('T', 'Ticketing'),
                    ('V', 'Advanced'),
                ],
                default='D',
                help_text=(
                    'Determines how articles are loaded. '
                    'Direct: M2M only. Memberships: auto-loads membership products. '
                    'Cashless: auto-loads top-ups. Ticketing: builds from future events. '
                    'Advanced: restaurant order mode.'
                ),
                max_length=1,
                verbose_name='POS type',
            ),
        ),
    ]

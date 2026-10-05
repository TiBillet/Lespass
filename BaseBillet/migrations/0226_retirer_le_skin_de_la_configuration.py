"""
Retire le champ `Configuration.skin`. Le thème graphique vit désormais dans
`pages.ConfigurationSite`.
/ Removes the `Configuration.skin` field. The graphic theme now lives in
`pages.ConfigurationSite`.

LOCALISATION : BaseBillet/migrations/0226_retirer_le_skin_de_la_configuration.py

Elle passe APRÈS la copie du skin (0225) : retirer le champ avant perdrait le skin
de chaque lieu existant.
/ It runs AFTER the skin copy (0225): removing the field earlier would lose every
existing venue's skin.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("BaseBillet", "0225_copier_le_skin_et_creer_la_page_d_accueil"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="configuration",
            name="skin",
        ),
    ]

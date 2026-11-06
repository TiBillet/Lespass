# Images de galerie : deux changements en une migration.
# / Gallery images: two changes in one migration.
#
# 1. Legende : 200 -> 500 caracteres. Une legende sert aussi de courte
#    presentation (ex. une structure sous son logo) et 200 caracteres coupaient
#    ces textes.
#    / Caption: 200 -> 500 characters.
# 2. Nouveau champ `tags` : badges separes par des virgules, rendus par les
#    affichages EQUIPE et RESSOURCES d'une SECTION (une image = un element).
#    / New `tags` field: comma-separated badges, rendered by the SECTION's
#    EQUIPE and RESSOURCES displays.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0004_bloc_carte_figee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='imagegalerie',
            name='legende',
            field=models.CharField(blank=True, help_text="Texte alternatif et légende de l'image (optionnel).", max_length=500, verbose_name='Légende'),
        ),
        migrations.AddField(
            model_name='imagegalerie',
            name='tags',
            field=models.CharField(blank=True, help_text='Blocs Équipe et Ressources : badges affichés sous le nom, séparés par des virgules. Ex. : Coordination, Salariée.', max_length=200, verbose_name='Tags'),
        ),
    ]

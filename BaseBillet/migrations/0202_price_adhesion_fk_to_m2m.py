# Migration FK adhesion_obligatoire → M2M adhesions_obligatoires
# 3 etapes : ajouter M2M, copier les donnees FK → M2M, supprimer FK
# / 3 steps: add M2M, copy FK data → M2M, remove FK

from django.db import migrations, models


def copy_fk_to_m2m(apps, schema_editor):
    """Copie les FK existantes vers le nouveau M2M / Copy existing FK values to new M2M."""
    Price = apps.get_model('BaseBillet', 'Price')
    for price in Price.objects.filter(adhesion_obligatoire__isnull=False):
        price.adhesions_obligatoires.add(price.adhesion_obligatoire)


def copy_m2m_to_fk(apps, schema_editor):
    """Reverse : copie le premier element M2M vers le FK / Reverse: copy first M2M element back to FK."""
    Price = apps.get_model('BaseBillet', 'Price')
    for price in Price.objects.all():
        first = price.adhesions_obligatoires.first()
        if first:
            price.adhesion_obligatoire = first
            price.save(update_fields=['adhesion_obligatoire'])


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0201_backfill_lignearticle_reservation'),
    ]

    operations = [
        # 1. Ajouter le M2M
        migrations.AddField(
            model_name='price',
            name='adhesions_obligatoires',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    'Rate available to subscribers only (OR logic: having at least one of the selected subscriptions is enough). '
                    'Only works for reservation-type products. '
                    'The rate will be visible if the user is logged in AND has paid at least one of these membership fees.'
                ),
                related_name='adhesions_obligatoires',
                to='BaseBillet.product',
                verbose_name='Subscriptions required',
            ),
        ),
        # 2. Copier les donnees FK → M2M
        migrations.RunPython(copy_fk_to_m2m, copy_m2m_to_fk),
        # 3. Supprimer l'ancien FK
        migrations.RemoveField(
            model_name='price',
            name='adhesion_obligatoire',
        ),
    ]

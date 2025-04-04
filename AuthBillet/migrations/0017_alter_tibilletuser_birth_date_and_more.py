# Generated by Django 4.2.17 on 2024-12-18 07:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AuthBillet', '0016_remove_tibilletuser_can_create_tenant'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tibilletuser',
            name='birth_date',
            field=models.DateField(blank=True, null=True, verbose_name='Date de naissance'),
        ),
        migrations.AlterField(
            model_name='tibilletuser',
            name='first_name',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Prenom'),
        ),
        migrations.AlterField(
            model_name='tibilletuser',
            name='last_name',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Nom'),
        ),
        migrations.AlterField(
            model_name='tibilletuser',
            name='last_see',
            field=models.DateTimeField(auto_now=True, verbose_name='Dernière connexion'),
        ),
        migrations.AlterField(
            model_name='tibilletuser',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Téléphone'),
        ),
        migrations.AlterField(
            model_name='tibilletuser',
            name='postal_code',
            field=models.IntegerField(blank=True, null=True, verbose_name='Code postal'),
        ),
    ]

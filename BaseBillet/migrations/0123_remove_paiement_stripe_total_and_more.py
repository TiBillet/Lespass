# Generated by Django 4.2.17 on 2025-03-09 09:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0122_alter_event_categorie'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='paiement_stripe',
            name='total',
        ),
        migrations.AlterField(
            model_name='product',
            name='categorie_article',
            field=models.CharField(choices=[('N', 'Selectionnez une catégorie'), ('B', 'Billet pour reservation payante'), ('A', 'Abonnement/Adhésion'), ('G', 'Badgeuse'), ('F', 'Reservation gratuite')], default='N', max_length=3, verbose_name='Type de produit'),
        ),
        migrations.AlterField(
            model_name='product',
            name='poids',
            field=models.PositiveSmallIntegerField(default=0, help_text="Ordre d'apparition du plus leger au plus lourd", verbose_name='Ordre'),
        ),
        migrations.AlterField(
            model_name='productsold',
            name='categorie_article',
            field=models.CharField(choices=[('N', 'Selectionnez une catégorie'), ('B', 'Billet pour reservation payante'), ('A', 'Abonnement/Adhésion'), ('G', 'Badgeuse'), ('F', 'Reservation gratuite')], default='N', max_length=3, verbose_name='Type de produit'),
        ),
    ]

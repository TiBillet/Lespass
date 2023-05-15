# Generated by Django 3.2 on 2023-04-27 07:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0063_auto_20230427_1105'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='legal_link',
            field=models.URLField(blank=True, null=True, verbose_name='Mentions légales'),
        ),
        migrations.AlterField(
            model_name='product',
            name='categorie_article',
            field=models.CharField(choices=[('N', 'Selectionnez une catégorie'), ('B', 'Billet'), ('P', "Pack d'objets"), ('R', 'Recharge cashless'), ('S', 'Recharge suspendue'), ('T', 'Vetement'), ('M', 'Merchandasing'), ('A', 'Adhésions associative'), ('B', 'Abonnement'), ('D', 'Don'), ('F', 'Reservation gratuite')], default='N', max_length=3, verbose_name="Type d'article"),
        ),
    ]
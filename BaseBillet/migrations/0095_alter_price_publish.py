# Generated by Django 4.2 on 2024-09-14 13:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0094_price_publish'),
    ]

    operations = [
        migrations.AlterField(
            model_name='price',
            name='publish',
            field=models.BooleanField(default=True, verbose_name='Publié'),
        ),
    ]

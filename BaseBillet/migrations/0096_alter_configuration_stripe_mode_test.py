# Generated by Django 4.2 on 2024-09-27 06:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0095_alter_price_publish'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuration',
            name='stripe_mode_test',
            field=models.BooleanField(default=False),
        ),
    ]
# Generated by Django 4.2.10 on 2024-02-21 14:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('root_billet', '0004_rootconfiguration_fedow_primary_pub_pem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rootconfiguration',
            name='fedow_create_place_apikey',
            field=models.CharField(blank=True, editable=False, max_length=200, null=True),
        ),
    ]

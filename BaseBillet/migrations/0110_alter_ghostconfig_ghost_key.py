# Generated by Django 4.2.17 on 2025-02-11 15:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0109_postaladdress_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ghostconfig',
            name='ghost_key',
            field=models.CharField(blank=True, max_length=400, null=True),
        ),
    ]

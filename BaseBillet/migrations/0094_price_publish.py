# Generated by Django 4.2 on 2024-09-01 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0093_membership_asset_fedow'),
    ]

    operations = [
        migrations.AddField(
            model_name='price',
            name='publish',
            field=models.BooleanField(default=True),
        ),
    ]
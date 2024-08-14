# Generated by Django 4.2.10 on 2024-04-01 10:57

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('AuthBillet', '0013_wallet_tibilletuser_wallet'),
        ('fedow_connect', '0004_alter_fedowconfig_fedow_place_admin_apikey'),
    ]

    operations = [
        migrations.AddField(
            model_name='fedowconfig',
            name='wallet',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='place', to='AuthBillet.wallet'),
        ),
    ]
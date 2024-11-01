# Generated by Django 4.2 on 2024-10-15 11:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0096_alter_configuration_stripe_mode_test'),
    ]

    operations = [
        migrations.AddField(
            model_name='price',
            name='free_price',
            field=models.BooleanField(default=False, help_text='Si coché, le prix sera demandé sur la page de paiement stripe', verbose_name='Prix libre'),
        ),
    ]
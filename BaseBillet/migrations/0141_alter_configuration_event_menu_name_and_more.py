# Generated by Django 4.2.17 on 2025-04-30 09:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0140_alter_configuration_membership_menu_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuration',
            name='event_menu_name',
            field=models.CharField(blank=True, help_text="'Calendar' If empty.", max_length=200, null=True, verbose_name='Calendar page name'),
        ),
        migrations.AlterField(
            model_name='product',
            name='validate_button_text',
            field=models.CharField(blank=True, help_text="'Subscribe' If empty. Only useful for membership or subscription products.", max_length=20, null=True, verbose_name='Validate button text for membership'),
        ),
    ]

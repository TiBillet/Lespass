# Generated by Django 4.2.17 on 2025-05-05 13:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0145_event_custom_confirmation_message'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuration',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Phone number'),
        ),
    ]

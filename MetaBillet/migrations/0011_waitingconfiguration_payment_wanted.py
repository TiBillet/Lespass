# Generated by Django 4.2.17 on 2025-05-13 13:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MetaBillet', '0010_alter_waitingconfiguration_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='waitingconfiguration',
            name='payment_wanted',
            field=models.BooleanField(default=False),
        ),
    ]

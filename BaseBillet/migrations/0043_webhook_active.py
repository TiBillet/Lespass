# Generated by Django 3.2 on 2022-10-18 09:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0042_webhook'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhook',
            name='active',
            field=models.BooleanField(default=False),
        ),
    ]
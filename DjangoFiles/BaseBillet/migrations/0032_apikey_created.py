# Generated by Django 3.2 on 2022-09-27 16:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0031_apikey'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='created',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
# Generated by Django 3.2 on 2023-05-23 10:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0072_auto_20230522_1614'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tag',
            options={'verbose_name': 'Tag', 'verbose_name_plural': 'Tags'},
        ),
        migrations.RemoveField(
            model_name='event',
            name='cashless',
        ),
    ]
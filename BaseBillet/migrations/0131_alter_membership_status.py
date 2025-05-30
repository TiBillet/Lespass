# Generated by Django 4.2.17 on 2025-03-20 11:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0130_configuration_first_input_label_membership_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membership',
            name='status',
            field=models.CharField(choices=[('D', 'Saved through the admin'), ('I', 'Import from file'), ('O', 'Single online payment'), ('A', 'Automatic renewal'), ('C', 'Cancelled')], default='O', max_length=1, verbose_name='Origin'),
        ),
    ]

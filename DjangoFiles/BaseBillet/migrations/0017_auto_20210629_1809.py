# Generated by Django 2.2 on 2021-06-29 14:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0016_auto_20210629_1739'),
    ]

    operations = [
        migrations.RenameField(
            model_name='lignearticle',
            old_name='articles',
            new_name='article',
        ),
        migrations.AlterField(
            model_name='lignearticle',
            name='reservation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='BaseBillet.Reservation', verbose_name='lignes_article'),
        ),
        migrations.AlterField(
            model_name='reservation',
            name='status',
            field=models.CharField(choices=[('NAN', 'Annulée'), ('MNV', 'Email non validé'), ('NPA', 'Non payée'), ('VAL', 'Validée'), ('PAY', 'Payée')], default='NPA', max_length=3, verbose_name='Status de la réservation'),
        ),
    ]
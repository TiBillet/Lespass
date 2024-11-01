# Generated by Django 4.2 on 2024-10-31 13:02

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('BaseBillet', '0098_alter_paiement_stripe_source_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membership',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='membership', to=settings.AUTH_USER_MODEL),
        ),
    ]
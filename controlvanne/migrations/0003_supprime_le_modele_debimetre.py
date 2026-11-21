"""
Supprime l'ancien lien TireuseBec.debimetre et le modèle Debimetre.
/ Drops the old TireuseBec.debimetre link and the Debimetre model.

LOCALISATION : controlvanne/migrations/0003_supprime_le_modele_debimetre.py

Les valeurs ont été copiées sur la tireuse par la migration 0002.
/ Values were copied onto the tap by migration 0002.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("controlvanne", "0002_debitmetre_sur_la_tireuse"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tireusebec",
            name="debimetre",
        ),
        migrations.DeleteModel(
            name="Debimetre",
        ),
    ]

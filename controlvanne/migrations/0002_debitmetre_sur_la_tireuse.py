"""
Range le modèle et le facteur du débitmètre sur la tireuse.
/ Stores the flow meter model and factor on the tap.

LOCALISATION : controlvanne/migrations/0002_debitmetre_sur_la_tireuse.py

1. Ajoute `flow_meter_model` et `flow_calibration_factor` sur TireuseBec.
2. Copie, pour chaque tireuse, le nom et le facteur de son ancien débitmètre.
   Une tireuse sans débitmètre garde les valeurs par défaut (modèle vide,
   facteur 6,5). Un débitmètre partagé donne ses valeurs à chacune de ses
   tireuses : rien ne change pour les volumes mesurés.

La migration 0003 supprime ensuite l'ancien lien et le modèle Debimetre. Elle
est à part : en Postgres, modifier des lignes puis la structure de la même
table dans une seule transaction peut échouer (« pending trigger events »).
/ 0003 then drops the old link and the Debimetre model, in its own migration:
updating rows then altering the same table in one transaction can fail.
"""

from django.db import migrations, models


def copier_le_debitmetre_sur_chaque_tireuse(apps, schema_editor):
    TireuseBec = apps.get_model("controlvanne", "TireuseBec")

    tireuses_avec_un_debitmetre = TireuseBec.objects.exclude(
        debimetre=None
    ).select_related("debimetre")

    for tireuse in tireuses_avec_un_debitmetre:
        tireuse.flow_meter_model = tireuse.debimetre.name
        tireuse.flow_calibration_factor = tireuse.debimetre.flow_calibration_factor
        tireuse.save(update_fields=["flow_meter_model", "flow_calibration_factor"])


class Migration(migrations.Migration):

    dependencies = [
        ("controlvanne", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tireusebec",
            name="flow_meter_model",
            field=models.CharField(
                blank=True,
                help_text="Flow meter model (e.g. YF-S201, FS300A)",
                max_length=100,
                verbose_name="Flow meter",
            ),
        ),
        migrations.AddField(
            model_name="tireusebec",
            name="flow_calibration_factor",
            field=models.FloatField(
                default=6.5,
                help_text="Calibration factor (Hz per L/min) — 1 L = factor × 60 pulses",
                verbose_name="Calibration factor",
            ),
        ),
        migrations.RunPython(
            copier_le_debitmetre_sur_chaque_tireuse,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

"""
Ajoute le « mode recharge » aux cartes primaires, et le donne aux caissiers qui
rechargent déjà.
/ Adds the "top-up mode" to primary cards, and grants it to cashiers who already top up.

LOCALISATION : laboutik/migrations/0003_carteprimaire_mode_recharge.py

Deux étapes, dans cet ordre / Two steps, in this order:
1. `AddField` : la case `CartePrimaire.mode_recharge`, fausse par défaut.
   / The `CartePrimaire.mode_recharge` box, false by default.
2. `donner_le_mode_recharge_aux_caissiers_cashless` : coche la case pour chaque carte
   primaire qui a au moins un point de vente de type Cashless (`comportement = "C"`).
   Ces caissiers rechargent aujourd'hui par le check carte. Sans cette étape, plus
   personne ne rechargerait le jour du déploiement.
   Les autres cartes restent sans le droit. Un gestionnaire peut cocher la case dans
   l'admin.
   / Ticks the box for every primary card with at least one Cashless point of sale.

laboutik est une application de lieu : la migration tourne dans chaque schéma de lieu.
Elle ne fait rien dans le schéma public (les tables n'y existent pas). La rejouer ne
change rien.
/ Tenant app: runs in every venue schema, does nothing in public, idempotent.

Spécification : TECH_DOC/SESSIONS/RECHARGE_CAISSE/SPEC.md (§2.2).
"""

from django.db import connection, migrations, models

# Le code du comportement « Cashless » d'un point de vente (`PointDeVente.CASHLESS`).
# / The "Cashless" behaviour code of a point of sale.
COMPORTEMENT_CASHLESS = "C"


def donner_le_mode_recharge_aux_caissiers_cashless(apps, schema_editor):
    """
    Coche le mode recharge des cartes primaires qui ont un point de vente Cashless.
    / Ticks top-up mode on primary cards that have a Cashless point of sale.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CartePrimaire = apps.get_model("laboutik", "CartePrimaire")
    CartePrimaire.objects.filter(
        points_de_vente__comportement=COMPORTEMENT_CASHLESS
    ).update(mode_recharge=True)


class Migration(migrations.Migration):
    dependencies = [
        ("laboutik", "0002_preparer_chaque_lieu"),
    ]

    operations = [
        migrations.AddField(
            model_name="carteprimaire",
            name="mode_recharge",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Autorise ce caissier à recharger les cartes cashless, depuis le "
                    "check carte et depuis les tuiles de recharge."
                ),
                verbose_name="Mode recharge",
            ),
        ),
        migrations.RunPython(
            donner_le_mode_recharge_aux_caissiers_cashless,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

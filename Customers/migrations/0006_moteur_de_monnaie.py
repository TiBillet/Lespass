"""
Ajoute le moteur de monnaie du lieu : `Client.moteur_monnaie` (legacy ou v2).
/ Adds the venue currency engine: `Client.moteur_monnaie` (legacy or v2).

LOCALISATION : Customers/migrations/0006_moteur_de_monnaie.py

Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §4.1.

Trois operations, dans cet ordre (l'ordre compte) :
1. le champ est ajoute avec le defaut `legacy` : tous les lieux qui existent avant le
   deploiement restent sur l'ancien Fedow ;
2. les emplacements vides du pool (`WAITING_CONFIG`) passent en `v2` : ils ont ete crees
   avant le deploiement, mais ils deviendront des lieux crees apres ;
3. le defaut devient `v2` : tout `Client` cree ensuite (pool, wizard, tests) est en `v2`.
/ Field added with default legacy, pool slots set to v2, then default switched to v2.

`Customers` est une app partagee : le routeur de django-tenants ne joue cette migration
que dans le schema public.
/ Shared app: django-tenants only runs this migration in the public schema.
"""

from django.db import migrations, models


def passer_en_v2_les_emplacements_en_attente(apps, schema_editor):
    """
    Passe en `v2` les `Client` de categorie `WAITING_CONFIG` (emplacements vides du pool,
    `onboard/tasks.py`). Le wizard les recategorise sans toucher au moteur.
    / Sets the WAITING_CONFIG Clients (empty pool slots) to v2.
    """
    Client = apps.get_model("Customers", "Client")

    nombre_d_emplacements_passes_en_v2 = Client.objects.filter(
        categorie="W",
    ).update(
        moteur_monnaie="v2",
    )

    if nombre_d_emplacements_passes_en_v2:
        print(
            f"  -> {nombre_d_emplacements_passes_en_v2} emplacement(s) du pool en moteur v2"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("Customers", "0005_libelles_fr_du_lieu"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="moteur_monnaie",
            field=models.CharField(
                choices=[("legacy", "Ancien Fedow"), ("v2", "Moteur V2")],
                default="legacy",
                max_length=6,
                verbose_name="Moteur de monnaie",
            ),
        ),
        migrations.RunPython(
            passer_en_v2_les_emplacements_en_attente,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="client",
            name="moteur_monnaie",
            field=models.CharField(
                choices=[("legacy", "Ancien Fedow"), ("v2", "Moteur V2")],
                default="v2",
                max_length=6,
                verbose_name="Moteur de monnaie",
            ),
        ),
    ]

"""
Ajoute Stock.suivi_actif : met le suivi du stock d'un produit en pause.
/ Adds Stock.suivi_actif: pauses stock tracking for a product.

Défaut True : les stocks existants restent suivis, aucune donnée à migrer.
/ Default True: existing stocks stay tracked, no data to migrate.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventaire", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="stock",
            name="suivi_actif",
            field=models.BooleanField(
                default=True,
                help_text="Décoché : les ventes ne décomptent plus ce stock. L'historique des mouvements est conservé.",
                verbose_name="Suivi actif",
            ),
        ),
    ]

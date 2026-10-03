# Aide du prix d'achat : en centimes, par unité de vente ; 0 = inconnu (chantier 05,
# fiche E-2, D21). Aucune donnée touchée.
# / Purchase price help text only. No data touched.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0231_product_consigne_remboursee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='prix_achat',
            field=models.IntegerField(default=0, help_text="Prix d'achat en centimes, par unité de vente (kg, litre, pièce) ; 0 = inconnu.", verbose_name='Purchase price (cents)'),
        ),
    ]

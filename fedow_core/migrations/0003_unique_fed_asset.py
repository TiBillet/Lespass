"""
Migration fedow_core.0003_unique_fed_asset.

LOCALISATION : fedow_core/migrations/0003_unique_fed_asset.py

UniqueConstraint partielle PostgreSQL garantissant qu'un seul Asset
de categorie 'FED' peut exister dans tout le systeme. Le FED est la
monnaie federee TiBillet unique, creee par bootstrap_fed_asset.

Toute tentative de creer un 2e Asset FED (ex: via l'admin Unfold ou
une commande de seed mal gardee) sera rejetee par PostgreSQL avec
IntegrityError.

/ Partial PostgreSQL UniqueConstraint ensuring only one Asset of
category 'FED' can exist. FED is the unique federated TiBillet
currency, created by bootstrap_fed_asset.

PREREQUIS : s'il existait deja plusieurs Assets FED en base (doublons
crees avant cette migration), la migration echouera avec IntegrityError.
Dans ce cas, dedupliquer manuellement via shell_plus AVANT de relancer :

    from fedow_core.models import Asset
    # Garder celui dont tenant_origin est 'federation_fed' (convention).
    canonique = Asset.objects.filter(
        category=Asset.FED,
        tenant_origin__schema_name='federation_fed',
    ).first()
    # Supprimer les autres (verifier Tokens/Transactions vides avant).
    Asset.objects.filter(category=Asset.FED).exclude(pk=canonique.pk).delete()

/ PREREQ: if duplicates exist, dedup manually via shell before running.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fedow_core', '0002_alter_transaction_action'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='asset',
            constraint=models.UniqueConstraint(
                condition=models.Q(('category', 'FED')),
                fields=('category',),
                name='unique_fed_asset',
            ),
        ),
    ]

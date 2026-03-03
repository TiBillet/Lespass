"""
Data migration : mettre amount=0 sur les LigneArticle dont le moyen de paiement est "Offert" (FREE / "NA").
"""
from django.db import connection, migrations


def fix_free_lignearticle_amount(apps, schema_editor):
    # BaseBillet est une TENANT_APP : la table n'existe pas dans le schema public
    if connection.schema_name == 'public':
        return

    LigneArticle = apps.get_model('BaseBillet', 'LigneArticle')
    updated = LigneArticle.objects.filter(
        payment_method="NA",
    ).exclude(
        amount=0,
    ).update(amount=0)
    if updated:
        print(f"  -> [{connection.schema_name}] {updated} LigneArticle(s) corrigée(s) : amount mis à 0 (paiement offert)")


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0197_alter_membership_contribution_value'),
    ]

    operations = [
        migrations.RunPython(
            fix_free_lignearticle_amount,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

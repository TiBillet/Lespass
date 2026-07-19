"""
Retire les champs remplaces par `affichage` et `sous_titre`.
/ Drops the fields replaced by `affichage` and `sous_titre`.

LOCALISATION : pages/migrations/0005_...

MIGRATION SEPAREE, ET C'EST OBLIGATOIRE : la 0004 fait des UPDATE et des
DELETE sur `pages_bloc` pour convertir les donnees. Postgres refuse ensuite
un ALTER TABLE sur la meme table dans la meme transaction :
    OperationalError: cannot ALTER TABLE "pages_bloc" because it has
    pending trigger events
Les suppressions de colonnes vivent donc dans leur propre transaction.
/ SEPARATE MIGRATION, ON PURPOSE: 0004 UPDATEs and DELETEs rows in
`pages_bloc`; Postgres then refuses an ALTER TABLE on that table in the same
transaction. Column drops need their own transaction.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0004_remove_bloc_affichage_image_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='bloc',
            name='affichage_image',
        ),
        migrations.RemoveField(
            model_name='bloc',
            name='image_position',
        ),
        migrations.RemoveField(
            model_name='bloc',
            name='repliable',
        ),
        migrations.RemoveField(
            model_name='bloc',
            name='surtitre',
        ),
    ]

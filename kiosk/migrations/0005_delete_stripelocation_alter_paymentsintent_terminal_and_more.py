"""
Deplacement des modeles Terminal et StripeLocation de kiosk vers laboutik.
/ Moves the Terminal and StripeLocation models from kiosk to laboutik.

Un TPE n'est pas reserve aux bornes libre-service : une caisse LaBoutik peut en avoir un.
Et surtout, le Terminal doit porter une cle etrangere vers laboutik.Printer.
Voir TECH_DOC/SESSIONS/IMPRESSION/SPEC.md.
"""

from django.db import connection, migrations, models
import django.db.models.deletion


def purger_les_payments_intent_orphelins(apps, schema_editor):
    """
    Vide la table PaymentsIntent avant de rebrancher sa cle etrangere.
    / Empties the PaymentsIntent table before repointing its foreign key.

    LOCALISATION : kiosk/migrations/0005_...

    INDISPENSABLE : les lignes existantes pointent vers l'ancienne table
    kiosk_terminal. La nouvelle contrainte vise laboutik_terminal, qui est vide.
    Sans cette purge, PostgreSQL refuse l'AlterField ci-dessous : violation de
    cle etrangere.

    C'est sans risque : un PaymentsIntent est une TRACE d'evenement Stripe, pas un
    credit. Le credit reel vit dans Fedow, pose par le webhook. Et LaBoutik V2 n'est
    deploye nulle part en production.
    """
    # Les tables de kiosk n'existent que dans les schemas tenant, jamais dans public.
    # / kiosk tables only exist in tenant schemas, never in public.
    if connection.schema_name == 'public':
        return

    PaymentsIntent = apps.get_model('kiosk', 'PaymentsIntent')

    nombre_de_traces_supprimees = PaymentsIntent.objects.all().delete()[0]
    if nombre_de_traces_supprimees:
        print(
            f"  -> [{connection.schema_name}] "
            f"{nombre_de_traces_supprimees} trace(s) PaymentsIntent purgee(s)"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0002_stripelocation_remove_pointdevente_printer_terminal'),
        ('kiosk', '0004_alter_terminal_options'),
    ]

    operations = [
        migrations.RunPython(
            purger_les_payments_intent_orphelins,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name='StripeLocation',
        ),
        migrations.AlterField(
            model_name='paymentsintent',
            name='terminal',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='laboutik.terminal', verbose_name='TPE'),
        ),
        migrations.DeleteModel(
            name='Terminal',
        ),
    ]

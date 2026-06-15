import datetime
from django.db import connection, migrations, models


def backfill_end_datetime(apps, schema_editor):
    """
    Calcule end_datetime pour toutes les réservations existantes.
    / Computes end_datetime for all existing bookings.

    end_datetime = start_datetime + slot_duration_minutes * slot_count.
    Ce champ est redondant mais nécessaire pour le filtrage SQL (finding §15).
    / Redundant but required for SQL filtering (finding §15).
    """
    # Ce modèle est une TENANT_APP — la table n'existe pas dans le schema public.
    # / This model is a TENANT_APP — the table does not exist in the public schema.
    if connection.schema_name == 'public':
        return

    Booking = apps.get_model('booking', 'Booking')

    nombre_de_reservations = 0
    for reservation in Booking.objects.all():
        reservation.end_datetime = reservation.start_datetime + datetime.timedelta(
            minutes=reservation.slot_duration_minutes * reservation.slot_count
        )
        reservation.save(update_fields=['end_datetime'])
        nombre_de_reservations += 1

    if nombre_de_reservations:
        print(f'  -> [{connection.schema_name}] {nombre_de_reservations} réservation(s) mise(s) à jour')


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0003_remove_tags_from_resource_and_resourcegroup'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='end_datetime',
            field=models.DateTimeField(editable=False, null=True, verbose_name='Slot end'),
        ),
        migrations.RunPython(
            backfill_end_datetime,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='booking',
            name='end_datetime',
            field=models.DateTimeField(editable=False, verbose_name='Slot end'),
        ),
    ]

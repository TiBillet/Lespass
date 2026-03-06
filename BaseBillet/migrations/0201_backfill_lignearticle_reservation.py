"""
Backfill : renseigne LigneArticle.reservation depuis paiement_stripe.reservation
pour les lignes existantes qui ont un paiement_stripe lie a une reservation.
/ Backfill: populates LigneArticle.reservation from paiement_stripe.reservation
for existing lines that have a paiement_stripe linked to a reservation.
"""
from django.db import migrations


def backfill_reservation_fk(apps, schema_editor):
    LigneArticle = apps.get_model('BaseBillet', 'LigneArticle')

    # Lignes avec paiement_stripe qui a une reservation, mais sans reservation directe
    # / Lines with paiement_stripe that has a reservation, but no direct reservation FK
    lignes_a_remplir = LigneArticle.objects.filter(
        reservation__isnull=True,
        paiement_stripe__reservation__isnull=False,
    ).select_related('paiement_stripe')

    total = 0
    for ligne in lignes_a_remplir.iterator(chunk_size=500):
        ligne.reservation = ligne.paiement_stripe.reservation
        ligne.save(update_fields=['reservation_id'])
        total += 1

    if total > 0:
        print(f"\n  Backfill: {total} LigneArticle(s) updated with reservation FK")


class Migration(migrations.Migration):

    dependencies = [
        ('BaseBillet', '0200_add_reservation_fk_to_lignearticle'),
    ]

    operations = [
        migrations.RunPython(
            backfill_reservation_fk,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

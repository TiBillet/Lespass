"""
Migration de données : supprime les doublons de SEOCache.
/ Data migration: removes duplicate SEOCache rows.

LOCALISATION : seo/migrations/0005_dedoublonner_seocache.py

Elle passe AVANT la migration suivante (0006), qui pose les contraintes d'unicité.
Sans ce nettoyage, la pose des contraintes échoue sur les données de production.
Données et schéma sont dans deux migrations séparées (tests/PIEGES.md 9.113).
/ It runs BEFORE the next migration (0006), which adds the unique constraints.
Without this cleanup, adding the constraints fails on production data.
Data and schema live in two separate migrations.

Code repris de l'ancienne `seo/0005_contraintes_uniques_seocache_et_dedoublonnage`.
/ Code taken from the former seo 0005 migration.
"""

from django.db import migrations, models


def supprimer_les_doublons_seocache(apps, schema_editor):
    """
    Supprime les doublons SEOCache avant de poser les contraintes uniques.
    / Removes duplicate SEOCache rows before adding the unique constraints.

    Pourquoi des doublons existent : unique_together ne protège pas les
    lignes tenant=None (PostgreSQL considère les NULL comme distincts), et
    deux reconstructions simultanées peuvent donc créer la même ligne d'agrégat.
    On garde la ligne la plus récente (updated_at) de chaque groupe : c'est
    du cache, il se recalcule tout seul.
    / Why duplicates exist: unique_together does not protect tenant=None rows
    (PostgreSQL treats NULLs as distinct), so concurrent rebuilds can create
    the same aggregate row. We keep the most recent row of each group: it is
    a cache, it rebuilds itself.
    """
    SEOCache = apps.get_model("seo", "SEOCache")

    groupes_en_double = (
        SEOCache.objects.values("cache_type", "tenant_id")
        .annotate(nombre=models.Count("id"))
        .filter(nombre__gt=1)
    )

    for groupe in groupes_en_double:
        lignes_du_groupe = SEOCache.objects.filter(
            cache_type=groupe["cache_type"],
            tenant_id=groupe["tenant_id"],
        ).order_by("-updated_at")

        ligne_a_garder = lignes_du_groupe.first()
        nombre_supprime = 0
        for ligne in lignes_du_groupe.exclude(pk=ligne_a_garder.pk):
            ligne.delete()
            nombre_supprime += 1

        if nombre_supprime:
            print(
                f"  -> SEOCache {groupe['cache_type']} "
                f"(tenant={groupe['tenant_id']}) : "
                f"{nombre_supprime} doublon(s) supprime(s)"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("seo", "0004_alter_seocache_cache_type"),
    ]

    operations = [
        migrations.RunPython(
            supprimer_les_doublons_seocache,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

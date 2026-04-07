"""
Management command pour lancer le rafraichissement du cache SEO.
/ Management command to run the SEO cache refresh.

Usage : python manage.py refresh_seo_cache

LOCALISATION: seo/management/commands/refresh_seo_cache.py
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rafraichit le cache SEO cross-tenant / Refresh cross-tenant SEO cache"

    def handle(self, *args, **options):
        from seo.tasks import refresh_seo_cache

        self.stdout.write(
            "Lancement du rafraichissement SEO... / Starting SEO refresh..."
        )
        result = refresh_seo_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Termine : {result['tenants']} tenants, "
                f"{result['events']} events, "
                f"{result['memberships']} memberships / Done"
            )
        )

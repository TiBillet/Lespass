from django.db import models
from django.utils.translation import gettext_lazy as _


class SEOCache(models.Model):
    """
    Cache SEO pre-calcule par le Celery task refresh_seo_cache.
    Vit dans le schema public (SHARED_APPS). Tous les tenants y accedent en lecture.
    / Pre-computed SEO cache populated by the refresh_seo_cache Celery task.
    Lives in the public schema (SHARED_APPS). All tenants read from it.

    LOCALISATION: seo/models.py

    Version V1 allegee : on ne porte que les lieux et les evenements.
    Les adhesions, initiatives crowdfunding et monnaies fedow_core
    sont volontairement exclues pour cette etape de migration.
    / V1 lightweight version: only venues and events are ported.
    Memberships, crowdfunding initiatives and fedow_core currencies
    are deliberately excluded for this migration step.
    """

    TENANT_SUMMARY = "tenant_summary"
    TENANT_EVENTS = "tenant_events"
    TENANT_POINTS = "tenant_points"
    AGGREGATE_EVENTS = "aggregate_events"
    AGGREGATE_LIEUX = "aggregate_lieux"
    AGGREGATE_POINTS = "aggregate_points"
    SITEMAP_INDEX = "sitemap_index"
    GLOBAL_COUNTS = "global_counts"
    FEDERATION_INCOMING = "federation_incoming"

    CACHE_TYPE_CHOICES = [
        (TENANT_SUMMARY, _("Tenant summary (config, stats, domain)")),
        (TENANT_EVENTS, _("Published events for tenant")),
        (TENANT_POINTS, _("Points (PA) for tenant")),
        (AGGREGATE_EVENTS, _("Aggregated events for network (ROOT)")),
        (AGGREGATE_LIEUX, _("Aggregated active venues (ROOT)")),
        (AGGREGATE_POINTS, _("Aggregated PostalAddress points for explorer map (ROOT)")),
        (SITEMAP_INDEX, _("Cross-tenant sitemap index (ROOT)")),
        (GLOBAL_COUNTS, _("Global counts: events, lieux (ROOT)")),
        (FEDERATION_INCOMING, _("Incoming FederatedPlace edges by target tenant")),
    ]

    cache_type = models.CharField(
        max_length=30,
        choices=CACHE_TYPE_CHOICES,
        db_index=True,
        verbose_name=_("Cache type"),
    )
    tenant = models.ForeignKey(
        "Customers.Client",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Tenant"),
        help_text=_("null for global aggregates (ROOT)"),
    )
    data = models.JSONField(
        default=dict,
        verbose_name=_("Cached data"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last updated"),
    )

    class Meta:
        # Deux contraintes uniques PARTIELLES au lieu d'un unique_together :
        # PostgreSQL 13 considere les NULL comme distincts dans un index unique,
        # donc unique_together ne protegeait PAS les agregats globaux (tenant=None).
        # Resultat : deux rebuilds concurrents (worker Celery + commande manuelle
        # refresh_seo_cache du flush) creaient des doublons, et tous les rebuilds
        # suivants crashaient en MultipleObjectsReturned.
        # / Two PARTIAL unique constraints instead of unique_together: PostgreSQL 13
        # treats NULLs as distinct in a unique index, so unique_together did NOT
        # protect global aggregate rows (tenant=None). Concurrent rebuilds created
        # duplicates and every later rebuild crashed with MultipleObjectsReturned.
        constraints = [
            models.UniqueConstraint(
                fields=["cache_type", "tenant"],
                condition=models.Q(tenant__isnull=False),
                name="seo_cache_unique_type_par_tenant",
            ),
            models.UniqueConstraint(
                fields=["cache_type"],
                condition=models.Q(tenant__isnull=True),
                name="seo_cache_unique_type_global",
            ),
        ]
        verbose_name = _("SEO Cache")
        verbose_name_plural = _("SEO Cache entries")

    def __str__(self):
        tenant_name = self.tenant.name if self.tenant else "global"
        return f"{self.cache_type} — {tenant_name}"

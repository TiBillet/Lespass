from django.db import models
from django.utils.translation import gettext_lazy as _


class SEOCache(models.Model):
    """
    Cache SEO pre-calcule par le Celery task refresh_seo_cache.
    Vit dans le schema public (SHARED_APPS). Tous les tenants y accedent en lecture.
    / Pre-computed SEO cache populated by the refresh_seo_cache Celery task.
    Lives in the public schema (SHARED_APPS). All tenants read from it.

    LOCALISATION: seo/models.py
    """

    TENANT_SUMMARY = "tenant_summary"
    TENANT_EVENTS = "tenant_events"
    TENANT_MEMBERSHIPS = "tenant_memberships"
    AGGREGATE_EVENTS = "aggregate_events"
    AGGREGATE_MEMBERSHIPS = "aggregate_memberships"
    AGGREGATE_LIEUX = "aggregate_lieux"
    SITEMAP_INDEX = "sitemap_index"

    CACHE_TYPE_CHOICES = [
        (TENANT_SUMMARY, _("Tenant summary (config, stats, domain)")),
        (TENANT_EVENTS, _("Published events for tenant")),
        (TENANT_MEMBERSHIPS, _("Published memberships for tenant")),
        (AGGREGATE_EVENTS, _("Aggregated events for network (ROOT)")),
        (AGGREGATE_MEMBERSHIPS, _("Aggregated memberships for network (ROOT)")),
        (AGGREGATE_LIEUX, _("Aggregated active venues (ROOT)")),
        (SITEMAP_INDEX, _("Cross-tenant sitemap index (ROOT)")),
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
        unique_together = [("cache_type", "tenant")]
        verbose_name = _("SEO Cache")
        verbose_name_plural = _("SEO Cache entries")

    def __str__(self):
        tenant_name = self.tenant.name if self.tenant else "global"
        return f"{self.cache_type} — {tenant_name}"

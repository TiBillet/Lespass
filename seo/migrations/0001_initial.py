# Generated migration for seo app — V1 lightweight (lieux + events only).
# / Migration generee pour l'app seo — V1 allegee (lieux + events uniquement).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        # On depend du modele Client de Customers (FK seo.SEOCache.tenant)
        # / Depends on Customers.Client (FK seo.SEOCache.tenant)
        ("Customers", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SEOCache",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "cache_type",
                    models.CharField(
                        choices=[
                            ("tenant_summary", "Tenant summary (config, stats, domain)"),
                            ("tenant_events", "Published events for tenant"),
                            ("aggregate_events", "Aggregated events for network (ROOT)"),
                            ("aggregate_lieux", "Aggregated active venues (ROOT)"),
                            ("sitemap_index", "Cross-tenant sitemap index (ROOT)"),
                            ("global_counts", "Global counts: events, lieux (ROOT)"),
                        ],
                        db_index=True,
                        max_length=30,
                        verbose_name="Cache type",
                    ),
                ),
                ("data", models.JSONField(default=dict, verbose_name="Cached data")),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Last updated"),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        help_text="null for global aggregates (ROOT)",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Customers.client",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "SEO Cache",
                "verbose_name_plural": "SEO Cache entries",
                "unique_together": {("cache_type", "tenant")},
            },
        ),
    ]

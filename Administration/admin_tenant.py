"""
Orchestrateur admin — ne contient plus de logique.
Chaque sous-module déclare ses propres @admin.register() et importe staff_admin_site depuis Administration.admin.site.
Ce fichier importe les sous-modules pour déclencher les enregistrements Django admin.
"""

from Administration.admin.site import staff_admin_site, sanitize_textfields  # noqa: F401
from Administration.admin.dashboard import (  # noqa: F401
    dashboard_callback, environment_callback, get_sidebar_navigation,
    MODULE_FIELDS, _build_modules_context, adhesion_badge_callback,
)
from Administration.admin import (  # noqa: F401
    configuration, tags, products, prices, laboutik, users,
    membership, sales, events, reservations, settings_apps, fedow, crowds,
    inventaire,
)

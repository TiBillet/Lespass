"""
Les routes du panneau Newsletter.
/ The Newsletter panel's routes.

LOCALISATION : newsletter/urls.py

Branchees sur `/newsletter/` dans TiBillet/urls_tenants.py.

Ces routes ne sont PAS publiques : le ViewSet est protege par `TenantAdminPermission`.
Elles sont appelees en hx-post/hx-get depuis le panneau de l'admin
(Administration/templates/admin/ghost/panneau_newsletter.html).
/ These routes are NOT public: the ViewSet is guarded by `TenantAdminPermission`. They are
called with hx-post/hx-get from the admin panel.

Routes finales :
    GET  /newsletter/admin/tester-connexion/
    POST /newsletter/admin/brouillon/<jours>/
"""

from rest_framework import routers

from newsletter.views import NewsletterAdminViewSet

router = routers.DefaultRouter()
router.register(r"admin", NewsletterAdminViewSet, basename="newsletter-admin")

urlpatterns = router.urls

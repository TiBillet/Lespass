from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include, re_path

from Administration.admin_tenant import staff_admin_site
# on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
from ApiBillet.views import Webhook_stripe
from BaseBillet.sitemap import EventSitemap, ProductSitemap, StaticViewSitemap

urlpatterns = [
    # path('jet/', include('jet.urls', 'jet')),  # Django JET URLS
    # re_path(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    path('admin/', staff_admin_site.urls, name="staff_admin_site"),

    # Sitemap
    # Access the complete sitemap at: https://yourdomain.com/sitemap.xml
    # Access specific sections:
    # - Events sitemap: https://yourdomain.com/sitemap.xml?section=events
    # - Products sitemap: https://yourdomain.com/sitemap.xml?section=products
    # - Static pages sitemap: https://yourdomain.com/sitemap.xml?section=static
    path('sitemap.xml', sitemap, {'sitemaps': {
        'events': EventSitemap,
        'products': ProductSitemap,
        'static': StaticViewSitemap,
    }, 'template_name': 'sitemaps/sitemap.xml'}, name='django.contrib.sitemaps.views.sitemap'),

    re_path(r'api/user/', include('AuthBillet.urls')),

    path('api/webhook_stripe/', Webhook_stripe.as_view()),


    # New semantic API v2
    re_path(r'api/v2/', include('api_v2.urls')),

    re_path(r'api/', include('ApiBillet.urls')),
    # re_path(r'qr/', include('QrcodeCashless.urls')),
    re_path(r'rss/', include('tibrss.urls')),
    re_path(r'logout/', include('tibrss.urls')),
    re_path(r'chat/', include('wsocket.urls')),

    # fwh : fedow Webhook
    re_path(r'fwh/', include('fedow_connect.urls')),
    re_path(r'fedow/', include('fedow_public.urls')),
    re_path(r'crowd/', include('crowds.urls')),

    # pour carte GEN1 Bisik
    # re_path(r'(?P<numero_carte>^[qsdf974]{5}$)', include('QrcodeCashless.urls')),

    path('', include('BaseBillet.urls')),

    # path('admin/', admin.site.urls, name="public_admin_url"),
]

if settings.DEBUG:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls")),]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Register custom error handlers
handler500 = 'BaseBillet.views.handler500'

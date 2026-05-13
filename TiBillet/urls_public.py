from django.conf.urls.static import static
from django.urls import path, include, re_path
from ApiBillet.views import Webhook_stripe
from django.conf import settings

urlpatterns = [

    # path('admin/', root_admin_site.urls, name="root_admin_site"),

    path('api/webhook_stripe/', Webhook_stripe.as_view()),
    path('api/discovery/', include('discovery.urls')),

    re_path(r'api/user/', include('AuthBillet.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    # Landing page ROOT : app seo (cf. TECH DOC/SESSIONS/M-To-V2/02-app-seo.md)
    # Remplace la redirection MetaBillet vers tibillet.org par une vraie home.
    # / ROOT landing page: seo app. Replaces MetaBillet redirect to tibillet.org.
    path('', include('seo.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG and not settings.TEST :
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls")), ]

from django.conf.urls.static import static
from django.urls import path, include, re_path
# from Administration.admin_root import root_admin_site
from ApiBillet.views import Webhook_stripe
from TiBillet import settings

urlpatterns = [

    # path('admin/', root_admin_site.urls, name="root_admin_site"),

    path('api/webhook_stripe/', Webhook_stripe.as_view()),

    re_path(r'api/user/', include('AuthBillet.urls')),
    path('', include('MetaBillet.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls")), ]

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

    # Wizard d'onboarding nouveau tenant (SHARED : accessible aussi sur tenants).
    # / Onboarding wizard for new tenants (SHARED: also reachable on tenants).
    path('', include('onboard.urls')),

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

# Register custom error handlers
# handler404 : page 404 skin-aware + HTMX-aware (actif quand DEBUG=0).
# Sans ces handlers sur le tenant public, Django rend 404.html/500.html avec
# les vues par defaut, qui n'injectent PAS base_template : {% extends base_template %}
# recoit '' -> TemplateSyntaxError, qui declenche 500.html -> re-crash en boucle.
# / handler404: skin-aware + HTMX-aware 404 page (active when DEBUG=0).
# Without these handlers on the public tenant, Django's default error views render
# 404.html/500.html without base_template -> TemplateSyntaxError -> 500 -> loop.
handler404 = 'BaseBillet.views.handler404'
handler500 = 'BaseBillet.views.handler500'

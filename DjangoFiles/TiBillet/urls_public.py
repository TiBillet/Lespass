from django.conf.urls.static import static
from django.urls import path, include, re_path

from Administration.admin_public import public_admin_site
# on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
# from AuthBillet.views import TokenCreateView_custom
from ApiBillet.views import Webhook_stripe
from TiBillet import settings

urlpatterns = [
    # path('jet/', include('jet.urls', 'jet')),  # Django JET URLS
    # re_path(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    # on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
    # re_path(r"^auth/token/login/?$", TokenCreateView_custom.as_view(), name="login"),
    # re_path(r'^auth/', include('djoser.urls')),

    path('admin/', public_admin_site.urls, name="public_admin_url"),
    path('api/webhook_stripe/', Webhook_stripe.as_view()),
    # re_path(r'^api/user/terminal/(?P<token>[0-9]{6})/$', validate_token_terminal.as_view(), name='validate_token_terminal'),
    # path('api/user/terminal/', create_terminal_user.as_view(), name='create_terminal_user'),
    re_path(r'api/user/', include('AuthBillet.urls')),
    path('', include('MetaBillet.urls')),
]

if settings.DEBUG is True:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += path("__reload__/", include("django_browser_reload.urls")),

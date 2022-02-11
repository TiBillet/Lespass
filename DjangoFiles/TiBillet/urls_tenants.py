"""TiBillet URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings
from Administration.admin_tenant import staff_admin_site

# on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
from ApiBillet.views import Webhook_stripe
from AuthBillet.views import TokenCreateView_custom

urlpatterns = [
    # path('jet/', include('jet.urls', 'jet')),  # Django JET URLS
    # re_path(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    # path('admin/', staff_admin_site.urls, name="staff_admin_site"),
    re_path(r'^admin\/{0,}', staff_admin_site.urls, name="staff_admin_site"),

    # on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
    # re_path(r"^auth/token/login/?$", TokenCreateView_custom.as_view(), name="login"),

    # re_path(r'^auth/', include('djoser.urls')),
    # re_path(r'^auth/', include('djoser.urls.authtoken')),
    # re_path(r'^auth/', include('djoser.urls.jwt')),

    # re_path(r'^user/', include('AuthBillet.urls')),

    re_path(r'api/user/', include('AuthBillet.urls')),
    re_path(r'api/', include('ApiBillet.urls')),
    re_path(r'qr/', include('QrcodeCashless.urls')),
    # pour carte GEN1 Bisik
    re_path(r'(?P<numero_carte>^\w{5}$)', include('QrcodeCashless.urls')),

    # catché par le front node JS, a supprimer prochainement
    path('stripe/return/<uuid:uuid_paiement>', Webhook_stripe.as_view()),

    path('', include('BaseBillet.urls')),

    # path('admin/', admin.site.urls, name="public_admin_url"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

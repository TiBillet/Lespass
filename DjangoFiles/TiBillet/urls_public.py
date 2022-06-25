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
from Administration.admin_public import public_admin_site
# on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
# from AuthBillet.views import TokenCreateView_custom
from ApiBillet.views import Webhook_stripe
from AuthBillet.views import create_terminal_user, validate_token_terminal

urlpatterns = [
    # path('jet/', include('jet.urls', 'jet')),  # Django JET URLS
    # re_path(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    # on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
    # re_path(r"^auth/token/login/?$", TokenCreateView_custom.as_view(), name="login"),
    # re_path(r'^auth/', include('djoser.urls')),

    path('admin/', public_admin_site.urls, name="public_admin_url"),
    path('api/webhook_stripe/', Webhook_stripe.as_view()),
    re_path(r'^api/user/terminal/(?P<token>[0-9]{6})/$', validate_token_terminal.as_view(), name='validate_token_terminal'),
    path('api/user/terminal/', create_terminal_user.as_view(), name='create_terminal_user'),
    re_path(r'api/user/', include('AuthBillet.urls')),

    path('', include('MetaBillet.urls')),
    # path('admin/', admin.site.urls, name="public_admin_url"),
]

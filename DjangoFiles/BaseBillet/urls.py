from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>/', base_view.Ticket_html_view.as_view()),
    path('event/<slug:slug>/', base_view.event, name='event'),

    path('membership_form/<uuid:uuid>/', base_view.membership_form.as_view(), name='membership_form'),

    path('create_product/', base_view.create_product, name='create_product'),
    path('home/', base_view.home, name='home'),
    path("memberships/", base_view.memberships, name='memberships'),
    path('test_jinja/', base_view.test_jinja, name='test_jinja'),
    path('connexion/', base_view.connexion, name='connexion'),
    path('deconnexion/', base_view.deconnexion, name='deconnexion'),
    path('emailconfirmation/<str:uuid>/<str:token>/',base_view.emailconfirmation, name='emailconfirmation'),

    path('', base_view.home, name="index"),
]
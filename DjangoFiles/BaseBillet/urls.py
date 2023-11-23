from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>/', base_view.Ticket_html_view.as_view()),
    path('mvt/event/<slug:slug>/', base_view.event, name='event'),

    path('mvt/membership_form/<uuid:uuid>/', base_view.membership_form.as_view(), name='membership_form'),

    path('mvt/create_product/', base_view.create_product, name='create_product'),
    path('mvt/home/', base_view.home, name='home'),
    path("mvt/memberships/", base_view.memberships, name='memberships'),
    path('mvt/test_jinja/', base_view.test_jinja, name='test_jinja'),
    path('mvt/login/', base_view.login, name='login'),
    path('mvt/emailconfirmation/<str:uuid>/<str:token>/',base_view.emailconfirmation, name='emailconfirmation'),

    path('', base_view.index.as_view(), name="index"),
]
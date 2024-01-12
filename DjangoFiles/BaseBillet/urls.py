from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>/', base_view.Ticket_html_view.as_view()),
    path('event/<slug:slug>/', base_view.event, name='event'),

    # path('membership_form/<uuid:uuid>/', base_view.membership_form.as_view(), name='membership_form'),

    path("validate_event/", base_view.validate_event, name='validate_event'),
    path('create_event/', base_view.create_event, name='create_event'),
    path('wiz_event/date/', base_view.event_date, name='event_date'),
    path('wiz_event/presentation/', base_view.event_presentation, name='event_presentation'),
    path('wiz_event/products/', base_view.event_products, name='event_products'),
    path('home/', base_view.home, name='home'),
    path("memberships/", base_view.memberships, name='memberships'),
    path("validate_membership/", base_view.validate_membership, name='validate_membership'),
    path("create_tenant/", base_view.create_tenant, name='create_tenant'),
    path("tenant/areas/", base_view.tenant_areas, name='tenant_areas'),
    path("tenant/informations/", base_view.tenant_informations, name='tenant_informations'),
    path("tenant/summary/", base_view.tenant_summary, name='tenant_summary'),
    path('test_jinja/', base_view.test_jinja, name='test_jinja'),
    path('connexion/', base_view.connexion, name='connexion'),
    path('deconnexion/', base_view.deconnexion, name='deconnexion'),
    path('emailconfirmation/<str:uuid>/<str:token>/',base_view.emailconfirmation, name='emailconfirmation'),

    path('', base_view.home, name="index"),
]
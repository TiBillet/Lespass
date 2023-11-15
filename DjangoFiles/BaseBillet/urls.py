from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>', base_view.Ticket_html_view.as_view()),
    path('event/<slug:slug>/', base_view.event.as_view(), name='show_event'),

    path('mvt/create_products/', base_view.create_products, name='create_products'),
    path('mvt/test_jinja/', base_view.test_jinja, name='test_jinja'),

    path('', base_view.index.as_view(), name="index"),
]
from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>', base_view.Ticket_html_view.as_view()),
    path('event/<slug:slug>/', base_view.event.as_view(), name='show_event'),

    path('mvt/create_product/', base_view.create_product, name='create_product'),
    path('mvt/accueil/', base_view.accueil, name='accueil'),
    path('mvt/test_jinja/', base_view.test_jinja, name='test_jinja'),

    path('', base_view.index.as_view(), name="index"),
]
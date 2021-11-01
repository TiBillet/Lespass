from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('ticket/<uuid:pk_uuid>', base_view.Ticket_html_view.as_view()),
    path('', base_view.index.as_view(), name="index"),
]
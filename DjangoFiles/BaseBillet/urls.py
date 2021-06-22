from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('event/<str:id>', base_view.event.as_view()),
    path('', base_view.index.as_view(), name="index"),
]
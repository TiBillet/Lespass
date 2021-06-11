from django.urls import include, path, re_path

from BaseBillet import views as base_view

urlpatterns = [
    path('', base_view.index.as_view(), name="index"),
]
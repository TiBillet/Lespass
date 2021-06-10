from django.urls import include, path, re_path

from MetaBillet import views as meta_view

urlpatterns = [
    path('', meta_view.index.as_view(), name="index"),
]
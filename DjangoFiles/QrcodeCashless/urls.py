from django.urls import include, path, re_path

from .views import index_scan

urlpatterns = [
    path('<uuid:uuid>', index_scan.as_view()),
]
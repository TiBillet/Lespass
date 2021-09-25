from django.urls import include, path, re_path

from .views import index_scan, gen_one_bisik

urlpatterns = [
    path('<uuid:uuid>', index_scan.as_view()),
    path('', gen_one_bisik.as_view())
]
from django.urls import include, path, re_path

from AuthBillet import views as auth_view

urlpatterns = [
    re_path('activate/<str:uid>/<str:token>', auth_view.activate.as_view()),
]
from django.urls import include, path, re_path

from .views import retour_stripe

urlpatterns = [
    path('return/<uuid:uuid>', retour_stripe.as_view()),
    path('webhook_stripe', retour_stripe.as_view()),
]
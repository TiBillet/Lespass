from django.urls import path, include
from rest_framework import routers

from fedow_connect import views

router = routers.DefaultRouter()
router.register(r'membership', views.Membership_fwh, basename='membership_from_fedow_webhook')


urlpatterns = [
    # path('', base_view.home, name="index"),
]

urlpatterns += router.urls

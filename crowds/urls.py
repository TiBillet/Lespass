# crowd/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InitiativeViewSet

router = DefaultRouter()
router.register(r"", InitiativeViewSet, basename="crowds")

urlpatterns = [
    # path('', base_view.home, name="index"),
]

urlpatterns += router.urls

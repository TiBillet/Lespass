# crowd/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InitiativeViewSet, GlobalFundingViewset

router = DefaultRouter()
router.register(r"", InitiativeViewSet, basename="crowds")
router.register(r"global-funding", GlobalFundingViewset, basename="crowds-global-funding")

urlpatterns = router.urls

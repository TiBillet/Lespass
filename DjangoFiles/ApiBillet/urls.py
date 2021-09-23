from django.urls import include, path, re_path

# from BaseBillet import views as base_view
from ApiBillet import views as api_view
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'events', api_view.EventViewSet)


urlpatterns = [
    path('', include(router.urls)),
]
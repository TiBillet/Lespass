from django.urls import include, path, re_path

# from BaseBillet import views as base_view
from ApiBillet import views as api_view
from rest_framework import routers

from ApiBillet.views import TicketPdf

router = routers.DefaultRouter()
router.register(r'events', api_view.EventsViewSet, basename='event')
router.register(r'products', api_view.ProductViewSet, basename='product')
router.register(r'prices', api_view.TarifBilletViewSet, basename='price')
router.register(r'reservations', api_view.ReservationViewset, basename='reservation')


urlpatterns = [
    path('', include(router.urls)),
    path('ticket/<uuid:pk_uuid>', TicketPdf.as_view(), name='ticket_uuid'),

]
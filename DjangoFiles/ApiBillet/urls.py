from django.urls import include, path, re_path
from ApiBillet import views as api_view
from rest_framework import routers
from ApiBillet.views import TicketPdf, Webhook_stripe
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

router = routers.DefaultRouter()
router.register(r'place', api_view.PlacesViewSet, basename='place')
router.register(r'artist', api_view.ArtistViewSet, basename='artist')
router.register(r'here', api_view.HereViewSet, basename='here')
router.register(r'events', api_view.EventsViewSet, basename='event')
router.register(r'products', api_view.ProductViewSet, basename='product')
router.register(r'prices', api_view.TarifBilletViewSet, basename='price')
router.register(r'reservations', api_view.ReservationViewset, basename='reservation')
router.register(r'membership', api_view.MembershipViewset, basename='membership')
router.register(r'me', api_view.MeViewset, basename='me')

urlpatterns = [
    path('', include(router.urls)),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # download ticket :
    path('ticket/pdf/<uuid:pk_uuid>', TicketPdf.as_view(), name='ticket_uuid_to_pdf'),
    path('webhook_stripe/', Webhook_stripe.as_view()),
    path('webhook_stripe/<uuid:uuid_paiement>', Webhook_stripe.as_view()),
]

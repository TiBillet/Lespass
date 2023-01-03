from django.urls import include, path, re_path
from ApiBillet import views as api_view
from rest_framework import routers
from ApiBillet.views import TicketPdf, Webhook_stripe, Gauge, Cancel_sub, Onboard_stripe_return, Onboard, UpdateFederatedAsset

router = routers.DefaultRouter()
router.register(r'place', api_view.TenantViewSet, basename='place')
router.register(r'artist', api_view.TenantViewSet, basename='artist')
router.register(r'here', api_view.HereViewSet, basename='here')
router.register(r'events', api_view.EventsViewSet, basename='event')
router.register(r'eventslug', api_view.EventsSlugViewSet, basename='eventslug')
router.register(r'products', api_view.ProductViewSet, basename='product')
router.register(r'prices', api_view.TarifBilletViewSet, basename='price')
router.register(r'reservations', api_view.ReservationViewset, basename='reservation')
router.register(r'membership', api_view.MembershipViewset, basename='membership')
router.register(r'optionticket', api_view.OptionTicket, basename='optionticket')
router.register(r'chargecashless', api_view.ChargeCashless, basename='chargecashless')
router.register(r'ticket', api_view.TicketViewset, basename='ticket')
router.register(r'detailCashlessCard', api_view.DetailCashlessCards, basename='detailCashlessCard')
router.register(r'loadCardsFromDict', api_view.Loadcardsfromdict, basename='loadCardsFromDict')


urlpatterns = [
    path('', include(router.urls)),
    # download ticket :
    path('ticket/pdf/<uuid:pk_uuid>', TicketPdf.as_view(), name='ticket_uuid_to_pdf'),
    path('update_federated_asset/', UpdateFederatedAsset.as_view(), name='update_federated_asset'),
    path('onboard/', Onboard.as_view()),
    path('onboard_stripe_return/<str:id_acc_connect>/', Onboard_stripe_return.as_view()),
    path('webhook_stripe/', Webhook_stripe.as_view()),
    path('webhook_stripe/<uuid:uuid_paiement>/', Webhook_stripe.as_view()),
    path('gauge/', Gauge.as_view()),
    path('cancel_sub/', Cancel_sub.as_view()),
    # path('LoadCardsFromCsv/', LoadCardsFromCsv.as_view()),
    # path('LoadCardsFromDict/', LoadCardsFromD.as_view()),
]

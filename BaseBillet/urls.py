from django.urls import path
from rest_framework import routers
from BaseBillet import views as base_view

router = routers.DefaultRouter()
router.register(r'memberships', base_view.MembershipMVT, basename='membership_mvt')
router.register(r'badge', base_view.Badge, basename='badge')
router.register(r'tenant', base_view.Tenant, basename='tenant')

router.register(r'my_account', base_view.MyAccount, basename='my_account')
router.register(r'qr', base_view.ScanQrCode, basename='scan_qrcode')
router.register(r'event', base_view.EventMVT, basename='event')


urlpatterns = [

    path('ticket/<uuid:pk_uuid>/', base_view.Ticket_html_view.as_view()),
    # path('event/<slug:slug>/', base_view.event, name='event'),

    # path("validate_event/", base_view.validate_event, name='validate_event'),
    # path('create_event/', base_view.create_event, name='create_event'),
    # path('wiz_event/date/', base_view.event_date, name='event_date'),
    # path('wiz_event/presentation/', base_view.event_presentation, name='event_presentation'),
    # path('wiz_event/products/', base_view.event_products, name='event_products'),
    # path('home/', base_view.index, name='home'),
    # path('agenda/', base_view.agenda, name='agenda'),

    # path("my_account/", base_view.my_account, name='my_account'),
    # path("my_account/wallet/", base_view.my_account_wallet, name='my_account_wallet'),
    # path("my_account/membership/", base_view.my_account_membership, name='my_account_membership'),
    # path("my_account/profile/", base_view.my_account_profile, name='my_account_profile'),

    path('connexion/', base_view.connexion, name='connexion'),
    path('deconnexion/', base_view.deconnexion, name='deconnexion'),
    path('emailconfirmation/<str:token>', base_view.emailconfirmation, name='emailconfirmation'),

    ##### TEST NICO
    # path("create_tenant/", base_view.create_tenant, name='create_tenant'),
    # path("tenant/areas/", base_view.tenant_areas, name='tenant_areas'),
    # path("tenant/informations/", base_view.tenant_informations, name='tenant_informations'),
    # path("tenant/summary/", base_view.tenant_summary, name='tenant_summary'),
    # path('test_jinja/', base_view.test_jinja, name='test_jinja'),

    path('', base_view.index, name="index"),
]

urlpatterns += router.urls

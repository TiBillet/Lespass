from django.templatetags.static import static
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers
from BaseBillet import views as base_view
from BaseBillet.views_robots import robots_txt
from BaseBillet.views_humans import humans_txt
from BaseBillet.test_error_views import test_404, test_500
import BaseBillet.views_scan as views_scan

router = routers.DefaultRouter()
router.register(r'memberships', base_view.MembershipMVT, basename='membership_mvt')
router.register(r'badge', base_view.Badge, basename='badge')
# NOTE 2026-05-16 : `Tenant` ViewSet supprime. Le flow legacy `/tenant/new/`
# est remplace par l'app `onboard/` (wizard multi-step). Les 2 actions
# Stripe `_from_config` ont ete migrees dans `PaiementStripe/`. Cf.
# `TECH_DOC/SESSIONS/ONBOARD/` et `TECH_DOC/SESSIONS/MOYENS_PAIEMENT/`.
# / `Tenant` ViewSet removed. Legacy `/tenant/new/` replaced by `onboard/`.
# Stripe `_from_config` actions moved to `PaiementStripe/`.
router.register(r'federation', base_view.FederationViewset, basename='federation')

router.register(r'my_account', base_view.MyAccount, basename='my_account')
router.register(r'qrcodescanpay', base_view.QrCodeScanPay, basename='qrcodescanpay')
router.register(r'qr', base_view.ScanQrCode, basename='scan_qrcode')
router.register(r'event', base_view.EventMVT, basename='event')
router.register(r'home', base_view.HomeViewset, basename='home')
router.register(r'login', base_view.TiBilletLogin, basename='login-viewset')
router.register(r'specialadminaction', base_view.SpecialAdminAction, basename='specialadminaction')
urlpatterns = [
    # Dynamic robots.txt - Access at: https://yourdomain.com/robots.txt
    # This automatically includes a reference to the sitemap at: https://yourdomain.com/sitemap.xml
    path('robots.txt', robots_txt, name='robots_txt'),

    # Dynamic humans.txt - Access at: https://yourdomain.com/humans.txt
    # Standard humanstxt.org : credits the Cooperative Code Commun team
    path('humans.txt', humans_txt, name='humans_txt'),

    # /favicon.ico est demande automatiquement par les navigateurs sur toutes
    # les pages, y compris non-HTML (sitemap.xml, robots.txt). On evite le 404
    # en redirigeant vers le favicon du skin reunion (PNG).
    # / Browsers auto-request /favicon.ico on all pages including non-HTML.
    # Redirect to the reunion skin favicon (PNG) to avoid 404s.
    path(
        'favicon.ico',
        RedirectView.as_view(url=static('reunion/img/favicon.png'), permanent=True),
        name='favicon_ico',
    ),

    ### SCAN TICKET API
    path('scan/check_api_scan/', views_scan.check_api_scan.as_view(), name='check_api_scan'),
    path('scan/check_allow_any/', views_scan.check_allow_any.as_view(), name='check_allow_any'),
    path('scan/check_allow_any_widlcard/', views_scan.check_allow_any_widlcard.as_view(),
         name='check_allow_any_widlcard'),
    path('scan/<str:pk>/pair/', views_scan.Pair.as_view(), name='check_api_scan'),
    path('scan/check_ticket/', views_scan.check_ticket.as_view(), name='check_ticket'),
    path('scan/ticket/', views_scan.ticket.as_view(), name='ticket'),
    path('scan/search_ticket/', views_scan.search_ticket.as_view(), name='search_ticket'),
    path('scan/list_tickets/', views_scan.list_tickets.as_view(), name='list_tickets'),

    # Test routes for error templates

    ### END SCAN TICKET API

    path('test-errors/404/', test_404, name='test_404'),
    path('test-errors/500/', test_500, name='test_500'),

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
    path('infos-pratiques/', base_view.infos_pratiques, name='infos_pratiques'),
    path('le-faire-festival/', base_view.le_faire_festival, name='le_faire_festival'),

    ##### TEST NICO
    # path("create_tenant/", base_view.create_tenant, name='create_tenant'),
    # path("tenant/areas/", base_view.tenant_areas, name='tenant_areas'),
    # path("tenant/informations/", base_view.tenant_informations, name='tenant_informations'),
    # path("tenant/summary/", base_view.tenant_summary, name='tenant_summary'),
    # path('test_jinja/', base_view.test_jinja, name='test_jinja'),
    path('', base_view.index, name="index"),
]

urlpatterns += router.urls

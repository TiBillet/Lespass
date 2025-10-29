# parent: TiBillet/urls_tenants.py

from django.urls import path
from laboutik import views

urlpatterns=[
	path('login_hardware',views.login_hardware),
	path('new_hardware',views.new_hardware),
	path('ask_primary_card',views.ask_primary_card),
	path('hx_read_nfc',views.hx_read_nfc),
	path('pv_route',views.pv_route),
	path('hx_display_type_payment',views.hx_display_type_payment),
	path('hx_confirm_payment',views.hx_confirm_payment),
	path('hx_payment',views.hx_payment),
	path('check_card',views.check_card)
]

# parent: TiBillet/urls_tenants.py

from django.urls import path
from laboutik import views

urlpatterns=[
	path('login_hardware',views.login_hardware),
	path('new_hardware',views.new_hardware),
	path('ask_primary_card',views.ask_primary_card),
	path('read_nfc',views.read_nfc),
	path('pv_route',views.pv_route),
	path('display_type_payment',views.display_type_payment),
	path('confirm_payment',views.confirm_payment),
	path('payment',views.payment),
	path('check_card',views.check_card)
]

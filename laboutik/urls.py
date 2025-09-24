# parent: TiBillet/urls_tenants.py

from django.urls import path
from laboutik import views

urlpatterns=[
	path('login_hardware',views.login_hardware),
	path('new_hardware',views.new_hardware),
	path('ask_primary_card',views.ask_primary_card),
	path('pv_route',views.pv_route),
	path('main_menu',views.main_menu),
	path('pvs_menu',views.pvs_menu),
	path('show_pv',views.show_pv)
]

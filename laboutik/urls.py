# parent: TiBillet/urls_tenants.py

from django.urls import path
from laboutik import views
urlpatterns=[
	path('login_hardware',views.login_hardware)
]

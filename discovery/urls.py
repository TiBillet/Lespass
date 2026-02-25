from django.urls import path

from discovery.views import ClaimPinView

urlpatterns = [
    path('claim/', ClaimPinView.as_view(), name='discovery-claim'),
]

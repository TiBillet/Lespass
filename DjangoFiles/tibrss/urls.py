from django.urls import path
from tibrss.views import LatestEntriesEvent

urlpatterns = [
    # ...
    path('latest/feed/', LatestEntriesEvent()),
    # ...
]

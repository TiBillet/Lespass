from django.urls import path
from . import views

urlpatterns = [
    # ...
    path('rss/latest/feed/', views.LatestEntriesEvent(), name='latest_entries_feed'),
    path('calendar/feed/', views.ical_feed, name='ical_feed'),
    path('event/<uuid:event_uuid>/invitation.ics', views.generate_invitation_ical, name='event_invitation_ical'),
    path('event/<uuid:event_uuid>/send-invitation/', views.send_event_invitation, name='send_event_invitation'),
    path('event/<uuid:event_uuid>/reservation/<uuid:reservation_uuid>/accept/', views.accept_invitation, name='accept_invitation'),
    path('event/<uuid:event_uuid>/reservation/<uuid:reservation_uuid>/decline/', views.decline_invitation, name='decline_invitation'),
    # ...
]

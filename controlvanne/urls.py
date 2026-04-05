from django.urls import path
from . import views
from . import calibration_views

urlpatterns = [
#    path("", views.index, name="index"),
    path("api/rfid/event/", views.api_rfid_event, name="api_rfid_event"),
    path("api/rfid/authorize", views.api_rfid_authorize, name="api_rfid_authorize"),
    path("api/rfid/ping", views.ping, name="api_rfid_ping"),
    path("api/rfid/register/", views.api_rfid_register, name="api_rfid_register"),
    path("", views.panel_multi, name="panel"),

    # Calibration débitmètre
    path(
        "calibration/<uuid:uuid>/",
        calibration_views.calibration_page,
        name="calibration_page",
    ),
    path(
        "calibration/<uuid:uuid>/mesure/<int:session_id>/",
        calibration_views.calibration_soumettre,
        name="calibration_soumettre",
    ),
    path(
        "calibration/<uuid:uuid>/mesure/<int:session_id>/supprimer/",
        calibration_views.calibration_supprimer,
        name="calibration_supprimer",
    ),
    path(
        "calibration/<uuid:uuid>/appliquer/",
        calibration_views.calibration_appliquer,
        name="calibration_appliquer",
    ),
]
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BasebilletConfig(AppConfig):
    name = 'BaseBillet'
    verbose_name = _("Ticketing")

    def ready(self):
        import BaseBillet.signals

        # Les miniatures stdimage sont redressees selon l'orientation EXIF des
        # photos de telephone. Voir BaseBillet/images_orientation.py.
        # / stdimage thumbnails follow the phone photos' EXIF orientation.
        from BaseBillet.images_orientation import brancher_orientation_exif_sur_stdimage
        brancher_orientation_exif_sur_stdimage()

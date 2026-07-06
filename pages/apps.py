from django.apps import AppConfig


class PagesConfig(AppConfig):
    # Constructeur de pages / landing pages par blocs prefabriques.
    # / Builder for pages / landing pages from prefabricated blocks.
    default_auto_field = "django.db.models.BigAutoField"
    name = "pages"
    verbose_name = "Pages"

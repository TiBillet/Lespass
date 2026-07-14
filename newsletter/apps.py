from django.apps import AppConfig


class NewsletterConfig(AppConfig):
    """
    App newsletter : fabrique des brouillons de newsletter dans une instance Ghost.
    / Newsletter app: builds newsletter drafts inside a Ghost instance.

    LOCALISATION : newsletter/apps.py

    Cette app n'a AUCUN modele : la configuration Ghost du tenant vit deja dans
    BaseBillet.models.GhostConfig (singleton django-solo). Donc aucune migration.
    / This app has NO model: the tenant's Ghost config already lives in GhostConfig.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "newsletter"

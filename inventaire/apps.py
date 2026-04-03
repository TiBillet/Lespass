"""
Configuration de l'app inventaire.
Gestion de stock optionnelle pour les produits POS.
/ Inventory app configuration. Optional stock management for POS products.

LOCALISATION : inventaire/apps.py
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InventaireConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventaire"
    verbose_name = _("Inventaire / Inventory")

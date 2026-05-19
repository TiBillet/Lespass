"""
Configuration de l'app comptabilite.
/ Configuration of the comptabilite app.

LOCALISATION : comptabilite/apps.py

App tenant qui hebergera : ClotureCaisse (cloture comptable),
CompteComptable et MappingMoyenDePaiement (plan comptable parametrable, en S5).
/ Tenant app hosting: ClotureCaisse (accounting closure), and later
CompteComptable + MappingMoyenDePaiement (configurable accounting plan, S5).
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ComptabiliteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptabilite"
    verbose_name = _("Comptabilité")

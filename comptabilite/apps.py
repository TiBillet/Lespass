"""
Configuration de l'app comptabilite.
/ Configuration of the comptabilite app.

LOCALISATION : comptabilite/apps.py

App tenant qui heberge ClotureCaisse (cloture comptable). Le plan comptable du lieu
vit dans la caisse : `laboutik.CompteComptable` et `laboutik.MappingMoyenDePaiement`
(voir laboutik/plan_comptable.py).
/ Tenant app hosting ClotureCaisse (accounting closure). The venue's chart of accounts
lives in the register app (laboutik).
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ComptabiliteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptabilite"
    verbose_name = _("Comptabilité")

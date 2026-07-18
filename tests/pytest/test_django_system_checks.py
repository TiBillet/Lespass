"""
Filet de securite : les system checks de Django doivent passer.
/ Safety net: Django's system checks must pass.

LOCALISATION : tests/pytest/test_django_system_checks.py

POURQUOI CE FICHIER EXISTE
--------------------------
Le 2026-07-13, `ruff check --fix` a supprime cet import de `Administration/admin_tenant.py` :

    from Administration.admin import (products, prices)

C'est un IMPORT A EFFET DE BORD : le nom importe n'est jamais reference, mais l'import
EXECUTE les decorateurs `@admin.register(Product, ...)` du module. Un linter le voit donc
comme mort. Sans lui, ProductAdmin n'est plus enregistre, et Django refuse de demarrer :

    admin.E039 — An admin for model "Product" has to be registered to be referenced by
    EventAdmin.autocomplete_fields

Le serveur est tombe, et 319 tests sont partis en erreur — non pas parce qu'ils testaient
l'admin, mais parce que la fixture `conftest.py` appelle `manage.py test_api_key`, qui ne
bootait plus. Le symptome etait donc a des kilometres de la cause.

CE TEST REND CETTE PANNE IMPOSSIBLE A RATER : il echoue immediatement, avec le vrai message
d'erreur de Django.

Deux protections complementaires :
1. ce test (le filet) ;
2. `[tool.ruff.lint.per-file-ignores]` dans pyproject.toml, qui interdit a ruff de toucher
   au F401 des fichiers d'admin / signals / apps / settings (la ceinture).
/ This test makes that failure impossible to miss.
"""

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import SystemCheckError


def test_les_system_checks_de_django_passent():
    """
    `manage.py check` doit passer. C'est ce que fait Django au demarrage du serveur :
    si ce test echoue, le serveur ne demarre pas non plus.
    / `manage.py check` must pass. If this fails, the server won't boot either.
    """
    try:
        call_command("check")
    except SystemCheckError as erreur:
        pytest.fail(
            f"Les system checks de Django echouent — le serveur ne demarrerait pas :\n\n"
            f"{erreur}\n\n"
            f"Cause frequente : un IMPORT A EFFET DE BORD a ete supprime (par ruff --fix, "
            f"ou a la main). Cherchez un `from <app>.admin import ...` disparu."
        )


def test_les_admins_a_effet_de_bord_sont_bien_enregistres():
    """
    NON-REGRESSION CIBLEE. Ces ModelAdmin ne sont enregistres QUE parce qu'un import a
    effet de bord charge leur module. Si l'import saute, ils disparaissent en silence —
    et `EventAdmin.autocomplete_fields` casse Django au demarrage.
    / TARGETED REGRESSION TEST. These ModelAdmin only exist because a side-effect import
    loads their module.
    """
    from BaseBillet.models import Price, Product

    modeles_qui_doivent_avoir_un_admin = [Product, Price]

    # On regarde TOUS les sites d'admin : le projet en a plusieurs (staff_admin_site,
    # le site par defaut...). Un modele enregistre sur n'importe lequel nous convient.
    # / Look at ALL admin sites: the project has several.
    from Administration.admin.site import staff_admin_site

    sites_dadmin = [admin.site, staff_admin_site]

    for modele in modeles_qui_doivent_avoir_un_admin:
        est_enregistre = any(modele in site._registry for site in sites_dadmin)
        assert est_enregistre, (
            f"{modele.__name__} n'a plus d'admin enregistre. L'import a effet de bord "
            f"`from Administration.admin import (products, prices)` a probablement ete "
            f"supprime de Administration/admin_tenant.py. Il est protege par une "
            f"directive noqa F401 : ne la retirez pas."
        )

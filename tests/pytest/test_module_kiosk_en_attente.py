"""
tests/pytest/test_module_kiosk_en_attente.py

La borne V2 (module kiosk) est en attente : aucun lieu ne peut l'allumer, et ses routes
sont fermées tant que le module est éteint.
/ The V2 kiosk is on hold: no venue can switch it on, its routes are closed while off.

LOCALISATION : tests/pytest/test_module_kiosk_en_attente.py

POURQUOI / WHY
La borne V2 envoie encore à Stripe les métadonnées que lit le webhook de la borne de
l'ancien Fedow : brancher un lecteur créditerait deux fois
(TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-03-fed-invisible-en-caisse.md, §3 bis).

CE QUI EST TESTÉ / WHAT IS TESTED
- tableau de bord : module éteint = carte grisée sans interrupteur ; module allumé =
  interrupteur gardé, pour l'éteindre ;
- `module_toggle` : refuse d'allumer le kiosk (POST direct), accepte de l'éteindre ;
- `IsKioskTerminal` : un terminal Kiosque du lieu est refusé quand le module est éteint.

La Configuration est lue en base puis modifiée EN MÉMOIRE : `get_solo()` la rend, et
`save()` est simulé. Rien n'est écrit dans la base de dev.
/ The Configuration is changed in memory only; save() is faked.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_module_kiosk_en_attente.py -v
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from Administration.admin_tenant import staff_admin_site
from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from kiosk.views import IsKioskTerminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def configuration_du_lieu(tenant):
    """La Configuration du lieu `lespass` (moteur v2), dans son schéma.
    / The `lespass` venue Configuration (v2 engine), in its schema."""
    with tenant_context(tenant):
        yield Configuration.objects.get()


def carte_du_kiosk(configuration):
    """La carte du module kiosk au tableau de bord. / The kiosk dashboard card."""
    for carte in dashboard._build_modules_context(configuration):
        if carte.get("testid") == "dashboard-card-kiosk":
            return carte
    pytest.fail("Aucune carte « dashboard-card-kiosk » au tableau de bord.")


def basculer_le_kiosk(configuration):
    """
    Appelle `ConfigurationAdmin.module_toggle` comme le POST HTMX du tableau de bord.
    Rend la réponse, le faux `save()` et les messages, en français.
    / Calls module_toggle like the dashboard POST; returns response, fake save, messages.
    """
    requete = RequestFactory().post(
        "/admin/BaseBillet/configuration/module-toggle/module_kiosk/"
    )
    requete.user = AnonymousUser()
    SessionMiddleware(lambda requete_recue: None).process_request(requete)
    requete._messages = FallbackStorage(requete)
    admin_de_la_configuration = staff_admin_site._registry[Configuration]

    with translation.override("fr"):
        with patch.object(Configuration, "get_solo", return_value=configuration):
            with patch.object(Configuration, "save", autospec=True) as faux_save:
                reponse = admin_de_la_configuration.module_toggle(
                    requete, "module_kiosk"
                )
        messages = [str(message) for message in requete._messages]
    return reponse, faux_save, messages


def test_kiosk_eteint_carte_grisee_sans_interrupteur(configuration_du_lieu):
    """Module éteint : la carte annonce un module à venir, sans interrupteur.
    / Module off: a coming-soon card, no switch."""
    configuration_du_lieu.module_kiosk = False

    carte = carte_du_kiosk(configuration_du_lieu)

    assert carte["type"] == "coming_soon"
    assert carte["montre_interrupteur"] is False


def test_kiosk_allume_garde_son_interrupteur(configuration_du_lieu):
    """Module resté allumé : l'interrupteur reste, pour pouvoir l'éteindre.
    / Module left on: the switch stays, to turn it off."""
    configuration_du_lieu.module_kiosk = True

    carte = carte_du_kiosk(configuration_du_lieu)

    assert carte["type"] == "generic"
    assert carte["montre_interrupteur"] is True


def test_module_toggle_refuse_d_allumer_le_kiosk(configuration_du_lieu):
    """Un POST direct ne peut pas allumer le kiosk : rien n'est enregistré.
    / A direct POST cannot switch the kiosk on: nothing is saved."""
    configuration_du_lieu.module_kiosk = False

    reponse, faux_save, messages = basculer_le_kiosk(configuration_du_lieu)

    assert configuration_du_lieu.module_kiosk is False
    assert faux_save.call_count == 0
    assert reponse["HX-Refresh"] == "true"
    assert "Ce module est en cours de développement" in " ".join(messages)


def test_module_toggle_eteint_le_kiosk_allume(configuration_du_lieu):
    """Un kiosk resté allumé peut être éteint.
    / A kiosk left on can be switched off."""
    configuration_du_lieu.module_kiosk = True

    _reponse, faux_save, _messages = basculer_le_kiosk(configuration_du_lieu)

    assert configuration_du_lieu.module_kiosk is False
    assert faux_save.call_count == 1


@pytest.mark.parametrize("module_allume, acces_attendu", [(False, False), (True, True)])
def test_la_borne_suit_le_module_kiosk(
    tenant, configuration_du_lieu, module_allume, acces_attendu
):
    """Un terminal Kiosque du lieu (v2) n'entre que si le module est allumé.
    / A kiosk terminal of the (v2) venue gets in only when the module is on."""
    configuration_du_lieu.module_kiosk = module_allume
    terminal_kiosque = TibilletUser(
        email="terminal-kiosque-en-attente@tibillet.localhost",
        espece=TibilletUser.TYPE_TERM,
        terminal_role=TibilletUser.ROLE_KIOSQUE,
        client_source_id=tenant.pk,
        is_active=True,
    )
    requete = RequestFactory().get("/kiosk/")
    requete.user = terminal_kiosque

    with patch.object(Configuration, "get_solo", return_value=configuration_du_lieu):
        acces_accorde = IsKioskTerminal().has_permission(requete, view=None)

    assert acces_accorde is acces_attendu

"""
Le menu « Ventes & comptabilité » montre le rapport des ventes, et plus
l'ancienne clôture de la caisse.
/ The "Sales & accounting" menu shows the sales report, no longer the old POS
closure.

LOCALISATION : tests/pytest/test_menu_rapports.py

CE QUE CE TEST PROTEGE
----------------------
Chantier 05-0 (décision D25) : les ventes de caisse se trouvent dans la section
« Ventes & comptabilité », par « Rapport des ventes » (clôtures `comptabilite`,
la clôture unique, toutes origines).
Chantier 05, fiche H-1a (Q-H2) : l'ancienne clôture de la caisse (`laboutik`,
« Ancien rapport caisse ») lit le moyen des lignes, qui ne dit plus comment une
vente est payée. Elle n'est plus dans aucune section du menu, module caisse actif
ou non. Ses adresses restent (support) jusqu'à son retrait.
/ D25: register sales are reached through "Sales report". H-1a: the old POS
  closure reads the lines' method; it is in no menu section any more.

Ce test lit seulement la navigation construite pour une requête admin. La
configuration du lieu est forcée EN MÉMOIRE et servie par un patch de
`get_solo()` : rien n'est écrit en base ni dans le cache (PIEGES 13.5).
/ Reads the navigation only. The venue config is forced in memory and served
  by patching get_solo(): nothing is written to the DB or the cache.
"""

from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import gettext as _
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from BaseBillet.models import Configuration
from Customers.models import Client


@pytest.fixture
def lieu_lespass(db):
    """
    Le lieu `lespass`, lieu ordinaire du seed.
    / The `lespass` venue, an ordinary seeded venue.
    """
    tenant = Client.objects.filter(schema_name="lespass").first()
    if tenant is None:
        pytest.fail("Le lieu 'lespass' (seed demo_data_v2) est introuvable.")
    return tenant


def _sections_avec_module_caisse(tenant, module_caisse):
    """
    Les sections brutes de la navigation, module caisse forcé actif ou inactif.
    / The raw navigation sections, with the POS module forced on or off.

    On lit les sections brutes (une par module) et pas la sidebar : la sidebar
    replie chaque module en un seul lien, la section de la caisse n'y montre
    plus ses pages.
    / Raw sections, not the sidebar: the sidebar folds each module into one link.

    :param tenant: le lieu / the venue
    :param module_caisse: valeur forcée de Configuration.module_caisse
    :return: liste de sections (dicts)
    """
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        configuration.module_caisse = module_caisse
        with patch.object(
            dashboard.Configuration, "get_solo", return_value=configuration
        ):
            return dashboard._construire_sections_modules(
                RequestFactory().get("/admin/")
            )


def _liens_de_la_section(section):
    """
    Les liens d'une section, dans l'ordre, en texte.
    / A section's links, in order, as text.
    """
    return [str(item.get("link")) for item in section.get("items", [])]


@pytest.mark.django_db
def test_menu_ventes_comptabilite_montre_le_rapport_des_ventes_sans_l_ancien(
    lieu_lespass,
):
    """
    Trois choses :
      1. « Ventes & comptabilité » montre « Rapport des ventes » ;
      2. module caisse actif : aucune section ne pointe vers l'ancienne clôture de
         la caisse ;
      3. module caisse inactif : elle n'apparaît nulle part non plus.
    / 1. the sales report is there; 2. POS module on: no section links to the old
      POS closures; 3. POS module off: nowhere either.
    """
    with tenant_context(lieu_lespass):
        lien_rapport_en_ligne = reverse(
            "staff_admin:comptabilite_cloturecaisse_changelist"
        )
    # L'ancienne clôture de la caisse n'est plus enregistrée dans l'admin : son adresse
    # est écrite en clair, `reverse()` ne la trouverait plus.
    # / The old POS closure is no longer registered: its address is written out.
    lien_rapport_caisse = "/admin/laboutik/cloturecaisse/"
    titre_de_la_section = _("Sales & accounting")

    # --- Module caisse actif ---
    # / --- POS module on ---
    sections = _sections_avec_module_caisse(lieu_lespass, module_caisse=True)

    sections_ventes = [
        section
        for section in sections
        if str(section.get("title", "")) == titre_de_la_section
    ]
    assert len(sections_ventes) == 1, (
        f"Une seule section « {titre_de_la_section} » attendue, "
        f"trouvé : {len(sections_ventes)}."
    )
    section_ventes = sections_ventes[0]
    liens_ventes = _liens_de_la_section(section_ventes)

    # 1. Le rapport des ventes est là, avec son libellé.
    # / 1. The sales report is there, with its label.
    assert lien_rapport_en_ligne in liens_ventes, (
        "La section Ventes & comptabilité doit lister le rapport des ventes. "
        f"Liens trouvés : {liens_ventes}"
    )
    titres_par_lien = {}
    for item in section_ventes.get("items", []):
        titres_par_lien[str(item.get("link"))] = str(item.get("title"))
    assert titres_par_lien[lien_rapport_en_ligne] == _("Rapport des ventes"), (
        f"Libellé attendu « Rapport des ventes », trouvé : "
        f"{titres_par_lien[lien_rapport_en_ligne]}"
    )

    # 2. Module caisse actif : aucune section ne pointe vers l'ancienne clôture.
    # / 2. POS module on: no section links to the old POS closures.
    sections_avec_l_ancien_rapport = []
    for section in sections:
        if lien_rapport_caisse in _liens_de_la_section(section):
            sections_avec_l_ancien_rapport.append(str(section.get("title", "")))
    assert sections_avec_l_ancien_rapport == [], (
        "L'ancien rapport caisse est encore dans le menu : "
        f"{sections_avec_l_ancien_rapport}"
    )

    # --- Module caisse inactif ---
    # / --- POS module off ---
    sections_sans_caisse = _sections_avec_module_caisse(
        lieu_lespass, module_caisse=False
    )

    # 3. Un lieu sans caisse ne voit le rapport caisse nulle part.
    # / 3. A venue without POS sees the POS report nowhere.
    sections_qui_montrent_la_caisse = [
        str(section.get("title", ""))
        for section in sections_sans_caisse
        if lien_rapport_caisse in _liens_de_la_section(section)
    ]
    assert sections_qui_montrent_la_caisse == [], (
        "Module caisse inactif : le rapport caisse ne doit apparaître nulle part. "
        f"Trouvé dans : {sections_qui_montrent_la_caisse}"
    )

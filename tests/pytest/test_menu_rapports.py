"""
Le menu « Ventes & comptabilité » range les deux rapports, l'un sous l'autre.
/ The "Sales & accounting" menu holds both reports, one under the other.

LOCALISATION : tests/pytest/test_menu_rapports.py

CE QUE CE TEST PROTEGE
----------------------
Chantier 05-0 (décision D25). Un usager ne trouvait pas ses ventes de caisse
dans « Rapports » : la clôture caisse (`laboutik`) était rangée dans la section
de la caisse, loin de la clôture en ligne (`comptabilite`).

Désormais, la section « Ventes & comptabilité » montre, dans cet ordre :
  1. « Rapport des ventes »    -> clôtures `comptabilite` (la clôture unique,
     toutes origines) ;
  2. « Ancien rapport caisse » -> clôtures `laboutik`, seulement si le
     module caisse est actif.
L'entrée caisse quitte la section de la caisse : elle n'est pas dupliquée.
/ Chantier 05-0 (D25): both closure reports live in "Sales & accounting",
  online first, POS second (only when the POS module is on), and the POS
  entry leaves the POS section.

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
def test_menu_ventes_comptabilite_range_les_deux_rapports(lieu_lespass):
    """
    Trois choses :
      1. « Ventes & comptabilité » montre le rapport en ligne PUIS le rapport caisse ;
      2. aucune autre section ne pointe vers les clôtures caisse (pas de doublon) ;
      3. module caisse inactif -> le rapport caisse n'apparaît nulle part.
    / 1. online report then POS report, in order; 2. no other section links to
      the POS closures; 3. POS module off -> the POS report is nowhere.
    """
    with tenant_context(lieu_lespass):
        lien_rapport_en_ligne = reverse(
            "staff_admin:comptabilite_cloturecaisse_changelist"
        )
        lien_rapport_caisse = reverse("staff_admin:laboutik_cloturecaisse_changelist")
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

    # 1. Les deux rapports sont là, en ligne d'abord, caisse ensuite.
    # / 1. Both reports are there, online first, POS second.
    assert (
        lien_rapport_en_ligne in liens_ventes
        and lien_rapport_caisse in liens_ventes
        and liens_ventes.index(lien_rapport_en_ligne)
        < liens_ventes.index(lien_rapport_caisse)
    ), (
        "La section Ventes & comptabilité doit lister le rapport en ligne "
        f"puis le rapport caisse. Liens trouvés : {liens_ventes}"
    )

    # 1 bis. Les libellés : « Rapport des ventes » (la clôture unique, toutes
    # origines) et « Ancien rapport caisse » (l'ancienne clôture de la caisse).
    # / 1a. The labels: the single closure report, and the old POS report.
    titres_par_lien = {}
    for item in section_ventes.get("items", []):
        titres_par_lien[str(item.get("link"))] = str(item.get("title"))
    assert titres_par_lien[lien_rapport_en_ligne] == _("Rapport des ventes"), (
        f"Libellé attendu « Rapport des ventes », trouvé : "
        f"{titres_par_lien[lien_rapport_en_ligne]}"
    )
    assert titres_par_lien[lien_rapport_caisse] == _("Ancien rapport caisse"), (
        f"Libellé attendu « Ancien rapport caisse », trouvé : "
        f"{titres_par_lien[lien_rapport_caisse]}"
    )

    # 2. Aucune autre section ne pointe vers les clôtures caisse.
    # / 2. No other section links to the POS closures.
    autres_sections_avec_caisse = [
        str(section.get("title", ""))
        for section in sections
        if section is not section_ventes
        and lien_rapport_caisse in _liens_de_la_section(section)
    ]
    assert autres_sections_avec_caisse == [], (
        "Le rapport caisse est encore rangé ailleurs : "
        f"{autres_sections_avec_caisse}"
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

"""
Tests E2E : la page « Observatoire des instances » de l'admin.
/ E2E tests: the admin "Instance observatory" page.

LOCALISATION : tests/e2e/test_admin_observatoire.py
Spec : TECH_DOC/SESSIONS/OBSERVATOIRE/SPEC.md (section 8).

CE QUE CES TESTS PROTEGENT (la partie navigateur, que pytest ne voit pas) :
1. Le JS lit les donnees, dessine le graphique et remplit la liste.
2. Changer un seuil reclasse les lieux, sans recharger la page.
3. Un lieu qui n'a que des billets gratuits est « actif » s'il est regulier, et porte
   l'usage « billetterie gratuite » ; le filtre par usage le retrouve.
4. Un nom de lieu malveillant s'affiche comme du texte, il ne s'execute pas.

Le cache de l'observatoire est REMPLACE par un jeu connu pendant le test, puis
remis tel quel a la fin (try/finally) : la base de dev est partagee, sans rollback.
Les chiffres de dev sont trop faibles pour qu'un seuil change un classement.
/ The observatory cache is replaced by a known set during the test, then restored.
"""

import json

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL

# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>`.
pytestmark = [pytest.mark.e2e, pytest.mark.admin]

NOM_DE_LIEU_MALVEILLANT = '<img src=x onerror="window.__observatoire_xss=1">'

# Deux lieux tres actifs : 1 250 EUR de CA chaque mois pendant 13 mois, donc 12 mois
# d'usage sur 12. Un lieu gratuit : 15 billets gratuits sur chacun des 3 derniers mois,
# donc 3 mois d'usage : « actif » avec le seuil par defaut (3). Avec un seuil « Actif »
# a 13 mois, plus personne n'est actif : tout le monde devient « peu utilise ».
# / Two very active venues (12 months of use), one free venue (3 months of use).
NOMBRE_DE_MOIS = 13
CLES = [
    "evenements",
    "billets_gratuits",
    "billets_payants",
    "billets_scannes",
    "adhesions",
    "ca_total",
    "ca_billetterie",
    "ca_adhesions",
    "ca_caisse",
    "recharges_ligne",
    "recharges_place",
    "locations",
    "transactions_cashless",
    "portemonnaies_actifs",
    "usagers",
]


def compteurs_du_lieu(ca_mensuel_en_centimes=0, billets_gratuits_des_3_derniers_mois=0):
    tableaux = []
    for cle in CLES:
        if cle in ("ca_total", "ca_caisse"):
            tableaux.append([ca_mensuel_en_centimes] * NOMBRE_DE_MOIS)
        elif cle == "billets_gratuits":
            tableaux.append([0] * (NOMBRE_DE_MOIS - 3) + [billets_gratuits_des_3_derniers_mois] * 3)
        else:
            tableaux.append([0] * NOMBRE_DE_MOIS)
    return tableaux


def jeu_de_donnees_connu():
    mois = [f"2025-{numero:02d}" for numero in range(1, 13)] + ["2026-01"]
    return {
        "cles": CLES,
        "mois": mois,
        "calcule_le": "2026-01-15T02:30",
        "calcule_par": "cron",
        "bilan": {"lieux_lus": 3, "erreurs": [], "duree_s": 1.0},
        "reseau": {
            "lieux": 3,
            "comptes": 10,
            "fedow_legacy_a_repondu": True,
            "total_des_recharges_en_centimes": 0,
            "recharges_legacy": [],
            "recharges_v2": [],
            "cartes": {"total": 4, "liees_a_un_compte": 2},
            "billets_valides": 0,
            "billets_scannes": 0,
            "heures_de_benevolat": 0,
            "heures_du_planning": 0,
            "heures_des_tokens_cadeaux_legacy": 0,
        },
        # [schema, nom, cree, points de vente, admins, federe, compteurs]
        "inst": [
            [
                "lieu-actif",
                "Lieu très actif",
                "2024-01-01",
                1,
                2,
                False,
                compteurs_du_lieu(ca_mensuel_en_centimes=125_000),
            ],
            [
                "lieu-xss",
                NOM_DE_LIEU_MALVEILLANT,
                "2024-01-01",
                0,
                1,
                False,
                compteurs_du_lieu(ca_mensuel_en_centimes=125_000),
            ],
            [
                "lieu-gratuit",
                "Lieu gratuit",
                "2025-01-01",
                0,
                1,
                False,
                compteurs_du_lieu(billets_gratuits_des_3_derniers_mois=15),
            ],
        ],
    }


@pytest.fixture
def cache_de_l_observatoire_connu(django_shell):
    """
    Pose le jeu connu dans SEOCache, puis remet l'ancienne valeur (ou rien).
    / Sets the known set in SEOCache, then restores the previous value (or nothing).
    """
    lecture_de_l_ancien = (
        "import json\n"
        "from seo.models import SEOCache\n"
        "ligne = SEOCache.objects.filter(cache_type=SEOCache.OBSERVATOIRE, tenant__isnull=True).first()\n"
        "print(json.dumps(ligne.data if ligne else None))\n"
    )
    ancien = django_shell(lecture_de_l_ancien, schema="public")
    django_shell(
        "import json\n"
        "from seo.models import SEOCache\n"
        f"donnees = json.loads({json.dumps(json.dumps(jeu_de_donnees_connu()))})\n"
        "SEOCache.objects.update_or_create(cache_type=SEOCache.OBSERVATOIRE, tenant=None, defaults={'data': donnees})\n",
        schema="public",
    )
    try:
        yield
    finally:
        django_shell(
            "import json\n"
            "from seo.models import SEOCache\n"
            f"ancien = json.loads({json.dumps(ancien)})\n"
            "if ancien is None:\n"
            "    SEOCache.objects.filter(cache_type=SEOCache.OBSERVATOIRE, tenant__isnull=True).delete()\n"
            "else:\n"
            "    SEOCache.objects.update_or_create(cache_type=SEOCache.OBSERVATOIRE, tenant=None, defaults={'data': ancien})\n",
            schema="public",
        )


class TestAdminObservatoire:
    """La page de l'observatoire, en superadmin. / The observatory page, as superadmin."""

    def test_la_page_dessine_le_graphique_et_un_seuil_reclasse_les_lieux(
        self, page, login_as_admin, cache_de_l_observatoire_connu
    ):
        """
        Le graphique se dessine ; monter le seuil « Actif » a 13 mois d'usage fait
        passer tous les lieux en « peu utilisé » (« très actif » demande aussi d'etre
        actif).
        / The chart is drawn; raising the "active" threshold reclassifies the venues.
        """
        login_as_admin(page)
        page.goto(f"{BASE_URL}/admin/observatoire/")

        expect(page.get_by_test_id("observatoire-tuiles")).to_contain_text("3")
        graphique_dessine = page.evaluate(
            "() => !!(window.Chart && Chart.getChart(document.getElementById('graph')))"
        )
        assert graphique_dessine

        # Une ligne de legende par activite, dans l'ordre : tres actif, actif, peu
        # utilise, sommeil.
        # / One legend line per activity, in order.
        lignes_de_la_legende = page.get_by_test_id("observatoire-legende-activite").locator("li")
        expect(lignes_de_la_legende.nth(0)).to_have_text("très actif 2")
        expect(lignes_de_la_legende.nth(1)).to_have_text("actif 1")

        page.get_by_test_id("observatoire-seuils").locator("summary").click()
        page.get_by_test_id("observatoire-seuil-actifMois").fill("13")

        expect(lignes_de_la_legende.nth(0)).to_have_text("très actif 0")
        expect(lignes_de_la_legende.nth(2)).to_have_text("peu utilisé 3")

    def test_la_bulle_d_aide_s_ouvre_au_survol_et_suit_les_seuils(
        self, page, login_as_admin, cache_de_l_observatoire_connu
    ):
        """
        Le « ? » d'une tuile montre sa methode de calcul au survol. Celle de « Vraiment
        actives » cite le seuil « Actif » en cours : elle change quand on le regle.
        Le « ? » du bloc « depuis le debut » s'ouvre aussi.
        / The "?" shows the method on hover, and follows the current thresholds.
        """
        login_as_admin(page)
        page.goto(f"{BASE_URL}/admin/observatoire/")

        aide_des_actives = page.get_by_test_id("observatoire-aide-synthese-1")
        bulle_des_actives = aide_des_actives.locator(".bulle")
        expect(bulle_des_actives).to_be_hidden()
        aide_des_actives.hover()
        expect(bulle_des_actives).to_be_visible()
        expect(bulle_des_actives).to_contain_text("au moins 3 mois d'usage")

        page.get_by_test_id("observatoire-seuils").locator("summary").click()
        page.get_by_test_id("observatoire-seuil-actifMois").fill("5")
        aide_des_actives = page.get_by_test_id("observatoire-aide-synthese-1")
        aide_des_actives.hover()
        expect(aide_des_actives.locator(".bulle")).to_contain_text("au moins 5 mois d'usage")

        aide_des_lieux = page.get_by_test_id("observatoire-aide-reseau-lieux")
        aide_des_lieux.hover()
        expect(aide_des_lieux.locator(".bulle")).to_be_visible()

    def test_un_lieu_aux_billets_gratuits_est_actif_et_filtre_par_son_usage(
        self, page, login_as_admin, cache_de_l_observatoire_connu
    ):
        """
        Un lieu sans argent, avec 15 billets gratuits sur 3 mois, est « actif » et porte
        l'usage « billetterie gratuite ». Le filtre par usage ne garde que lui.
        / A money-less venue with free tickets on 3 months is "active" and filterable.
        """
        login_as_admin(page)
        page.goto(f"{BASE_URL}/admin/observatoire/")

        liste = page.get_by_test_id("observatoire-liste")
        ligne_du_lieu_gratuit = liste.locator("tr", has_text="Lieu gratuit")
        expect(ligne_du_lieu_gratuit).to_contain_text("billetterie gratuite")
        expect(ligne_du_lieu_gratuit.locator("td").nth(4)).to_have_text("actif")

        page.get_by_test_id("observatoire-filtre-usage").select_option("billetterie_gratuite")

        expect(liste.locator("tbody tr")).to_have_count(1)
        expect(liste.locator("tbody tr")).to_contain_text("Lieu gratuit")

    def test_un_nom_de_lieu_malveillant_ne_s_execute_pas(
        self, page, login_as_admin, cache_de_l_observatoire_connu
    ):
        """
        Le nom d'un lieu est saisi par un admin de lieu : il doit rester du texte.
        / A venue name is typed by a venue admin: it must stay text.
        """
        login_as_admin(page)
        page.goto(f"{BASE_URL}/admin/observatoire/")

        liste = page.get_by_test_id("observatoire-liste")
        expect(liste).to_contain_text(NOM_DE_LIEU_MALVEILLANT)
        assert page.evaluate("() => window.__observatoire_xss") is None
        assert liste.locator("img").count() == 0

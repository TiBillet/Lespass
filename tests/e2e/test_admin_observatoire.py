"""
Tests E2E : la page « Observatoire des instances » de l'admin.
/ E2E tests: the admin "Instance observatory" page.

LOCALISATION : tests/e2e/test_admin_observatoire.py
Spec : TECH_DOC/SESSIONS/OBSERVATOIRE/SPEC.md (section 8).

CE QUE CES TESTS PROTEGENT (la partie navigateur, que pytest ne voit pas) :
1. Le JS lit les donnees, dessine le graphique et remplit la liste.
2. Changer un seuil reclasse les lieux, sans recharger la page.
3. Un nom de lieu malveillant s'affiche comme du texte, il ne s'execute pas.

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

# Un lieu tres actif : 1 250 EUR de CA chaque mois pendant 13 mois, soit 15 000 EUR
# sur 12 mois. Avec le seuil par defaut (10 000 EUR), il est « tres actif ».
# Au-dessus de 15 000 EUR, il devient « peu utilise ».
# / A very active venue: 15,000 EUR over 12 months; above that threshold, "barely used".
NOMBRE_DE_MOIS = 13
CLES = [
    "evenements",
    "inscriptions",
    "billets_scannes",
    "adhesions",
    "ca_total",
    "ca_billetterie",
    "ca_adhesions",
    "ca_caisse",
    "recharges_ligne",
    "recharges_place",
    "cartes_actives",
    "connexions_admin",
    "usagers",
]


def compteurs_du_lieu(ca_mensuel_en_centimes):
    tableaux = []
    for cle in CLES:
        if cle in ("ca_total", "ca_caisse"):
            tableaux.append([ca_mensuel_en_centimes] * NOMBRE_DE_MOIS)
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
        "bilan": {"lieux_lus": 2, "erreurs": [], "duree_s": 1.0},
        "inst": [
            [
                "lieu-actif",
                "Lieu très actif",
                "S",
                "2024-01-01",
                1,
                2,
                compteurs_du_lieu(125_000),
            ],
            [
                "lieu-xss",
                NOM_DE_LIEU_MALVEILLANT,
                "S",
                "2024-01-01",
                0,
                1,
                compteurs_du_lieu(125_000),
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
        Le graphique se dessine ; monter le seuil « Actif » au-dessus du CA des lieux
        les fait passer de « très actif » a « peu utilisé ».
        / The chart is drawn; raising the "active" threshold reclassifies the venues.
        """
        login_as_admin(page)
        page.goto(f"{BASE_URL}/admin/observatoire/")

        expect(page.get_by_test_id("observatoire-tuiles")).to_contain_text("2")
        graphique_dessine = page.evaluate(
            "() => !!(window.Chart && Chart.getChart(document.getElementById('graph')))"
        )
        assert graphique_dessine

        legende = page.get_by_test_id("observatoire-legende-activite")
        expect(legende).to_contain_text("très actif 2")

        page.get_by_test_id("observatoire-seuils").locator("summary").click()
        champ_du_seuil_actif = page.get_by_test_id("observatoire-seuil-actifCA")
        champ_du_seuil_actif.fill("20000")

        expect(legende).to_contain_text("très actif 0")
        expect(legende).to_contain_text("peu utilisé 2")

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

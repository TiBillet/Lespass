"""
tests/pytest/test_afficher_poids.py — Filtres template afficher_poids et has_poids.
/ Template filters afficher_poids and has_poids.

Couvre la conversion automatique kg/L et l'affichage compact colle.
/ Covers automatic kg/L conversion and compact joined display.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_afficher_poids.py -v
"""
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

from laboutik.templatetags.laboutik_filters import afficher_poids, has_poids


# ---------------------------------------------------------------------------
# Filtre afficher_poids — conversion automatique g/kg, cl/L
# / afficher_poids filter — automatic g/kg, cl/L conversion
# ---------------------------------------------------------------------------

class TestAfficherPoidsGrammes:
    """Unite GR : sous 1000 g → "Xg", au-dessus → "Y,Zkg".
    / GR unit: under 1000 g → "Xg", above → "Y,Zkg"."""

    def test_350_grammes_reste_en_grammes(self):
        article = {"poids_total": 350, "unite_poids": "GR"}
        assert afficher_poids(article) == "350g"

    def test_999_grammes_reste_en_grammes(self):
        article = {"poids_total": 999, "unite_poids": "GR"}
        assert afficher_poids(article) == "999g"

    def test_1000_grammes_devient_1kg_sans_decimale(self):
        """1000g exactement → "1kg", pas "1,0kg" ni "1,00kg".
        / Exactly 1000g → "1kg", not "1,0kg" or "1,00kg"."""
        article = {"poids_total": 1000, "unite_poids": "GR"}
        assert afficher_poids(article) == "1kg"

    def test_1500_grammes_devient_1_5_kg(self):
        article = {"poids_total": 1500, "unite_poids": "GR"}
        assert afficher_poids(article) == "1,5kg"

    def test_1250_grammes_devient_1_25_kg(self):
        article = {"poids_total": 1250, "unite_poids": "GR"}
        assert afficher_poids(article) == "1,25kg"

    def test_12500_grammes_devient_12_5_kg(self):
        article = {"poids_total": 12500, "unite_poids": "GR"}
        assert afficher_poids(article) == "12,5kg"


class TestAfficherPoidsCentilitres:
    """Unite CL : sous 100 cl → "Xcl", au-dessus → "Y,ZL".
    / CL unit: under 100 cl → "Xcl", above → "Y,ZL"."""

    def test_50_centilitres_reste_en_cl(self):
        article = {"poids_total": 50, "unite_poids": "CL"}
        assert afficher_poids(article) == "50cl"

    def test_99_centilitres_reste_en_cl(self):
        article = {"poids_total": 99, "unite_poids": "CL"}
        assert afficher_poids(article) == "99cl"

    def test_100_centilitres_devient_1L(self):
        article = {"poids_total": 100, "unite_poids": "CL"}
        assert afficher_poids(article) == "1L"

    def test_200_centilitres_devient_2L(self):
        article = {"poids_total": 200, "unite_poids": "CL"}
        assert afficher_poids(article) == "2L"

    def test_175_centilitres_devient_1_75_L(self):
        article = {"poids_total": 175, "unite_poids": "CL"}
        assert afficher_poids(article) == "1,75L"


class TestAfficherPoidsAbsentOuInconnu:
    """Cas degenere : pas de poids ou unite inconnue.
    / Edge cases: no weight or unknown unit."""

    def test_poids_total_none_renvoie_chaine_vide(self):
        article = {"poids_total": None, "unite_poids": "GR"}
        assert afficher_poids(article) == ""

    def test_poids_total_zero_renvoie_chaine_vide(self):
        article = {"poids_total": 0, "unite_poids": "GR"}
        assert afficher_poids(article) == ""

    def test_dict_vide_renvoie_chaine_vide(self):
        assert afficher_poids({}) == ""

    def test_none_renvoie_chaine_vide(self):
        assert afficher_poids(None) == ""

    def test_unite_unite_inconnue_renvoie_brut(self):
        """Unite "UN" (pieces) ou autre : on affiche le nombre brut sans suffixe.
        Cas qui ne devrait pas arriver en pratique (Stock vrac = GR ou CL).
        / Unknown unit: show raw number without suffix.
        Should not happen in practice (vrac Stock = GR or CL)."""
        article = {"poids_total": 350, "unite_poids": "UN"}
        assert afficher_poids(article) == "350"


# ---------------------------------------------------------------------------
# Filtre has_poids — detection de presence d'au moins un article vrac
# / has_poids filter — detect at least one vrac article in the list
# ---------------------------------------------------------------------------

class TestHasPoids:
    """Affichage conditionnel de la colonne "Poids/Vol".
    / Conditional display of the "Weight/Vol" column."""

    def test_liste_vide_renvoie_false(self):
        assert has_poids([]) is False

    def test_none_renvoie_false(self):
        assert has_poids(None) is False

    def test_aucun_article_avec_poids_renvoie_false(self):
        articles = [
            {"nom": "Pinte", "qty_total": 5, "poids_total": None},
            {"nom": "Demi", "qty_total": 3, "poids_total": None},
        ]
        assert has_poids(articles) is False

    def test_un_article_avec_poids_renvoie_true(self):
        articles = [
            {"nom": "Pinte", "qty_total": 5, "poids_total": None},
            {"nom": "Cacahuetes vrac", "qty_total": 3, "poids_total": 350},
        ]
        assert has_poids(articles) is True

    def test_premier_article_avec_poids_renvoie_true(self):
        articles = [
            {"nom": "Vin vrac", "qty_total": 2, "poids_total": 100},
            {"nom": "Pinte", "qty_total": 5, "poids_total": None},
        ]
        assert has_poids(articles) is True

    def test_poids_total_zero_compte_comme_absent(self):
        """qty_total=2 mais poids_total=0 → considere comme article non vrac.
        / qty_total=2 but poids_total=0 → considered non-vrac."""
        articles = [
            {"nom": "Article qty 0g", "qty_total": 2, "poids_total": 0},
        ]
        assert has_poids(articles) is False

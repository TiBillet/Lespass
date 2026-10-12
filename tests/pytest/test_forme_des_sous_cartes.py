"""
Tests : la forme des sous-cartes d'un bloc MEDIA_ET_CARTES vient de leur contenu.
/ Tests: a MEDIA_ET_CARTES block's sub-card shape comes from their content.

LOCALISATION : tests/pytest/test_forme_des_sous_cartes.py

Code teste : pages/templatetags/pages_tags.py:forme_des_sous_cartes, lu par
pages/templates/pages/V2/partials/bloc_section_media_et_cartes.html.
Fonction pure : pas de base de donnees.
/ Pure function: no database.
"""

from pages.templatetags.pages_tags import forme_des_sous_cartes


def test_des_valeurs_en_un_mot_deviennent_des_pastilles():
    valeurs = [
        {"titre": "Horizontalité"},
        {"titre": "Curiosité"},
        {"titre": "Solidarité"},
    ]
    assert forme_des_sous_cartes(valeurs) == "pastilles"


def test_des_phrases_sans_texte_deviennent_une_liste():
    phrases = [
        {"titre": "Un espace sans condition de diplôme, d'âge ou de parcours"},
        {"titre": "Des ateliers de rencontres ouverts à tous"},
    ]
    assert forme_des_sous_cartes(phrases) == "liste"


def test_un_seul_titre_long_suffit_a_passer_en_liste():
    # Un mélange de mots seuls et d'une phrase reste une liste : une pastille
    # contenant une phrase entière serait illisible.
    # / One sentence among single words keeps the list shape.
    melange = [{"titre": "Bar"}, {"titre": "Cuisine du soir et repas partagés"}]
    assert forme_des_sous_cartes(melange) == "liste"


def test_un_texte_sur_une_seule_sous_carte_garde_les_cartes():
    avec_texte = [
        {"titre": "Bénévolat", "texte": "Organisation, accueil des nouveaux bénévoles"},
        {"titre": "Bar"},
    ]
    assert forme_des_sous_cartes(avec_texte) == "cartes"


def test_un_mot_trop_long_n_est_pas_une_pastille():
    mot_tres_long = [{"titre": "Anticonstitutionnellement-et-plus"}]
    assert forme_des_sous_cartes(mot_tres_long) == "liste"

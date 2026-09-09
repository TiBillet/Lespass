"""
La colonne « Poids/Vol » du rapport de cloture est-elle RENDUE ?
/ Is the closure report's "Weight/Vol." column actually RENDERED?

LOCALISATION : tests/pytest/test_cloture_colonne_poids.py

POURQUOI CE FICHIER EXISTE
--------------------------
Les filtres `has_poids` et `afficher_poids` avaient deja des tests unitaires
(tests/pytest/test_afficher_poids.py), tous au vert. Mais la colonne qu'ils
alimentent n'etait rendue NULLE PART : elle n'existait que dans
`Administration/templates/admin/cloture_detail.html`, un gabarit reference par
aucun Python et aucun gabarit — du code mort. Le seul template reellement
branche est `admin/cloture/rapport_before.html`
(Administration/admin/laboutik.py, `change_form_before_template`).

La fonctionnalite avait donc ete construite dans le mauvais fichier. Les tests
des filtres passaient, et l'utilisateur ne voyait rien.
/ The filters were unit-tested and green, but the column they feed lived only
  in a dead template. The feature was built in the wrong file.

Le poids est pourtant bien calcule a chaque rapport
(`laboutik/reports.py`, cles `poids_total` / `unite_poids`) : la donnee etait
produite puis jetee.

LA LECON, et la raison d'etre de ce fichier : tester un filtre ne prouve pas
qu'il est branche. Ces tests rendent le VRAI gabarit.
/ Testing a filter does not prove it is wired up. These tests render the real
  template.
"""

import pytest
from django.template.loader import render_to_string

GABARIT = "admin/cloture/rapport_before.html"


class _ClotureFactice:
    """
    Le strict necessaire pour que le gabarit se rende.

    Le pied de page fait `{{ cloture_obj.total_perpetuel|euros }}` SANS garde :
    le filtre `euros` fait un `int()` et leve donc sur une valeur absente. On
    fournit un nombre plutot que None. (A signaler : c'est une fragilite reelle
    du gabarit, pas seulement du test.)
    / The footer calls |euros without a guard, and the filter int()s its input.
    """

    numero_sequentiel = 1
    responsable = "test"
    point_de_vente = None
    datetime_ouverture = None
    datetime_cloture = None
    hash_lignes = "abc"
    total_perpetuel = 0

    def get_niveau_display(self):
        return "Journaliere"


def _contexte(articles):
    """
    Le minimum que le gabarit attend pour rendre la section « detail ventes ».
    Les autres sections sont gardees par `{% if section %}` et se sautent.
    / The other sections are guarded by {% if section %} and skip themselves.
    """
    return {
        "rapport": {
            "detail_ventes": {
                "Boissons": {"articles": articles, "total_ttc": 1000},
            }
        },
        "cloture_obj": _ClotureFactice(),
    }


ARTICLE_AU_POIDS = {
    "nom": "Vrac 1kg",
    "qty_vendus": 2,
    "qty_offerts": 0,
    "qty_total": 2,
    "total_ht": 900,
    "total_tva": 100,
    "total_ttc": 1000,
    "cout_total": 400,
    "benefice": 600,
    "poids_total": 1500,
    "unite_poids": "GR",
}

ARTICLE_A_L_UNITE = {
    "nom": "Biere pression",
    "qty_vendus": 3,
    "qty_offerts": 1,
    "qty_total": 4,
    "total_ht": 900,
    "total_tva": 100,
    "total_ttc": 1000,
    "cout_total": 400,
    "benefice": 600,
    "poids_total": None,
    "unite_poids": None,
}


def test_la_colonne_est_rendue_quand_un_article_se_vend_au_poids():
    """
    LE test qui manquait. Il aurait attrape le fait que la colonne vivait dans
    un gabarit mort.
    / The missing test: it would have caught the column living in a dead file.
    """
    html = render_to_string(GABARIT, _contexte([ARTICLE_AU_POIDS]))

    assert "Poids/Vol" in html, "L'en-tete de colonne est absent du rapport rendu."
    assert 'data-testid="cloture-poids-vol"' in html, "La cellule est absente."
    # Et la valeur est bien convertie par le filtre : 1500 g -> 1,5kg
    assert "1.5kg" in html or "1,5kg" in html, html[:0] or "Valeur de poids absente."


def test_la_colonne_disparait_quand_aucun_article_ne_se_vend_au_poids():
    """
    Une colonne de tirets sur toutes les categories serait du bruit. Le
    gabarit ne doit l'afficher que si elle a quelque chose a dire.
    / A column of dashes on every category would be noise.
    """
    html = render_to_string(GABARIT, _contexte([ARTICLE_A_L_UNITE]))

    assert "Poids/Vol" not in html
    assert 'data-testid="cloture-poids-vol"' not in html


def test_la_colonne_apparait_des_qu_UN_article_de_la_categorie_a_un_poids():
    """
    `has_poids` regarde la categorie entiere : un seul article au poids suffit,
    et les autres affichent alors un tiret.
    / One weighed article in the category is enough.
    """
    html = render_to_string(GABARIT, _contexte([ARTICLE_A_L_UNITE, ARTICLE_AU_POIDS]))
    assert "Poids/Vol" in html
    assert html.count('data-testid="cloture-poids-vol"') == 2


@pytest.mark.parametrize(
    "articles, colspan_attendu",
    [([ARTICLE_AU_POIDS], 'colspan="7"'), ([ARTICLE_A_L_UNITE], 'colspan="6"')],
)
def test_le_colspan_de_la_ligne_de_total_suit_la_colonne(articles, colspan_attendu):
    """
    Une colonne en plus decale le tableau : sans ce `colspan` adaptatif, la
    ligne « Total » se retrouverait desalignee d'une cellule.
    / Without the adaptive colspan the total row would be misaligned.
    """
    html = render_to_string(GABARIT, _contexte(articles))
    assert colspan_attendu in html


def test_le_gabarit_mort_n_existe_plus():
    """
    Garde-fou : si `cloture_detail.html` revenait, la colonne pourrait a
    nouveau etre modifiee au mauvais endroit sans que personne ne le voie.
    / Guard: if the dead template came back, the same mistake could recur.
    """
    from pathlib import Path

    from django.conf import settings

    mort = (
        Path(settings.BASE_DIR) / "Administration/templates/admin/cloture_detail.html"
    )
    assert not mort.exists(), (
        "cloture_detail.html est reapparu. C'etait un gabarit mort : la colonne "
        "Poids/Vol y avait ete ajoutee par erreur et n'etait jamais rendue."
    )

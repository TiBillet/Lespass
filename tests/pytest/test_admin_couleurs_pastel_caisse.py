"""
Couleur de fond des boutons de caisse : palette pastel imposée.
/ POS button background color: pastel palette only.

LOCALISATION : tests/pytest/test_admin_couleurs_pastel_caisse.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Dans l'admin, un article de caisse (POSProduct) et une catégorie de caisse
(CategorieProduct) ne proposent que les 33 couleurs de la palette pastel
(11 teintes x 3 niveaux). Il n'y a plus de sélecteur libre, ni de champ
« couleur du texte ». Le formulaire écrit lui-même le texte :
- fond pastel : texte foncé #1a1a1a ;
- pas de fond : pas de texte (la caisse prend la valeur par défaut) ;
- ancien fond hors palette, conservé : le texte ne change pas.

Les formulaires sont testés sans les enregistrer : on appelle clean() sur une
instance en mémoire. Rien n'est écrit en base.
/ Forms are tested without saving: clean() on an in-memory instance.

Lancement / Run:
    python -m pytest tests/pytest/test_admin_couleurs_pastel_caisse.py -v
"""

import re

import pytest
from django import forms
from django.template.loader import render_to_string
from django_tenants.utils import tenant_context

# Palette pastel : design tokens --color-{teinte}-{100|200|300}, dans l'ordre.
# / Pastel palette: --color-{hue}-{100|200|300} design tokens, in order.
PALETTE_PASTEL_ATTENDUE = [
    "#a1d9fe",
    "#6bc4fe",
    "#3dabf3",  # blue
    "#b7f7ff",
    "#8df2ff",
    "#42e9ff",  # cyan
    "#d2bcff",
    "#b996fe",
    "#b18aff",  # violet
    "#b5ffd7",
    "#8effc2",
    "#63ffab",  # mint
    "#f9aece",
    "#ff88bb",
    "#ff589f",  # pink
    "#fff7b8",
    "#feef78",
    "#ffe833",  # yellow
    "#fbd99c",
    "#fbc86f",
    "#feb940",  # amber
    "#ffcaa9",
    "#ffb181",
    "#ff9655",  # orange
    "#feb1b2",
    "#fe8c8e",
    "#fd686b",  # coral
    "#c4fbb0",
    "#a9fe8a",
    "#8fff67",  # lime
    "#adadf9",
    "#9292fb",
    "#7676ff",  # indigo
]


class TestPalettePastel:
    """La palette est exactement celle du nuancier. / Exactly the swatch palette."""

    def test_les_33_couleurs_sont_celles_du_nuancier_dans_l_ordre(self):
        from Administration.admin.products import codes_de_la_palette_pastel_caisse

        assert codes_de_la_palette_pastel_caisse() == PALETTE_PASTEL_ATTENDUE

    def test_aucune_couleur_n_est_en_double(self):
        from Administration.admin.products import codes_de_la_palette_pastel_caisse

        codes = codes_de_la_palette_pastel_caisse()
        assert len(codes) == len(set(codes))

    def test_chaque_teinte_a_trois_niveaux(self):
        from Administration.admin.products import PALETTE_PASTEL_CAISSE

        assert len(PALETTE_PASTEL_CAISSE) == 11
        for nom_teinte, couleurs_de_la_teinte in PALETTE_PASTEL_CAISSE:
            assert len(couleurs_de_la_teinte) == 3, nom_teinte


class TestCouleurDuTexte:
    """Le texte suit le fond. / Text color follows the background."""

    def test_fond_pastel_donne_un_texte_fonce(self):
        from Administration.admin.products import couleur_de_texte_pour_un_fond_pastel

        assert couleur_de_texte_pour_un_fond_pastel("#a1d9fe", "#ffffff") == "#1a1a1a"

    def test_pas_de_fond_donne_pas_de_texte(self):
        from Administration.admin.products import couleur_de_texte_pour_un_fond_pastel

        assert couleur_de_texte_pour_un_fond_pastel("", "#ffffff") is None

    def test_fond_hors_palette_garde_le_texte_actuel(self):
        from Administration.admin.products import couleur_de_texte_pour_un_fond_pastel

        assert couleur_de_texte_pour_un_fond_pastel("#1e40af", "#ffffff") == "#ffffff"


class TestValidationDuCodeCouleur:
    """Seul #rrggbb (ou vide) est accepté. / Only #rrggbb (or empty)."""

    def test_un_code_valide_est_mis_en_minuscules(self):
        from Administration.admin.products import _valider_couleur_hexadecimale

        assert _valider_couleur_hexadecimale(" #A1D9FE ") == "#a1d9fe"

    def test_vide_est_accepte(self):
        from Administration.admin.products import _valider_couleur_hexadecimale

        assert _valider_couleur_hexadecimale(None) == ""

    def test_un_code_invalide_est_refuse(self):
        from Administration.admin.products import _valider_couleur_hexadecimale

        with pytest.raises(forms.ValidationError):
            _valider_couleur_hexadecimale("#zzz")


class TestWidgetPastilles:
    """Le widget affiche les pastilles et coche la bonne. / Swatches render."""

    def _rendre_le_widget(self, valeur):
        from Administration.admin.products import CouleurFondPastelWidget

        widget = CouleurFondPastelWidget(libelle_aucune="Aucune (test)")
        return widget.render(
            "couleur_fond_pos", valeur, attrs={"id": "id_couleur_fond_pos"}
        )

    def test_le_widget_affiche_33_pastilles_et_aucune(self):
        html = self._rendre_le_widget("")
        for code_couleur in PALETTE_PASTEL_ATTENDUE:
            assert f'data-testid="caisse-pastille-{code_couleur[1:]}"' in html
        assert 'data-testid="caisse-pastille-aucune"' in html
        assert "Aucune (test)" in html
        assert html.count('type="radio"') == 34

    def test_la_couleur_actuelle_est_cochee(self):
        html = self._rendre_le_widget("#FF88BB")
        assert re.search(r'value="#ff88bb"\s+id="[^"]+"\s+checked', html)
        assert len(re.findall(r"\schecked>", html)) == 1

    def test_une_couleur_hors_palette_est_gardee_et_cochee(self):
        html = self._rendre_le_widget("#1e40af")
        assert 'data-testid="caisse-pastille-actuelle"' in html
        assert re.search(r'value="#1e40af"\s+id="[^"]+"\s+checked', html)
        assert len(re.findall(r"\schecked>", html)) == 1


class TestFormulaireArticleCaisse:
    """Fiche article de caisse (POSProductForm). / POS item form."""

    def test_plus_de_palette_ni_de_couleur_de_texte(self, tenant):
        from Administration.admin.products import (
            CouleurFondPastelWidget,
            POSProductForm,
        )

        with tenant_context(tenant):
            champs = POSProductForm.base_fields
        assert "palette_pos" not in champs
        assert "couleur_texte_pos" not in champs
        assert isinstance(champs["couleur_fond_pos"].widget, CouleurFondPastelWidget)

    def _nettoyer(self, tenant, fond, texte_actuel):
        from Administration.admin.products import POSProductForm
        from BaseBillet.models import POSProduct

        with tenant_context(tenant):
            article = POSProduct(
                name="Article test pastel", couleur_texte_pos=texte_actuel
            )
            formulaire = POSProductForm(instance=article)
            formulaire.cleaned_data = {"couleur_fond_pos": fond}
            formulaire.clean()
        return article.couleur_texte_pos

    def test_fond_pastel_ecrit_un_texte_fonce(self, tenant):
        assert self._nettoyer(tenant, "#6bc4fe", "#ffffff") == "#1a1a1a"

    def test_sans_fond_le_texte_est_vide(self, tenant):
        assert self._nettoyer(tenant, "", "#ffffff") is None

    def test_fond_hors_palette_garde_le_texte(self, tenant):
        assert self._nettoyer(tenant, "#1e40af", "#ffffff") == "#ffffff"


class TestFormulaireCategorieCaisse:
    """Fiche catégorie de caisse (CategorieProductForm). / POS category form."""

    def test_plus_de_palette_ni_de_couleur_de_texte(self):
        from Administration.admin.products import (
            CategorieProductForm,
            CouleurFondPastelWidget,
        )

        champs = CategorieProductForm.base_fields
        assert "palette" not in champs
        assert "couleur_texte" not in champs
        assert isinstance(champs["couleur_fond"].widget, CouleurFondPastelWidget)

    def _nettoyer(self, tenant, fond, texte_actuel):
        from Administration.admin.products import CategorieProductForm
        from BaseBillet.models import CategorieProduct

        with tenant_context(tenant):
            categorie = CategorieProduct(
                name="Categorie test pastel", couleur_texte=texte_actuel
            )
            formulaire = CategorieProductForm(instance=categorie)
            formulaire.cleaned_data = {"couleur_fond": fond}
            formulaire.clean()
        return categorie.couleur_texte

    def test_fond_pastel_ecrit_un_texte_fonce(self, tenant):
        assert self._nettoyer(tenant, "#feb940", "#ffffff") == "#1a1a1a"

    def test_sans_fond_le_texte_est_vide(self, tenant):
        assert self._nettoyer(tenant, "", "#ffffff") is None

    def test_fond_hors_palette_garde_le_texte(self, tenant):
        assert self._nettoyer(tenant, "#1e40af", "#ffffff") == "#ffffff"


def test_le_gabarit_du_widget_existe():
    """Le gabarit se charge seul (syntaxe Django valide). / Template loads."""
    html = render_to_string(
        "admin/product/widget_couleur_fond_pastel.html",
        {
            "widget": {"name": "x", "attrs": {"id": "id_x"}},
            "groupes_de_couleurs": [],
            "couleur_actuelle": "",
            "couleur_actuelle_hors_liste": "",
            "libelle_aucune": "Aucune",
        },
    )
    assert 'data-testid="caisse-pastilles-fond"' in html

"""
Tests E2E : la description longue d'un évènement est rangée au premier
enregistrement dans l'admin, puis ne bouge plus.
/ E2E tests: an event's long description is tidied on the first admin save,
then stays the same.

LOCALISATION : tests/e2e/test_admin_texte_riche_enregistrements.py

Code testé / Tested code :
- Administration/utils.py : clean_html (garde les <div>), normaliser_html_editeur
- Administration/admin/site.py : sanitize_textfields (appelé par EventAdmin.save_model)
- static/js/trix_paragraphes.js : les <p> voisins ne sont pas fusionnés par Trix

Pourquoi un vrai navigateur : l'éditeur de l'admin (Trix) relit le HTML en base
et le réécrit avant l'envoi du formulaire. Un ancien texte comme
`<br><br> Texte…</p><br>` revient du navigateur sous la forme
`<div><br><br> Texte…</div>…<div><br><br></div>`. Seul un vrai aller-retour
navigateur → serveur montre si le texte se répare, et s'il reste stable.
/ Trix rewrites the stored HTML before the form is sent: only a real browser
round-trip shows whether the text is repaired and then stays stable.

Les écritures en base passent par `django_shell` (validées aussitôt). L'évènement
créé est supprimé à la fin du test.
/ DB writes go through django_shell; the created event is deleted at the end.
"""

import json

import pytest

from tests.e2e.conftest import BASE_URL


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>`.
pytestmark = [pytest.mark.e2e, pytest.mark.admin]

NOM_DE_L_EVENEMENT = "E2E texte riche enregistrements"

# Ancien format, mesuré sur La Filature : <br> nus au début, listes coupées
# en listes d'un seul point, <br> après le dernier bloc.
# / Old format measured on La Filature.
DESCRIPTION_A_L_ANCIEN_FORMAT = (
    "<br><br> Créé en 2008 dans le cadre d'ateliers."
    "<p>Présentation :</p>"
    "<ul><li>Un</li></ul> <ul><li>Deux</li></ul> <ul><li>Trois</li></ul>"
    "<p>Fin du texte.</p><br>"
)
DESCRIPTION_RANGEE = (
    "<div>Créé en 2008 dans le cadre d'ateliers.</div>"
    "<p>Présentation :</p>"
    "<ul><li>Un</li><li>Deux</li><li>Trois</li></ul>"
    "<p>Fin du texte.</p>"
)


def _creer_l_evenement(django_shell, description):
    """
    Crée l'évènement, puis écrit la description par update() pour qu'aucun
    nettoyage ne passe dessus. `img=""` et `sticker_img=""` sont indispensables
    pour pouvoir le supprimer (tests/PIEGES.md, delete_orphans de django-stdimage).
    / Creates the event, then writes the raw description with update().
    """
    return django_shell(
        "import datetime\n"
        "from django.utils import timezone\n"
        "from BaseBillet.models import Event\n"
        f"Event.objects.filter(name={NOM_DE_L_EVENEMENT!r}).delete()\n"
        "evenement = Event.objects.create(\n"
        f"    name={NOM_DE_L_EVENEMENT!r},\n"
        "    datetime=timezone.now() + datetime.timedelta(days=40),\n"
        "    img='', sticker_img='',\n"
        ")\n"
        "Event.objects.filter(pk=evenement.pk).update(\n"
        f"    long_description={description!r}\n"
        ")\n"
        "print(evenement.pk)\n"
    )


def _description_en_base(django_shell, uuid_de_l_evenement):
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import Event\n"
        f"evenement = Event.objects.get(pk={uuid_de_l_evenement!r})\n"
        "print(json.dumps(evenement.long_description))\n"
    )
    return json.loads(sortie)


def _enregistrer_et_continuer(page, adresse_de_la_fiche):
    """
    Ouvre la fiche, attend que Trix ait réécrit le champ caché, puis clique
    sur « Enregistrer et continuer ».
    / Opens the form, waits for Trix, clicks "Save and continue".
    """
    page.goto(adresse_de_la_fiche)
    editeur = page.locator('trix-editor[input*="long_description"]')
    editeur.wait_for()
    # Trix écrit le champ caché au chargement : on attend qu'il soit prêt.
    # / Trix writes the hidden input on load: wait for it.
    page.wait_for_function(
        "() => document.querySelector('trix-editor[input*=\"long_description\"]').editor"
    )
    with page.expect_navigation():
        page.locator('[name="_continue"]').click()
    assert page.locator(".errorlist").count() == 0, "le formulaire a été refusé"


def test_l_ancien_format_est_range_au_premier_enregistrement_puis_stable(
    page, login_as_admin, django_shell
):
    """
    Trois enregistrements sans modification : la description est rangée dès
    le premier, et les deux suivants ne la changent plus (pas de <br> en plus).
    / Three saves without changes: tidied on the first, unchanged afterwards.
    """
    uuid_de_l_evenement = _creer_l_evenement(django_shell, DESCRIPTION_A_L_ANCIEN_FORMAT)
    adresse_de_la_fiche = (
        f"{BASE_URL}/admin/BaseBillet/event/{uuid_de_l_evenement}/change/"
    )
    try:
        login_as_admin(page)

        descriptions_apres_chaque_enregistrement = []
        for _numero_d_enregistrement in range(3):
            _enregistrer_et_continuer(page, adresse_de_la_fiche)
            descriptions_apres_chaque_enregistrement.append(
                _description_en_base(django_shell, uuid_de_l_evenement)
            )

        assert descriptions_apres_chaque_enregistrement == [DESCRIPTION_RANGEE] * 3
    finally:
        django_shell(
            "from BaseBillet.models import Event\n"
            f"Event.objects.filter(pk={uuid_de_l_evenement!r}).delete()\n"
        )


def test_les_paragraphes_voisins_ne_sont_pas_fusionnes(
    page, login_as_admin, django_shell
):
    """
    Trois <p> qui se suivent restent trois <p> après un enregistrement. Sans
    static/js/trix_paragraphes.js, Trix les fusionne à l'ouverture de la fiche :
    <p>Un.Deux.Trois.</p>.
    / Three neighbouring <p> stay separate after a save.
    """
    trois_paragraphes = "<p>Un.</p><p>Deux.</p><p>Trois.</p>"
    uuid_de_l_evenement = _creer_l_evenement(django_shell, trois_paragraphes)
    adresse_de_la_fiche = (
        f"{BASE_URL}/admin/BaseBillet/event/{uuid_de_l_evenement}/change/"
    )
    try:
        login_as_admin(page)
        _enregistrer_et_continuer(page, adresse_de_la_fiche)
        assert _description_en_base(django_shell, uuid_de_l_evenement) == trois_paragraphes
    finally:
        django_shell(
            "from BaseBillet.models import Event\n"
            f"Event.objects.filter(pk={uuid_de_l_evenement!r}).delete()\n"
        )

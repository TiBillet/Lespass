"""
Texte riche : nettoyage (clean_html) puis rangement (normaliser_html_editeur).
/ Rich text: sanitizing (clean_html) then tidying (normaliser_html_editeur).

LOCALISATION : tests/pytest/test_texte_riche_normalisation.py

Code testé / Tested code :
- Administration/utils.py : ALLOWED_TAGS (avec "div"), clean_html,
  normaliser_html_editeur
- Administration/admin/site.py : sanitize_textfields
- api_v2/serializers.py : EventCreateSerializer et EventPatchSerializer,
  validate_description
- BaseBillet/views.py : _creer_event_depuis_brouillon (wizard public)
- Administration/utils.py : texte_brut_vers_html (wizard et API v2)
- Administration/management/commands/normaliser_textes_riches.py (réparation)
- ApiBillet/serializers.py : ProductCreateSerializer, EventCreateSerializer,
  EventWriteSerializer (API historique)
- Administration/admin_tenant.py : EventResource.before_save_instance (import CSV)

L'éditeur de l'admin (Trix) écrit chaque bloc dans un <div>. Le copier-coller
et les anciens enregistrements laissent des <br> en début et en fin de texte,
des blocs vides et des listes coupées en listes d'un seul point.
/ Trix writes each block in a <div>; paste and old saves leave stray <br>,
empty blocks and split lists.

Les cas viennent des descriptions mesurées sur La Filature (prod) et dans
l'éditeur de dev (TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md, constats C3 à C6).

Lancer / Run :
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_texte_riche_normalisation.py -q
"""

import pytest
from django_tenants.utils import tenant_context

from Administration.utils import (
    clean_html,
    normaliser_html_editeur,
    texte_brut_vers_html,
)


def _nettoyer_et_ranger(html):
    """Le chemin complet d'un enregistrement. / The full save path."""
    return normaliser_html_editeur(clean_html(html))


# ---------------------------------------------------------------------------
# clean_html garde les <div> de Trix
# / clean_html keeps Trix <div>
# ---------------------------------------------------------------------------


def test_clean_html_garde_le_div_et_retire_ses_attributs():
    html_nettoye = clean_html('<div class="x" style="color:red" onclick="y()">Texte</div>')
    assert html_nettoye == "<div>Texte</div>"


def test_clean_html_garde_les_blocs_de_trix():
    html_de_trix = "<div>Bonjour,<br><br>Deuxième paragraphe.</div><div>Suite.</div>"
    assert clean_html(html_de_trix) == html_de_trix


# ---------------------------------------------------------------------------
# normaliser_html_editeur : ce qui est retiré
# / normaliser_html_editeur: what is removed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html_avant, html_attendu",
    [
        # Listes coupées par un espace (collage d'un mail).
        # / Lists split by a space (pasted mail).
        (
            "<ul><li>Un</li></ul> <ul><li>Deux</li></ul> <ul><li>Trois</li></ul>",
            "<ul><li>Un</li><li>Deux</li><li>Trois</li></ul>",
        ),
        # Listes coupées par un espace insécable.
        # / Lists split by a non-breaking space.
        (
            "<ol><li>Un</li></ol>&nbsp;<ol><li>Deux</li></ol>",
            "<ol><li>Un</li><li>Deux</li></ol>",
        ),
        # Listes coupées par un bloc vide (Trix relit l'espace entre deux <li>).
        # / Lists split by an empty block.
        (
            "<ul><li>Un</li></ul><div> </div><ul><li>Deux</li></ul>",
            "<ul><li>Un</li><li>Deux</li></ul>",
        ),
        # Blocs vides au milieu. / Empty blocks in the middle.
        (
            "<div>Un</div><div> </div><p>&nbsp;</p><div>Deux</div>",
            "<div>Un</div><div>Deux</div>",
        ),
        # Ancien format de La Filature : <br> nus au début, <br> après le dernier bloc.
        # / Old La Filature format: bare <br> at the start, <br> after the last block.
        (
            "<br><br> Créé en 2008.<p>Suite.</p><br>",
            "Créé en 2008.<p>Suite.</p>",
        ),
        # <br> en tête du premier bloc (ce que Trix renvoie pour l'ancien format).
        # / <br> at the head of the first block (Trix re-wraps the old format).
        (
            "<div><br><br> Créé en 2008.</div><div>Suite.</div>",
            "<div>Créé en 2008.</div><div>Suite.</div>",
        ),
        # Bloc final fait seulement de <br> (C6 : + 1 <br> à chaque enregistrement).
        # / Last block made only of <br>.
        (
            "<div>Texte.</div><div><br><br></div>",
            "<div>Texte.</div>",
        ),
        # <br> en queue du dernier bloc. / <br> at the tail of the last block.
        (
            "<div>Texte.<br><br>&nbsp;</div>",
            "<div>Texte.</div>",
        ),
        # Deux passes : retirer le bloc de <br> met un <br> nu en tête du texte.
        # / Two passes: removing the <br> block leaves a bare <br> at the start.
        (
            "<div><br></div><br><div><br>Texte.</div><div><br></div>",
            "<div>Texte.</div>",
        ),
    ],
)
def test_normaliser_retire_les_restes(html_avant, html_attendu):
    assert normaliser_html_editeur(html_avant) == html_attendu


# ---------------------------------------------------------------------------
# normaliser_html_editeur : ce qui est gardé
# / normaliser_html_editeur: what is kept
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html_inchange",
    [
        # Ligne vide voulue au milieu (Trix : bloc <div><br></div>).
        # / Intended blank line in the middle.
        "<div>Un</div><div><br></div><div>Deux</div>",
        # Saut de paragraphe dans un même bloc. / Paragraph break in one block.
        "<div>Bonjour,<br><br>Deuxième paragraphe.</div>",
        # Deux listes séparées par du texte. / Two lists separated by text.
        "<ul><li>Un</li></ul><div>Texte</div><ul><li>Deux</li></ul>",
        # Une liste à puces puis une liste numérotée. / A bullet list then a numbered list.
        "<ul><li>Un</li></ul> <ol><li>Deux</li></ol>",
        # Du HTML déjà propre. / Already tidy HTML.
        "<p>Un.</p><p>Deux.</p>",
    ],
)
def test_normaliser_garde_ce_qui_est_voulu(html_inchange):
    assert normaliser_html_editeur(html_inchange) == html_inchange


@pytest.mark.parametrize("valeur_vide", ["", None])
def test_normaliser_rend_une_valeur_vide_telle_quelle(valeur_vide):
    assert normaliser_html_editeur(valeur_vide) == valeur_vide


@pytest.mark.parametrize(
    "html_avant",
    [
        "<br><br> Créé en 2008.<p>Suite.</p><br>",
        "<ul><li>Un</li></ul> <ul><li>Deux</li></ul><div><br><br></div>",
        "<div><br>Texte<br><br></div><div> </div>",
    ],
)
def test_nettoyer_et_ranger_est_stable(html_avant):
    """
    Deux enregistrements sans modification donnent le même texte.
    / Saving twice without changes gives the same text.
    """
    une_fois = _nettoyer_et_ranger(html_avant)
    assert _nettoyer_et_ranger(une_fois) == une_fois


# ---------------------------------------------------------------------------
# Branchements : admin, API v2, wizard
# / Wiring: admin, API v2, wizard
# ---------------------------------------------------------------------------

HTML_A_RANGER = "<div><br><br>Texte.</div><ul><li>Un</li></ul> <ul><li>Deux</li></ul><div><br></div>"
HTML_RANGE = "<div>Texte.</div><ul><li>Un</li><li>Deux</li></ul>"


def test_sanitize_textfields_nettoie_et_range():
    """L'admin (save_model) range le HTML. / The admin tidies the HTML."""
    from Administration.admin.site import sanitize_textfields
    from BaseBillet.models import Event

    evenement_non_enregistre = Event(
        name="Test", long_description=HTML_A_RANGER + "<script>alert(1)</script>"
    )
    sanitize_textfields(evenement_non_enregistre)
    assert evenement_non_enregistre.long_description == HTML_RANGE

    # Un deuxième enregistrement ne change plus rien.
    # / A second save changes nothing.
    sanitize_textfields(evenement_non_enregistre)
    assert evenement_non_enregistre.long_description == HTML_RANGE


@pytest.mark.parametrize("nom_du_serializer", ["EventCreateSerializer", "EventPatchSerializer"])
def test_api_v2_description_nettoyee_et_rangee(nom_du_serializer):
    from api_v2 import serializers as serializers_api_v2

    classe_du_serializer = getattr(serializers_api_v2, nom_du_serializer)
    description_validee = classe_du_serializer().validate_description(HTML_A_RANGER)
    assert description_validee == HTML_RANGE


@pytest.mark.django_db
def test_wizard_description_nettoyee_et_rangee(tenant):
    """
    Le wizard public range la description. Transaction annulée à la fin.
    / The public wizard tidies the description. Rolled back at the end.
    """
    from django.contrib.auth.models import AnonymousUser
    from django.utils import timezone

    from BaseBillet.models import PostalAddress
    from BaseBillet.views import _creer_event_depuis_brouillon

    with tenant_context(tenant):
        brouillon = {
            "name": "Test wizard rangement",
            "datetime": (timezone.now() + timezone.timedelta(days=10)).isoformat(),
            "long_description": HTML_A_RANGER,
            "tags": "",
            "jauge_max": None,
        }
        evenement = _creer_event_depuis_brouillon(
            brouillon, PostalAddress.objects.first(), AnonymousUser(), est_staff=True
        )
        evenement.refresh_from_db()
        assert evenement.long_description == HTML_RANGE


# ---------------------------------------------------------------------------
# Texte brut (wizard, API v2) converti en HTML
# / Plain text (wizard, API v2) converted to HTML
# ---------------------------------------------------------------------------


def test_texte_brut_garde_ses_sauts_de_ligne():
    assert (
        texte_brut_vers_html("Bonjour,\r\n\r\nDeuxième paragraphe.")
        == "<div>Bonjour,<br>\n<br>\nDeuxième paragraphe.</div>"
    )


def test_texte_brut_est_echappe():
    html = texte_brut_vers_html("1 < 2 et 3 > 2 & fin")
    assert html == "<div>1 &lt; 2 et 3 &gt; 2 &amp; fin</div>"


def test_texte_brut_une_url_suivie_d_un_saut_de_ligne_est_coupee_avant():
    html = texte_brut_vers_html("Vidéo : https://example.org/v\nSuite")
    assert (
        html == '<div>Vidéo : <a href="https://example.org/v" rel="nofollow">'
        "https://example.org/v</a><br>\nSuite</div>"
    )


def test_du_html_n_est_pas_converti():
    html_existant = "<p>Déjà du HTML.</p>\n<p>Suite.</p>"
    assert texte_brut_vers_html(html_existant) == html_existant


def test_un_script_dans_le_texte_est_retire():
    """Un texte avec <script> contient une balise : il est traité comme du HTML,
    et clean_html retire le script.
    / A text with <script> holds a tag: treated as HTML, clean_html removes it."""
    html = normaliser_html_editeur(
        clean_html(texte_brut_vers_html("Avant<script>alert(1)</script>"))
    )
    assert "<script" not in html


def test_une_url_avec_des_parametres_reste_intacte():
    """
    « &region=sud » ne doit pas être lu comme l'entité « &reg » (®) : le lien
    de billetterie collé dans le wizard doit rester juste.
    / "&region=" must not be read as the "&reg" entity.
    """
    html = _nettoyer_et_ranger(
        texte_brut_vers_html("Billets : https://billetterie.org/?id=3&region=sud&section=2")
    )
    assert 'href="https://billetterie.org/?id=3&amp;region=sud&amp;section=2"' in html


def test_une_adresse_mail_entre_chevrons_n_est_pas_une_balise():
    """
    Le texte est converti (sauts de ligne gardés) et l'adresse reste lisible.
    / The text is converted and the address stays readable.
    """
    html = _nettoyer_et_ranger(texte_brut_vers_html("Contact : Jean <jean@exemple.org>\nLigne 2"))
    assert html.startswith("<div>Contact : Jean ")
    assert "&lt;jean@exemple.org&gt;</a><br>\nLigne 2</div>" in html


def test_des_milliers_de_sauts_de_ligne_sont_traites_vite():
    """
    Le wizard public accepte 5 000 caractères. Le rangement doit rester
    linéaire : une regex non ancrée prenait 8 s sur ce texte.
    / The public wizard accepts 5,000 chars: tidying must stay linear.
    """
    import time

    debut = time.perf_counter()
    html = _nettoyer_et_ranger(texte_brut_vers_html("a" + "\n" * 5000 + "b"))
    assert time.perf_counter() - debut < 0.5
    assert html.startswith("<div>a<br>") and html.endswith("<br>\nb</div>")


@pytest.mark.parametrize("nom_du_serializer", ["EventCreateSerializer", "EventPatchSerializer"])
def test_api_v2_description_en_texte_brut_convertie(nom_du_serializer):
    from api_v2 import serializers as serializers_api_v2

    classe_du_serializer = getattr(serializers_api_v2, nom_du_serializer)
    description_validee = classe_du_serializer().validate_description("Ligne 1\nLigne 2")
    assert description_validee == "<div>Ligne 1<br>\nLigne 2</div>"


@pytest.mark.django_db
def test_wizard_texte_brut_converti(tenant):
    """
    Le textarea du wizard envoie du texte brut : il est enregistré en HTML.
    / The wizard textarea sends plain text: saved as HTML.
    """
    from django.contrib.auth.models import AnonymousUser
    from django.utils import timezone

    from BaseBillet.models import PostalAddress
    from BaseBillet.views import _creer_event_depuis_brouillon

    with tenant_context(tenant):
        brouillon = {
            "name": "Test wizard texte brut",
            "datetime": (timezone.now() + timezone.timedelta(days=10)).isoformat(),
            "long_description": "Bonjour,\r\n\r\nInfos : https://example.org\r\n",
            "tags": "",
            "jauge_max": None,
        }
        evenement = _creer_event_depuis_brouillon(
            brouillon, PostalAddress.objects.first(), AnonymousUser(), est_staff=True
        )
        evenement.refresh_from_db()
        assert evenement.long_description == (
            '<div>Bonjour,<br>\n<br>\nInfos : <a href="https://example.org" '
            'rel="nofollow">https://example.org</a></div>'
        )


# ---------------------------------------------------------------------------
# Commande de réparation des events déjà en base
# / Repair command for events already in the database
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_commande_repare_les_events_et_la_passe_a_blanc_n_ecrit_rien(tenant):
    """
    --dry-run n'écrit rien ; la vraie passe répare ; une seconde passe ne
    change plus rien. Transaction annulée à la fin.
    / --dry-run writes nothing; the real run repairs; a second run changes nothing.
    """
    from django.core.management import call_command
    from django.utils import timezone

    from BaseBillet.models import Event

    descriptions_avant_et_apres = {
        "Ligne 1\nLigne 2": "<div>Ligne 1<br>\nLigne 2</div>",
        "<br><br> Texte.<p>Fin.</p><br>": "Texte.<p>Fin.</p>",
        "<ul><li>Un</li></ul> <ul><li>Deux</li></ul>": "<ul><li>Un</li><li>Deux</li></ul>",
        "<p>Déjà propre.</p>": "<p>Déjà propre.</p>",
        "Tom &amp; Jerry": "<div>Tom &amp; Jerry</div>",
        "Entrée 5&nbsp;€": "<div>Entrée 5&nbsp;€</div>",
    }

    with tenant_context(tenant):
        uuid_par_description = {}
        for numero, description in enumerate(descriptions_avant_et_apres):
            evenement = Event.objects.create(
                name=f"Test commande texte riche {numero}",
                datetime=timezone.now() + timezone.timedelta(days=50 + numero),
                img="",
                sticker_img="",
            )
            Event.objects.filter(pk=evenement.pk).update(long_description=description)
            uuid_par_description[description] = evenement.pk

    def _descriptions_en_base():
        with tenant_context(tenant):
            return {
                description: Event.objects.get(pk=uuid).long_description
                for description, uuid in uuid_par_description.items()
            }

    call_command("normaliser_textes_riches", "--dry-run")
    assert _descriptions_en_base() == {d: d for d in descriptions_avant_et_apres}

    call_command("normaliser_textes_riches")
    assert _descriptions_en_base() == descriptions_avant_et_apres

    call_command("normaliser_textes_riches")
    assert _descriptions_en_base() == descriptions_avant_et_apres


def test_api_v2_description_de_produit_nettoyee():
    """
    La description d'un produit est rendue en HTML (|safe) : formulaire
    d'adhésion, page Badgeuse. L'API v2 la nettoie comme celle des events.
    / Product description is rendered as HTML: API v2 sanitizes it.
    """
    from api_v2.serializers import ProductCreateSerializer

    description_validee = ProductCreateSerializer().validate_description(
        '<p>Badge.</p><img src="x" onerror="alert(1)"><script>alert(2)</script>'
    )
    assert description_validee == '<p>Badge.</p><img src="x">'


# ---------------------------------------------------------------------------
# API historique et import CSV : même nettoyage que l'admin
# / Legacy API and CSV import: same sanitizing as the admin
# ---------------------------------------------------------------------------

DESCRIPTION_AVEC_SCRIPT = '<p>Texte.</p><img src="x" onerror="alert(1)"><script>alert(2)</script>'
DESCRIPTION_SANS_SCRIPT = '<p>Texte.</p><img src="x">'


@pytest.mark.parametrize(
    "nom_du_serializer, nom_de_la_methode",
    [
        ("ProductCreateSerializer", "validate_long_description"),
        ("EventCreateSerializer", "validate_long_description"),
        ("EventWriteSerializer", "validate_description"),
    ],
)
def test_api_historique_description_nettoyee(nom_du_serializer, nom_de_la_methode):
    from ApiBillet import serializers as serializers_api_historique

    classe_du_serializer = getattr(serializers_api_historique, nom_du_serializer)
    methode_de_validation = getattr(classe_du_serializer(), nom_de_la_methode)
    assert methode_de_validation(DESCRIPTION_AVEC_SCRIPT) == DESCRIPTION_SANS_SCRIPT
    assert methode_de_validation("Ligne 1\nLigne 2") == "<div>Ligne 1<br>\nLigne 2</div>"


def test_import_csv_des_events_nettoie_la_description():
    """
    L'import CSV ne passe pas par save_model : EventResource nettoie lui-même
    la description avant l'enregistrement.
    / CSV import skips save_model: EventResource sanitizes the description itself.
    """
    from Administration.admin_tenant import EventResource
    from BaseBillet.models import Event

    evenement_importe = Event(name="Import", long_description=DESCRIPTION_AVEC_SCRIPT)
    EventResource().before_save_instance(evenement_importe, row={})
    assert evenement_importe.long_description == DESCRIPTION_SANS_SCRIPT

    evenement_en_texte_brut = Event(name="Import", long_description="Ligne 1\r\nLigne 2")
    EventResource().before_save_instance(evenement_en_texte_brut, row={})
    assert evenement_en_texte_brut.long_description == "<div>Ligne 1<br>\nLigne 2</div>"


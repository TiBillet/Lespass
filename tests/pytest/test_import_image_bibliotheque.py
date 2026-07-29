"""
Test pytest — Bibliotheque d'images (ImageBibliotheque) et colonne img.

Couvre :
- ImageUrlWidget : resolution de la cellule 'img' par NOM d'image de la
  bibliotheque (insensible a la casse), repli sur l'URL, erreur sinon.
- Import complet EventResource : la cellule img contenant le nom d'une
  image de la bibliotheque rattache ce fichier a l'evenement.

Regles du projet respectees (voir tests/README.md et tests/PIEGES.md) :
- base de dev partagee, pas de rollback : noms suffixes par uuid4().hex[:8]
- tenant_context(tenant) obligatoire (piege 9.1)
- nettoyage de l'evenement en SQL brut (le signal post_delete de stdimage
  plante quand le champ image est vide) ; la bibliotheque, elle, a une
  image : suppression ORM classique (nettoie aussi le fichier).

Lancez avec :
  docker exec lespass_django poetry run pytest tests/pytest/test_import_image_bibliotheque.py -q
"""
import base64
from uuid import uuid4

import tablib
import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django_tenants.utils import tenant_context

from Administration.admin_tenant import EventResource, ImageUrlWidget
from BaseBillet.models import Event, ImageBibliotheque, Tag

# Date fixe et lointaine : evite toute collision avec des evenements reels.
# / Fixed far-future date to avoid collisions with real events.
DATE_IMPORT = "2027-03-15 20:30:00"

# PNG 1x1 minimal pour peupler le champ image de la bibliotheque.
# / Minimal 1x1 PNG used as the library image file.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _creer_image_bibliotheque(nom):
    """Cree une image de bibliotheque avec un vrai fichier (variations
    stdimage generees). / Create a library image with a real file."""
    return ImageBibliotheque.objects.create(
        name=nom,
        img=ContentFile(PNG_1PX, name=f"{nom}.png"),
    )


def _supprimer_evenement_en_sql_brut(uuid_evenement):
    """Suppression de l'evenement en SQL brut (stdimage post_delete plante
    sur champ vide). / Raw SQL event delete (stdimage post_delete crashes
    on an empty image field)."""
    with connection.cursor() as curseur:
        curseur.execute(
            'DELETE FROM "BaseBillet_event" WHERE uuid = %s',
            [str(uuid_evenement)],
        )


def test_widget_retourne_none_pour_valeurs_vides(tenant):
    """Cellule vide -> pas d'image, pas d'erreur.
    / Empty cell -> no image, no error."""
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        assert widget.clean(None) is None
        assert widget.clean("") is None
        assert widget.clean("   ") is None


def test_widget_resout_par_nom_bibliotheque(tenant):
    """La cellule contenant le nom d'une image de la bibliotheque retourne
    son fichier, sans telechargement.
    / A cell holding a library image name returns its file directly."""
    suffixe = uuid4().hex[:8]
    nom = f"Affiche Test {suffixe}"
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        bib = _creer_image_bibliotheque(nom)
        try:
            image = widget.clean(nom)

            assert image is not None
            # Le widget retourne le FieldFile de la bibliotheque : meme
            # fichier, pas de copie.
            # / The widget returns the library FieldFile: same file, no copy.
            assert image.name == bib.img.name
        finally:
            bib.delete()


def test_widget_resout_par_nom_insensible_casse(tenant):
    """La recherche par nom ignore la casse.
    / Name lookup is case-insensitive."""
    suffixe = uuid4().hex[:8]
    nom = f"Visuel Concert {suffixe}"
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        bib = _creer_image_bibliotheque(nom)
        try:
            image = widget.clean(nom.upper())

            assert image is not None
            assert image.name == bib.img.name
        finally:
            bib.delete()


def test_widget_nom_inconnu_et_pas_url_leve_erreur(tenant):
    """Une valeur qui n'est ni un nom de bibliotheque ni une URL http(s)
    est rejetee avec un message explicite.
    / A value that is neither a library name nor an http(s) URL is rejected."""
    suffixe = uuid4().hex[:8]
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        with pytest.raises(ValueError, match="bibliothèque"):
            widget.clean(f"nom inexistant {suffixe}")


def test_import_evenement_avec_image_bibliotheque(tenant):
    """Import complet : la cellule img = nom de bibliotheque rattache
    l'image de la bibliotheque a l'evenement cree.
    / Full import: img cell = library name attaches the library image."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Img Bib {suffixe}"
    nom_image = f"Affiche Bib {suffixe}"

    with tenant_context(tenant):
        bib = _creer_image_bibliotheque(nom_image)
        uuid_evenement = None
        try:
            donnees = tablib.Dataset(
                [nom_image, nom_evenement, DATE_IMPORT],
                headers=["img", "name", "datetime"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert not resultat.has_errors()

            evenement = Event.objects.get(name=nom_evenement)
            uuid_evenement = evenement.uuid
            # L'evenement reutilise le fichier de la bibliotheque.
            # / The event reuses the library file.
            assert evenement.img.name == bib.img.name
        finally:
            # Ordre : evenement d'abord (SQL brut, ne touche pas au
            # fichier), puis la bibliotheque en ORM (nettoie le fichier).
            # / Order: event first (raw SQL, leaves the file alone), then
            # / the library via ORM (cleans up the file).
            if uuid_evenement is not None:
                _supprimer_evenement_en_sql_brut(uuid_evenement)
            bib.delete()


def _creer_tag(nom):
    """Cree un tag de test. / Create a test tag."""
    return Tag.objects.create(name=nom, slug=nom.lower().replace(' ', '-'))


def test_widget_repli_via_tag_quand_cellule_vide(tenant):
    """Cellule img vide + short_description = nom d'un tag : l'image de la
    bibliotheque taguee avec ce nom est retournee.
    / Empty img cell + short_description matching a tag name returns the
    library image carrying that tag."""
    suffixe = uuid4().hex[:8]
    nom_tag = f"brazil-{suffixe}"
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        tag = _creer_tag(nom_tag)
        bib = _creer_image_bibliotheque(f"Affiche Tag {suffixe}")
        bib.tags.add(tag)
        try:
            # Cellule vide, casse differente : le repli doit quand meme
            # trouver l'image.
            # / Empty cell, different case: the fallback still finds it.
            image = widget.clean("", row={"short_description": nom_tag.upper()})

            assert image is not None
            assert image.name == bib.img.name
        finally:
            bib.delete()
            tag.delete()


def test_widget_repli_sans_correspondance_retourne_none(tenant):
    """Cellule vide et short_description sans tag correspondant -> pas
    d'image, pas d'erreur.
    / Empty cell with no matching tag -> no image, no error."""
    suffixe = uuid4().hex[:8]
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        assert widget.clean("", row={"short_description": f"genre inconnu {suffixe}"}) is None
        # Ligne sans la colonne short_description : idem.
        # / Row without the short_description column: same.
        assert widget.clean("", row={}) is None


def test_cellule_remplie_prioritaire_sur_repli_tag(tenant):
    """Une cellule img remplie (nom de bibliotheque) garde la priorite sur
    le repli par tag.
    / A filled img cell (library name) wins over the tag fallback."""
    suffixe = uuid4().hex[:8]
    nom_tag = f"funk-{suffixe}"
    widget = ImageUrlWidget()

    with tenant_context(tenant):
        tag = _creer_tag(nom_tag)
        bib_tag = _creer_image_bibliotheque(f"Affiche Via Tag {suffixe}")
        bib_tag.tags.add(tag)
        bib_explicite = _creer_image_bibliotheque(f"Affiche Explicite {suffixe}")
        try:
            image = widget.clean(
                f"Affiche Explicite {suffixe}",
                row={"short_description": nom_tag},
            )

            assert image is not None
            assert image.name == bib_explicite.img.name
        finally:
            bib_tag.delete()
            bib_explicite.delete()
            tag.delete()


def test_import_evenement_image_via_tag(tenant):
    """Import complet : img vide, short_description = nom de tag -> l'image
    taguee de la bibliotheque est rattachee a l'evenement.
    / Full import: empty img, short_description = tag name -> the tagged
    library image is attached to the event."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Img Tag {suffixe}"
    nom_tag = f"techno-{suffixe}"

    with tenant_context(tenant):
        tag = _creer_tag(nom_tag)
        bib = _creer_image_bibliotheque(f"Affiche Import Tag {suffixe}")
        bib.tags.add(tag)
        uuid_evenement = None
        try:
            donnees = tablib.Dataset(
                ["", nom_evenement, DATE_IMPORT, nom_tag],
                headers=["img", "name", "datetime", "short_description"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert not resultat.has_errors()

            evenement = Event.objects.get(name=nom_evenement)
            uuid_evenement = evenement.uuid
            assert evenement.img.name == bib.img.name
        finally:
            if uuid_evenement is not None:
                _supprimer_evenement_en_sql_brut(uuid_evenement)
            bib.delete()
            tag.delete()


def test_import_sans_colonne_img_repli_tag(tenant):
    """Le fichier n'a PAS de colonne img : le repli par tag doit quand meme
    rattacher l'image (hook before_import_row de EventResource).
    / File without an img column: the tag fallback still attaches the image
    / (EventResource.before_import_row hook)."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Sans Col Img {suffixe}"
    nom_tag = f"groove-{suffixe}"

    with tenant_context(tenant):
        tag = _creer_tag(nom_tag)
        bib = _creer_image_bibliotheque(f"Affiche Sans Col {suffixe}")
        bib.tags.add(tag)
        uuid_evenement = None
        try:
            donnees = tablib.Dataset(
                [nom_evenement, DATE_IMPORT, nom_tag],
                headers=["name", "datetime", "short_description"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert not resultat.has_errors()

            evenement = Event.objects.get(name=nom_evenement)
            uuid_evenement = evenement.uuid
            assert evenement.img.name == bib.img.name
        finally:
            if uuid_evenement is not None:
                _supprimer_evenement_en_sql_brut(uuid_evenement)
            bib.delete()
            tag.delete()


def test_import_repli_tag_insensible_accents(tenant):
    """'Eclectique' dans le fichier doit trouver le tag 'éclectique'
    (comparaison sans accents).
    / 'Eclectique' in the file matches the 'éclectique' tag (accent-
    / insensitive comparison)."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Accents {suffixe}"
    nom_tag = f"éclectique-{suffixe}"

    with tenant_context(tenant):
        tag = _creer_tag(nom_tag)
        bib = _creer_image_bibliotheque(f"Affiche Accents {suffixe}")
        bib.tags.add(tag)
        uuid_evenement = None
        try:
            donnees = tablib.Dataset(
                ["", nom_evenement, DATE_IMPORT, f"Eclectique-{suffixe}"],
                headers=["img", "name", "datetime", "short_description"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert not resultat.has_errors()

            evenement = Event.objects.get(name=nom_evenement)
            uuid_evenement = evenement.uuid
            assert evenement.img.name == bib.img.name
        finally:
            if uuid_evenement is not None:
                _supprimer_evenement_en_sql_brut(uuid_evenement)
            bib.delete()
            tag.delete()


def test_import_image_aussi_en_sticker(tenant):
    """L'image importee est aussi copiee dans sticker_img : les cartes de
    l'agenda affichent get_sticker_img(), qui ne regarde jamais img.
    / The imported image is also copied to sticker_img: agenda cards render
    / get_sticker_img(), which never falls back to img."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Sticker {suffixe}"

    with tenant_context(tenant):
        bib = _creer_image_bibliotheque(f"Affiche Sticker {suffixe}")
        uuid_evenement = None
        try:
            donnees = tablib.Dataset(
                [bib.name, nom_evenement, DATE_IMPORT],
                headers=["img", "name", "datetime"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert not resultat.has_errors()

            evenement = Event.objects.get(name=nom_evenement)
            uuid_evenement = evenement.uuid
            assert evenement.img.name == bib.img.name
            assert evenement.sticker_img.name == bib.img.name
        finally:
            if uuid_evenement is not None:
                _supprimer_evenement_en_sql_brut(uuid_evenement)
            bib.delete()

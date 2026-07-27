"""
Test pytest — Import d'évènements via EventResource (admin django-import-export).

Ce test couvre le widget PostalAddressWidget et la ressource EventResource
utilisés par le bouton "Importer" de l'admin des évènements
(Administration/admin_tenant.py).

Cas couverts :
- valeurs vides (None, "", espaces) -> pas d'adresse
- recherche d'adresse insensible a la casse (iexact)
- recherche d'adresse insensible aux espaces en debut/fin de cellule (strip)
- creation automatique de l'adresse si elle n'existe pas (get_or_create)
- import complet d'un evenement avec adresse, y compris via un vrai flux xlsx

Regles du projet respectees (voir tests/README.md et tests/PIEGES.md) :
- base de dev partagee, pas de rollback : noms suffixes par uuid4().hex[:8]
- assertions en delta (piege 9.60), jamais de total absolu
- tenant_context(tenant) obligatoire : Event.save() appelle
  connection.tenant.get_primary_domain() (piege 9.1)
- nettoyage en SQL brut : le signal post_delete de stdimage plante quand le
  champ image est vide (pattern repris de test_seo_cache_fragments.py)

/ Pytest — Event import via EventResource (django-import-export admin).
/ Covers empty values, case-insensitive and whitespace-tolerant address lookup,
/ auto-creation of missing addresses, and a full event import (incl. xlsx).
/ Dev DB rules: uuid-suffixed names, delta assertions, tenant_context,
/ raw SQL cleanup (stdimage post_delete crashes on null image name).

Lancez avec :
  docker exec lespass_django poetry run pytest tests/pytest/test_event_import_resource.py -q
"""
import base64
from unittest.mock import MagicMock, patch
from uuid import uuid4

import tablib
import pytest
from django.core.files.storage import default_storage
from django.db import connection
from django_tenants.utils import tenant_context

from Administration.admin_tenant import EventResource, PostalAddressWidget
from BaseBillet.models import Event, PostalAddress


# Date fixe et lointaine : evite toute collision avec des evenements reels.
# Format impose par EventResource.Meta.widgets : '%Y-%m-%d %H:%M:%S'.
# / Fixed far-future date. Format required by the resource: '%Y-%m-%d %H:%M:%S'.
DATE_IMPORT = "2027-03-15 20:30:00"


def _creer_adresse(nom):
    """Cree une adresse postale de test dans le schema courant.
    / Create a test postal address in the current schema."""
    return PostalAddress.objects.create(name=nom)


def _supprimer_en_sql_brut(table, colonne_pk, valeurs_pk):
    """Suppression en SQL brut, sans passer par l'ORM.

    Pourquoi : le signal post_delete de django-stdimage plante
    (TypeError: splitext(None)) quand on supprime un objet dont le champ
    image n'a jamais ete rempli. Nos objets de test n'ont pas d'image.
    Pattern repris de tests/pytest/test_seo_cache_fragments.py.

    Attention : la cle primaire n'a pas le meme nom partout — 'uuid' pour
    Event, 'id' pour PostalAddress. Le nom de table et la colonne sont des
    constantes du test, jamais des entrees utilisateur.

    / Raw SQL delete, bypassing the ORM: stdimage's post_delete signal
    / crashes (TypeError: splitext(None)) when the image field was never
    / set. PK column names differ ('uuid' for Event, 'id' for PostalAddress).
    / Table and column names are constants here, never user input.
    """
    with connection.cursor() as curseur:
        for valeur_pk in valeurs_pk:
            curseur.execute(
                f'DELETE FROM "{table}" WHERE {colonne_pk} = %s',
                [str(valeur_pk)],
            )


def test_widget_retourne_none_pour_valeurs_vides(tenant):
    """Une cellule vide (None, chaine vide ou uniquement des espaces) ne doit
    donner aucune adresse — et surtout ne doit rien creer en base.
    / An empty cell (None, empty string or spaces only) yields no address
    and must not create anything."""
    widget = PostalAddressWidget(PostalAddress, field='name')

    with tenant_context(tenant):
        # Delta : le nombre d'adresses ne doit pas bouger.
        # / Delta assertion: address count must not change (piege 9.60).
        nombre_avant = PostalAddress.objects.count()

        assert widget.clean(None) is None
        assert widget.clean("") is None
        assert widget.clean("   ") is None

        nombre_apres = PostalAddress.objects.count()
        assert nombre_apres == nombre_avant


def test_widget_trouve_adresse_existante_insensible_casse(tenant):
    """La recherche ignore la casse : 'salle des fetes' trouve 'Salle Des Fetes',
    sans creer de doublon.
    / Lookup is case-insensitive and must not create a duplicate."""
    suffixe = uuid4().hex[:8]
    nom_en_base = f"Salle Des Fetes {suffixe}"
    widget = PostalAddressWidget(PostalAddress, field='name')

    with tenant_context(tenant):
        adresse = _creer_adresse(nom_en_base)
        try:
            nombre_avant = PostalAddress.objects.count()

            adresse_trouvee = widget.clean(nom_en_base.lower())

            assert adresse_trouvee is not None
            assert adresse_trouvee.pk == adresse.pk
            # Pas de creation : le total ne bouge pas.
            # / No creation: count unchanged.
            assert PostalAddress.objects.count() == nombre_avant
        finally:
            _supprimer_en_sql_brut("BaseBillet_postaladdress", "id", [adresse.pk])


def test_widget_ignore_espaces_debut_et_fin(tenant):
    """Les espaces en debut/fin de cellule sont ignores (strip) : la cellule
    '  Salle  ' trouve l'adresse 'Salle'.
    / Leading/trailing spaces are stripped before lookup."""
    suffixe = uuid4().hex[:8]
    nom_en_base = f"Place Du Marche {suffixe}"
    widget = PostalAddressWidget(PostalAddress, field='name')

    with tenant_context(tenant):
        adresse = _creer_adresse(nom_en_base)
        try:
            nombre_avant = PostalAddress.objects.count()

            adresse_trouvee = widget.clean(f"   {nom_en_base}   ")

            assert adresse_trouvee is not None
            assert adresse_trouvee.pk == adresse.pk
            assert PostalAddress.objects.count() == nombre_avant
        finally:
            _supprimer_en_sql_brut("BaseBillet_postaladdress", "id", [adresse.pk])


def test_widget_cree_adresse_si_inconnue(tenant):
    """Si l'adresse n'existe pas, elle est creee avec le nom nettoye (strip).
    C'est le comportement get_or_create du widget.
    / Unknown address names are auto-created with the stripped name."""
    suffixe = uuid4().hex[:8]
    nom_nouveau = f"Nouvelle Salle {suffixe}"
    widget = PostalAddressWidget(PostalAddress, field='name')

    with tenant_context(tenant):
        nombre_avant = PostalAddress.objects.count()

        adresse_creee = widget.clean(f"  {nom_nouveau}  ")

        try:
            assert adresse_creee is not None
            # Le nom enregistre est nettoye des espaces en debut/fin.
            # / The stored name is stripped.
            assert adresse_creee.name == nom_nouveau
            # Delta : exactement une adresse de plus.
            # / Delta: exactly one more address.
            assert PostalAddress.objects.count() == nombre_avant + 1
        finally:
            _supprimer_en_sql_brut("BaseBillet_postaladdress", "id", [adresse_creee.pk])


def test_import_evenement_avec_adresse_casse_et_espaces(tenant):
    """Import complet d'une ligne (name, datetime, postal_address) : l'evenement
    est cree et rattache a la bonne adresse malgre la casse et les espaces.
    / Full row import: the event is created and linked to the right address
    despite case and surrounding spaces."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Import {suffixe}"
    nom_adresse = f"Theatre Municipal {suffixe}"

    with tenant_context(tenant):
        adresse = _creer_adresse(nom_adresse)
        uuid_evenement_importe = None
        try:
            # On construit le tableau comme le ferait le fichier xlsx de
            # l'utilisateur : adresse en minuscules et entouree d'espaces.
            # / Build the dataset like the user's xlsx would: lowercase
            # address name padded with spaces.
            donnees = tablib.Dataset(
                [nom_evenement, DATE_IMPORT, f"  {nom_adresse.lower()}  "],
                headers=["name", "datetime", "postal_address"],
            )

            ressource = EventResource()
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            # Une ligne, une creation, pas d'erreur.
            # / One row, one creation, no error.
            assert resultat.totals["new"] == 1
            assert not resultat.has_errors()

            evenement_importe = Event.objects.get(name=nom_evenement)
            uuid_evenement_importe = evenement_importe.pk
            assert evenement_importe.postal_address is not None
            assert evenement_importe.postal_address.pk == adresse.pk
        finally:
            if uuid_evenement_importe is not None:
                _supprimer_en_sql_brut("BaseBillet_event", "uuid", [uuid_evenement_importe])
            _supprimer_en_sql_brut("BaseBillet_postaladdress", "id", [adresse.pk])


def test_import_evenement_via_flux_xlsx(tenant):
    """Meme import, mais en passant par de vrais octets xlsx (openpyxl) :
    on reproduit le parcours reel du bouton "Importer" de l'admin.
    / Same import through real xlsx bytes (openpyxl), reproducing the actual
    admin "Import" flow."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Festival Xlsx {suffixe}"
    nom_adresse = f"Chapiteau Rouge {suffixe}"

    with tenant_context(tenant):
        adresse = _creer_adresse(nom_adresse)
        uuid_evenement_importe = None
        try:
            donnees = tablib.Dataset(
                [nom_evenement, DATE_IMPORT, nom_adresse.upper()],
                headers=["name", "datetime", "postal_address"],
            )

            # Aller-retour par le format xlsx : export puis relecture,
            # exactement ce que fait django-import-export avec le fichier.
            # / Round-trip through the xlsx format: export then reload,
            # exactly what django-import-export does with the uploaded file.
            octets_xlsx = donnees.export("xlsx")
            donnees_relues = tablib.Dataset().load(octets_xlsx, "xlsx")

            ressource = EventResource()
            resultat = ressource.import_data(donnees_relues, dry_run=False, raise_errors=True)

            assert resultat.totals["new"] == 1
            assert not resultat.has_errors()

            evenement_importe = Event.objects.get(name=nom_evenement)
            uuid_evenement_importe = evenement_importe.pk
            assert evenement_importe.postal_address is not None
            assert evenement_importe.postal_address.pk == adresse.pk
        finally:
            if uuid_evenement_importe is not None:
                _supprimer_en_sql_brut("BaseBillet_event", "uuid", [uuid_evenement_importe])
            _supprimer_en_sql_brut("BaseBillet_postaladdress", "id", [adresse.pk])


# Plus petit PNG valide (1 pixel) : sert de fausse affiche telechargee.
# Les variations stdimage (thumbnails) sont generees a la sauvegarde, il faut
# donc une vraie image lisible par Pillow, pas des octets aleatoires.
# / Smallest valid PNG (1 pixel): used as a fake downloaded poster. stdimage
# / variations are generated on save, so Pillow must be able to read it.
PNG_1_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_import_evenement_avec_image_depuis_url(tenant):
    """La colonne img contient une URL : l'image est telechargee et enregistree
    dans le champ img de l'evenement. Le reseau est mocke (pas de vrai appel).
    / The img column holds a URL: the image is downloaded into the event's
    img field. Network is mocked (no real HTTP call)."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Affiche {suffixe}"

    # Fausse reponse HTTP : un vrai PNG, un Content-Type image.
    # / Fake HTTP response: a real PNG with an image Content-Type.
    fausse_reponse = MagicMock()
    fausse_reponse.content = PNG_1_PIXEL
    fausse_reponse.headers = {"Content-Type": "image/png"}
    fausse_reponse.raise_for_status = MagicMock()

    with tenant_context(tenant):
        uuid_evenement_importe = None
        nom_fichier_image = None
        try:
            donnees = tablib.Dataset(
                [nom_evenement, DATE_IMPORT, "https://exemple.fr/affiche-test.png"],
                headers=["name", "datetime", "img"],
            )

            ressource = EventResource()
            # On patche requests.get la ou le widget l'utilise.
            # / Patch requests.get where the widget uses it.
            with patch("Administration.admin_tenant.requests.get", return_value=fausse_reponse):
                resultat = ressource.import_data(donnees, dry_run=False, raise_errors=True)

            assert resultat.totals["new"] == 1
            assert not resultat.has_errors()

            evenement_importe = Event.objects.get(name=nom_evenement)
            uuid_evenement_importe = evenement_importe.pk

            # L'image est bien enregistree et le fichier existe dans le storage.
            # / The image is saved and the file exists in storage.
            assert evenement_importe.img, "L'evenement doit avoir une image."
            nom_fichier_image = evenement_importe.img.name
            assert default_storage.exists(nom_fichier_image)
        finally:
            if uuid_evenement_importe is not None:
                # On supprime d'abord les fichiers image (principal +
                # variations stdimage) tant que l'objet existe, puis la ligne
                # en SQL brut (meme raison que les autres tests).
                # / Delete the image files first (main + stdimage variations)
                # / while the object exists, then the row via raw SQL.
                evenement_a_nettoyer = Event.objects.get(pk=uuid_evenement_importe)
                if evenement_a_nettoyer.img:
                    evenement_a_nettoyer.img.delete(save=False)
                _supprimer_en_sql_brut("BaseBillet_event", "uuid", [uuid_evenement_importe])


def test_import_evenement_img_url_invalide_remonte_erreur(tenant):
    """Une URL qui ne pointe pas vers une image doit produire une erreur de
    ligne explicite, pas un crash ni un evenement cree sans prevenir.
    / A URL that does not serve an image must produce an explicit row error,
    not a crash nor a silently image-less event."""
    suffixe = uuid4().hex[:8]
    nom_evenement = f"Concert Mauvaise Url {suffixe}"

    # Fausse reponse HTTP : du HTML, pas une image.
    # / Fake HTTP response: HTML, not an image.
    fausse_reponse = MagicMock()
    fausse_reponse.content = b"<html>page</html>"
    fausse_reponse.headers = {"Content-Type": "text/html"}
    fausse_reponse.raise_for_status = MagicMock()

    with tenant_context(tenant):
        nombre_evenements_avant = Event.objects.count()

        donnees = tablib.Dataset(
            [nom_evenement, DATE_IMPORT, "https://exemple.fr/page.html"],
            headers=["name", "datetime", "img"],
        )

        ressource = EventResource()
        with patch("Administration.admin_tenant.requests.get", return_value=fausse_reponse):
            resultat = ressource.import_data(donnees, dry_run=False, raise_errors=False)

        # La ligne est "invalide" (ValueError du widget converti en
        # ValidationError par django-import-export) et rien n'est cree en
        # base (delta nul).
        # / The row is "invalid" (widget ValueError converted to ValidationError
        # / by django-import-export) and nothing is created (zero delta).
        assert resultat.has_validation_errors()
        assert Event.objects.count() == nombre_evenements_avant

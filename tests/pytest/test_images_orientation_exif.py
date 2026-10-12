"""
Tests : les miniatures stdimage suivent l'orientation EXIF des photos.
/ Tests: stdimage thumbnails follow the photos' EXIF orientation.

LOCALISATION : tests/pytest/test_images_orientation_exif.py

Code teste : BaseBillet/images_orientation.py, branche au demarrage par
BaseBillet/apps.py:ready() sur StdImageFieldFile.process_variation.

Les tests appellent process_variation directement, avec une image Pillow en
memoire : aucun fichier, aucune base de donnees. C'est exactement l'etape ou
stdimage transforme l'original en miniature.
/ Tests call process_variation directly on an in-memory Pillow image: no file,
no database. That is precisely where stdimage turns the original into a thumbnail.
"""

from io import BytesIO

from PIL import Image
from stdimage.models import StdImageField, StdImageFieldFile

from BaseBillet.images_orientation import ETIQUETTE_EXIF_ORIENTATION


def _photo_jpeg_640x480_avec_orientation(orientation):
    """
    Fabrique une photo JPEG 640x480 (paysage) portant l'etiquette EXIF demandee,
    puis la rouvre comme le fait stdimage (Image.open sur le fichier).
    / Builds a 640x480 landscape JPEG with the given EXIF tag, reopened like stdimage does.
    """
    photo = Image.new("RGB", (640, 480), color=(200, 30, 30))
    etiquettes_exif = Image.Exif()
    etiquettes_exif[ETIQUETTE_EXIF_ORIENTATION] = orientation

    fichier_en_memoire = BytesIO()
    photo.save(fichier_en_memoire, format="JPEG", exif=etiquettes_exif)
    fichier_en_memoire.seek(0)
    return Image.open(fichier_en_memoire)


def _variation_hdr():
    """
    Variation « hdr » telle que la declarent les modeles (1280x1280, sans recadrage).
    / The "hdr" variation as models declare it (1280x1280, no crop).
    """
    variation = dict(StdImageField.def_variation)
    variation.update({"name": "hdr", "width": 1280, "height": 1280, "crop": False})
    return variation


def test_photo_avec_orientation_6_donne_une_miniature_en_portrait():
    # Orientation 6 = le telephone etait tenu debout : la photo doit etre
    # tournee de 90 degres, donc 640x480 devient 480x640.
    # / Orientation 6 = phone held upright: 640x480 must become 480x640.
    photo_de_telephone = _photo_jpeg_640x480_avec_orientation(6)

    miniature, arguments_de_sauvegarde = StdImageFieldFile.process_variation(
        _variation_hdr(),
        image=photo_de_telephone,
    )

    assert miniature.size == (480, 640)


def test_photo_redressee_garde_son_format_pour_la_sauvegarde():
    # stdimage enregistre la miniature au format lu sur l'image. Une copie
    # Pillow perd ce format : la correction doit le recopier.
    # / stdimage saves using the image format; a Pillow copy loses it.
    photo_de_telephone = _photo_jpeg_640x480_avec_orientation(6)

    miniature, arguments_de_sauvegarde = StdImageFieldFile.process_variation(
        _variation_hdr(),
        image=photo_de_telephone,
    )

    assert arguments_de_sauvegarde["format"] == "JPEG"
    fichier_de_sortie = BytesIO()
    miniature.save(fichier_de_sortie, **arguments_de_sauvegarde)
    assert fichier_de_sortie.tell() > 0


def test_photo_deja_droite_reste_inchangee():
    # Orientation 1 = rien a faire : la miniature garde le format paysage.
    # / Orientation 1 = nothing to do: the thumbnail stays landscape.
    photo_deja_droite = _photo_jpeg_640x480_avec_orientation(1)

    miniature, arguments_de_sauvegarde = StdImageFieldFile.process_variation(
        _variation_hdr(),
        image=photo_deja_droite,
    )

    assert miniature.size == (640, 480)

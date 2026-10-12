"""
Redresse les photos selon leur orientation EXIF avant de fabriquer les miniatures.
/ Straightens photos according to their EXIF orientation before building thumbnails.

LOCALISATION : BaseBillet/images_orientation.py

LE PROBLEME QUE CE MODULE COUVRE :
Un telephone n'enregistre pas les pixels d'une photo « dans le bon sens ». Il les
enregistre comme le capteur les voit, et il ajoute une etiquette EXIF
« Orientation » (6 = tourner de 90 degres, 3 = de 180, etc.). Le navigateur lit
cette etiquette et affiche la photo droite.
django-stdimage (6.0.2) fabrique les miniatures (thumbnail, crop, hdr, fhd...)
en redimensionnant les pixels BRUTS, puis les enregistre SANS l'etiquette.
Resultat : l'original s'affiche droit, toutes les miniatures s'affichent couchees.
/ Phones store raw sensor pixels plus an EXIF Orientation tag. stdimage resizes
the raw pixels and saves the thumbnail without the tag, so thumbnails show
rotated while the original shows upright.

LA CORRECTION :
On remplace StdImageFieldFile.process_variation par une version qui applique
d'abord ImageOps.exif_transpose. Un seul point d'entree couvre TOUS les
StdImageField du projet (BaseBillet, pages, crowds, MetaBillet, QrcodeCashless),
qu'ils soient remplis par l'admin, l'API v2 ou un script.
/ We replace process_variation with a version that applies exif_transpose first.
One entry point covers every StdImageField in the project.

POURQUOI UNE SURCHARGE AU DEMARRAGE ET PAS UNE SOUS-CLASSE DE CHAMP :
une sous-classe obligerait a changer chaque declaration de champ (une vingtaine)
et creerait des migrations AlterField dans cinq applications, sans rien changer
en base. La surcharge ne touche aucun modele.
/ A field subclass would change ~20 field declarations and add no-op migrations
in five apps. The override touches no model.

FLUX :
BaseBillet/apps.py:BasebilletConfig.ready()
  -> brancher_orientation_exif_sur_stdimage()   (une seule fois au demarrage)
Ensuite, a chaque enregistrement d'image :
  stdimage StdImageFieldFile.render_variation()
  -> process_variation_avec_orientation_exif()   (CETTE VERSION)
  -> process_variation d'origine de stdimage      (redimensionnement)

REPARATION DES IMAGES DEJA EN BASE :
pages/management/commands/regenerer_variations_exif.py
"""

from PIL import ImageOps
from stdimage.models import StdImageFieldFile

# Numero de l'etiquette EXIF « Orientation » (norme EXIF, tag 274).
# / EXIF "Orientation" tag number (EXIF standard, tag 274).
ETIQUETTE_EXIF_ORIENTATION = 0x0112

# Valeur 1 = la photo est deja droite, rien a faire.
# / Value 1 = the photo is already upright, nothing to do.
ORIENTATION_DEJA_DROITE = 1


def lire_orientation_exif(image):
    """
    Renvoie l'orientation EXIF d'une image Pillow (1 si absente).
    / Returns the EXIF orientation of a Pillow image (1 when missing).
    """
    etiquettes_exif = image.getexif()
    orientation = etiquettes_exif.get(
        ETIQUETTE_EXIF_ORIENTATION, ORIENTATION_DEJA_DROITE
    )
    return orientation


# On garde la fonction d'origine de stdimage pour l'appeler apres le redressement.
# `.__func__` : process_variation est une classmethod, on recupere la fonction nue.
# / Keep stdimage's original function to call it after straightening.
_process_variation_d_origine = StdImageFieldFile.process_variation.__func__


def process_variation_avec_orientation_exif(cls, variation, image):
    """
    Redresse l'image selon son EXIF, puis laisse stdimage fabriquer la miniature.
    / Straightens the image from its EXIF, then lets stdimage build the thumbnail.

    :param variation: dictionnaire de variation stdimage (name, width, height, crop...)
    :param image: image Pillow ouverte sur le fichier original
    :return: (image, arguments de sauvegarde), comme la version d'origine
    """
    orientation = lire_orientation_exif(image)
    if orientation == ORIENTATION_DEJA_DROITE:
        return _process_variation_d_origine(cls, variation, image)

    # exif_transpose renvoie une COPIE tournee. Une copie Pillow perd son
    # attribut `format` (JPEG, PNG...), or stdimage s'en sert pour choisir le
    # format d'enregistrement : sans lui, la sauvegarde echoue. On le recopie.
    # / exif_transpose returns a rotated COPY, which loses `format`; stdimage
    # needs it to pick the save format, so we copy it over.
    format_du_fichier_original = image.format
    image_redressee = ImageOps.exif_transpose(image)
    image_redressee.format = format_du_fichier_original

    return _process_variation_d_origine(cls, variation, image_redressee)


def brancher_orientation_exif_sur_stdimage():
    """
    Installe process_variation_avec_orientation_exif dans stdimage.
    Appelee une seule fois, par BaseBillet/apps.py:ready().
    / Installs the EXIF-aware process_variation into stdimage. Called once by ready().
    """
    StdImageFieldFile.process_variation = classmethod(
        process_variation_avec_orientation_exif
    )

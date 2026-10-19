"""
Images responsives du skin V2 : hero a deux tailles, quinconce en srcset.
/ V2 skin responsive images: two-size hero, srcset on the image + text block.

LOCALISATION : tests/pytest/test_pages_images_responsives.py

Hero (bloc banniere et accueil par defaut) : hdr sous 64rem, fhd au-dessus.
Le preload doit suivre le meme seuil, sinon le navigateur telecharge les deux.
Quinconce (_section_texte_image.html) : srcset med/hdr avec les vraies largeurs
des fichiers, plus width/height contre le decalage de mise en page.

Pas de base de donnees ni de fichier image : les variantes sont des objets
simples qui portent url, width et height, comme les variantes de stdimage.
/ No database or image file: variations are plain objects carrying url,
width and height, like stdimage variations.
"""

from types import SimpleNamespace

from django.template.loader import render_to_string


def _variante(nom, largeur, hauteur):
    """Une variante d'image comme celles de stdimage (url, width, height).
    / An image variation like stdimage's (url, width, height)."""
    return SimpleNamespace(
        url=f"/media/images/photo.{nom}.jpg", width=largeur, height=hauteur
    )


def _config_avec_image():
    """Une Configuration dont l'image du lieu a ses variantes hdr et fhd.
    / A Configuration whose venue image has hdr and fhd variations."""
    image_du_lieu = SimpleNamespace(
        hdr=_variante("hdr", 1280, 720),
        fhd=_variante("fhd", 1920, 1080),
    )
    return SimpleNamespace(img=image_du_lieu)


def test_hero_v2_pose_les_deux_tailles_d_image():
    """Le bloc banniere V2 donne la petite (hdr) et la grande (fhd) image au CSS.
    / The V2 banner block gives both the hdr and fhd images to the CSS."""
    bloc = SimpleNamespace(titre="Le lieu", sous_titre="")

    html = render_to_string(
        "pages/V2/partials/bloc_section_banniere.html",
        {"bloc": bloc, "config": _config_avec_image()},
    )

    assert "--tb-hero-image: url('/media/images/photo.fhd.jpg');" in html
    assert "--tb-hero-image-petit: url('/media/images/photo.hdr.jpg');" in html


def _section_texte_image(image):
    """Rend le quinconce V2 avec l'image donnee. / Renders the V2 block."""
    bloc = SimpleNamespace(
        image=image, titre="Une capture", texte="", bouton_label=""
    )
    return render_to_string(
        "pages/V2/partials/_section_texte_image.html",
        {"bloc": bloc, "cote": "gauche"},
    )


def test_quinconce_v2_propose_med_et_hdr_au_navigateur():
    """Le srcset donne med et hdr avec leurs vraies largeurs, plus sizes.
    / The srcset lists med and hdr with their real widths, plus sizes."""
    image = SimpleNamespace(
        med=_variante("med", 480, 270),
        hdr=_variante("hdr", 1280, 720),
    )

    html = _section_texte_image(image)

    assert (
        'srcset="/media/images/photo.med.jpg 480w, /media/images/photo.hdr.jpg 1280w"'
        in html
    )
    assert 'sizes="(max-width: 48rem) 100vw, (max-width: 72rem) 50vw, 36rem"' in html
    assert 'width="1280" height="720"' in html
    assert 'src="/media/images/photo.hdr.jpg"' in html


def test_quinconce_v2_sans_srcset_pour_une_petite_image():
    """Une image d'origine plus petite que 480 px : med et hdr ont la meme
    largeur, le srcset n'apporterait rien.
    / A source smaller than 480 px: med and hdr share a width, no srcset."""
    image = SimpleNamespace(
        med=_variante("med", 400, 300),
        hdr=_variante("hdr", 400, 300),
    )

    html = _section_texte_image(image)

    assert "srcset=" not in html
    assert 'width="400" height="300"' in html

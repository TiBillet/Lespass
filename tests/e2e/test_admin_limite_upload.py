"""
Tests E2E : dans l'admin, un fichier trop lourd pour nginx est refuse AVANT l'envoi.
/ E2E tests: in the admin, a file too heavy for nginx is rejected BEFORE sending.

LOCALISATION : tests/e2e/test_admin_limite_upload.py
Script teste : static/js/admin_limite_upload.js

nginx refuse les requetes de plus de 12 Mo (client_max_body_size 12M) avec sa
propre page 413 : le formulaire rempli est perdu. Le script de l'admin vide le
champ fichier trop lourd, affiche un message sous le champ, et laisse le reste
du formulaire intact.
/ nginx rejects requests over 12 MB with its own 413 page (form lost). The admin
script empties the heavy file field, shows a message, keeps the rest of the form.

Page utilisee : l'ajout d'un evenement (champ image « img »). Rien n'est enregistre :
le formulaire n'est jamais soumis.
/ Page used: event add form (image field "img"). Nothing is saved: never submitted.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>`.
pytestmark = [pytest.mark.e2e, pytest.mark.admin]

ADRESSE_AJOUT_EVENEMENT = f"{BASE_URL}/admin/BaseBillet/event/add/"
UN_MEGA_OCTET = 1024 * 1024


def _fichier_image_factice(poids_en_octets):
    """
    Un fichier « .jpg » du poids demande. Son contenu n'est jamais lu : seul le
    poids compte pour le script.
    / A ".jpg" file of the given weight. Content never read: only weight matters.
    """
    return {
        "name": "photo_test.jpg",
        "mimeType": "image/jpeg",
        "buffer": b"0" * poids_en_octets,
    }


def test_admin_refuse_un_fichier_trop_lourd_et_garde_le_formulaire(
    page, login_as_admin
):
    """
    Un fichier de 13 Mo est refuse des qu'il est choisi : message visible, champ
    fichier vide, nom de l'evenement deja saisi toujours la.
    / A 13 MB file is rejected on selection: visible message, empty file field,
    already-typed event name kept.
    """
    login_as_admin(page)
    page.goto(ADRESSE_AJOUT_EVENEMENT)

    champ_nom = page.locator("#id_name")
    champ_nom.fill("Nom saisi avant le fichier")

    champ_image = page.locator('input[type="file"][name="img"]')
    champ_image.set_input_files(_fichier_image_factice(13 * UN_MEGA_OCTET))

    message_d_erreur = page.locator('[data-testid="admin-upload-erreur-poids"]')
    expect(message_d_erreur).to_be_visible()
    expect(message_d_erreur).to_contain_text("13")

    nombre_de_fichiers_gardes = champ_image.evaluate("champ => champ.files.length")
    assert nombre_de_fichiers_gardes == 0

    expect(champ_nom).to_have_value("Nom saisi avant le fichier")


def test_admin_accepte_un_fichier_leger_sans_message(page, login_as_admin):
    """
    Un fichier de 1 Mo est garde, sans message d'erreur.
    / A 1 MB file is kept, with no error message.
    """
    login_as_admin(page)
    page.goto(ADRESSE_AJOUT_EVENEMENT)

    champ_image = page.locator('input[type="file"][name="img"]')
    champ_image.set_input_files(_fichier_image_factice(UN_MEGA_OCTET))

    expect(page.locator('[data-testid="admin-upload-erreur-poids"]')).to_have_count(0)
    nombre_de_fichiers_gardes = champ_image.evaluate("champ => champ.files.length")
    assert nombre_de_fichiers_gardes == 1


def test_admin_efface_le_message_quand_un_fichier_leger_remplace_le_lourd(
    page, login_as_admin
):
    """
    Apres un refus, choisir un fichier leger retire le message.
    / After a refusal, choosing a light file removes the message.
    """
    login_as_admin(page)
    page.goto(ADRESSE_AJOUT_EVENEMENT)

    champ_image = page.locator('input[type="file"][name="img"]')
    champ_image.set_input_files(_fichier_image_factice(13 * UN_MEGA_OCTET))
    expect(page.locator('[data-testid="admin-upload-erreur-poids"]')).to_be_visible()

    champ_image.set_input_files(_fichier_image_factice(UN_MEGA_OCTET))
    expect(page.locator('[data-testid="admin-upload-erreur-poids"]')).to_have_count(0)


def test_admin_compte_le_total_des_fichiers_de_tous_les_champs(page, login_as_admin):
    """
    8 Mo dans « Image principale » passent. 6 Mo de plus dans « Ajouter des images »
    font 14 Mo au total : ce second choix est refuse, le premier fichier est garde.
    / 8 MB in the main image pass. 6 MB more in the gallery make 14 MB: the second
    choice is refused, the first file is kept.
    """
    login_as_admin(page)
    page.goto(ADRESSE_AJOUT_EVENEMENT)

    champ_image_principale = page.locator('input[type="file"][name="img"]')
    champ_galerie = page.locator('input[type="file"][name="galerie_nouvelles_images"]')

    champ_image_principale.set_input_files(_fichier_image_factice(8 * UN_MEGA_OCTET))
    champ_galerie.set_input_files(_fichier_image_factice(6 * UN_MEGA_OCTET))

    message_d_erreur = page.locator('[data-testid="admin-upload-erreur-poids"]')
    expect(message_d_erreur).to_have_count(1)
    expect(message_d_erreur).to_contain_text("8 Mo")

    assert champ_galerie.evaluate("champ => champ.files.length") == 0
    assert champ_image_principale.evaluate("champ => champ.files.length") == 1


def test_admin_remet_le_libelle_du_champ_apres_un_refus(page, login_as_admin):
    """
    Apres un refus, le libelle du champ Unfold redevient celui du chargement de la
    page. Sur une fiche existante, c'est l'adresse de l'image enregistree : la
    personne voit qu'elle n'a pas perdu son image.
    / After a refusal, the Unfold field label goes back to its page-load text.
    """
    login_as_admin(page)
    page.goto(ADRESSE_AJOUT_EVENEMENT)

    champ_image = page.locator('input[type="file"][name="img"]')
    # Le libelle : l'<input type="text" disabled> du cadre Unfold, a cote du champ fichier.
    # / The label: the disabled text input of the Unfold frame.
    identifiant_du_champ = champ_image.get_attribute("id")
    libelle_du_champ = page.locator(
        f'label[for="{identifiant_du_champ}"] input[type="text"][disabled]'
    )
    libelle_au_chargement = libelle_du_champ.input_value()

    champ_image.set_input_files(_fichier_image_factice(UN_MEGA_OCTET))
    expect(libelle_du_champ).to_have_value("photo_test.jpg")

    champ_image.set_input_files(_fichier_image_factice(13 * UN_MEGA_OCTET))
    expect(page.locator('[data-testid="admin-upload-erreur-poids"]')).to_be_visible()
    expect(libelle_du_champ).to_have_value(libelle_au_chargement)

"""
Page « Ajouter une adhésion » : le champ « Numéro de carte » porte un bouton qui lit
le QR code de la carte à la caméra.
/ "Add membership" page: the card number field has a camera QR code reader button.

LOCALISATION : tests/pytest/test_admin_membership_scan_qr_carte.py

Code testé :
- Administration/admin_tenant.py — CardNumberQrScanWidget, MembershipAddForm.card_number
- Administration/templates/admin/widgets/card_number_qr_scan.html

Ce test vérifie seulement le rendu côté serveur : le champ, le bouton et le script.
La lecture du QR code (extraction de l'UUID, mise en majuscules) se fait en JavaScript :
pytest ne peut pas l'exécuter. Elle se vérifie à la main (voir le fichier CHANGELOG).
/ Server-side rendering only. The JS QR reading is checked by hand.
"""

import pytest

pytestmark = pytest.mark.django_db


def test_la_page_d_ajout_d_adhesion_affiche_le_bouton_de_scan_de_carte(admin_client):
    # L'admin ouvre le formulaire d'ajout d'une adhésion.
    # / The admin opens the add membership form.
    reponse = admin_client.get("/admin/BaseBillet/membership/add/")
    assert reponse.status_code == 200

    html_de_la_page = reponse.content.decode()

    # Le champ d'origine est toujours là : la saisie à la main reste possible.
    # / The original input is still there: manual input stays possible.
    assert 'name="card_number"' in html_de_la_page

    # Le bouton « Flasher », la vidéo et la zone de message sont rendus.
    # / The scan button, the video and the message area are rendered.
    assert 'data-testid="membership-card-qr-start"' in html_de_la_page
    assert 'data-testid="membership-card-qr-video"' in html_de_la_page
    assert 'data-testid="membership-card-qr-message"' in html_de_la_page

    # Le script importe la lib de lecture de QR code déjà présente dans le projet.
    # / The script imports the QR code library already in the project.
    assert "commun/js/qr-scanner.min.js" in html_de_la_page

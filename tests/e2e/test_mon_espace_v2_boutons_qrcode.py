"""
tests/e2e/test_mon_espace_v2_boutons_qrcode.py
Les boutons de paiement par QR code de « Mon espace » (skin V2), a l'ecran.
/ The QR code payment buttons of "My space" (V2 skin), on screen.

LOCALISATION : tests/e2e/test_mon_espace_v2_boutons_qrcode.py

CE QUE CE FICHIER VERIFIE / WHAT THIS FILE CHECKS
--------------------------------------------------
L'admin du lieu ouvre `/my_account/` a deux largeurs : 375 px (telephone) et
1280 px (ordinateur). Dans les deux cas :
- le bandeau « Initier un paiement » prend toute la largeur du module « Mes
  responsabilites » ;
- les libelles ne debordent pas de leur bouton, et les boutons restent dans l'ecran ;
- les deux boutons sont visibles : « Initier un paiement » (bandeau) et, sous « Ma
  carte », le bouton du scanner. Sa variante suit l'email de l'admin des E2E, lu en
  base au depart : bleu « Scanner un QR code de paiement » si l'email est valide,
  gris desactive « Please valid your email… » sinon (le libelle le plus long, celui
  qui risque le plus de deborder). Le bouton bleu est clique par l'adherent du
  parcours `test_adhesion_recompense_puis_qrcode.py`.
A 375 px, le texte du bandeau et son bouton sont empiles. A 1280 px, ils sont cote a
cote. Une capture de chaque largeur est ecrite dans `tests/e2e/artefacts/captures/`
(dossier ignore par git), pour un controle a l'oeil.

Le rendu des boutons selon le profil (caissier, simple adherent, email non valide…)
est verifie en pytest : `tests/pytest/test_mon_espace_v2_boutons_qrcode.py`. Le
parcours complet avec les clics est dans `test_adhesion_recompense_puis_qrcode.py`.
/ Profile-dependent rendering is checked in pytest; the full click-through journey
lives in test_adhesion_recompense_puis_qrcode.py.

AUCUNE EMISSION DE MONNAIE / NO MONEY ISSUED
---------------------------------------------
L'index V2 lit le solde de l'admin sur le Fedow de dev : le Fedow doit repondre.
Rien n'est ecrit, ni sur le Fedow, ni en base.
/ The V2 index reads the balance on the dev Fedow; nothing is written.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne, le Fedow de dev repond ;
- le lieu `lespass` est en skin V2. Sinon : `docker exec lespass_django poetry run
  python manage.py charger_site_lespass`.

Lancement / Run:
    make e2e ARGS="tests/e2e/test_mon_espace_v2_boutons_qrcode.py"
"""

import os
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import DOSSIER_ARTEFACTS

DOSSIER_DES_CAPTURES = os.path.join(DOSSIER_ARTEFACTS, "captures")

# Tolerance des comparaisons de positions, en pixels (arrondis du navigateur).
# / Position comparison tolerance, in pixels (browser rounding).
TOLERANCE_EN_PIXELS = 2


@pytest.fixture(scope="module")
def lieu_en_skin_v2(django_shell):
    """Echoue, avec la consigne, si le lieu n'est pas en skin V2.

    Le skin se LIT en base, par `objects.first()`. Jamais `get_solo()` : il cree la
    ligne si elle manque, et passe par le cache memcached partage avec le serveur.
    / Fails with what to do if the venue is not on the V2 skin. Read only.
    """
    sortie = django_shell(
        "from pages.models import ConfigurationSite\n"
        "configuration_du_site = ConfigurationSite.objects.first()\n"
        "print('SKIN=' + (configuration_du_site.skin if configuration_du_site\n"
        "                 else 'AUCUNE_CONFIGURATION'))"
    )
    trouve = re.search(r"SKIN=(\S+)", sortie)
    skin_du_lieu = trouve.group(1) if trouve else None
    if skin_du_lieu != "V2":
        pytest.fail(
            f"Le lieu 'lespass' n'est pas en skin V2 (lu : {skin_du_lieu}). Ces "
            "boutons sont ceux de l'index V2. Remettre le skin : docker exec "
            "lespass_django poetry run python manage.py charger_site_lespass"
        )
    return skin_du_lieu


@pytest.fixture(scope="module")
def testid_du_bouton_scanner_de_l_admin(django_shell, admin_email):
    """Le `data-testid` du bouton scanner que l'admin des E2E doit voir.

    Lu en base, sans rien ecrire : le test ne change pas l'email de l'admin.
    / The scanner button testid the E2E admin must see. Read only.
    """
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        f"admin = TibilletUser.objects.get(email='{admin_email}')\n"
        "print('EMAIL_VALIDE=' + str(bool(admin.email_valid)))"
    )
    if "EMAIL_VALIDE=True" in sortie:
        return "compte-scanner-qrcode"
    return "compte-scanner-qrcode-email-non-valide"


# Mesures faites dans le navigateur : les boites des elements, et le debordement
# de chaque libelle (largeur du contenu plus grande que la largeur visible).
# / Measured in the browser: element boxes, and each label's overflow.
SCRIPT_DE_MESURE = """
(testid_du_bouton_scanner) => {
    const boite = (element) => {
        const rectangle = element.getBoundingClientRect();
        return {gauche: rectangle.left, droite: rectangle.right,
                haut: rectangle.top, bas: rectangle.bottom, largeur: rectangle.width};
    };
    const deborde = (element) => element.scrollWidth > element.clientWidth + 1;

    const bandeau = document.querySelector('[data-testid="compte-initier-paiement"]');
    const texte = bandeau.querySelector('.compte__encaisser-texte');
    const bouton_encaisser = document.querySelector('[data-testid="compte-initier-paiement-bouton"]');
    const bouton_scanner = document.querySelector(`[data-testid="${testid_du_bouton_scanner}"]`);
    const corps_du_module = bandeau.parentElement;
    const style_du_bandeau = getComputedStyle(bandeau);

    return {
        largeur_de_l_ecran: document.documentElement.clientWidth,
        // Place disponible pour le bandeau : le corps du module, moins ses marges.
        // / Room available for the banner: the module body minus its margins.
        largeur_disponible: corps_du_module.clientWidth
            - parseFloat(style_du_bandeau.marginLeft)
            - parseFloat(style_du_bandeau.marginRight),
        bandeau: boite(bandeau),
        texte: boite(texte),
        bouton_encaisser: boite(bouton_encaisser),
        bouton_scanner: boite(bouton_scanner),
        texte_deborde: deborde(texte),
        bouton_encaisser_deborde: deborde(bouton_encaisser),
        bouton_scanner_deborde: deborde(bouton_scanner),
    };
}
"""


@pytest.mark.parametrize("largeur_de_l_ecran", [375, 1280])
def test_les_boutons_qrcode_de_mon_espace_v2_tiennent_dans_l_ecran(
    page,
    login_as_admin,
    lieu_en_skin_v2,
    testid_du_bouton_scanner_de_l_admin,
    largeur_de_l_ecran,
):
    """Bandeau pleine largeur, libelles sans debordement, deux boutons visibles.
    / Full-width banner, no label overflow, both buttons visible."""
    page.set_viewport_size({"width": largeur_de_l_ecran, "height": 900})
    login_as_admin(page)
    page.goto("/my_account/")

    bouton_encaisser = page.get_by_test_id("compte-initier-paiement-bouton")
    bouton_scanner = page.get_by_test_id(testid_du_bouton_scanner_de_l_admin)
    expect(
        bouton_encaisser,
        "Pas de bouton « Initier un paiement » : l'admin des E2E n'a plus le droit "
        "d'encaisser sur ce lieu, ou le bandeau a quitte l'index V2.",
    ).to_be_visible()
    expect(
        bouton_scanner,
        f"Pas de bouton '{testid_du_bouton_scanner_de_l_admin}' : le bouton du "
        "scanner a quitte « Ma carte », ou ne suit plus l'email de l'admin.",
    ).to_be_visible()

    # Les messages flottants (ex. « Merci de valider votre adresse mail… ») se
    # posent en bas a droite et peuvent couvrir le bandeau : on les ferme, comme le
    # ferait l'utilisateur, avant la capture.
    # / Floating toasts may cover the banner: close them, as a user would.
    boutons_fermer_les_messages = page.locator("#toastContainer .toast.show .btn-close")
    for _numero_du_message in range(boutons_fermer_les_messages.count()):
        boutons_fermer_les_messages.first.click()
    expect(page.locator("#toastContainer .toast.show")).to_have_count(0)

    # Le bouton du bandeau recoit bien le clic : rien ne le recouvre. Essai sans
    # clic (`trial`) : Playwright verifie seulement qu'il est cliquable.
    # / The banner button receives the click: nothing covers it (trial, no click).
    bouton_encaisser.click(trial=True, timeout=3000)

    os.makedirs(DOSSIER_DES_CAPTURES, exist_ok=True)
    page.screenshot(
        path=os.path.join(
            DOSSIER_DES_CAPTURES,
            f"mon_espace_v2_boutons_qrcode_{largeur_de_l_ecran}.png",
        ),
        full_page=True,
    )

    mesures = page.evaluate(SCRIPT_DE_MESURE, testid_du_bouton_scanner_de_l_admin)

    # Le bandeau prend toute la place du module : il n'est pas range dans la grille.
    # / The banner takes the whole module width: it is not inside the grid.
    assert abs(mesures["bandeau"]["largeur"] - mesures["largeur_disponible"]) <= (
        TOLERANCE_EN_PIXELS
    ), f"Le bandeau n'est pas pleine largeur : {mesures}"

    # Aucun libelle ne deborde, et les boutons restent dans l'ecran.
    # / No label overflows, and the buttons stay on screen.
    assert not mesures["texte_deborde"], f"Le texte du bandeau deborde : {mesures}"
    assert not mesures["bouton_encaisser_deborde"], (
        f"Le libelle « Initier un paiement » deborde : {mesures}"
    )
    assert not mesures["bouton_scanner_deborde"], (
        f"Le libelle du bouton scanner deborde : {mesures}"
    )
    for nom_du_bouton in ("bouton_encaisser", "bouton_scanner"):
        boite_du_bouton = mesures[nom_du_bouton]
        assert boite_du_bouton["gauche"] >= -TOLERANCE_EN_PIXELS, (
            f"Le {nom_du_bouton} sort de l'ecran a gauche : {mesures}"
        )
        assert (
            boite_du_bouton["droite"]
            <= mesures["largeur_de_l_ecran"] + TOLERANCE_EN_PIXELS
        ), f"Le {nom_du_bouton} sort de l'ecran a droite : {mesures}"

    texte = mesures["texte"]
    bouton = mesures["bouton_encaisser"]
    if largeur_de_l_ecran == 375:
        # Telephone : le bouton passe sous le texte.
        # / Phone: the button goes below the text.
        assert bouton["haut"] >= texte["bas"] - TOLERANCE_EN_PIXELS, (
            f"A 375 px, le bouton du bandeau n'est pas sous le texte : {mesures}"
        )
    else:
        # Ordinateur : texte a gauche, bouton a droite, sur la meme ligne.
        # / Desktop: text on the left, button on the right, same row.
        assert bouton["gauche"] >= texte["droite"] - TOLERANCE_EN_PIXELS, (
            f"A 1280 px, le bouton du bandeau n'est pas a droite du texte : {mesures}"
        )
        assert bouton["haut"] < texte["bas"] and bouton["bas"] > texte["haut"], (
            f"A 1280 px, le bouton et le texte du bandeau ne sont pas sur la meme "
            f"ligne : {mesures}"
        )

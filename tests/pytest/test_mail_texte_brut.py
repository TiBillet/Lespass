"""
Tests de la version texte brut (text/plain) des mails.
/ Tests of the emails' plain-text (text/plain) version.

LOCALISATION : tests/pytest/test_mail_texte_brut.py

Code testé / Tested code : BaseBillet/tasks.py (texte_brut_depuis_le_html, CeleryMailerClass)

Sans texte brut, le text/plain partait vide : mail-tester relevait MIME_HTML_ONLY
et MPART_ALT_DIFF (-0,8 point SpamAssassin au total).
/ Without plain text, text/plain was empty: mail-tester flagged MIME_HTML_ONLY
and MPART_ALT_DIFF (-0.8 SpamAssassin points in total).

Les mails sont lus dans `mailoutbox` (pytest-django) : rien ne part vraiment.
/ Emails are read from `mailoutbox` (pytest-django): nothing is really sent.

Lancer / Run : make test ARGS="tests/pytest/test_mail_texte_brut.py"
"""

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.tasks import texte_brut_depuis_le_html

pytestmark = pytest.mark.django_db

URL_DE_CONFIRMATION = "https://lespass.tibillet.localhost/emailconfirmation/JETON"


# --- La conversion / The conversion ---


def test_le_texte_d_apercu_masque_n_apparait_pas():
    """
    Le texte d'aperçu (div display:none) sert à la liste des mails, pas au corps.
    / The preview text (display:none div) is for the inbox list, not the body.
    """
    html = (
        '<div style="display:none; max-height:0;">Texte d aperçu<div>imbriqué</div></div>'
        "<p>Corps du mail</p>"
    )

    texte = texte_brut_depuis_le_html(html)

    assert "aperçu" not in texte
    assert "imbriqué" not in texte
    assert texte == "Corps du mail"


def test_le_style_et_le_titre_n_apparaissent_pas():
    """Le contenu de <head>, <style> et <title> est ignoré. / <head>, <style>, <title> content is ignored."""
    html = "<html><head><title>Sujet</title><style>p {color: red;}</style></head><body><p>Bonjour</p></body></html>"

    assert texte_brut_depuis_le_html(html) == "Bonjour"


def test_un_lien_est_ecrit_en_clair_apres_son_texte():
    """
    Sans l'adresse en clair, un lecteur en texte brut ne peut pas cliquer le bouton.
    / Without the plain address, a plain-text reader cannot click the button.
    """
    html = f'<p><a href="{URL_DE_CONFIRMATION}">Confirmer mon email</a></p>'

    assert texte_brut_depuis_le_html(html) == f"Confirmer mon email ({URL_DE_CONFIRMATION})"


def test_les_blocs_passent_a_la_ligne_et_les_espaces_sont_resserres():
    """Un bloc = une ligne, une seule ligne vide entre deux blocs. / One block = one line, one blank line between."""
    html = "<table><tr><td>  Premier   paragraphe  </td></tr></table>\n\n\n<p>Second&nbsp;paragraphe</p>"

    assert texte_brut_depuis_le_html(html) == "Premier paragraphe\n\nSecond paragraphe"


# --- Le mail envoyé / The sent email ---


def test_un_mail_a_gabarit_part_avec_un_texte_brut_fidele_au_html(tenant, mailoutbox):
    """
    Le mail de confirmation (celui testé par mail-tester) a un text/plain rempli,
    qui reprend le texte du HTML et le lien du bouton.
    / The confirmation email (the one mail-tester checked) has a filled text/plain,
    with the HTML's text and the button link.
    """
    from BaseBillet.tasks import CeleryMailerClass

    with tenant_context(tenant):
        mail = CeleryMailerClass(
            email="destinataire@mock.test",
            title="Lespass : Confirmez votre email",
            template="emails/connexion.html",
            context={
                "organisation": "Lespass",
                "connexion_url": URL_DE_CONFIRMATION,
                "base_url": "https://lespass.tibillet.localhost",
            },
        )
        mail.send()

    assert len(mailoutbox) == 1
    texte_brut = mailoutbox[0].body
    assert "Merci de confirmer votre email pour Lespass." in texte_brut
    assert f"Confirmer mon email ({URL_DE_CONFIRMATION})" in texte_brut
    assert "<" not in texte_brut

    message_mime = mailoutbox[0].message()
    types_des_parties = [partie.get_content_type() for partie in message_mime.walk()]
    assert "text/plain" in types_des_parties
    assert "text/html" in types_des_parties


def test_un_texte_fourni_par_l_appelant_est_garde(tenant, mailoutbox):
    """
    Les mails qui ont leur gabarit .txt (codes OTP, onboarding) gardent leur texte.
    / Emails with their own .txt template (OTP codes, onboarding) keep their text.
    """
    from BaseBillet.tasks import CeleryMailerClass

    with tenant_context(tenant):
        mail = CeleryMailerClass(
            email="destinataire@mock.test",
            title="Votre code",
            text="Votre code : 123456",
            template="emails/connexion.html",
            context={"organisation": "Lespass", "connexion_url": URL_DE_CONFIRMATION},
        )
        mail.send()

    assert mailoutbox[0].body == "Votre code : 123456"

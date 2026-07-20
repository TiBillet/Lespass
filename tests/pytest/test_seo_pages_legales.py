"""
Tests des pages legales du site ROOT public.
/ Tests for the public ROOT site legal pages.

LOCALISATION : tests/pytest/test_seo_pages_legales.py

Ces tests protegent une exigence LEGALE, pas une preference d'affichage.
Les mentions legales sont imposees par la LCEN (article 6-III) et la
politique de confidentialite par le RGPD (articles 13 et 14). Une route
cassee ou un lien de pied de page supprime par megarde met la cooperative
en infraction, en silence : rien ne plante, la page disparait simplement.

C'est exactement le genre de regression qu'aucun autre test ne rattrape,
d'ou ce fichier.
/ These tests guard a LEGAL requirement, not a display preference. A broken
route or a removed footer link silently puts the coop out of compliance.

PIEGE RENCONTRE PENDANT L'ECRITURE DE CES PAGES :
La syntaxe de commentaire courte de Django ne fonctionne que sur UNE SEULE
ligne. Etalee sur plusieurs lignes, elle n'est plus un commentaire : Django
execute son contenu. Les gabarits legaux utilisent donc le tag "comment".
Le test qui rend reellement chaque page attrape ce cas.
/ Django's short comment syntax is single-line only; multi-line usage is
executed, not ignored. Rendering each page catches this.
"""

import pytest
from django.test import Client
from django.urls import reverse

# Domaine du tenant public en developpement. django-tenants choisit le schema
# a partir de l'en-tete Host : sans lui, la requete part sur un autre tenant
# et les routes de seo/urls.py n'existent pas.
# / Public tenant domain in dev. django-tenants picks the schema from the Host
# header; without it the request lands on another tenant.
DOMAINE_TENANT_PUBLIC = "tibillet.localhost"

# reverse() interroge l'urlconf par DEFAUT, qui est celui des tenants
# (TiBillet/urls_tenants.py). L'app `seo` n'y est pas montee : elle ne vit que
# dans l'urlconf du schema public. Sans ce parametre explicite, reverse() leve
# "'seo' is not a registered namespace" alors que la route existe bel et bien.
# / reverse() queries the DEFAULT urlconf (tenants). The `seo` app only lives
# in the public-schema urlconf, hence this explicit parameter.
URLCONF_DU_TENANT_PUBLIC = "TiBillet.urls_public"

# Les trois documents legaux, avec le nom de route et un extrait de texte qui
# doit imperativement apparaitre dans la page rendue.
# / The three legal documents: route name plus a snippet that must appear.
PAGES_LEGALES = [
    ("seo:mentions_legales", "/mentions-legales/", "913 628 665"),
    ("seo:cgu", "/cgu/", "TiBillet est un outil, pas un vendeur de billets"),
    ("seo:confidentialite", "/confidentialite/", "Nous ne vendons aucune donnée"),
]


@pytest.fixture
def client_public():
    """
    Client de test pointant sur le tenant public.
    / Test client targeting the public tenant.
    """
    return Client(SERVER_NAME=DOMAINE_TENANT_PUBLIC)


@pytest.mark.django_db
@pytest.mark.parametrize("nom_de_route, chemin_attendu, extrait_attendu", PAGES_LEGALES)
def test_la_page_legale_repond_et_contient_son_texte(
    client_public, nom_de_route, chemin_attendu, extrait_attendu
):
    """
    Chaque page legale repond 200 et affiche bien son contenu.
    / Each legal page returns 200 and shows its content.

    On verifie trois choses d'un coup :
    1. La route est bien montee sur le tenant public.
    2. Le chemin de l'URL n'a pas bouge (il est cite dans des documents
       imprimes et dans des e-mails deja envoyes).
    3. Le gabarit se rend sans erreur et le texte est bien la.
    """
    # Le chemin doit rester stable : il circule hors du site.
    # / The path must stay stable: it travels outside the site.
    assert reverse(nom_de_route, urlconf=URLCONF_DU_TENANT_PUBLIC) == chemin_attendu

    reponse = client_public.get(chemin_attendu)

    assert reponse.status_code == 200

    html_de_la_page = reponse.content.decode("utf-8")
    assert extrait_attendu in html_de_la_page


@pytest.mark.django_db
def test_le_pied_de_page_public_pointe_vers_les_trois_pages_legales(client_public):
    """
    La landing publique affiche les trois liens legaux dans son pied de page.
    / The public landing shows the three legal links in its footer.

    Une page legale que personne ne peut atteindre depuis l'accueil ne remplit
    pas son role : la loi demande qu'elle soit accessible, pas seulement
    qu'elle existe.
    / A legal page nobody can reach from the home page does not do its job.
    """
    reponse = client_public.get("/")

    assert reponse.status_code == 200

    html_de_la_landing = reponse.content.decode("utf-8")

    for chemin_legal in ["/mentions-legales/", "/cgu/", "/confidentialite/"]:
        assert chemin_legal in html_de_la_landing


@pytest.mark.django_db
def test_les_pages_legales_sont_listees_dans_le_sitemap_root(client_public):
    """
    Le sitemap ROOT declare les trois pages legales.
    / The ROOT sitemap declares the three legal pages.

    Les pages legales sont indexables a dessein : leur presence est un signal
    de confiance, et les outils d'audit de conformite les cherchent depuis le
    sitemap autant que depuis le pied de page.
    """
    reponse = client_public.get("/sitemap-root.xml")

    assert reponse.status_code == 200

    xml_du_sitemap = reponse.content.decode("utf-8")

    assert "/mentions-legales/" in xml_du_sitemap
    assert "/cgu/" in xml_du_sitemap
    assert "/confidentialite/" in xml_du_sitemap

"""
La barre « Gérer / Configurer / Analyser » d'un module, et les onglets des inlines.
/ A module's "Manage / Configure / Analyse" bar, and inline tabs.

LOCALISATION : tests/pytest/test_admin_barre_de_module.py

CE QUE CES TESTS PROTEGENT
--------------------------

1. LA BARRE DU MODULE N'EST QUE SUR LES SINGLETONS. Elle est construite par
   `get_tabs()` (Administration/admin/dashboard.py). Ses onglets ne changent pas
   le contenu de la page : ils ramenent a la page du module (/admin/module/<slug>/
   ?onglet=...). Sur une liste ou une fiche, elle pretait a confusion. Sur un
   singleton django-solo (formulaire affiche a l'URL de liste), elle reste : c'est
   le seul chemin vers les autres pages du module.
   / The module bar only shows on singletons.

2. UN ONGLET D'INLINE A TOUJOURS UN LIEN POUR L'OUVRIR. Unfold ne dessine qu'une
   barre d'onglets par page (unfold/templatetags/unfold.py, tab_list) : quand la
   barre du module etait posee sur les fiches, les inlines `tab = True` (champs de
   formulaire des produits, blocs des pages) restaient caches par
   `x-show="activeTab == '...'"`, sans aucun bouton pour les ouvrir.
   / An inline tab always has a link to open it.

La barre du module se reconnait a ses liens `?onglet=` : aucune autre partie de
l'admin n'en porte.
/ The module bar is recognised by its `?onglet=` links.

Lancement / Run:
    make test ARGS="tests/pytest/test_admin_barre_de_module.py"
"""

import re

import pytest
from django.test import Client as HttpClient, override_settings
from django.urls import reverse
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_navigateur(db):
    """Le lieu `lespass` et un client HTTP connecte en superadmin.
    / The `lespass` venue and an HTTP client logged in as superadmin."""
    lieu = Client.objects.get(schema_name="lespass")
    with tenant_context(lieu):
        superadmin = TibilletUser.objects.filter(is_superuser=True).first()
    if superadmin is None:
        pytest.fail("Aucun superadmin dans la base de dev.")
    navigateur = HttpClient(HTTP_HOST=lieu.domains.first().domain)
    navigateur.force_login(superadmin)
    return lieu, navigateur


def _premier_produit_d_adhesion(lieu):
    from BaseBillet.models import Product

    with tenant_context(lieu):
        produit = Product.objects.filter(categorie_article=Product.ADHESION).first()
    if produit is None:
        pytest.fail("Le lieu 'lespass' (seed demo_data_v2) n'a aucun produit d'adhesion.")
    return produit


@pytest.mark.django_db
def test_une_liste_n_a_pas_la_barre_du_module(lieu_et_navigateur):
    """La liste des produits d'adhesion ne porte pas la barre du module.
    / The membership product list has no module bar."""
    _lieu, navigateur = lieu_et_navigateur
    contenu = navigateur.get("/admin/BaseBillet/membershipproduct/").content.decode()
    assert "?onglet=" not in contenu


@pytest.mark.django_db
def test_une_fiche_n_a_pas_la_barre_du_module_et_rend_ses_onglets(lieu_et_navigateur):
    """La fiche d'un produit d'adhesion n'a pas la barre du module, et son onglet
    « champs de formulaire » a de nouveau un lien pour l'ouvrir.
    / A membership product form has no module bar, and its form-fields tab is back."""
    lieu, navigateur = lieu_et_navigateur
    produit = _premier_produit_d_adhesion(lieu)
    contenu = navigateur.get(
        f"/admin/BaseBillet/membershipproduct/{produit.pk}/change/"
    ).content.decode()
    assert "?onglet=" not in contenu
    assert 'href="#form_fields"' in contenu


@pytest.mark.django_db
def test_un_singleton_garde_la_barre_du_module(lieu_et_navigateur):
    """Les reglages du site web (singleton) gardent la barre : c'est leur seul chemin
    vers les autres pages du module.
    / The site settings singleton keeps the bar: its only way to sibling pages."""
    _lieu, navigateur = lieu_et_navigateur
    contenu = navigateur.get("/admin/pages/configurationsite/").content.decode()
    assert "?onglet=" in contenu


@pytest.mark.django_db
def test_chaque_onglet_d_inline_a_un_lien_pour_l_ouvrir(lieu_et_navigateur):
    """
    Garde-fou generique : pour chaque admin qui declare un inline `tab = True`, la
    fiche du premier objet porte un lien `#<prefixe>` pour ouvrir cet onglet.
    Attrape la classe entiere du bug, y compris sur un inline ajoute demain.
    / Generic guard: every `tab = True` inline has a link to open it.
    """
    from django.test import RequestFactory

    from Administration.admin.site import staff_admin_site

    lieu, navigateur = lieu_et_navigateur
    with tenant_context(lieu):
        superadmin = TibilletUser.objects.filter(is_superuser=True).first()
    requete = RequestFactory().get("/admin/")
    requete.user = superadmin

    admins_verifiees = 0
    onglets_sans_lien = []

    for modele, admin_du_modele in staff_admin_site._registry.items():
        inlines_en_onglet = [
            inline for inline in admin_du_modele.inlines if getattr(inline, "tab", False)
        ]
        if not inlines_en_onglet:
            continue

        # Le queryset de l'admin, pas `objects` : les modeles proxy (ticketproduct,
        # membershipproduct...) filtrent leur categorie dans get_queryset().
        # / The admin queryset, not `objects`: proxy models filter in get_queryset().
        with tenant_context(lieu):
            objet = admin_du_modele.get_queryset(requete).first()
        if objet is None:
            pytest.fail(f"Aucun objet pour {modele._meta.label} : le seed demo_data_v2 en fournit.")

        adresse = reverse(
            f"staff_admin:{modele._meta.app_label}_{modele._meta.model_name}_change",
            args=[objet.pk],
        )
        # DEBUG=True comme le serveur de dev (appels Fedow, voir
        # test_admin_configuration_onglets.py).
        # / DEBUG=True like the dev server (Fedow calls).
        with override_settings(DEBUG=True):
            reponse = navigateur.get(adresse)
        assert reponse.status_code == 200, f"{adresse} repond {reponse.status_code}"
        contenu = reponse.content.decode()
        admins_verifiees += 1

        groupes_caches = set(re.findall(r'x-show="activeTab == \'([\w-]+)\'"', contenu))
        liens = set(re.findall(r'href="#([\w-]+)"', contenu))
        for groupe in sorted(groupes_caches - liens - {"general"}):
            onglets_sans_lien.append(f"{adresse} : #{groupe}")

    assert admins_verifiees, "Aucune admin avec un inline en onglet : le test ne prouverait rien."
    assert not onglets_sans_lien, (
        f"Ces onglets d'inline n'ont aucun lien pour les ouvrir : {onglets_sans_lien}"
    )

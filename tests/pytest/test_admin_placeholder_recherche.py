"""
Le champ de recherche dit sur quoi il cherche.
/ The search field says what it searches.

LOCALISATION : tests/pytest/test_admin_placeholder_recherche.py

CE QUE CES TESTS PROTEGENT
--------------------------
Le champ de recherche d'une changelist affichait « Type to search ». Il ne
disait pas SUR QUOI la recherche porte. Sur MembershipAdmin elle fouille
l'e-mail, le prenom, le nom, le numero de carte et le formulaire :
l'utilisateur ne pouvait pas le deviner, et tapait souvent la mauvaise chose.
55 classes d'admin sur 82 ont un `search_fields` — l'information existait
partout, elle n'etait jamais montree.

LE MECANISME, ET POURQUOI IL N'Y A AUCUN GABARIT SURCHARGE. Unfold rend
`search_help_text` COMME PLACEHOLDER du champ
(unfold/templates/admin/search_form.html), la ou l'admin Django natif l'affiche
en petit sous le champ. Une simple property sur la classe de base du projet
suffit donc.
/ Unfold renders search_help_text as the placeholder, so no template override.

CE QUI PEUT CASSER EN SILENCE, et que ces tests couvrent :
  - un libelle qui radote (« prenom, prenom ») faute de dedoublonnage ;
  - un lookup lie affiche brut (« user email ») au lieu du champ resolu ;
  - une exception sur une classe dont un `search_fields` pointe une annotation
    — sur une page de LISTE, ce serait une 500 ;
  - une classe qui perd la classe de base du projet au fil des refontes.
/ Silent failures: repeated labels, raw lookups, exceptions on list pages, and
  admin classes drifting off the project base class.

Meme pattern que les autres tests d'admin : base de dev vivante.
"""

import re

import pytest
from django.test import Client as HttpClient
from django.urls import NoReverseMatch, reverse
from django_tenants.utils import tenant_context

from Administration.admin.base import ModelAdmin as ModelAdminDuProjet
from Administration.admin.site import staff_admin_site
from AuthBillet.models import TibilletUser
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_superadmin(db):
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
        if utilisateur:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un domaine et un superadmin.")


@pytest.fixture
def navigateur(lieu_et_superadmin):
    _tenant, domaine, utilisateur = lieu_et_superadmin
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


def _admin(nom_de_classe):
    for admin in staff_admin_site._registry.values():
        if admin.__class__.__name__ == nom_de_classe:
            return admin
    pytest.skip(f"{nom_de_classe} n'est pas enregistree sur ce site.")


# --------------------------------------------------------------------------- #
# La classe de base                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_toutes_les_classes_heritent_de_la_base_du_projet():
    """
    Le point d'accroche ne vaut que s'il est universel. Une classe qui
    importerait encore `ModelAdmin` depuis `unfold.admin` perdrait le
    placeholder sans que rien ne le signale.
    / The hook is only worth having if it is universal.
    """
    egarees = [
        admin.__class__.__name__
        for admin in staff_admin_site._registry.values()
        if not isinstance(admin, ModelAdminDuProjet)
    ]
    assert not egarees, (
        f"Ces classes n'heritent pas de Administration.admin.base.ModelAdmin : "
        f"{sorted(egarees)}. Elles importent probablement encore depuis unfold.admin."
    )


# --------------------------------------------------------------------------- #
# La fabrication du libelle                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_une_classe_sans_search_fields_ne_pose_pas_de_placeholder():
    """
    Sans `search_fields`, Unfold n'affiche meme pas la barre de recherche.
    Poser un texte serait au mieux inutile, au pire trompeur.
    / Without search_fields Unfold hides the bar entirely.
    """
    sans_recherche = [
        a for a in staff_admin_site._registry.values() if not a.search_fields
    ]
    assert sans_recherche, "Aucune classe sans search_fields : test sans objet."
    for admin in sans_recherche:
        assert admin.search_help_text is None, admin.__class__.__name__


@pytest.mark.django_db
def test_un_seul_champ_ne_produit_pas_de_points_de_suspension():
    """« Rechercher : nom… » laisserait croire qu'il y a autre chose."""
    admin = _admin("EventAdmin")
    assert list(admin.search_fields) == ["name"]
    assert "…" not in admin.search_help_text


@pytest.mark.django_db
def test_les_lookups_lies_sont_resolus_en_libelle_humain():
    """
    `user__email` doit donner « email », pas « user email ». Et
    `pricesold__productsold__product__name` — trois niveaux — doit se resoudre
    aussi.
    / Related lookups must resolve to the terminal field's label.
    """
    membership = _admin("MembershipAdmin")
    texte = membership.search_help_text
    assert "user email" not in texte, texte
    assert "user__email" not in texte, texte

    ligne = _admin("LigneArticleAdmin")
    assert "pricesold" not in ligne.search_help_text


@pytest.mark.django_db
def test_les_libelles_en_double_sont_fusionnes():
    """
    Sur HumanUserAdmin, `first_name` et `memberships__first_name` donnent tous
    deux « prenom ». Sans dedoublonnage le placeholder radoterait.
    / Two entries can share a label; the placeholder must not repeat itself.
    """
    admin = _admin("HumanUserAdmin")
    texte = admin.search_help_text
    libelles = texte.split(":", 1)[1].replace("…", "").split(",")
    libelles = [libelle.strip() for libelle in libelles]
    assert len(libelles) == len(set(libelles)), texte


@pytest.mark.django_db
def test_le_nombre_de_champs_affiches_est_plafonne():
    """
    Le champ fait `lg:w-96` et porte la classe `truncate` : au-dela de trois
    libelles, le CSS couperait de toute facon. Autant s'arreter proprement.
    / Beyond three labels the CSS truncates anyway.
    """
    from Administration.admin.base import NOMBRE_DE_CHAMPS_AFFICHES

    admin = _admin("MembershipAdmin")
    assert len(admin.search_fields) > NOMBRE_DE_CHAMPS_AFFICHES
    texte = admin.search_help_text
    assert texte.endswith("…"), texte
    assert texte.count(",") == NOMBRE_DE_CHAMPS_AFFICHES - 1, texte


@pytest.mark.django_db
def test_aucune_classe_ne_leve_en_calculant_son_placeholder():
    """
    Un `search_fields` peut pointer une annotation ou une propriete, qui ne
    sont pas des champs de modele. Lever ici mettrait une page de LISTE en 500 :
    le repli doit toujours produire quelque chose.
    / A search entry may point at an annotation; raising would 500 a list page.
    """
    en_erreur = []
    for admin in staff_admin_site._registry.values():
        try:
            admin.search_help_text
        except Exception as erreur:  # noqa: BLE001 — c'est precisement l'objet du test
            en_erreur.append((admin.__class__.__name__, repr(erreur)))
    assert not en_erreur, en_erreur


# --------------------------------------------------------------------------- #
# Le rendu reel                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_le_placeholder_apparait_dans_le_html_d_une_changelist(navigateur):
    """
    Le test qui compte : verifier l'objet Python ne prouve pas qu'Unfold
    l'affiche. On regarde l'attribut `placeholder` du champ rendu.
    / Checking the Python object does not prove Unfold renders it.
    """
    admin = _admin("MembershipAdmin")
    attendu = admin.search_help_text

    reponse = navigateur.get("/admin/BaseBillet/membership/")
    assert reponse.status_code == 200
    html = reponse.content.decode()

    # On isole le champ de recherche de la changelist (id="searchbar") : la
    # page contient AUSSI la palette de commandes d'Unfold
    # (unfold/helpers/command.html), qui garde legitimement « Type to search ».
    # Chercher ce texte dans toute la page testerait le mauvais widget.
    # / Isolate the changelist input: the page also holds Unfold's command
    #   palette, which legitimately keeps the generic text.
    champ = re.search(r"<input[^>]*id=\"searchbar\"[^>]*>", html)
    assert champ, "Champ de recherche de la changelist introuvable."
    balise = champ.group(0)

    assert f'placeholder="{attendu}"' in balise, (
        f"Le placeholder calcule n'est pas sur le champ. Balise : {balise}"
    )
    assert "Type to search" not in balise, "Le texte generique d'Unfold est reste."


@pytest.mark.django_db
def test_les_changelists_avec_recherche_repondent_toujours(navigateur):
    """
    Filet large : la property est lue au rendu de CHAQUE changelist ayant une
    recherche. Une erreur dedans se verrait en 500, pas en test unitaire.
    / The property is read when rendering every searchable changelist.
    """
    en_echec = []
    for modele, admin in staff_admin_site._registry.items():
        if not admin.search_fields:
            continue
        options = modele._meta
        try:
            url = reverse(
                f"staff_admin:{options.app_label}_{options.model_name}_changelist"
            )
        except NoReverseMatch:
            continue
        code = navigateur.get(url).status_code
        if code >= 500:
            en_echec.append((url, code))
    assert not en_echec, en_echec

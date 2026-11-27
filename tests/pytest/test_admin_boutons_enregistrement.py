"""
Les boutons d'enregistrement de l'admin.
/ The admin save buttons.

LOCALISATION : tests/pytest/test_admin_boutons_enregistrement.py

CE QUE CES TESTS PROTEGENT
--------------------------
1. Les pages de configuration (modèles django-solo) héritent de `SingletonAdmin`
   (Administration/admin/base.py) : un seul bouton « Enregistrer », qui reste sur
   la page, avec un message en français.
2. Le bouton « _continue » des autres pages affiche son vrai libellé
   (« Enregistrer et continuer les modifications »). Sans la surcharge
   Administration/templates/admin/submit_line.html, Unfold 0.89 + Django 4.2
   affichent « Enregistrer et afficher ».
/ 1. Configuration pages: one "Save" button that stays on the page.
  2. The "_continue" button shows its real label on the other pages.

Même pattern que les autres tests d'admin : base de dev vivante, chaque test
annulé par la transaction de pytest-django.
/ Same pattern as the other admin tests: live dev DB, rolled back by pytest-django.
"""

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django_tenants.utils import tenant_context
from solo.admin import SingletonModelAdmin

from Administration.admin.base import SingletonAdmin
from Administration.admin.site import staff_admin_site
from AuthBillet.models import TibilletUser
from BaseBillet.models import Event
from comptabilite.models import ConfigurationDesRapports
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Réutilise la base de dev (pas de création de base de test).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_superadmin(db):
    """
    Rend le lieu `lespass`, avec son domaine et un superadmin.
    / Returns the `lespass` tenant, with its domain and a superadmin.
    """
    for tenant in Client.objects.filter(schema_name="lespass"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
        if utilisateur:
            return tenant, domaine.domain, utilisateur
    pytest.fail(
        "Le lieu 'lespass' (seed demo_data_v2) n'a pas : un domaine et un superadmin."
    )


@pytest.fixture
def navigateur(lieu_et_superadmin):
    """Un client HTTP déjà connecté sur le lieu, en français. / A logged-in client, in French."""
    _tenant, domaine, utilisateur = lieu_et_superadmin
    client = HttpClient(HTTP_HOST=domaine, HTTP_ACCEPT_LANGUAGE="fr")
    client.force_login(utilisateur)
    return client


def test_toutes_les_pages_de_configuration_heritent_de_singletonadmin():
    """
    Une page de configuration qui hériterait directement de SingletonModelAdmin
    renverrait au tableau de bord, avec un message en anglais.
    / A configuration page inheriting SingletonModelAdmin directly would redirect
    to the dashboard, with an English message.
    """
    pages_de_configuration_oubliees = []
    for modele, classe_d_admin in staff_admin_site._registry.items():
        est_une_page_de_configuration = isinstance(classe_d_admin, SingletonModelAdmin)
        if est_une_page_de_configuration and not isinstance(
            classe_d_admin, SingletonAdmin
        ):
            pages_de_configuration_oubliees.append(type(classe_d_admin).__name__)

    assert pages_de_configuration_oubliees == []


@pytest.mark.django_db
def test_une_page_de_configuration_n_a_qu_un_bouton_enregistrer(navigateur):
    reponse = navigateur.get(
        reverse("staff_admin:comptabilite_configurationdesrapports_changelist")
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'name="_save"' in contenu
    assert 'name="_continue"' not in contenu


@pytest.mark.django_db
def test_enregistrer_une_page_de_configuration_reste_sur_la_page(
    navigateur, lieu_et_superadmin
):
    """
    On poste les valeurs ACTUELLES : le cache de django-solo survit à l'annulation
    de la transaction. Poster d'autres valeurs les laisserait dans le cache du
    serveur de dev.
    / Post the CURRENT values: solo's cache survives the rollback.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        reglages_actuels = ConfigurationDesRapports.get_solo()
        donnees_du_formulaire = {}
        for nom_du_champ in (
            "envoyer_le_recap_quotidien",
            "envoyer_le_rapport_hebdomadaire",
            "envoyer_le_rapport_mensuel",
            "envoyer_le_rapport_annuel",
        ):
            if getattr(reglages_actuels, nom_du_champ):
                donnees_du_formulaire[nom_du_champ] = "on"
        identifiants_des_destinataires = []
        for destinataire in reglages_actuels.destinataires.all():
            identifiants_des_destinataires.append(str(destinataire.pk))
        donnees_du_formulaire["destinataires"] = identifiants_des_destinataires
    donnees_du_formulaire["_save"] = "Enregistrer"

    adresse_de_la_page = reverse(
        "staff_admin:comptabilite_configurationdesrapports_changelist"
    )
    reponse = navigateur.post(adresse_de_la_page, donnees_du_formulaire)

    assert reponse.status_code == 302
    assert reponse["Location"] == adresse_de_la_page

    page_suivante = navigateur.get(adresse_de_la_page).content.decode()
    assert "Modifications enregistrées." in page_suivante


@pytest.mark.django_db
def test_un_formulaire_ordinaire_affiche_le_vrai_libelle_de_continuer(
    navigateur, lieu_et_superadmin
):
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        evenement = Event.objects.first()
    if evenement is None:
        pytest.fail("Le lieu 'lespass' (seed demo_data_v2) n'a aucun événement.")

    reponse = navigateur.get(
        reverse("staff_admin:BaseBillet_event_change", args=[evenement.pk])
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "Enregistrer et continuer les modifications" in contenu
    assert "Enregistrer et afficher" not in contenu

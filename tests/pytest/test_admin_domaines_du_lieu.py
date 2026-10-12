"""
Admin des lieux : les domaines d'un lieu, modifiables par un superuser.
/ Venues admin: a venue's domains, editable by a superuser.

LOCALISATION : tests/pytest/test_admin_domaines_du_lieu.py

On ouvre l'admin depuis le lieu `lespass` et on modifie les domaines d'un AUTRE
lieu (`festival`) : c'est le cas reel (l'admin des lieux sert depuis un lieu et
touche tous les autres). Tout se passe dans une transaction annulee a la fin.
/ The admin runs on `lespass` and edits ANOTHER venue's domains. Rolled back.
"""

import pytest
from django.core.cache import cache
from django.test import Client as HttpClient
from django.urls import reverse
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client, Domain
from fabriques_panier import identifiant_unique, taches_celery_enregistrees

pytestmark = pytest.mark.django_db


@pytest.fixture
def lieu_modifie():
    lieu = Client.objects.get(schema_name="festival")
    assert lieu.domains.count() == 1, "Le lieu festival doit avoir un seul domaine."
    return lieu


@pytest.fixture
def adresse_de_la_fiche(lieu_modifie):
    return reverse("staff_admin:Customers_client_change", args=[lieu_modifie.pk])


def _navigateur(utilisateur):
    domaine_de_l_admin = Client.objects.get(schema_name="lespass").domains.first()
    navigateur = HttpClient(HTTP_HOST=domaine_de_l_admin.domain, secure=True)
    navigateur.force_login(utilisateur)
    return navigateur


@pytest.fixture
def superuser():
    utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
    assert utilisateur is not None, "Aucun superuser dans la base de dev."
    return utilisateur


@pytest.fixture
def admin_de_lieu():
    """Un admin du lieu lespass, sans etre superuser. / A venue admin, not superuser."""
    with taches_celery_enregistrees():
        utilisateur = TibilletUser.objects.create(
            email=f"admin-domaines-{identifiant_unique()}@example.org",
            username=f"admin-domaines-{identifiant_unique()}",
            is_staff=True,
        )
        utilisateur.client_admin.add(Client.objects.get(schema_name="lespass"))
    return utilisateur


def _donnees_du_formulaire(lieu, lignes):
    """
    Donnees POST de la fiche : une ligne par domaine.
    lignes = [{"id": pk ou None, "domain": str, "is_primary": bool, "DELETE": bool}]
    / POST data of the venue form: one row per domain.
    """
    domaines_existants = [ligne for ligne in lignes if ligne.get("id")]
    donnees = {
        "domains-TOTAL_FORMS": str(len(lignes)),
        "domains-INITIAL_FORMS": str(len(domaines_existants)),
        "domains-MIN_NUM_FORMS": "0",
        "domains-MAX_NUM_FORMS": "1000",
        "_save": "Enregistrer",
    }
    for numero, ligne in enumerate(lignes):
        prefixe = f"domains-{numero}-"
        donnees[prefixe + "tenant"] = str(lieu.pk)
        donnees[prefixe + "domain"] = ligne["domain"]
        if ligne.get("id"):
            donnees[prefixe + "id"] = str(ligne["id"])
        if ligne.get("is_primary"):
            donnees[prefixe + "is_primary"] = "on"
        if ligne.get("DELETE"):
            donnees[prefixe + "DELETE"] = "on"
    return donnees


def test_un_superuser_voit_les_domaines_du_lieu(
    superuser, lieu_modifie, adresse_de_la_fiche
):
    reponse = _navigateur(superuser).get(adresse_de_la_fiche)

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'name="domains-TOTAL_FORMS"' in html
    assert lieu_modifie.domains.first().domain in html


def test_un_admin_de_lieu_ne_voit_ni_ne_modifie_les_domaines(
    admin_de_lieu, lieu_modifie, adresse_de_la_fiche
):
    navigateur = _navigateur(admin_de_lieu)
    reponse = navigateur.get(adresse_de_la_fiche)
    assert 'name="domains-TOTAL_FORMS"' not in reponse.content.decode()

    domaine = lieu_modifie.domains.first()
    navigateur.post(
        adresse_de_la_fiche,
        _donnees_du_formulaire(
            lieu_modifie,
            [{"id": domaine.pk, "domain": "pirate.example", "is_primary": True}],
        ),
    )
    domaine.refresh_from_db()
    assert domaine.domain != "pirate.example"


def test_un_superuser_ajoute_un_domaine_et_le_rend_principal(
    superuser, lieu_modifie, adresse_de_la_fiche
):
    ancien_domaine = lieu_modifie.domains.first()
    cle_du_middleware = f"canonical_primary_domain:{lieu_modifie.schema_name}"
    with tenant_context(lieu_modifie):
        cache.set(cle_du_middleware, ancien_domaine.domain, 60)

    reponse = _navigateur(superuser).post(
        adresse_de_la_fiche,
        _donnees_du_formulaire(
            lieu_modifie,
            [
                {"id": ancien_domaine.pk, "domain": ancien_domaine.domain},
                {"domain": "  Nouveau-Domaine.EXAMPLE ", "is_primary": True},
            ],
        ),
    )

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    principal = Domain.objects.get(tenant=lieu_modifie, is_primary=True)
    assert principal.domain == "nouveau-domaine.example"
    ancien_domaine.refresh_from_db()
    assert ancien_domaine.is_primary is False
    with tenant_context(lieu_modifie):
        assert cache.get(cle_du_middleware) is None


@pytest.mark.parametrize(
    "lignes_a_envoyer, message_attendu",
    [
        (
            lambda d: [
                {"id": d.pk, "domain": d.domain, "is_primary": True},
                {"domain": "second.example", "is_primary": True},
            ],
            "Cochez un seul domaine principal.",
        ),
        (
            lambda d: [{"id": d.pk, "domain": d.domain}],
            "Cochez un seul domaine principal.",
        ),
        (
            lambda d: [
                {"id": d.pk, "domain": d.domain, "is_primary": True, "DELETE": True}
            ],
            "Un lieu doit garder au moins un domaine.",
        ),
        (
            lambda d: [{"id": d.pk, "domain": "https://monlieu.example/"}],
            "Saisissez le nom de domaine seul",
        ),
    ],
    ids=["deux-principaux", "aucun-principal", "plus-aucun-domaine", "avec-https"],
)
def test_un_formulaire_incoherent_est_refuse(
    superuser, lieu_modifie, adresse_de_la_fiche, lignes_a_envoyer, message_attendu
):
    domaine = lieu_modifie.domains.first()
    domaine_avant = (domaine.domain, domaine.is_primary)

    reponse = _navigateur(superuser).post(
        adresse_de_la_fiche,
        _donnees_du_formulaire(lieu_modifie, lignes_a_envoyer(domaine)),
    )

    assert reponse.status_code == 200
    assert message_attendu in reponse.content.decode()
    domaine.refresh_from_db()
    assert (domaine.domain, domaine.is_primary) == domaine_avant
    assert lieu_modifie.domains.count() == 1

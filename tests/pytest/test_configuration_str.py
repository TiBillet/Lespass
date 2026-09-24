"""
Le libelle d'un lieu (Configuration.__str__) doit etre une VRAIE chaine.
/ A venue's label must be a real string.

LOCALISATION : tests/pytest/test_configuration_str.py

CE QUE CE TEST PROTEGE
----------------------
gettext_lazy ne renvoie pas une chaine mais un objet paresseux (__proxy__).
Django, lui, appelle str(objet) pour fabriquer le sous-titre de la page de
modification, et Python exige alors une vraie chaine.

Ecrire `return _("Parametres")` dans un __str__ fait donc planter la page
avec « TypeError: __str__ returned non-string (type __proxy__) ».

Le piege est sournois : la branche qui concatene
(`_("Parametres pour ") + self.organisation`) resout le proxy toute seule.
Le bug ne se voyait donc QUE sur les lieux dont le nom est vide — cas rare,
mais qui renvoyait une 500 sur /admin/BaseBillet/configuration/.
/ Only the empty-name branch was broken, because string concatenation already
  resolves the proxy. Hence a 500 that stayed hidden on most venues.

Meme pattern que les autres tests d'admin : base de dev vivante.
/ Same pattern as the other admin tests: live dev DB.
"""

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def un_lieu(db):
    """Le premier lieu venu. / Any tenant."""
    tenant = Client.objects.exclude(schema_name="public").first()
    if tenant is None:
        pytest.fail("Aucun lieu en base.")
    return tenant


@pytest.mark.django_db
def test_le_libelle_est_une_vraie_chaine_avec_un_nom(un_lieu):
    """
    Lieu qui a un nom : le libelle doit etre un str, pas un objet paresseux.
    / Named venue: the label must be a real str.
    """
    with tenant_context(un_lieu):
        configuration = Configuration.get_solo()
        configuration.organisation = "Un Lieu De Test"
        libelle = str(configuration)

    # `type(...) is str` et non `isinstance` : un __proxy__ peut se faire
    # passer pour une chaine dans certains contextes, pas ici.
    # / `type(...) is str`, not isinstance: a proxy can masquerade as a str.
    assert type(libelle) is str
    assert "Un Lieu De Test" in libelle


@pytest.mark.django_db
def test_le_libelle_est_une_vraie_chaine_sans_nom(un_lieu):
    """
    LE cas qui plantait : lieu sans nom.
    / The branch that used to crash: unnamed venue.
    """
    with tenant_context(un_lieu):
        configuration = Configuration.get_solo()
        configuration.organisation = ""
        libelle = str(configuration)

    assert type(libelle) is str
    assert libelle, "Le libelle ne doit pas etre vide."


@pytest.mark.django_db
def test_le_libelle_reste_traduit(un_lieu):
    """
    Le correctif ne doit pas avoir casse la traduction : on force une vraie
    chaine, mais on la veut toujours dans la langue active.
    / Forcing a real string must not break translation.
    """
    with tenant_context(un_lieu):
        configuration = Configuration.get_solo()
        configuration.organisation = ""

        with translation.override("en"):
            en_anglais = str(configuration)
        with translation.override("fr"):
            en_francais = str(configuration)

    assert type(en_anglais) is str and type(en_francais) is str
    assert en_anglais != en_francais, (
        "Le libelle est identique en anglais et en francais : "
        "la traduction ne s'applique plus."
    )

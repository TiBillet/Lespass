"""
L'admin des cles API montre ou trouver la documentation de l'API v2.
/ The API key admin shows where to find the API v2 documentation.

LOCALISATION : tests/pytest/test_admin_cle_api_aide.py

CE QUE CES TESTS PROTEGENT
--------------------------
Une cle API sert souvent a confier un travail a un agent (script, IA). La
personne qui cree la cle doit savoir quoi lui donner avec : le contrat de
l'API (api_v2/openapi-schema.yaml) et le guide pour agent (skill tibillet-api).
L'encart d'aide de la page (HelpDisplayMixin) porte ces deux liens, sur la
liste des cles et sur le formulaire de creation.
/ The help box of the API key admin links the OpenAPI contract and the agent
guide, on the list page and on the creation form.

Meme pattern que les autres tests d'admin : base de dev vivante, client admin
de la fixture conftest (admin_client).
"""

import pytest
from django.urls import reverse

URL_DU_CONTRAT_OPENAPI_BRUT = (
    "https://raw.githubusercontent.com/TiBillet/Lespass/main/api_v2/openapi-schema.yaml"
)
URL_DU_SKILL_TIBILLET_API = (
    "https://github.com/TiBillet/Lespass/tree/main/TECH_DOC/SKILLS/tibillet-api"
)


@pytest.mark.django_db
def test_la_liste_des_cles_api_donne_le_lien_du_contrat_et_du_skill(admin_client):
    """La liste des cles API affiche le lien du .yaml et celui du skill.
    / The API key list shows the .yaml and skill links."""
    reponse = admin_client.get(reverse("staff_admin:BaseBillet_externalapikey_changelist"))
    assert reponse.status_code == 200
    contenu_de_la_page = reponse.content.decode()
    assert URL_DU_CONTRAT_OPENAPI_BRUT in contenu_de_la_page
    assert URL_DU_SKILL_TIBILLET_API in contenu_de_la_page


@pytest.mark.django_db
def test_la_creation_d_une_cle_api_donne_le_lien_du_contrat_et_du_skill(admin_client):
    """Le formulaire de creation d'une cle affiche aussi les deux liens.
    / The key creation form also shows both links."""
    reponse = admin_client.get(reverse("staff_admin:BaseBillet_externalapikey_add"))
    assert reponse.status_code == 200
    contenu_de_la_page = reponse.content.decode()
    assert URL_DU_CONTRAT_OPENAPI_BRUT in contenu_de_la_page
    assert URL_DU_SKILL_TIBILLET_API in contenu_de_la_page

"""
Apercu de skin : les vues partielles htmx repondent, avec ou sans apercu.
/ Skin preview: htmx partial views answer, with or without a preview.

LOCALISATION : tests/pytest/test_skin_preview_partiels.py

POURQUOI / WHY :
Certaines vues partielles ne passent pas par `get_context` : `MyAccount.my_cards`,
`MyAccount.tokens_table` et `EventMVT.partial_list` (filtres et « voir plus » de l'agenda).
Elles lisaient le skin a previsualiser dans un contexte qui ne le contenait pas
(KeyError → erreur 500). Elles le lisent maintenant dans la requete
(`BaseBillet.views.skin_preview_de_la_requete`). `tokens_table` est deja couvert par
tests/pytest/test_balance_soldes_et_recharge.py ; ce fichier couvre les deux autres.
/ Some partial views skip get_context; they now read the preview from the request.

Lancement / Run :
    docker exec lespass_django poetry run pytest tests/pytest/test_skin_preview_partiels.py -v
"""
from unittest import mock

import pytest
from django.test import Client as DjangoClient


pytestmark = pytest.mark.django_db

HOTE_DU_LIEU = "lespass.tibillet.localhost"


@pytest.mark.parametrize("parametres", ["", "?skin_preview=V2", "?skin_preview=None"])
def test_la_liste_partielle_de_l_agenda_repond(parametres):
    """
    Les filtres et le « voir plus » de l'agenda chargent `/event/partial_list/` : la vue
    repond 200, sans apercu, avec un apercu valide, ou avec la valeur « None » que htmx
    envoyait hors apercu.
    / The agenda partial list answers 200 with or without a preview.
    """
    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    reponse = navigateur.get(f"/event/partial_list/{parametres}", HTTP_HX_REQUEST="true")
    assert reponse.status_code == 200, (
        f"/event/partial_list/{parametres} repond {reponse.status_code}."
    )


@pytest.mark.parametrize("parametres", ["", "?skin_preview=V2"])
def test_le_tableau_des_cartes_de_mon_compte_repond(admin_user, parametres):
    """
    Le tableau des cartes de « Mon compte » (`/my_account/my_cards/`) repond 200, avec ou
    sans apercu. Fedow est simule : on ne teste que le rendu de la vue.
    / The "My account" cards table answers 200; Fedow is mocked.
    """
    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    navigateur.force_login(admin_user)

    api = mock.MagicMock()
    api.NFCcard.retrieve_card_by_signature.return_value = []

    with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
        reponse = navigateur.get(f"/my_account/my_cards/{parametres}", HTTP_HX_REQUEST="true")

    assert reponse.status_code == 200, (
        f"/my_account/my_cards/{parametres} repond {reponse.status_code}."
    )

"""
tests/pytest/test_relier_les_cartes_rapatriees.py

La commande `relier_les_cartes_rapatriees` relie à leur propriétaire les cartes locales
qu'un lieu a reçues sans propriétaire, alors que l'ancien Fedow les dit liées.
/ The command links to their owner the local cards left without owner while the old
Fedow says they are linked.

LOCALISATION : tests/pytest/test_relier_les_cartes_rapatriees.py

CE QUI EST TESTÉ / WHAT IS TESTED
- passage à blanc (par défaut) : la carte est annoncée, rien n'est écrit ;
- `--executer` : la carte porte sa propriétaire ;
- carte anonyme chez l'ancien Fedow : elle reste sans propriétaire ;
- personne inconnue ici : signalée, sans erreur, la carte reste sans propriétaire.

L'ancien Fedow est simulé (client `FedowAPI` de la commande) ; la garde du fichier
voisin fait échouer tout envoi réseau réel. La base de dev porte d'autres cartes sans
propriétaire : le faux Fedow ne les connaît pas, elles sont signalées en erreur. Les
tests ne lisent donc que les lignes de LEUR carte.
/ The old Fedow is faked; the neighbouring guard fails any real network call.

PIÈGES (tests/PIEGES.md)
- CarteCashless est en SHARED_APPS : pas de FastTenantTestCase (9.30).
- tenant_context, jamais schema_context (9.1).
- Tout est annulé par la transaction `django_db` (base de dev partagée).

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_relier_les_cartes_rapatriees.py -v
"""

import uuid
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django_tenants.utils import tenant_context

from QrcodeCashless.models import CarteCashless, Detail
from fedow_connect.fedow_api import CarteInconnueDeFedow
from fedow_connect.models import FedowConfig
from test_carte_liee_chez_fedow_fed_en_caisse import (
    aucun_appel_reseau_vers_l_ancien_fedow,  # noqa: F401 (garde automatique / autouse guard)
    fiche_de_carte,
    proprietaire_avec_son_portefeuille,
    tag_neuf,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def lieu(tenant):
    """Le lieu `lespass`, dans son schéma. / The `lespass` venue, in its schema."""
    with tenant_context(tenant):
        yield SimpleNamespace(tenant=tenant)


CHEMIN_DU_CLIENT_FEDOW_DE_LA_COMMANDE = (
    "QrcodeCashless.management.commands.relier_les_cartes_rapatriees.FedowAPI"
)


def carte_locale_sans_proprietaire(lieu):
    """
    Une carte locale émise par le lieu, sans propriétaire : l'état d'une carte rapatriée
    avant que le rapatriement ne pose la propriétaire.
    / A local card issued by the venue, without owner.
    """
    tag_id = tag_neuf()
    detail = Detail.objects.create(origine=lieu.tenant, generation=31042)
    return CarteCashless.objects.create(
        tag_id=tag_id, number=tag_neuf(), uuid=uuid.uuid4(), detail=detail
    )


def lancer_la_commande(lieu, fiches, executer):
    """
    Lance la commande sur le lieu, l'ancien Fedow ne connaissant que `fiches`.
    / Runs the command, the old Fedow knowing only `fiches`.

    :return: (sortie standard, sortie d'erreur)
    """
    fiche_par_tag = {}
    for fiche in fiches:
        fiche_par_tag[fiche["first_tag_id"]] = fiche

    def lire_la_fiche(tag_id):
        if tag_id not in fiche_par_tag:
            raise CarteInconnueDeFedow(f"Carte inconnue de Fedow : {tag_id}")
        return fiche_par_tag[tag_id]

    client_de_l_ancien_fedow = MagicMock()
    client_de_l_ancien_fedow.NFCcard.retrieve.side_effect = lire_la_fiche

    sortie_standard = StringIO()
    sortie_d_erreur = StringIO()
    arguments = ["relier_les_cartes_rapatriees", "--schema", lieu.tenant.schema_name]
    if executer:
        arguments.append("--executer")
    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch(
            CHEMIN_DU_CLIENT_FEDOW_DE_LA_COMMANDE, return_value=client_de_l_ancien_fedow
        ):
            call_command(*arguments, stdout=sortie_standard, stderr=sortie_d_erreur)
    return sortie_standard.getvalue(), sortie_d_erreur.getvalue()


def test_passage_a_blanc_annonce_la_carte_sans_rien_ecrire(lieu):
    """Par défaut, la commande annonce la carte à relier et n'écrit rien.
    / By default, the command announces the card and writes nothing."""
    carte = carte_locale_sans_proprietaire(lieu)
    proprietaire = proprietaire_avec_son_portefeuille()
    fiche = fiche_de_carte(
        carte.tag_id, uuid_du_portefeuille=proprietaire.wallet.uuid, est_anonyme=False
    )

    sortie, _sortie_d_erreur = lancer_la_commande(lieu, [fiche], executer=False)

    assert f"{carte.tag_id} : à relier à {proprietaire.email}" in sortie
    assert "Passage à blanc" in sortie
    carte.refresh_from_db()
    assert carte.user_id is None


def test_executer_relie_la_carte_a_sa_proprietaire(lieu):
    """Avec --executer, la carte locale porte la personne que l'ancien Fedow lui donne.
    / With --executer, the local card carries the person the old Fedow names."""
    carte = carte_locale_sans_proprietaire(lieu)
    proprietaire = proprietaire_avec_son_portefeuille()
    fiche = fiche_de_carte(
        carte.tag_id, uuid_du_portefeuille=proprietaire.wallet.uuid, est_anonyme=False
    )

    sortie, sortie_d_erreur = lancer_la_commande(lieu, [fiche], executer=True)

    assert carte.tag_id not in sortie_d_erreur
    assert f"{carte.tag_id} : reliée à {proprietaire.email}" in sortie
    carte.refresh_from_db()
    assert carte.user_id == proprietaire.pk


def test_carte_anonyme_chez_l_ancien_fedow_reste_sans_proprietaire(lieu):
    """Une carte anonyme chez l'ancien Fedow (portefeuille éphémère) n'est pas touchée.
    / An anonymous card on the old Fedow is left untouched."""
    carte = carte_locale_sans_proprietaire(lieu)
    fiche = fiche_de_carte(
        carte.tag_id, uuid_du_portefeuille=uuid.uuid4(), est_anonyme=True
    )

    sortie, sortie_d_erreur = lancer_la_commande(lieu, [fiche], executer=True)

    assert carte.tag_id not in sortie_d_erreur
    assert "1 anonyme(s)" in sortie
    carte.refresh_from_db()
    assert carte.user_id is None


def test_personne_inconnue_ici_est_signalee_sans_erreur(lieu):
    """Liée chez l'ancien Fedow à un portefeuille qu'aucune personne d'ici ne porte :
    la carte est signalée, reste sans propriétaire, et la commande va au bout.
    / Linked there to a wallet nobody here holds: reported, left without owner."""
    carte = carte_locale_sans_proprietaire(lieu)
    portefeuille_inconnu = uuid.uuid4()
    fiche = fiche_de_carte(
        carte.tag_id, uuid_du_portefeuille=portefeuille_inconnu, est_anonyme=False
    )

    sortie, sortie_d_erreur = lancer_la_commande(lieu, [fiche], executer=True)

    assert f"{carte.tag_id} : liée chez l'ancien Fedow" in sortie_d_erreur
    assert "personne inconnue ici" in sortie_d_erreur
    assert "Terminé" in sortie
    carte.refresh_from_db()
    assert carte.user_id is None

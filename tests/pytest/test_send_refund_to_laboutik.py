"""
Tests pytest : envoi des remboursements et avoirs vers LaBoutik (issue #319).
/ Pytest tests: sending refunds and credit notes to LaBoutik (issue #319).

LOCALISATION : tests/pytest/test_send_refund_to_laboutik.py
Code teste / Tested code : BaseBillet/tasks.py (send_refund_to_laboutik,
trouver_ligne_de_vente_originale).

Le probleme : LaBoutik enregistre un remboursement en le rattachant a la vente
d'origine. S'il ne connait pas cette vente, il repond 404 et le remboursement
etait perdu. Maintenant, la tache verifie d'abord que la vente d'origine a ete
envoyee. Sinon, elle relance l'envoi de la vente et reessaie plus tard.
/ LaBoutik links a refund to its original sale and answers 404 if it does not know
it. The task now checks the original sale first and re-sends it if needed.

LaBoutik n'est jamais appele : requests.post et check_serveur_cashless sont mockes.
On appelle la tache en direct (.run) : self.retry() leve alors celery Retry.
/ LaBoutik is never called (mocked). The task runs directly: self.retry() raises Retry.

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_send_refund_to_laboutik.py -q
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from celery.exceptions import Retry

from fabriques_reservation import (
    creer_evenement_et_produit,
    identifiant_aleatoire,
    nettoyer_vente_admin,
    vente_admin_especes,
)


@pytest.fixture
def vente_especes_et_avoir(api_client, auth_headers, tenant):
    """
    Cree une vente admin en especes (1 billet) et un avoir sur cette vente.
    L'avoir est cree SANS original_lignearticle_uuid dans ses metadata,
    comme les anciens avoirs (cas qui donnait un 400 cote LaBoutik).
    / Creates a cash admin sale and a credit note WITHOUT the original uuid in metadata.

    Le create() avec status=CREDIT_NOTE ne declenche pas le signal :
    aucune tache Celery n'est lancee par la fixture.
    / create() with the final status does not fire the signal.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
    _reservation, ligne_de_vente = vente_admin_especes(tenant, event_uuid, price_uuid, qty=1)

    with tenant_context(tenant):
        avoir = LigneArticle.objects.create(
            pricesold=ligne_de_vente.pricesold,
            qty=-1,
            amount=ligne_de_vente.amount,
            vat=ligne_de_vente.vat,
            payment_method=ligne_de_vente.payment_method,
            credit_note_for=ligne_de_vente,
            status=LigneArticle.CREDIT_NOTE,
        )

    yield ligne_de_vente, avoir

    nettoyer_vente_admin(tenant, ligne_de_vente)


def _lancer_la_tache_de_remboursement(avoir_pk, reponse_de_laboutik=None):
    """
    Lance send_refund_to_laboutik en direct, avec LaBoutik mocke.
    / Runs send_refund_to_laboutik directly, with LaBoutik mocked.

    :return: (resultat ou exception levee, mock de requests.post, mock de send_sale_to_laboutik.delay)
    """
    from BaseBillet.models import Configuration
    from BaseBillet.tasks import send_refund_to_laboutik

    if reponse_de_laboutik is None:
        reponse_de_laboutik = MagicMock(status_code=200, text="")

    with (
        patch("BaseBillet.tasks.time.sleep"),
        patch.object(Configuration, "check_serveur_cashless", return_value=True),
        patch("BaseBillet.tasks.requests.post", return_value=reponse_de_laboutik) as mock_post,
        patch("BaseBillet.tasks.send_sale_to_laboutik.delay") as mock_envoi_de_la_vente,
    ):
        try:
            resultat = send_refund_to_laboutik.run(avoir_pk)
        except Retry as exception_retry:
            resultat = exception_retry

    return resultat, mock_post, mock_envoi_de_la_vente


def test_vente_pas_encore_envoyee_relance_la_vente_et_reessaie_plus_tard(vente_especes_et_avoir, tenant):
    """
    La vente d'origine n'est pas dans LaBoutik : on relance son envoi,
    on n'envoie PAS le remboursement, et la tache se replanifie.
    / Original sale not in LaBoutik: re-send it, don't send the refund, retry later.
    """
    from django_tenants.utils import tenant_context

    ligne_de_vente, avoir = vente_especes_et_avoir
    assert not ligne_de_vente.sended_to_laboutik

    with tenant_context(tenant):
        resultat, mock_post, mock_envoi_de_la_vente = _lancer_la_tache_de_remboursement(avoir.pk)

    assert isinstance(resultat, Retry)
    mock_envoi_de_la_vente.assert_called_once_with(ligne_de_vente.pk)
    mock_post.assert_not_called()


def test_vente_deja_envoyee_envoie_le_remboursement_avec_uuid_d_origine(vente_especes_et_avoir, tenant):
    """
    La vente d'origine est dans LaBoutik : le remboursement part.
    L'uuid d'origine est ajoute au payload meme si l'avoir ne l'a pas en metadata.
    Apres un 200, l'avoir est marque comme envoye.
    / Original sale already synced: refund is sent with the original uuid, then flagged.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    ligne_de_vente, avoir = vente_especes_et_avoir

    with tenant_context(tenant):
        LigneArticle.objects.filter(pk=ligne_de_vente.pk).update(sended_to_laboutik=True)
        resultat, mock_post, mock_envoi_de_la_vente = _lancer_la_tache_de_remboursement(avoir.pk)
        avoir.refresh_from_db()

    assert resultat is True
    mock_envoi_de_la_vente.assert_not_called()
    mock_post.assert_called_once()

    url_appelee = mock_post.call_args.args[0]
    assert url_appelee.endswith("/api/refundfromlespass")

    payload_envoye = json.loads(mock_post.call_args.kwargs["data"])
    assert payload_envoye["metadata"]["original_lignearticle_uuid"] == str(ligne_de_vente.uuid)
    assert avoir.sended_to_laboutik is True


def test_reponse_404_de_laboutik_abandonne_sans_marquer_envoye(vente_especes_et_avoir, tenant):
    """
    LaBoutik repond 404 (vente d'origine inconnue) : la tache abandonne,
    l'avoir n'est pas marque comme envoye.
    / LaBoutik answers 404: task gives up, the credit note is not flagged as sent.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    ligne_de_vente, avoir = vente_especes_et_avoir
    reponse_404 = MagicMock(status_code=404, text="Not found")

    with tenant_context(tenant):
        LigneArticle.objects.filter(pk=ligne_de_vente.pk).update(sended_to_laboutik=True)
        resultat, _mock_post, _mock_envoi = _lancer_la_tache_de_remboursement(avoir.pk, reponse_404)
        avoir.refresh_from_db()

    assert resultat is False
    assert avoir.sended_to_laboutik is False


def test_remboursement_sans_vente_d_origine_abandonne_sans_appeler_laboutik(vente_especes_et_avoir, tenant):
    """
    Une ligne sans credit_note_for ni metadata d'origine ne peut pas etre
    enregistree par LaBoutik : on abandonne sans l'appeler.
    / A line with no link to its original sale is dropped without calling LaBoutik.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    ligne_de_vente, _avoir = vente_especes_et_avoir

    with tenant_context(tenant):
        remboursement_orphelin = LigneArticle.objects.create(
            pricesold=ligne_de_vente.pricesold,
            qty=-1,
            amount=ligne_de_vente.amount,
            vat=ligne_de_vente.vat,
            payment_method=ligne_de_vente.payment_method,
            status=LigneArticle.REFUNDED,
        )
        try:
            resultat, mock_post, mock_envoi_de_la_vente = _lancer_la_tache_de_remboursement(
                remboursement_orphelin.pk
            )
        finally:
            remboursement_orphelin.delete()

    assert resultat is False
    mock_post.assert_not_called()
    mock_envoi_de_la_vente.assert_not_called()


def test_trouver_ligne_de_vente_originale_par_metadata(vente_especes_et_avoir, tenant):
    """
    Remboursement Stripe : pas de credit_note_for, l'origine est dans metadata.
    / Stripe refund: no credit_note_for, the original is found through metadata.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle
    from BaseBillet.tasks import trouver_ligne_de_vente_originale

    ligne_de_vente, _avoir = vente_especes_et_avoir

    with tenant_context(tenant):
        remboursement_stripe = LigneArticle(
            pricesold=ligne_de_vente.pricesold,
            qty=-1,
            amount=ligne_de_vente.amount,
            metadata={"original_lignearticle_uuid": str(ligne_de_vente.uuid)},
        )
        ligne_trouvee = trouver_ligne_de_vente_originale(remboursement_stripe)

    assert ligne_trouvee == ligne_de_vente

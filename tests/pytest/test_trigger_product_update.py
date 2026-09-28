"""
tests/pytest/test_trigger_product_update.py
La tache qui previent LaBoutik V1 qu'un produit adhesion a change.
/ The task that tells LaBoutik V1 a membership product changed.

LOCALISATION : tests/pytest/test_trigger_product_update.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`BaseBillet.tasks.trigger_product_update_tasks` part a CHAQUE enregistrement d'un
produit (signal post_save). Elle ne sert que si LaBoutik V1 est configure, et
seulement pour une adhesion. Elle doit donc sortir tout de suite dans tous les
autres cas, sans pause : sinon chaque produit enregistre (tests compris) occupe un
processus Celery une seconde pour rien.

Le produit est cherche par une boucle courte (le save() qui a declenche la tache
peut ne pas etre encore visible), pas par une pause fixe.

Pas de base de donnees : la configuration, le produit, la pause et l'appel reseau
sont simules. / No database: config, product, sleep and network call are mocked.

Lancement / Run:
    make test ARGS="tests/pytest/test_trigger_product_update.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402

from BaseBillet.models import Product  # noqa: E402
from BaseBillet.tasks import trigger_product_update_tasks  # noqa: E402

UUID_DU_PRODUIT = "5fe5230e-212b-4b66-b657-0998db8015a6"


def _configuration(avec_laboutik_v1, serveur_repond=True):
    """Une configuration de lieu simulee, avec ou sans LaBoutik V1.
    / A mocked venue configuration, with or without LaBoutik V1."""
    return SimpleNamespace(
        server_cashless="https://laboutik.example" if avec_laboutik_v1 else None,
        key_cashless="cle-api" if avec_laboutik_v1 else None,
        check_serveur_cashless=mock.Mock(return_value=serveur_repond),
        domain=lambda: "lieu.example",
    )


def _lancer_la_tache(configuration, produits_successifs):
    """Lance la tache (sans Celery) ; `produits_successifs` : ce que renvoie chaque
    recherche du produit (None = pas encore visible).
    / Runs the task; each lookup returns the next value of produits_successifs."""
    with (
        mock.patch("BaseBillet.tasks.Configuration") as classe_configuration,
        mock.patch("BaseBillet.tasks.Product.objects.filter") as recherche_du_produit,
        mock.patch("BaseBillet.tasks.time.sleep") as pause,
        mock.patch("BaseBillet.tasks.requests.post") as envoi_a_laboutik,
    ):
        classe_configuration.get_solo.return_value = configuration
        recherche_du_produit.return_value.first.side_effect = produits_successifs
        trigger_product_update_tasks(UUID_DU_PRODUIT)
    return pause, envoi_a_laboutik, recherche_du_produit


def _adhesion():
    return SimpleNamespace(pk=UUID_DU_PRODUIT, categorie_article=Product.ADHESION)


def test_sans_laboutik_v1_la_tache_sort_tout_de_suite():
    """Pas de LaBoutik V1 : ni pause, ni recherche du produit, ni reseau.
    / No LaBoutik V1: no sleep, no product lookup, no network."""
    configuration = _configuration(avec_laboutik_v1=False)

    pause, envoi_a_laboutik, recherche_du_produit = _lancer_la_tache(
        configuration, [_adhesion()]
    )

    pause.assert_not_called()
    recherche_du_produit.assert_not_called()
    configuration.check_serveur_cashless.assert_not_called()
    envoi_a_laboutik.assert_not_called()


def test_une_adhesion_est_envoyee_a_laboutik_v1_sans_pause():
    """LaBoutik V1 configure, adhesion deja en base : un envoi, aucune pause.
    / LaBoutik V1 set, membership already saved: one call, no sleep."""
    configuration = _configuration(avec_laboutik_v1=True)

    pause, envoi_a_laboutik, _recherche = _lancer_la_tache(configuration, [_adhesion()])

    pause.assert_not_called()
    envoi_a_laboutik.assert_called_once()
    assert envoi_a_laboutik.call_args.kwargs["data"] == {"product_pk": UUID_DU_PRODUIT}


def test_le_produit_est_attendu_par_une_boucle_courte():
    """Produit visible au 3e essai : deux courtes pauses, puis l'envoi.
    / Product visible on the 3rd try: two short sleeps, then the call."""
    configuration = _configuration(avec_laboutik_v1=True)

    pause, envoi_a_laboutik, _recherche = _lancer_la_tache(
        configuration, [None, None, _adhesion()]
    )

    assert pause.call_count == 2
    for appel in pause.call_args_list:
        assert appel.args[0] < 1
    envoi_a_laboutik.assert_called_once()


def test_un_produit_introuvable_n_est_pas_envoye():
    """Produit jamais visible (supprime) : la boucle s'arrete, rien n'est envoye.
    / Product never visible (deleted): the loop stops, nothing is sent."""
    configuration = _configuration(avec_laboutik_v1=True)

    _pause, envoi_a_laboutik, recherche_du_produit = _lancer_la_tache(
        configuration, [None] * 50
    )

    assert recherche_du_produit.call_count == 10
    envoi_a_laboutik.assert_not_called()


def test_un_produit_qui_n_est_pas_une_adhesion_n_interroge_pas_laboutik_v1():
    """Produit de caisse : ni ping du serveur, ni envoi.
    / POS product: no server ping, no call."""
    configuration = _configuration(avec_laboutik_v1=True)
    produit_de_caisse = SimpleNamespace(pk=UUID_DU_PRODUIT, categorie_article=Product.NONE)

    _pause, envoi_a_laboutik, _recherche = _lancer_la_tache(
        configuration, [produit_de_caisse]
    )

    configuration.check_serveur_cashless.assert_not_called()
    envoi_a_laboutik.assert_not_called()


# ----------------------------------------------------------------------
# Le signal post_save qui envoie la tache / The post_save signal that sends the task
# ----------------------------------------------------------------------


def _appeler_le_signal(categorie_article):
    """Appelle le receveur post_save sur un produit simule ; renvoie les simulations
    de `transaction.on_commit` et de `delay`.
    / Calls the post_save receiver on a mocked product."""
    from BaseBillet.signals import trigger_product_update

    produit = SimpleNamespace(pk=UUID_DU_PRODUIT, categorie_article=categorie_article)
    with (
        mock.patch("BaseBillet.signals.transaction.on_commit") as a_la_validation,
        mock.patch("BaseBillet.signals.trigger_product_update_tasks.delay") as envoi_de_la_tache,
    ):
        trigger_product_update(sender=Product, instance=produit, created=True)
        return a_la_validation, envoi_de_la_tache


def test_le_signal_n_envoie_rien_pour_un_produit_qui_n_est_pas_une_adhesion():
    """Un article de caisse enregistre : aucune tache.
    / A saved POS item: no task."""
    a_la_validation, envoi_de_la_tache = _appeler_le_signal(Product.NONE)

    a_la_validation.assert_not_called()
    envoi_de_la_tache.assert_not_called()


def test_le_signal_envoie_la_tache_d_une_adhesion_apres_la_validation():
    """Une adhesion enregistree : la tache part a la validation de la transaction
    (on_commit), pas avant.
    / A saved membership: the task is sent on commit, not before."""
    a_la_validation, envoi_de_la_tache = _appeler_le_signal(Product.ADHESION)

    envoi_de_la_tache.assert_not_called()
    a_la_validation.assert_called_once()
    rappel_a_la_validation = a_la_validation.call_args.args[0]
    with mock.patch("BaseBillet.signals.trigger_product_update_tasks.delay") as envoi:
        rappel_a_la_validation()
    envoi.assert_called_once_with(UUID_DU_PRODUIT)

"""
Tests pour la tâche Celery horaire des clôtures + email auto de la clôture comptable.
/ Tests for the hourly Celery closure task + automatic closure report email.

LOCALISATION : tests/pytest/test_comptabilite_celery.py

CE QUI EST TESTÉ
- La tâche horaire `cron_clotures_automatiques` (`TiBillet/celery.py`) envoie une
  sous-tâche `generer_les_clotures_automatiques_du_lieu` par lieu (le filet J à
  l'heure de fermeture + 2 h, puis les clôtures semaine, mois, année en heure locale).
  Un lieu en erreur est journalisé et n'empêche pas les autres. Le détail de ces règles
  est testé dans `tests/pytest/test_cloture_unique.py`.
- L'email de clôture : envoyé seulement si des destinataires sont configurés et que
  la périodicité du rapport est celle de la clôture.
/ What is tested: the hourly task runs every venue's automatic closures; the closure
email is only sent when configured.

SCHÉMA DÉDIÉ pour l'email : une J lit toutes les ventes du lieu ; le lieu de test ne
contient que la vente du test, et chaque test annule sa transaction à la fin. La
configuration du lieu (emails, périodicité) est réécrite à chaque test : son cache
(django-solo) survit à l'annulation de la transaction.
/ Dedicated schema for the email; the venue configuration is rewritten in every test.

Lancer / Run : make test ARGS="tests/pytest/test_comptabilite_celery.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from decimal import Decimal  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from BaseBillet.models import Configuration, PaymentMethod, Product, SaleOrigin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.tasks import envoyer_email_cloture, generer_cloture_pour_tenant  # noqa: E402
from Customers.models import Client  # noqa: E402
from fabriques_vente import creer_tarif_vendu, fabriquer_vente_encaissee  # noqa: E402
from laboutik.models import LaboutikConfiguration  # noqa: E402


def _schemas_des_lieux():
    """Tous les schémas sauf `public`. / Every schema except public."""
    return set(
        Client.objects.exclude(schema_name="public").values_list(
            "schema_name", flat=True
        )
    )


@pytest.mark.django_db
def test_cron_clotures_automatiques_lance_une_sous_tache_par_lieu():
    """
    La tâche horaire `cron_clotures_automatiques` lance une sous-tâche
    `generer_les_clotures_automatiques_du_lieu.delay(schema)` par lieu (tous les
    schémas sauf `public`), jamais la fonction elle-même : un lieu lent ne retient pas
    les autres. La sous-tâche est remplacée : rien n'est envoyé ni écrit.
    / The hourly task sends one sub-task per venue (mocked).
    """
    from TiBillet.celery import cron_clotures_automatiques

    with patch(
        "comptabilite.tasks.generer_les_clotures_automatiques_du_lieu"
    ) as sous_tache_simulee:
        cron_clotures_automatiques()

    schemas_envoyes = set()
    for appel in sous_tache_simulee.delay.call_args_list:
        schemas_envoyes.add(appel.args[0])
    assert schemas_envoyes == _schemas_des_lieux()
    sous_tache_simulee.assert_not_called()


@pytest.mark.django_db
def test_cron_une_erreur_dans_un_lieu_est_journalisee_et_n_empeche_pas_les_autres(
    caplog,
):
    """
    L'envoi de la sous-tâche du premier lieu échoue (simulé) : l'erreur est journalisée
    avec le schéma du lieu, et les sous-tâches des autres lieux sont quand même
    envoyées.
    / One venue failing is logged and does not stop the others.
    """
    from TiBillet.celery import cron_clotures_automatiques

    schemas_des_lieux = _schemas_des_lieux()
    schema_en_panne = sorted(schemas_des_lieux)[0]

    def envoi_en_panne_pour_un_lieu(schema_name):
        if schema_name == schema_en_panne:
            raise RuntimeError("panne simulée")

    with patch(
        "comptabilite.tasks.generer_les_clotures_automatiques_du_lieu"
    ) as sous_tache_simulee:
        sous_tache_simulee.delay.side_effect = envoi_en_panne_pour_un_lieu
        with caplog.at_level("ERROR", logger="comptabilite.tasks"):
            cron_clotures_automatiques()

    schemas_tentes = set()
    for appel in sous_tache_simulee.delay.call_args_list:
        schemas_tentes.add(appel.args[0])
    assert schemas_tentes == schemas_des_lieux
    assert schema_en_panne in caplog.text


class TestEmailDeCloture(FastTenantTestCase):
    """
    L'email automatique de la clôture. / The automatic closure email.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_comptabilite_celery"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-comptabilite-celery.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test comptabilite celery"

    def setUp(self):
        """
        Le lieu de test, son singleton de caisse, aucun email de rapport, une vente d'un
        jus en espèces, puis la J qui la couvre.
        / The test venue, no report email, one juice sale, then its J.
        """
        connection.set_tenant(self.tenant)
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.rapport_emails = ""
        configuration.save()

        tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        self.uuid_de_la_j = generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )

    def test_envoyer_email_cloture_skip_si_pas_de_config(self):
        """
        Si Configuration.rapport_emails est vide, l'email n'est PAS envoye.
        / If rapport_emails is empty, no email is sent.
        """
        with patch("comptabilite.tasks.CeleryMailerClass") as MockMailer:
            result = envoyer_email_cloture(self.tenant.schema_name, self.uuid_de_la_j)
            assert result is False
            MockMailer.assert_not_called()

    def test_envoyer_email_cloture_envoie_si_config_ok(self):
        """
        Si rapport_emails est configure ET rapport_periodicite matche le niveau,
        CeleryMailerClass est instancie avec le PDF en attachement.
        / If config matches, CeleryMailerClass is called with the PDF attachment.
        """
        configuration = Configuration.get_solo()
        configuration.rapport_emails = "compta@example.com, tresorerie@example.com"
        configuration.rapport_periodicite = ClotureCaisse.NIVEAU_JOURNALIER
        configuration.save()

        # L'envoi de l'email est remplacé : on lit les arguments qu'il reçoit. Son
        # `send()` rend 1, comme l'envoi de Django quand il réussit.
        # / The mailer is replaced to read its arguments; send() returns 1 like Django.
        with patch("comptabilite.tasks.CeleryMailerClass") as MockMailer:
            mock_instance = MagicMock()
            mock_instance.send.return_value = 1
            MockMailer.return_value = mock_instance

            envoyer_email_cloture(self.tenant.schema_name, self.uuid_de_la_j)

            assert MockMailer.called, "CeleryMailerClass should be instantiated"
            kwargs = MockMailer.call_args.kwargs
            # Deux destinataires, séparés par une virgule dans la configuration.
            # / Two recipients, comma-separated in the configuration.
            assert kwargs.get("email") == [
                "compta@example.com", "tresorerie@example.com",
            ]
            # Un seul fichier joint : le PDF de la clôture.
            # / One attachment: the closure PDF.
            assert kwargs.get("attached_files") is not None
            assert len(kwargs["attached_files"]) == 1
            # Le nom du PDF commence par « cloture- ».
            # / The PDF name starts with "cloture-".
            filename = list(kwargs["attached_files"].keys())[0]
            assert filename.startswith("cloture-") and filename.endswith(".pdf")
            mock_instance.send.assert_called_once()

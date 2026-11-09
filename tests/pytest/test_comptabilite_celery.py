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

from datetime import datetime, time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from BaseBillet.models import Configuration, PaymentMethod, Product, SaleOrigin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.tasks import (  # noqa: E402
    envoyer_email_cloture,
    generer_cloture_pour_tenant,
)
from Customers.models import Client  # noqa: E402
from fabriques_vente import (  # noqa: E402
    abonner_aux_envois_des_rapports,
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
)
from laboutik.models import LaboutikConfiguration  # noqa: E402


def _schemas_des_lieux():
    """
    Tous les schémas sauf `public` et sauf les emplacements vides `WAITING_CONFIG`.
    / Every schema except public and the empty WAITING_CONFIG slots.
    """
    return set(
        Client.objects.exclude(schema_name="public")
        .exclude(categorie=Client.WAITING_CONFIG)
        .values_list("schema_name", flat=True)
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


@pytest.mark.django_db
def test_cron_ignore_les_emplacements_vides_waiting_config():
    """
    Un emplacement vide (`WAITING_CONFIG`) ne reçoit pas de sous-tâche de clôture :
    il n'a aucune vente, et son schéma peut être en cours de migration par
    `cron_morning` (le lire pendant la migration provoque un interblocage).
    L'emplacement est une simple ligne `Client`, sans schéma PostgreSQL
    (`auto_create_schema = False`), annulée avec la transaction du test.
    / An empty WAITING_CONFIG slot gets no closure sub-task.
    """
    from TiBillet.celery import cron_clotures_automatiques

    emplacement_vide = Client(
        schema_name="test_emplacement_vide_cloture",
        name="Test emplacement vide cloture",
        categorie=Client.WAITING_CONFIG,
    )
    emplacement_vide.auto_create_schema = False
    emplacement_vide.save()

    with patch(
        "comptabilite.tasks.generer_les_clotures_automatiques_du_lieu"
    ) as sous_tache_simulee:
        cron_clotures_automatiques()

    schemas_envoyes = set()
    for appel in sous_tache_simulee.delay.call_args_list:
        schemas_envoyes.add(appel.args[0])
    assert "test_emplacement_vide_cloture" not in schemas_envoyes
    assert schemas_envoyes == _schemas_des_lieux()


class TestEmailDeCloture(FastTenantTestCase):
    """
    L'email automatique d'une clôture H, M ou A (`envoyer_email_cloture`). Une J n'a
    pas d'email automatique : son Z part dans le récap du matin.
    / The automatic e-mail of an H, M or A closure; a J has none (morning recap).
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
        Sans destinataire dans les réglages des envois, l'email n'est PAS envoyé.
        / Without any recipient in the mail settings, no email is sent.
        """
        with patch("comptabilite.tasks.CeleryMailerClass") as MockMailer:
            result = envoyer_email_cloture(self.tenant.schema_name, self.uuid_de_la_j)
            assert result is False
            MockMailer.assert_not_called()

    def test_envoyer_email_cloture_envoie_si_config_ok(self):
        """
        Avec deux destinataires et le rapport hebdomadaire coché, l'envoi automatique
        de la clôture de la semaine instancie CeleryMailerClass avec le PDF en
        attachement.
        / With two recipients and the weekly report ticked, the automatic sending of
        the week closure calls CeleryMailerClass with the PDF attachment.
        """
        # La semaine de la vente du setUp, clôturée le lundi suivant à 5 h 10, heure du
        # lieu (fermeture à 2 h : le filet de ce lundi est passé à 4 h). Créée avant de
        # régler les destinataires : sa création ne demande aucun envoi.
        # / The week of the setUp sale, closed the next Monday at 5:10 local time;
        # created before the recipients are set, so no sending is requested.
        configuration = Configuration.get_solo()
        configuration.heure_de_fermeture = time(2, 0)
        configuration.save()
        fuseau_du_lieu = configuration.get_tzinfo()
        aujourd_hui = timezone.localtime(timezone.now(), fuseau_du_lieu).date()
        lundi_suivant = aujourd_hui + timedelta(days=7 - aujourd_hui.weekday())
        lundi_suivant_a_5h10 = datetime.combine(
            lundi_suivant, time(5, 10), tzinfo=fuseau_du_lieu
        )
        with patch("django.utils.timezone.now", return_value=lundi_suivant_a_5h10):
            uuid_de_la_semaine = generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_HEBDOMADAIRE,
            )
        assert uuid_de_la_semaine is not None

        abonner_aux_envois_des_rapports("compta@example.com", "tresorerie@example.com")

        # L'envoi de l'email est remplacé : on lit les arguments qu'il reçoit. Son
        # `send()` rend 1, comme l'envoi de Django quand il réussit.
        # / The mailer is replaced to read its arguments; send() returns 1 like Django.
        with patch("comptabilite.tasks.CeleryMailerClass") as MockMailer:
            mock_instance = MagicMock()
            mock_instance.send.return_value = 1
            MockMailer.return_value = mock_instance

            email_envoye = envoyer_email_cloture(
                self.tenant.schema_name, uuid_de_la_semaine
            )

            assert email_envoye is True
            assert MockMailer.called, "CeleryMailerClass should be instantiated"
            kwargs = MockMailer.call_args.kwargs
            # Les deux destinataires de la liste, triés par e-mail.
            # / The list's two recipients, sorted by e-mail.
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

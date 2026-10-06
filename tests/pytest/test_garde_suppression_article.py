"""
Garde de suppression : un article d'une vente RÉGLÉE ne se supprime jamais.
/ Delete guard: an item of a SETTLED sale is never deleted.

LOCALISATION : tests/pytest/test_garde_suppression_article.py

CE QUE CES TESTS REGARDENT
- une vente encaissée : `LigneArticle.objects.filter(vente=v).delete()` (suppression par
  queryset), `article.delete()` (suppression d'un objet) et la suppression du tarif vendu
  (cascade vers ses articles) lèvent `ProtectedError`, et les articles sont toujours là ;
- un article d'une vente EN ATTENTE, d'une vente ANNULÉE, ou sans vente, se supprime
  toujours.
/ What these tests check: a settled sale refuses queryset, instance and cascade deletes
of its items (ProtectedError, items still there); a pending, cancelled or sale-less item
is still deleted.

POURQUOI UN `transaction.atomic()` AUTOUR DE CHAQUE SUPPRESSION REFUSÉE
Django efface dans un bloc atomique SANS point de sauvegarde. Une erreur levée dedans
casse la transaction du test : les requêtes suivantes seraient refusées. Le bloc
`atomic()` du test pose un point de sauvegarde, annulé proprement par l'erreur.
/ Django deletes inside an atomic block without savepoint: the test's own atomic() adds
a savepoint, so the refused delete does not break the test transaction.

SCHÉMA DÉDIÉ : chaque test annule sa transaction à la fin, rien ne reste en base.
/ Dedicated schema: each test is rolled back, nothing stays in the database.

CODE TESTÉ / CODE UNDER TEST
- BaseBillet/models.py — refuser_la_suppression_d_un_article_d_une_vente_reglee
  (receveur `pre_delete` de `LigneArticle`).

Lancer / Run : make test ARGS="tests/pytest/test_garde_suppression_article.py"
"""

from decimal import Decimal

from django.db import connection, transaction
from django.db.models.deletion import ProtectedError
from django_tenants.test.cases import FastTenantTestCase

from BaseBillet.models import LigneArticle, PaymentMethod, PriceSold, SaleOrigin
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import ajouter_article, annuler_vente, ouvrir_vente
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import LaboutikConfiguration

PRIX_DU_JUS_EN_CENTIMES = 350
TVA_DU_JUS = Decimal("20")


class TestGardeSuppressionArticle(FastTenantTestCase):
    """
    La garde `pre_delete` de `LigneArticle`, dans un schéma dédié.
    / The LigneArticle pre_delete guard, in a dedicated schema.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_garde_suppression"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-garde-suppression.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test garde de suppression"

    def setUp(self):
        """
        Le lieu du test, le singleton de la caisse, et un jus à vendre.
        / The test venue, the register singleton, and a juice to sell.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé de l'empreinte (PIEGES 9.86).
        # / The register singleton holds the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        self.tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")

    def article_de_deux_jus(self):
        """
        L'article « 2 jus à 3,50 € », à passer à `ajouter_article`.
        / The "2 juices at 3.50 €" item, for ajouter_article.
        """
        return {
            "pricesold": self.tarif_du_jus,
            "quantite": Decimal("2"),
            "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
            "taux_tva": TVA_DU_JUS,
        }

    def encaisser_deux_jus_en_especes(self):
        """
        Une vente réglée de deux jus (700 centimes) payés en espèces.
        / A settled sale of two juices (700 cents) paid in cash.
        """
        return fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[self.article_de_deux_jus()],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 700}],
        )

    # ------------------------------------------------------------------ #
    #  Vente réglée : toute suppression d'article est refusée
    #  / Settled sale: every item delete is refused
    # ------------------------------------------------------------------ #

    def test_supprimer_par_queryset_les_articles_d_une_vente_reglee_est_refuse(self):
        """
        `LigneArticle.objects.filter(vente=v).delete()` lève `ProtectedError` : le
        receveur `pre_delete` est appelé pour chaque ligne. L'article est toujours là,
        et la vente garde ses deux égalités.
        / A queryset delete raises ProtectedError; the item is still there.
        """
        vente = self.encaisser_deux_jus_en_especes()
        assert vente.statut == Vente.Statut.REGLEE
        assert LigneArticle.objects.filter(vente=vente).count() == 1

        with self.assertRaises(ProtectedError) as erreur:
            with transaction.atomic():
                LigneArticle.objects.filter(vente=vente).delete()

        assert "vente réglée" in str(erreur.exception)
        assert LigneArticle.objects.filter(vente=vente).count() == 1
        verifier_egalites(vente)

    def test_supprimer_un_article_d_une_vente_reglee_est_refuse(self):
        """
        `article.delete()` lève `ProtectedError`. L'article est toujours là.
        / An instance delete raises ProtectedError; the item is still there.
        """
        vente = self.encaisser_deux_jus_en_especes()
        article = LigneArticle.objects.get(vente=vente)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                article.delete()

        assert LigneArticle.objects.filter(pk=article.pk).exists()
        verifier_egalites(vente)

    def test_supprimer_le_tarif_vendu_d_une_vente_reglee_est_refuse(self):
        """
        Le tarif vendu efface ses articles en cascade (`on_delete=CASCADE`) : la
        cascade passe aussi par la garde. `ProtectedError`, l'article et le tarif
        vendu sont toujours là.
        / Deleting the sold price cascades to its items: the guard refuses it too.
        """
        vente = self.encaisser_deux_jus_en_especes()

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                PriceSold.objects.filter(pk=self.tarif_du_jus.pk).delete()

        assert PriceSold.objects.filter(pk=self.tarif_du_jus.pk).exists()
        assert LigneArticle.objects.filter(vente=vente).count() == 1

    # ------------------------------------------------------------------ #
    #  Vente en attente, vente annulée, sans vente : la suppression passe
    #  / Pending sale, cancelled sale, no sale: the delete goes through
    # ------------------------------------------------------------------ #

    def test_un_article_d_une_vente_en_attente_se_supprime(self):
        """
        Une vente EN ATTENTE n'est pas scellée : son article se supprime, par queryset.
        / A pending sale is not sealed: its item is deleted.
        """
        vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
        ajouter_article(vente, **self.article_de_deux_jus())
        assert vente.statut == Vente.Statut.EN_ATTENTE

        LigneArticle.objects.filter(vente=vente).delete()

        assert LigneArticle.objects.filter(vente=vente).count() == 0

    def test_un_article_d_une_vente_annulee_se_supprime(self):
        """
        Une vente ANNULÉE n'a ni numéro ni empreinte : son article se supprime.
        / A cancelled sale has no number nor fingerprint: its item is deleted.
        """
        vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
        article = ajouter_article(vente, **self.article_de_deux_jus())
        vente_annulee = annuler_vente(vente)
        assert vente_annulee.statut == Vente.Statut.ANNULEE

        LigneArticle.objects.get(pk=article.pk).delete()

        assert not LigneArticle.objects.filter(pk=article.pk).exists()

    def test_un_article_sans_vente_se_supprime(self):
        """
        Une ligne qui n'a pas été écrite par le service de vente (`vente` vide) se
        supprime toujours.
        / A line without a sale is always deleted.
        """
        article_sans_vente = LigneArticle.objects.create(
            pricesold=self.tarif_du_jus,
            qty=Decimal("1"),
            amount=PRIX_DU_JUS_EN_CENTIMES,
        )
        assert article_sans_vente.vente_id is None

        article_sans_vente.delete()

        assert not LigneArticle.objects.filter(pk=article_sans_vente.pk).exists()

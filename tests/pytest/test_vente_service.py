"""
Tests du service de vente : ouvrir, ajouter des articles et des règlements, encaisser,
annuler. Et la garde qui empêche de modifier une vente réglée.
/ Tests of the sale service: open, add items and payments, settle, cancel. And the guard
that forbids changing a settled sale.

LOCALISATION : tests/pytest/test_vente_service.py

CE QUE CES TESTS REGARDENT
- `ouvrir_vente` rend la vente déjà ouverte pour une clé d'idempotence connue ;
- `ajouter_reglement` refuse un montant qui n'est pas un entier non nul ;
- `ouvrir_vente` et `ajouter_reglement` refusent une nature, une origine ou un moyen
  hors de leurs choix ;
- `ajouter_article` écrit la ligne sans lancer la machine à statuts, applique la règle
  « offert à montant non nul », fige `hors_chiffre_affaires`, refuse une TVA sur une
  vente en points ;
- `encaisser_vente` vérifie les deux égalités, pose un numéro sans trou, une seule fois,
  refuse une vente annulée, et refuse une vente sans article (sauf vidage de carte et
  correction) ;
- une vente réglée refuse toute modification par `save()` (sauf les champs libres de la
  ligne, comme son statut), et la garde compare les valeurs telles que la base les
  stocke (une quantité à 28 décimales en mémoire vaut sa version à 6 décimales) ;
- une vente réglée ou annulée ne reçoit plus d'article ni de règlement ; `annuler_vente`
  refuse une vente réglée et rend telle quelle une vente déjà annulée ;
- la ligne porte l'origine de sa vente, sauf si le producteur en passe une ;
- l'empreinte chaînée : chaque vente réglée porte une empreinte calculée sur le message
  de la fiche §5 et sur l'empreinte de la vente précédente ; `verifier_chaine_ventes`
  signale une vente altérée par `.update()` (empreinte fausse), une vente supprimée (trou
  de numéro), un règlement supprimé (égalité rompue), une empreinte précédente changée
  (maillon cassé).
/ What these tests check: the sale service functions, the settled-sale guard and the
chained fingerprint of the sales.

SCHÉMA DÉDIÉ
Ces tests lisent la numérotation des ventes : ils tournent dans un schéma à eux
(`FastTenantTestCase`), où aucune autre vente n'existe. Chaque test annule sa transaction
à la fin : la première vente encaissée d'un test porte donc toujours le numéro 1.
Le singleton `LaboutikConfiguration` est créé à la main (tests/PIEGES.md 9.86).
/ Dedicated schema: no other sale exists, each test is rolled back, so the first settled
sale of a test is number 1.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md
(§2, §3, §4, §7) et CHANTIER-05-montants-entiers.md (§2, §4 D3-D5, D8, D9, D12, D16).

CODE TESTÉ / CODE UNDER TEST
- BaseBillet/services_vente.py — ouvrir_vente, ajouter_article, ajouter_reglement,
  encaisser_vente, annuler_vente, EgaliteDeVenteRompue ;
- BaseBillet/models_vente.py — Vente.save(), Reglement.save() (garde) ;
- BaseBillet/models.py — LigneArticle.save() (garde) ;
- laboutik/integrity.py — calculer_hmac_vente, verifier_chaine_ventes.

Lancer / Run : make test ARGS="tests/pytest/test_vente_service.py"
"""

import datetime
import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django_tenants.test.cases import FastTenantTestCase

from BaseBillet.models import LigneArticle, PaymentMethod, Product, SaleOrigin
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    MOYENS_OFFERTS,
    EgaliteDeVenteRompue,
    ajouter_article,
    ajouter_reglement,
    annuler_vente,
    encaisser_vente,
    ouvrir_vente,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.integrity import calculer_hmac_vente, verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration, PointDeVente

# Un jus à 3,50 € TTC, TVA 20 % : le prix unitaire des articles de ces tests.
# / A juice at 3.50 € incl. VAT, 20 %: the unit price used in these tests.
PRIX_DU_JUS_EN_CENTIMES = 350
TVA_DU_JUS = Decimal("20")


def calculer_l_empreinte_attendue(vente, cle, previous_hmac):
    """
    Recalcule l'empreinte d'une vente À LA MAIN, depuis le message écrit dans la fiche
    (CHANTIER-05-A-vente-reglement.md §5), sans passer par `calculer_hmac_vente`.
    / Recomputes a sale fingerprint BY HAND, from the message written in the spec.

    LOCALISATION : tests/pytest/test_vente_service.py

    Cette fonction recopie la fiche, champ par champ. Elle ne doit pas appeler le code
    testé : sinon, une erreur dans le message (une clé oubliée, une date pas en UTC, un
    tri manquant) serait recopiée des deux côtés, et le test passerait quand même.
    Le message est un JSON canonique : clés triées, sans espace, accents gardés.
    / This function copies the spec field by field and never calls the tested code.

    :param vente: la vente (relue en base par cette fonction)
    :param cle: la clé de l'empreinte du lieu (texte)
    :param previous_hmac: l'empreinte de la vente précédente ("" pour la première)
    :return: l'empreinte HMAC-SHA256, en 64 caractères hexadécimaux
    """
    vente_relue = Vente.objects.get(pk=vente.pk)

    # Les articles, triés par uuid.
    # / The items, sorted by uuid.
    articles_du_message = []
    for article in LigneArticle.objects.filter(vente=vente_relue).order_by("uuid"):
        articles_du_message.append(
            [
                str(article.uuid),
                str(article.pricesold_id),
                f"{article.qty:.6f}",
                article.amount,
                f"{article.vat:.2f}",
                article.total_catalogue,
                article.part_offerte,
                article.source_offert,
                article.part_en_jetons,
                article.total_ttc,
                article.total_ht,
                article.total_tva,
                article.hors_chiffre_affaires,
            ]
        )

    # Les règlements, triés par uuid. Un champ vide s'écrit "".
    # / The payments, sorted by uuid. An empty field is written "".
    reglements_du_message = []
    for reglement in Reglement.objects.filter(vente=vente_relue).order_by("uuid"):
        reglements_du_message.append(
            [
                str(reglement.uuid),
                reglement.moyen,
                reglement.montant,
                str(reglement.asset or ""),
                str(reglement.carte_id or ""),
                str(reglement.fedow_transaction_uuid or ""),
                reglement.reference_externe,
            ]
        )

    heure_d_encaissement_en_utc = vente_relue.datetime_encaissement.astimezone(
        datetime.timezone.utc
    )
    donnees = {
        "format": 1,
        "uuid": str(vente_relue.uuid),
        "numero": vente_relue.numero,
        "datetime_encaissement": heure_d_encaissement_en_utc.isoformat(),
        "nature": vente_relue.nature,
        "origine": vente_relue.origine,
        "unite": vente_relue.unite,
        "statut": vente_relue.statut,
        "point_de_vente": str(vente_relue.point_de_vente_id or ""),
        "vente_liee": str(vente_relue.vente_liee_id or ""),
        "totaux": [
            vente_relue.total_catalogue,
            vente_relue.total_offert,
            vente_relue.total_ttc,
            vente_relue.total_ht,
            vente_relue.total_tva,
        ],
        "articles": articles_du_message,
        "reglements": reglements_du_message,
        "previous_hmac": previous_hmac,
    }
    message = json.dumps(
        donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hmac.new(
        cle.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def anomalie_signalee(anomalies, vente, raison_attendue):
    """
    Dit si `verifier_chaine_ventes` a signalé cette vente, pour cette raison.
    / Tells whether the chain check reported this sale, for this reason.

    LOCALISATION : tests/pytest/test_vente_service.py

    Une anomalie est un dictionnaire : "numero", "uuid" (texte) et "raison" (phrase en
    français). La raison est comparée en minuscules : « Empreinte fausse : … » contient
    bien « empreinte fausse ».
    / An anomaly is a dict: "numero", "uuid" (text), "raison" (French sentence).

    :param anomalies: la liste rendue par `verifier_chaine_ventes`
    :param vente: la vente attendue dans une anomalie
    :param raison_attendue: un morceau de la raison, en minuscules (ex. "trou de numéro")
    :return: True si une anomalie de cette vente contient cette raison
    """
    for anomalie in anomalies:
        meme_vente = anomalie["uuid"] == str(vente.uuid)
        meme_raison = raison_attendue in anomalie["raison"].lower()
        if meme_vente and meme_raison:
            return True
    return False


class TestServiceDeVente(FastTenantTestCase):
    """
    Le service de vente et la garde d'une vente réglée, dans un schéma dédié.
    / The sale service and the settled-sale guard, in a dedicated schema.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_vente_service"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-vente-service.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test service de vente"

    def setUp(self):
        """
        Le lieu du test, le singleton de la caisse, et un jus à vendre.
        / The test venue, the register singleton, and a juice to sell.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (PIEGES 9.86) : il porte la
        # clé de l'empreinte des ventes.
        # / The register singleton must exist in the database: it holds the HMAC key.
        LaboutikConfiguration.get_solo().save()

        self.tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")

    def ouvrir_une_vente_en_caisse(self, **autres_champs):
        """
        Ouvre une vente de caisse (nature VENTE, sauf si on en passe une autre).
        / Opens a register sale (nature VENTE unless another one is given).
        """
        nature = autres_champs.pop("nature", Vente.Nature.VENTE)
        return ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=nature, **autres_champs)

    def ajouter_des_jus(self, vente, quantite, **autres_champs):
        """
        Ajoute `quantite` jus à 3,50 € (TVA 20 %) à la vente, par le service.
        / Adds `quantite` juices at 3.50 € (20 % VAT) to the sale, through the service.
        """
        return ajouter_article(
            vente,
            pricesold=self.tarif_du_jus,
            quantite=Decimal(quantite),
            prix_unitaire=PRIX_DU_JUS_EN_CENTIMES,
            taux_tva=TVA_DU_JUS,
            **autres_champs,
        )

    def encaisser_des_jus_payes_en_especes(self, quantite):
        """
        Écrit et encaisse, par le service, une vente de `quantite` jus réglés en espèces.
        / Writes and settles, through the service, a sale of juices paid in cash.
        """
        montant_en_centimes = PRIX_DU_JUS_EN_CENTIMES * int(quantite)
        return fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal(quantite),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": montant_en_centimes},
            ],
        )

    def cle_de_l_empreinte_du_lieu(self):
        """
        La clé de l'empreinte du lieu, celle qu'utilise `encaisser_vente`.
        / The venue fingerprint key, the one used by encaisser_vente.
        """
        return LaboutikConfiguration.get_solo().get_or_create_hmac_key()

    def alterer_par_update(
        self, champ_altere, vente_a_alterer, vente_de_reference, point_de_vente
    ):
        """
        Altère une vente réglée par `.update()`, sans passer par `save()`.
        / Tampers with a settled sale through .update(), bypassing save().

        `.update()` écrit en base sans appeler `save()` : la garde d'immutabilité ne voit
        rien. Seule l'empreinte peut révéler l'altération.
        La vente à altérer est celle de `encaisser_des_jus_payes_en_especes("3")` : un
        article de 1050 (HT 875, TVA 175), un règlement de 1050 en espèces.
        / .update() bypasses the immutability guard: only the fingerprint can reveal it.

        :param champ_altere: le nom du cas (voir la liste du test)
        :param vente_a_alterer: la vente réglée à altérer
        :param vente_de_reference: une autre vente réglée, pour le cas `vente_liee`
        :param point_de_vente: un point de vente, pour le cas `point_de_vente`
        """
        ventes_a_alterer = Vente.objects.filter(pk=vente_a_alterer.pk)

        if champ_altere == "total_ttc d'un article":
            # Les contraintes de base refusent un `total_ttc` changé seul
            # (total_ttc = total_catalogue − part_offerte ; HT + TVA = total_ttc) : la
            # baisse de 50 centimes est donc déguisée en « offert », cohérent pour la base.
            # / The base constraints refuse total_ttc alone: the change is disguised as
            # a consistent "offered" part.
            LigneArticle.objects.filter(vente=vente_a_alterer).update(
                part_offerte=50,
                total_ttc=1000,
                total_ht=833,
                total_tva=167,
            )
        elif champ_altere == "montant d'un règlement":
            Reglement.objects.filter(vente=vente_a_alterer).update(montant=1000)
        elif champ_altere == "vente_liee":
            ventes_a_alterer.update(vente_liee=vente_de_reference)
        elif champ_altere == "point_de_vente":
            ventes_a_alterer.update(point_de_vente=point_de_vente)
        elif champ_altere == "numero":
            ventes_a_alterer.update(numero=vente_a_alterer.numero + 100)
        elif champ_altere == "datetime_encaissement":
            une_heure_plus_tot = vente_a_alterer.datetime_encaissement - (
                datetime.timedelta(hours=1)
            )
            ventes_a_alterer.update(datetime_encaissement=une_heure_plus_tot)
        elif champ_altere == "nature":
            ventes_a_alterer.update(nature=Vente.Nature.AVOIR)
        elif champ_altere == "origine":
            ventes_a_alterer.update(origine=SaleOrigin.ADMIN)
        elif champ_altere == "unite":
            ventes_a_alterer.update(unite=str(uuid.uuid4()))
        elif champ_altere == "totaux de la vente":
            ventes_a_alterer.update(total_offert=100)
        else:
            raise ValueError(f"Cas d'altération inconnu : {champ_altere}")

    # ----------------------------------------------------------------------
    # Ouverture, règlements et articles
    # / Opening, payments and items
    # ----------------------------------------------------------------------

    def test_ouvrir_vente_meme_cle_rend_la_meme_vente(self):
        """
        Anti double clic : ouvrir deux fois une vente avec la même clé d'idempotence
        rend la vente déjà ouverte. Une seule vente existe pour cette clé.
        / Opening twice with the same idempotency key returns the same sale.
        """
        cle_d_idempotence = f"cle-test-vente-{uuid.uuid4()}"

        premiere_vente = self.ouvrir_une_vente_en_caisse(
            idempotency_key=cle_d_idempotence
        )
        vente_du_second_clic = self.ouvrir_une_vente_en_caisse(
            idempotency_key=cle_d_idempotence
        )

        assert vente_du_second_clic.pk == premiere_vente.pk
        assert Vente.objects.filter(idempotency_key=cle_d_idempotence).count() == 1

    def test_reglement_decimal_ou_nul_refuse(self):
        """
        Un règlement est un montant en centimes ENTIERS, non nul, copié de sa source.
        `ajouter_reglement` refuse un `Decimal`, un `float` et 0, avant toute écriture :
        aucun règlement n'est créé.
        / A payment is a non-zero whole-cent int: Decimal, float and 0 are refused, and
        nothing is written.
        """
        vente = self.ouvrir_une_vente_en_caisse()

        montants_refuses = [Decimal("5.5"), 5.5, 0]
        for montant_refuse in montants_refuses:
            with pytest.raises(ValueError):
                ajouter_reglement(
                    vente, moyen=PaymentMethod.CASH, montant=montant_refuse
                )

        assert Reglement.objects.filter(vente=vente).count() == 0

    def test_valeurs_hors_choix_refusees(self):
        """
        Le service refuse (ValueError) une valeur qui n'est pas dans ses choix :
        - `ajouter_reglement` : un moyen hors de `PaymentMethod` ;
        - `ouvrir_vente` : une origine hors de `SaleOrigin`, une nature hors de
          `Vente.Nature`.
        La base ne vérifie pas les choix d'un champ texte : sans ce refus, la valeur
        serait écrite telle quelle. Rien n'est écrit : aucun règlement, et aucune autre
        vente que celle ouverte au début du test.
        Chaque cas est joué, puis le test liste ceux qui n'ont pas été refusés.
        / Values outside the choices are refused, and nothing is written. Every case is
        played, then the test lists those not refused.
        """
        vente = self.ouvrir_une_vente_en_caisse()

        # Les valeurs inventées tiennent dans la longueur de leur colonne : seule la
        # vérification des choix peut les refuser.
        # / The made-up values fit their column length: only the choices check refuses.
        cas_a_verifier = [
            (
                "moyen de règlement « XX »",
                ajouter_reglement,
                {"vente": vente, "moyen": "XX", "montant": PRIX_DU_JUS_EN_CENTIMES},
            ),
            (
                "origine de vente « ZZ »",
                ouvrir_vente,
                {"origine": "ZZ", "nature": Vente.Nature.VENTE},
            ),
            (
                "nature de vente « INCONNUE »",
                ouvrir_vente,
                {"origine": SaleOrigin.LABOUTIK, "nature": "INCONNUE"},
            ),
        ]

        cas_non_refuses = []
        for nom_du_cas, fonction_du_service, arguments in cas_a_verifier:
            try:
                fonction_du_service(**arguments)
            except ValueError:
                continue
            cas_non_refuses.append(nom_du_cas)

        assert cas_non_refuses == [], f"Valeurs hors choix acceptées : {cas_non_refuses}"
        assert Reglement.objects.filter(vente=vente).count() == 0
        assert Vente.objects.count() == 1

    def test_ajouter_article_ne_declenche_aucune_transition(self):
        """
        Les déclencheurs d'une ligne (Fedow, e-mails, envoi à l'ancien LaBoutik) partent
        sur une TRANSITION de statut faite par un `save()`, jamais à la création
        (`BaseBillet/signals.py`, `pre_save_signal_status`).
        1. Une ligne créée par le service directement en « payée », puis encaissée : la
           fonction de la transition « payée » n'est jamais appelée. Le service ne fait
           aucun `save()` sur la ligne après sa création.
        2. Une ligne créée « non envoyée au paiement », que le producteur passe ensuite
           à « payée » par un `save()` : la fonction est appelée une fois, et une seule,
           même après l'encaissement.
        / The status machine runs on a save() transition, never at creation. The service
        never saves a line after creating it; the producer's own transition runs once.
        """
        # La transition « payée » appelle cette fonction (ligne_article_paid) : on la
        # remplace pour compter ses appels.
        # / The "paid" transition calls this function: replaced to count its calls.
        with patch(
            "BaseBillet.signals.TRIGGER_LigneArticlePaid_ActionByCategorie"
        ) as declencheur_de_la_ligne_payee:
            # 1. Créée « payée » par le service, puis encaissée.
            # / 1. Created "paid" by the service, then settled.
            vente_payee_a_la_creation = self.ouvrir_une_vente_en_caisse()
            self.ajouter_des_jus(
                vente_payee_a_la_creation,
                quantite="1",
                status=LigneArticle.PAID,
                payment_method=PaymentMethod.CASH,
            )
            ajouter_reglement(
                vente_payee_a_la_creation,
                moyen=PaymentMethod.CASH,
                montant=PRIX_DU_JUS_EN_CENTIMES,
            )
            encaisser_vente(vente_payee_a_la_creation)

            assert declencheur_de_la_ligne_payee.call_count == 0

            # 2. Le producteur fait lui-même la transition « non envoyée → payée »,
            # puis encaisse (T15 : encaisser après la transition).
            # / 2. The producer makes the transition itself, then settles.
            vente_payee_par_le_producteur = self.ouvrir_une_vente_en_caisse()
            ligne_du_producteur = self.ajouter_des_jus(
                vente_payee_par_le_producteur,
                quantite="1",
                status=LigneArticle.CREATED,
                payment_method=PaymentMethod.CASH,
            )
            ligne_du_producteur.status = LigneArticle.PAID
            ligne_du_producteur.save()
            ajouter_reglement(
                vente_payee_par_le_producteur,
                moyen=PaymentMethod.CASH,
                montant=PRIX_DU_JUS_EN_CENTIMES,
            )
            encaisser_vente(vente_payee_par_le_producteur)

            assert declencheur_de_la_ligne_payee.call_count == 1

        verifier_egalites(vente_payee_a_la_creation)
        verifier_egalites(vente_payee_par_le_producteur)

    def test_offert_a_montant_non_nul_part_offerte_et_reglement_free(self):
        """
        Un article offert à prix non nul (menu à 15,00 €) : le service pose
        `part_offerte = total_catalogue = 1500`, `source_offert = OFFRIR`, un net vendu
        de 0, et ajoute lui-même le règlement FREE de 1500. La vente s'encaisse sans
        autre règlement, et ses deux égalités tiennent.
        Deux façons de le demander, même résultat :
        - le paramètre explicite `offert_en_totalite=True` ;
        - le moyen historique `payment_method=FREE` sur la ligne (transition, retiré en H).
        / An item offered at a non-zero price: offered part = catalogue, OFFRIR, net 0, and
        a FREE payment of 1500 added by the service. Same result both ways.
        """
        tarif_du_menu = creer_tarif_vendu(nom="Menu", prix_en_euros="15.00")
        facons_d_offrir = [
            {"offert_en_totalite": True},
            {"payment_method": PaymentMethod.FREE},
        ]

        for facon_d_offrir in facons_d_offrir:
            vente = self.ouvrir_une_vente_en_caisse()
            ligne_offerte = ajouter_article(
                vente,
                pricesold=tarif_du_menu,
                quantite=Decimal("1"),
                prix_unitaire=1500,
                taux_tva=Decimal("20"),
                **facon_d_offrir,
            )

            ligne_offerte.refresh_from_db()
            assert ligne_offerte.total_catalogue == 1500
            assert ligne_offerte.part_offerte == 1500
            assert ligne_offerte.source_offert == LigneArticle.SourceOffert.OFFRIR
            assert ligne_offerte.total_ttc == 0
            assert ligne_offerte.total_ht == 0
            assert ligne_offerte.total_tva == 0

            reglements_de_la_vente = list(Reglement.objects.filter(vente=vente))
            assert len(reglements_de_la_vente) == 1
            assert reglements_de_la_vente[0].moyen == PaymentMethod.FREE
            assert reglements_de_la_vente[0].montant == 1500

            encaisser_vente(vente)
            verifier_egalites(vente)

    def test_vente_en_points_refuse_une_tva(self):
        """
        Une vente en points (`unite` = l'uuid de la monnaie de points) n'est pas de
        l'argent : ses articles ont une TVA de 0 (D9). `ajouter_article` refuse une TVA
        de 20 % sur une telle vente, et n'écrit aucune ligne.
        / A points sale is not money: a 20 % VAT is refused, no line is written.
        """
        uuid_de_la_monnaie_de_points = str(uuid.uuid4())
        vente_en_points = self.ouvrir_une_vente_en_caisse(
            unite=uuid_de_la_monnaie_de_points
        )

        with pytest.raises(ValueError):
            ajouter_article(
                vente_en_points,
                pricesold=self.tarif_du_jus,
                quantite=Decimal("1"),
                prix_unitaire=30000,
                taux_tva=Decimal("20"),
            )

        assert LigneArticle.objects.filter(vente=vente_en_points).count() == 0

    def test_ajouter_article_recopie_l_origine_de_la_vente(self):
        """
        La ligne porte l'origine de sa vente : un article ajouté à une vente de caisse,
        sans `sale_origin`, est une ligne « caisse » (LABOUTIK), et non « en ligne »
        (le défaut du champ). Si le producteur passe `sale_origin=` lui-même, sa valeur
        est gardée.
        / The line carries its sale's origin, unless the producer passes one explicitly.
        """
        vente_de_caisse = self.ouvrir_une_vente_en_caisse()

        ligne_sans_origine = self.ajouter_des_jus(vente_de_caisse, quantite="1")
        ligne_avec_origine_explicite = self.ajouter_des_jus(
            vente_de_caisse,
            quantite="1",
            sale_origin=SaleOrigin.ADMIN,
        )

        ligne_sans_origine.refresh_from_db()
        ligne_avec_origine_explicite.refresh_from_db()
        assert ligne_sans_origine.sale_origin == SaleOrigin.LABOUTIK
        assert ligne_avec_origine_explicite.sale_origin == SaleOrigin.ADMIN

    # ----------------------------------------------------------------------
    # Hors chiffre d'affaires
    # / Off revenue
    # ----------------------------------------------------------------------

    def test_hors_chiffre_affaires_calcule_depuis_le_produit_ou_force(self):
        """
        `ajouter_article` calcule `hors_chiffre_affaires` depuis le produit vendu :
        - vrai pour les méthodes de caisse RE (recharge euros), RC (recharge cadeau),
          TM (recharge temps), VR (virement pot central), FD (fidélité) ;
        - vrai pour la catégorie RECHARGE_CASHLESS (recharge API v2, sans méthode de
          caisse) ;
        - faux pour une vente ordinaire (VT) ;
        - vrai quand le producteur le force (`hors_chiffre_affaires=True`, écart
          d'encaissement de la fiche D), même sur une vente ordinaire.
        / The service computes the off-revenue flag from the product, or takes it forced.
        """
        cas_a_verifier = [
            # (méthode de caisse, catégorie, forcé par le producteur, attendu)
            (Product.RECHARGE_EUROS, Product.NONE, False, True),
            (Product.RECHARGE_CADEAU, Product.NONE, False, True),
            (Product.RECHARGE_TEMPS, Product.NONE, False, True),
            (Product.VIREMENT_RECU, Product.NONE, False, True),
            (Product.FIDELITE, Product.NONE, False, True),
            (None, Product.RECHARGE_CASHLESS, False, True),
            (Product.VENTE, Product.NONE, False, False),
            (Product.VENTE, Product.NONE, True, True),
        ]

        for methode_caisse, categorie_article, force, attendu in cas_a_verifier:
            tarif_vendu = creer_tarif_vendu(
                nom=f"Produit {methode_caisse} {categorie_article}",
                prix_en_euros="20.00",
                methode_caisse=methode_caisse,
                categorie_article=categorie_article,
            )
            vente = self.ouvrir_une_vente_en_caisse()
            ligne = ajouter_article(
                vente,
                pricesold=tarif_vendu,
                quantite=Decimal("1"),
                prix_unitaire=2000,
                taux_tva=Decimal("0"),
                hors_chiffre_affaires=force,
            )

            ligne.refresh_from_db()
            assert ligne.hors_chiffre_affaires is attendu, (
                f"méthode {methode_caisse}, catégorie {categorie_article}, "
                f"forcé {force} : hors chiffre d'affaires attendu {attendu}"
            )

    def test_hors_chiffre_affaires_fige(self):
        """
        `hors_chiffre_affaires` est figé à la vente. Une recharge euros vendue, puis son
        produit changé en « vente » : la ligne déjà écrite reste hors chiffre
        d'affaires. Une nouvelle ligne du même produit, elle, suit le produit changé.
        / The flag is frozen at sale time: changing the product later does not change
        the line already written; a new line follows the changed product.
        """
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge euros",
            prix_en_euros="20.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        vente = self.ouvrir_une_vente_en_caisse()
        ligne_de_la_recharge = ajouter_article(
            vente,
            pricesold=tarif_de_la_recharge,
            quantite=Decimal("1"),
            prix_unitaire=2000,
            taux_tva=Decimal("0"),
        )

        produit_de_la_recharge = tarif_de_la_recharge.productsold.product
        produit_de_la_recharge.methode_caisse = Product.VENTE
        produit_de_la_recharge.save()

        ligne_de_la_recharge.refresh_from_db()
        assert ligne_de_la_recharge.hors_chiffre_affaires is True

        ligne_ecrite_apres_le_changement = ajouter_article(
            vente,
            pricesold=tarif_de_la_recharge,
            quantite=Decimal("1"),
            prix_unitaire=2000,
            taux_tva=Decimal("0"),
        )
        ligne_ecrite_apres_le_changement.refresh_from_db()
        assert ligne_ecrite_apres_le_changement.hors_chiffre_affaires is False

    # ----------------------------------------------------------------------
    # Encaissement : les deux égalités
    # / Settlement: the two equalities
    # ----------------------------------------------------------------------

    def test_encaisser_refuse_si_reglements_differents_du_catalogue(self):
        """
        Trois jus à 3,50 € (catalogue 1050), réglés 1049 en espèces : la 1ʳᵉ égalité
        est rompue. `encaisser_vente` lève `EgaliteDeVenteRompue`, avec les deux sommes
        dans le message, et n'écrit rien : la vente reste en attente, sans numéro.
        / Catalogue 1050, paid 1049: refused with both sums in the message, nothing written.
        """
        vente = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente, quantite="3")
        ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=1049)

        with pytest.raises(EgaliteDeVenteRompue) as erreur_levee:
            encaisser_vente(vente)

        message_de_l_erreur = str(erreur_levee.value)
        assert "1049" in message_de_l_erreur
        assert "1050" in message_de_l_erreur

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_relue.numero is None
        assert vente_relue.datetime_encaissement is None

    def test_encaisser_refuse_si_argent_different_du_net(self):
        """
        Un article à 5,00 € dont 3,00 € sont offerts (net vendu 200), réglé 500 en CB.
        La 1ʳᵉ égalité tient (500 = catalogue 500) ; la 2ᵉ est rompue : 500 d'argent
        pour 200 de net vendu. Seule la 2ᵉ égalité peut refuser cette vente.
        / Offered 300 out of 500, paid 500 by card: only the 2nd equality refuses it.
        """
        tarif_du_plat = creer_tarif_vendu(nom="Plat", prix_en_euros="5.00")
        vente = self.ouvrir_une_vente_en_caisse()
        ajouter_article(
            vente,
            pricesold=tarif_du_plat,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            part_offerte=300,
            source_offert=LigneArticle.SourceOffert.OFFRIR,
        )
        ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=500)

        with pytest.raises(EgaliteDeVenteRompue):
            encaisser_vente(vente)

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_relue.numero is None

    def test_encaisser_refuse_un_offert_sans_reglement_de_trace(self):
        """
        Un article à 5,00 € dont 3,00 € sont offerts (net vendu 200), réglé 200 en CB,
        SANS le règlement « offert » de trace des 300 offerts. La 2ᵉ égalité tient
        (200 d'argent = 200 de net) ; la 1ʳᵉ est rompue : 200 réglés pour 500 de
        catalogue. Seule la 1ʳᵉ égalité peut refuser cette vente : le test vérifie son
        message (« totaux catalogue », absent du message de la 2ᵉ).
        Rien n'est écrit : la vente reste en attente, sans numéro.
        / Offered 300 out of 500 with no offered trace payment, 200 paid by card: only
        the 1st equality refuses it, checked through its own message.
        """
        tarif_du_plat = creer_tarif_vendu(nom="Plat", prix_en_euros="5.00")
        vente = self.ouvrir_une_vente_en_caisse()
        ajouter_article(
            vente,
            pricesold=tarif_du_plat,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            part_offerte=300,
            source_offert=LigneArticle.SourceOffert.OFFRIR,
        )
        ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=200)

        with pytest.raises(EgaliteDeVenteRompue, match="totaux catalogue"):
            encaisser_vente(vente)

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_relue.numero is None

    def test_moyens_offerts_ne_contient_que_free(self):
        """
        Le seul moyen « offert » est FREE (bouton OFFRIR, recharge cadeau). Un jeton
        dépensé solde la dette du lieu envers le porteur (D8 bis) : le règlement
        « jetons » (LG) est un vrai règlement, il compte dans la 2ᵉ égalité.
        / The only "offered" method is FREE. A spent token settles the venue's debt
        (D8 bis): the LG payment is a real payment, counted in the 2nd equality.
        """
        assert MOYENS_OFFERTS == [PaymentMethod.FREE]

    def test_vente_payante_sans_reglement_refusee(self):
        """
        Un article à 5,00 € sans aucun règlement : Σ règlements (0) ≠ catalogue (500).
        La vente est refusée et reste en attente, sans numéro.
        / A 500 item without payment is refused and stays pending, without number.
        """
        tarif_du_plat = creer_tarif_vendu(nom="Plat", prix_en_euros="5.00")
        vente = self.ouvrir_une_vente_en_caisse()
        ajouter_article(
            vente,
            pricesold=tarif_du_plat,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
        )

        with pytest.raises(EgaliteDeVenteRompue):
            encaisser_vente(vente)

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_relue.numero is None

    def test_vente_gratuite_sans_reglement_encaissee(self):
        """
        Un article à 0 € et aucun règlement : 0 = 0, la vente est encaissée. Aucun
        règlement de 0 n'est jamais écrit : une vente gratuite n'en a pas.
        / A 0 € item without payment is settled: a free sale has no payment.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 0,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[],
        )

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.REGLEE
        assert vente_relue.numero == 1
        assert Reglement.objects.filter(vente=vente).count() == 0
        verifier_egalites(vente)

    def test_vidage_de_carte_sans_article_encaisse(self):
        """
        Vider une carte (D12) : une vente VIDAGE_CARTE SANS article, dont les
        règlements s'annulent : +500 en monnaie locale (les jetons repris), −500 en
        espèces (l'argent rendu). Elle est encaissée, avec des totaux à 0.
        / Emptying a card: no item, payments +500 local currency and −500 cash, settled.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            articles=[],
            reglements=[
                {"moyen": PaymentMethod.LOCAL_EURO, "montant": 500},
                {"moyen": PaymentMethod.CASH, "montant": -500},
            ],
        )

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.REGLEE
        assert vente_relue.numero == 1
        assert vente_relue.total_catalogue == 0
        assert vente_relue.total_ttc == 0
        verifier_egalites(vente)

    def test_vente_sans_article_refusee_sauf_vidage_et_correction(self):
        """
        Une vente sans article n'est acceptée que pour un vidage de carte ou une
        correction de moyen de paiement (leurs règlements s'annulent).
        1. Une VENTE sans article, avec deux règlements qui s'annulent (+500 espèces,
           −500 CB) : les deux égalités tiennent (0 = 0), c'est donc bien la règle
           « sans article » qui la refuse. Elle reste en attente, sans numéro.
        2. Une CORRECTION sans article (D14), mêmes règlements (−500 espèces, +500 CB) :
           elle est encaissée.
        / A sale without item is refused, except card emptying and correction. The
        refused VENTE keeps both equalities: only the "no item" rule can refuse it.
        """
        vente_sans_article = self.ouvrir_une_vente_en_caisse()
        ajouter_reglement(vente_sans_article, moyen=PaymentMethod.CASH, montant=500)
        ajouter_reglement(vente_sans_article, moyen=PaymentMethod.CC, montant=-500)

        with pytest.raises(ValueError):
            encaisser_vente(vente_sans_article)

        vente_sans_article_relue = Vente.objects.get(pk=vente_sans_article.pk)
        assert vente_sans_article_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_sans_article_relue.numero is None

        correction = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            articles=[],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": -500},
                {"moyen": PaymentMethod.CC, "montant": 500},
            ],
        )

        correction_relue = Vente.objects.get(pk=correction.pk)
        assert correction_relue.statut == Vente.Statut.REGLEE
        assert correction_relue.numero == 1
        verifier_egalites(correction)

    # ----------------------------------------------------------------------
    # Encaissement : le numéro et les statuts
    # / Settlement: the number and the statuses
    # ----------------------------------------------------------------------

    def test_encaisser_deux_fois_meme_numero(self):
        """
        Encaisser deux fois la même vente (webhook Stripe + retour de l'acheteur) : le
        2ᵉ appel renvoie la vente telle quelle. Même numéro, même heure
        d'encaissement, une seule vente réglée.
        / Settling twice returns the same sale: same number, same time, one settled sale.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": PRIX_DU_JUS_EN_CENTIMES},
            ],
        )
        vente_apres_le_premier_encaissement = Vente.objects.get(pk=vente.pk)

        vente_renvoyee_par_le_second_appel = encaisser_vente(vente)

        vente_apres_le_second_encaissement = Vente.objects.get(pk=vente.pk)
        assert vente_renvoyee_par_le_second_appel.pk == vente.pk
        assert vente_apres_le_premier_encaissement.numero == 1
        assert vente_apres_le_second_encaissement.numero == 1
        assert (
            vente_apres_le_second_encaissement.datetime_encaissement
            == vente_apres_le_premier_encaissement.datetime_encaissement
        )
        assert Vente.objects.filter(statut=Vente.Statut.REGLEE).count() == 1
        verifier_egalites(vente)

    def test_encaisser_vente_annulee_refuse(self):
        """
        Une vente annulée (Stripe a refusé) ne s'encaisse plus, même si ses égalités
        tiennent : pas de retour arrière (D16). Elle reste annulée, sans numéro.
        / A cancelled sale cannot be settled, even with valid equalities.
        """
        vente = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente, quantite="1")
        ajouter_reglement(
            vente, moyen=PaymentMethod.CASH, montant=PRIX_DU_JUS_EN_CENTIMES
        )
        annuler_vente(vente)

        with pytest.raises(ValueError):
            encaisser_vente(vente)

        vente_relue = Vente.objects.get(pk=vente.pk)
        assert vente_relue.statut == Vente.Statut.ANNULEE
        assert vente_relue.numero is None

    def test_numeros_consecutifs_sans_trou(self):
        """
        Trois ventes encaissées l'une après l'autre reçoivent les numéros 1, 2, 3.
        / Three settled sales get numbers 1, 2, 3.
        """
        ventes_encaissees = []
        for _numero_de_passage in range(3):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal("2"),
                        "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                        "taux_tva": TVA_DU_JUS,
                    },
                ],
                reglements=[
                    {"moyen": PaymentMethod.CC, "montant": 700},
                ],
            )
            ventes_encaissees.append(vente)

        numeros_relus = []
        for vente in ventes_encaissees:
            numeros_relus.append(Vente.objects.get(pk=vente.pk).numero)
        assert numeros_relus == [1, 2, 3]

        for vente in ventes_encaissees:
            verifier_egalites(vente)

    def test_vente_annulee_ou_en_attente_ne_prend_pas_de_numero(self):
        """
        Une vente laissée en attente (paiement pas encore constaté) et une vente
        annulée ne consomment aucun numéro : la première vente réglée, ouverte après
        elles, porte le numéro 1.
        / Pending and cancelled sales take no number: the first settled one is number 1.
        """
        vente_en_attente = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente_en_attente, quantite="1")

        vente_annulee = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente_annulee, quantite="1")
        annuler_vente(vente_annulee)

        vente_reglee = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": PRIX_DU_JUS_EN_CENTIMES},
            ],
        )

        vente_en_attente_relue = Vente.objects.get(pk=vente_en_attente.pk)
        vente_annulee_relue = Vente.objects.get(pk=vente_annulee.pk)
        vente_reglee_relue = Vente.objects.get(pk=vente_reglee.pk)
        assert vente_reglee_relue.numero == 1
        assert vente_en_attente_relue.statut == Vente.Statut.EN_ATTENTE
        assert vente_en_attente_relue.numero is None
        assert vente_annulee_relue.statut == Vente.Statut.ANNULEE
        assert vente_annulee_relue.numero is None
        verifier_egalites(vente_reglee)

    # ----------------------------------------------------------------------
    # Garde d'immutabilité d'une vente réglée
    # / Immutability guard of a settled sale
    # ----------------------------------------------------------------------

    def test_vente_reglee_refuse_toute_modification_par_save(self):
        """
        Sur une vente réglée (trois jus, 1050 en espèces) :
        - changer le montant d'un règlement puis `save()` → refusé ;
        - changer le prix unitaire (`amount`) d'une ligne puis `save()` → refusé ;
        - changer un total de la vente puis `save()` → refusé ;
        - rien n'a changé en base ;
        - changer le STATUT de la ligne puis `save()` → accepté (la machine à statuts
          et les tâches Celery écrivent encore ce champ).
        / On a settled sale, save() refuses money changes but accepts a status change.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("3"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 1050},
            ],
        )

        reglement_a_modifier = Reglement.objects.get(vente=vente)
        reglement_a_modifier.montant = 1000
        with pytest.raises(ValueError):
            reglement_a_modifier.save()

        ligne_a_modifier = LigneArticle.objects.get(vente=vente)
        ligne_a_modifier.amount = 300
        with pytest.raises(ValueError):
            ligne_a_modifier.save()

        vente_a_modifier = Vente.objects.get(pk=vente.pk)
        vente_a_modifier.total_ttc = 1000
        with pytest.raises(ValueError):
            vente_a_modifier.save()

        # Rien n'a été écrit.
        # / Nothing was written.
        assert Reglement.objects.get(pk=reglement_a_modifier.pk).montant == 1050
        assert LigneArticle.objects.get(pk=ligne_a_modifier.pk).amount == 350
        assert Vente.objects.get(pk=vente.pk).total_ttc == 1050

        # Le statut de la ligne reste libre.
        # / The line status stays free.
        ligne_dont_le_statut_change = LigneArticle.objects.get(pk=ligne_a_modifier.pk)
        ligne_dont_le_statut_change.status = LigneArticle.VALID
        ligne_dont_le_statut_change.save()
        assert (
            LigneArticle.objects.get(pk=ligne_a_modifier.pk).status
            == LigneArticle.VALID
        )

        verifier_egalites(vente)

    def test_statut_d_une_ligne_reglee_modifiable_sur_l_instance_du_service(self):
        """
        La part d'un jus à 3,50 € payée 5,00 € en monnaie locale (cascade) a la quantité
        `Decimal(500) / Decimal(350)` : 28 décimales en mémoire, 6 en base (1,428571).
        Sur la ligne rendue par `ajouter_article` (la MÊME instance, jamais relue), une
        fois la vente encaissée :
        - changer le statut puis `save()` → accepté : la quantité en mémoire vaut, arrondie
          comme la base la stocke, la quantité en base ;
        - changer vraiment la quantité puis `save()` → refusé (ValueError), et la base
          garde 1,428571.
        / On the very instance returned by ajouter_article, a status change is accepted
        (the 28-decimal qty equals the stored 6-decimal one), a real qty change is refused.
        """
        quantite_de_la_part_a_28_decimales = Decimal(500) / Decimal(350)
        vente = self.ouvrir_une_vente_en_caisse()
        ligne_rendue_par_le_service = ajouter_article(
            vente,
            pricesold=self.tarif_du_jus,
            quantite=quantite_de_la_part_a_28_decimales,
            prix_unitaire=PRIX_DU_JUS_EN_CENTIMES,
            taux_tva=TVA_DU_JUS,
            total_catalogue_impose=500,
        )
        ajouter_reglement(vente, moyen=PaymentMethod.LOCAL_EURO, montant=500)
        encaisser_vente(vente)

        # Le statut change sur l'instance du service : accepté.
        # / The status changes on the service instance: accepted.
        ligne_rendue_par_le_service.status = LigneArticle.VALID
        ligne_rendue_par_le_service.save()
        ligne_relue = LigneArticle.objects.get(pk=ligne_rendue_par_le_service.pk)
        assert ligne_relue.status == LigneArticle.VALID

        # Un vrai changement de quantité, sur la même instance : refusé.
        # / A real quantity change, on the same instance: refused.
        ligne_rendue_par_le_service.qty = Decimal("2")
        with pytest.raises(ValueError):
            ligne_rendue_par_le_service.save()
        ligne_relue = LigneArticle.objects.get(pk=ligne_rendue_par_le_service.pk)
        assert ligne_relue.qty == Decimal("1.428571")

        verifier_egalites(vente)

    def test_ajouter_a_une_vente_reglee_refuse(self):
        """
        Une vente encaissée ne se modifie plus (D14), et une vente annulée non plus :
        `ajouter_article` et `ajouter_reglement` refusent (ValueError) sur une vente
        REGLEE comme sur une vente ANNULEE. Rien n'est écrit : le nombre d'articles et
        de règlements de chaque vente reste le même.
        / No item or payment can be added to a settled or cancelled sale.
        """
        vente_reglee = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": PRIX_DU_JUS_EN_CENTIMES},
            ],
        )

        vente_annulee = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente_annulee, quantite="1")
        annuler_vente(vente_annulee)

        for vente_close in [vente_reglee, vente_annulee]:
            nombre_d_articles_avant = LigneArticle.objects.filter(
                vente=vente_close
            ).count()
            nombre_de_reglements_avant = Reglement.objects.filter(
                vente=vente_close
            ).count()

            with pytest.raises(ValueError):
                self.ajouter_des_jus(vente_close, quantite="1")
            with pytest.raises(ValueError):
                ajouter_reglement(
                    vente_close,
                    moyen=PaymentMethod.CASH,
                    montant=PRIX_DU_JUS_EN_CENTIMES,
                )

            assert (
                LigneArticle.objects.filter(vente=vente_close).count()
                == nombre_d_articles_avant
            )
            assert (
                Reglement.objects.filter(vente=vente_close).count()
                == nombre_de_reglements_avant
            )

        verifier_egalites(vente_reglee)

    def test_annuler_vente_reglee_refusee_et_annulee_rendue_telle_quelle(self):
        """
        `annuler_vente` :
        - sur une vente REGLEE → refus (ValueError) : une vente encaissée ne s'annule
          pas, on fait un avoir. Elle reste réglée, avec son numéro ;
        - sur une vente déjà ANNULEE (même message Stripe reçu deux fois) → la vente est
          rendue telle quelle, toujours annulée, sans numéro.
        / Cancelling a settled sale is refused; cancelling a cancelled sale returns it as is.
        """
        vente_reglee = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": PRIX_DU_JUS_EN_CENTIMES},
            ],
        )

        # Le refus vient d'`annuler_vente` elle-même, pas de la garde de `Vente.save()` :
        # « ne s'annule pas » n'est que dans le message d'`annuler_vente`.
        # / The refusal comes from annuler_vente itself, not from the Vente.save() guard.
        with pytest.raises(ValueError, match="ne s'annule pas"):
            annuler_vente(vente_reglee)

        vente_reglee_relue = Vente.objects.get(pk=vente_reglee.pk)
        assert vente_reglee_relue.statut == Vente.Statut.REGLEE
        assert vente_reglee_relue.numero == 1

        vente_annulee = self.ouvrir_une_vente_en_caisse()
        self.ajouter_des_jus(vente_annulee, quantite="1")
        annuler_vente(vente_annulee)

        vente_rendue_au_second_appel = annuler_vente(vente_annulee)

        assert vente_rendue_au_second_appel.pk == vente_annulee.pk
        vente_annulee_relue = Vente.objects.get(pk=vente_annulee.pk)
        assert vente_annulee_relue.statut == Vente.Statut.ANNULEE
        assert vente_annulee_relue.numero is None
        verifier_egalites(vente_reglee)

    # ----------------------------------------------------------------------
    # Empreinte chaînée des ventes
    # / Chained fingerprint of the sales
    # ----------------------------------------------------------------------

    def test_premiere_vente_chainee_sur_vide_puis_suivante_sur_la_precedente(self):
        """
        Deux ventes encaissées l'une après l'autre :
        - la 1ʳᵉ est chaînée sur le vide : `previous_hmac` = "" ;
        - la 2ᵉ est chaînée sur la 1ʳᵉ : son `previous_hmac` est l'empreinte de la 1ʳᵉ ;
        - chaque empreinte est celle du message de la fiche §5, recalculée à la main
          (`calculer_l_empreinte_attendue`), et `calculer_hmac_vente` rend la même ;
        - `verifier_chaine_ventes` ne signale rien.
        La 2ᵉ vente a deux articles (dont un offert) et deux règlements : le tri par uuid
        et les champs de l'offert entrent dans le message.
        / The 1st sale is chained on "", the 2nd on the 1st; each fingerprint matches the
        spec message recomputed by hand; the chain check reports nothing.
        """
        premiere_vente = self.encaisser_des_jus_payes_en_especes(quantite="3")

        tarif_du_menu = creer_tarif_vendu(nom="Menu", prix_en_euros="15.00")
        seconde_vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("2"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
                {
                    "pricesold": tarif_du_menu,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1500,
                    "taux_tva": Decimal("10"),
                    "offert_en_totalite": True,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 700},
            ],
        )

        cle = self.cle_de_l_empreinte_du_lieu()
        premiere_vente_relue = Vente.objects.get(pk=premiere_vente.pk)
        seconde_vente_relue = Vente.objects.get(pk=seconde_vente.pk)

        # La 1ʳᵉ vente est chaînée sur le vide.
        # / The 1st sale is chained on nothing.
        assert premiere_vente_relue.previous_hmac == ""
        assert len(premiere_vente_relue.hmac_hash) == 64
        assert premiere_vente_relue.hmac_hash == calculer_l_empreinte_attendue(
            premiere_vente_relue, cle, ""
        )

        # La 2ᵉ vente est chaînée sur la 1ʳᵉ.
        # / The 2nd sale is chained on the 1st.
        assert seconde_vente_relue.previous_hmac == premiere_vente_relue.hmac_hash
        assert seconde_vente_relue.hmac_hash == calculer_l_empreinte_attendue(
            seconde_vente_relue, cle, premiere_vente_relue.hmac_hash
        )
        assert (
            calculer_hmac_vente(
                seconde_vente_relue, cle, premiere_vente_relue.hmac_hash
            )
            == seconde_vente_relue.hmac_hash
        )

        assert verifier_chaine_ventes(cle) == []

        verifier_egalites(premiere_vente)
        verifier_egalites(seconde_vente)

    def test_alterer_une_vente_reglee_casse_la_chaine(self):
        """
        Une vente réglée altérée par `.update()` (qui contourne la garde de `save()`) :
        `verifier_chaine_ventes` la signale « empreinte fausse ». Un cas par clé du
        message de la fiche §5 qu'un `.update()` peut changer simplement :
        - un article (`total_ttc`) ; un règlement (`montant`) ;
        - la vente : `vente_liee`, `point_de_vente`, `numero`, `datetime_encaissement`,
          `nature`, `origine`, `unite`, ses totaux.
        Clés hors de cette liste : `format` (constante), `uuid` (clé primaire, pointée
        par les articles et les règlements), `previous_hmac` (vu par le test du maillon
        cassé), `statut` (une vente sortie de REGLEE sort de la chaîne : c'est un trou).
        Chaque cas tourne dans un point de sauvegarde annulé à la fin : le cas suivant
        repart d'une chaîne saine. Tous les cas sont joués, puis le test liste ceux qui
        n'ont pas été signalés.
        / A settled sale tampered with through .update() is reported as "empreinte
        fausse", one case per message key. Each case runs in a rolled-back savepoint.
        """
        cle = self.cle_de_l_empreinte_du_lieu()
        point_de_vente = PointDeVente.objects.create(
            name=f"TEST_vente comptoir {uuid.uuid4()}"
        )
        vente_de_reference = self.encaisser_des_jus_payes_en_especes(quantite="1")

        champs_a_alterer = [
            "total_ttc d'un article",
            "montant d'un règlement",
            "vente_liee",
            "point_de_vente",
            "numero",
            "datetime_encaissement",
            "nature",
            "origine",
            "unite",
            "totaux de la vente",
        ]

        champs_dont_l_alteration_n_est_pas_signalee = []
        for champ_altere in champs_a_alterer:
            with transaction.atomic():
                vente_a_alterer = self.encaisser_des_jus_payes_en_especes(quantite="3")

                anomalies_avant_l_alteration = verifier_chaine_ventes(cle)
                assert anomalies_avant_l_alteration == [], (
                    f"Cas « {champ_altere} » : la chaîne doit être saine avant "
                    f"l'altération. Anomalies : {anomalies_avant_l_alteration}"
                )

                self.alterer_par_update(
                    champ_altere, vente_a_alterer, vente_de_reference, point_de_vente
                )

                anomalies_apres_l_alteration = verifier_chaine_ventes(cle)
                alteration_signalee = anomalie_signalee(
                    anomalies_apres_l_alteration, vente_a_alterer, "empreinte fausse"
                )
                if not alteration_signalee:
                    champs_dont_l_alteration_n_est_pas_signalee.append(champ_altere)

                # Annule ce point de sauvegarde : la vente altérée disparaît.
                # / Roll this savepoint back: the tampered sale disappears.
                transaction.set_rollback(True)

        assert champs_dont_l_alteration_n_est_pas_signalee == [], (
            f"Altérations non signalées « empreinte fausse » : "
            f"{champs_dont_l_alteration_n_est_pas_signalee}"
        )

        verifier_egalites(vente_de_reference)

    def test_empreinte_precedente_modifiee_signale_un_maillon_casse(self):
        """
        Deux ventes réglées. On remplace par `.update()` l'empreinte précédente
        (`previous_hmac`) de la 2ᵉ : elle ne pointe plus sur l'empreinte de la 1ʳᵉ.
        `verifier_chaine_ventes` signale la 2ᵉ vente « maillon cassé ».
        / The 2nd sale's previous_hmac no longer matches the 1st sale's fingerprint:
        the chain check reports a broken link on the 2nd sale.
        """
        premiere_vente = self.encaisser_des_jus_payes_en_especes(quantite="1")
        seconde_vente = self.encaisser_des_jus_payes_en_especes(quantite="2")
        cle = self.cle_de_l_empreinte_du_lieu()
        assert verifier_chaine_ventes(cle) == []

        Vente.objects.filter(pk=seconde_vente.pk).update(previous_hmac="0" * 64)

        anomalies = verifier_chaine_ventes(cle)
        assert anomalie_signalee(anomalies, seconde_vente, "maillon cassé"), anomalies

        verifier_egalites(premiere_vente)
        verifier_egalites(seconde_vente)

    def test_supprimer_une_vente_laisse_un_trou_signale(self):
        """
        Trois ventes réglées, numéros 1, 2, 3. La vente n° 2 est supprimée par SQL brut
        (l'ORM refuse : les clés étrangères PROTECT de ses articles et règlements).
        1. `verifier_chaine_ventes` signale un « trou de numéro » sur la vente n° 3 (celle
           qui suit le trou).
        2. La vente suivante prend le numéro 4 : le numéro est le plus grand numéro + 1,
           jamais le nombre de ventes réglées + 1 (qui redonnerait 3, déjà pris).
        / Sale #2 is deleted with raw SQL: a "trou de numéro" is reported on sale #3, and
        the next sale gets number 4 (highest + 1, never count + 1).
        """
        ventes_reglees = []
        for _numero_de_passage in range(3):
            ventes_reglees.append(self.encaisser_des_jus_payes_en_especes(quantite="1"))
        vente_supprimee = ventes_reglees[1]
        vente_apres_le_trou = ventes_reglees[2]
        cle = self.cle_de_l_empreinte_du_lieu()
        assert verifier_chaine_ventes(cle) == []

        # Suppression par SQL brut : les règlements et les articles d'abord, puis la
        # vente elle-même.
        # / Raw SQL deletion: payments and items first, then the sale itself.
        with connection.cursor() as curseur:
            curseur.execute(
                'DELETE FROM "BaseBillet_reglement" WHERE vente_id = %s',
                [vente_supprimee.pk],
            )
            curseur.execute(
                'DELETE FROM "BaseBillet_lignearticle" WHERE vente_id = %s',
                [vente_supprimee.pk],
            )
            curseur.execute(
                'DELETE FROM "BaseBillet_vente" WHERE uuid = %s',
                [vente_supprimee.pk],
            )

        # 1. Le trou est signalé sur la vente n° 3.
        # / 1. The gap is reported on sale #3.
        anomalies = verifier_chaine_ventes(cle)
        assert anomalie_signalee(anomalies, vente_apres_le_trou, "trou de numéro"), (
            anomalies
        )
        numeros_signales_pour_le_trou = []
        for anomalie in anomalies:
            if "trou de numéro" in anomalie["raison"].lower():
                numeros_signales_pour_le_trou.append(anomalie["numero"])
        assert numeros_signales_pour_le_trou == [3]

        # 2. La vente suivante prend le numéro 4.
        # / 2. The next sale gets number 4.
        vente_suivante = self.encaisser_des_jus_payes_en_especes(quantite="1")
        assert Vente.objects.get(pk=vente_suivante.pk).numero == 4

        verifier_egalites(ventes_reglees[0])
        verifier_egalites(vente_apres_le_trou)
        verifier_egalites(vente_suivante)

    def test_supprimer_un_reglement_signale_egalite_rompue(self):
        """
        Une vente réglée de trois jus (1050) : 700 en espèces et 350 en CB. Le règlement
        CB est supprimé par SQL brut. Relue en base, la vente n'a plus que 700 de
        règlements pour 1050 d'articles : `verifier_chaine_ventes` la signale
        « égalité rompue ».
        / The card payment is deleted with raw SQL: the chain check reports the sale as
        "égalité rompue" (equalities read back from the database).
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("3"),
                    "prix_unitaire": PRIX_DU_JUS_EN_CENTIMES,
                    "taux_tva": TVA_DU_JUS,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 700},
                {"moyen": PaymentMethod.CC, "montant": 350},
            ],
        )
        cle = self.cle_de_l_empreinte_du_lieu()
        assert verifier_chaine_ventes(cle) == []

        reglement_par_carte = Reglement.objects.get(vente=vente, moyen=PaymentMethod.CC)
        with connection.cursor() as curseur:
            curseur.execute(
                'DELETE FROM "BaseBillet_reglement" WHERE uuid = %s',
                [reglement_par_carte.pk],
            )

        anomalies = verifier_chaine_ventes(cle)
        assert anomalie_signalee(anomalies, vente, "égalité rompue"), anomalies

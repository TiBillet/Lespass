"""
Tests de la reprise des ventes existantes : le calcul du plan et le passage à blanc.
/ Tests of the takeover of existing sales: the plan computation and the dry run.

LOCALISATION : tests/pytest/test_reprise_des_ventes.py

LE BESOIN
En production, les anciennes lignes d'article (`LigneArticle`) n'ont ni vente, ni
règlement, ni montants entiers. La reprise leur donnera tout cela, une fois, la nuit de
la mise en production. Ces tests portent sur la première moitié : le CALCUL. Pour un
lieu, il lit les anciennes lignes et les paiements Stripe, et il construit en mémoire la
liste des ventes à créer. Il n'écrit rien en base. Une seconde étape écrira ce plan tel
quel, sans le recalculer.
/ Old sale lines have no sale, no payment, no integer amounts. This file tests the
computation only: it builds the list of sales in memory and writes nothing.

LE PLAN, TEL QUE LES TESTS LE LISENT
`calculer_le_plan_de_reprise(moment_de_la_reprise)` (BaseBillet/reprise_des_ventes.py)
lit le lieu courant et rend un plan :
- `plan.ventes` : la liste des ventes à écrire (`VenteAReprendre`) ;
- `plan.anomalies` : un dict {type d'anomalie (texte) : nombre de lignes}, sans aucune
  donnée personnelle ;
- `plan.nombre_de_lignes_lues` ;
- `plan.nombre_de_paiements_stripe_sans_ligne` (hors paiements `T`) ;
- `plan.total_ancien_calcul` : Σ `amount × qty` des lignes lues ;
- `plan.total_nouveau_calcul` : Σ `total_ttc` des articles du plan.

Une vente à reprendre (`VenteAReprendre`) porte :
- `cle_du_groupe` (texte) : elle deviendra `idempotency_key = "reprise-<clé>"` ;
- `nature`, `statut` (valeurs de `Vente.Nature` et `Vente.Statut`), `unite` ("EUR") ;
- `datetime_de_la_vente`, `client` (un utilisateur ou None), `paiement_stripe` ;
- `moyen_du_paiement_stripe`, `montant_encaisse_du_paiement_stripe` : ce qu'il faudra
  poser sur le paiement Stripe (None : rien à poser) ;
- `uuid_de_la_ligne_d_origine` (un avoir) et `credit_note_for_a_poser` (vrai quand
  l'origine vient de `metadata`) ;
- `articles` : des `ArticleAReprendre` ; `reglements` : des `ReglementAReprendre`.

Un article à reprendre porte `ligne` (l'ancienne ligne, ou None pour un article à
créer), `methode_caisse_du_produit_a_creer` (None, ou "VR" pour un virement reçu),
`quantite`, `prix_unitaire`, `taux_tva`, `asset`, et ses montants entiers :
`total_catalogue`, `part_offerte`, `source_offert`, `part_en_jetons`, `total_ttc`,
`total_ht`, `total_tva`, `hors_chiffre_affaires`.
Un règlement à reprendre porte `moyen`, `montant`, `asset`, `paiement_stripe`,
`reference_externe`.
/ The plan exposes the sales to write, the anomalies (counts only), and the totals.

LES ANCIENNES LIGNES
Elles sont fabriquées par `LigneArticle.objects.create`, SANS vente, à la forme exacte de
la production (fiche R §3 et §14). Leur date (`datetime`, en `auto_now_add`) et leur taux
de TVA sont reposés ensuite par `.update()` : à la création, `LigneArticle.save()`
remplace une TVA nulle par celle du produit.
/ Old lines are created without a sale, in the exact production shape; date and VAT are
set afterwards by .update().

COMMENT CHAQUE TEST RETROUVE SES VENTES
Les tests tournent dans un schéma à eux (`FastTenantTestCase`), annulé à la fin de chaque
test : le plan ne lit que les lignes du test.
/ Dedicated schema, rolled back after each test: the plan reads only the test's lines.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§3 à
§10, §13 R-1, §14, §17) et le brief CHANTIER-05-briefs/05-R-1.md.

Lancer / Run : make test ARGS="tests/pytest/test_reprise_des_ventes.py"
"""

import io
import json
import uuid
from datetime import datetime, timedelta
from datetime import timezone as fuseau_horaire
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase

from AuthBillet.models import Wallet
from BaseBillet.models import (
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Product,
    Reservation,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from fabriques_panier import (
    creer_evenement_avec_tarif,
    creer_utilisateur,
    noms_des_taches,
    taches_celery_enregistrees,
)
from fabriques_vente import creer_tarif_vendu
from fedow_public.models import AssetFedowPublic

# Les types d'anomalie lus dans `plan.anomalies` (textes du rapport).
# / The anomaly types read in plan.anomalies (report texts).
ANOMALIE_FORME_NON_PREVUE = "forme non prévue"
ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE = "origine d'avoir introuvable"

# La date d'un transfert Stripe de test : 14/11/2023 22:13:20 UTC, en horodatage Unix.
# / A test Stripe transfer date, as a Unix timestamp.
HORODATAGE_DU_TRANSFERT = 1700000000
DATE_DU_TRANSFERT = datetime(2023, 11, 14, 22, 13, 20, tzinfo=fuseau_horaire.utc)


def _reglements_lisibles(vente_a_reprendre):
    """
    Les règlements d'une vente du plan, en tuples triés : (moyen, montant, asset,
    paiement Stripe, référence externe). Un test compare alors une liste entière.
    / The sale's payments as sorted tuples, so a test compares a whole list.
    """
    reglements_en_tuples = []
    for reglement in vente_a_reprendre.reglements:
        reglements_en_tuples.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.asset,
                reglement.paiement_stripe,
                reglement.reference_externe,
            )
        )
    reglements_en_tuples.sort(key=lambda reglement: (reglement[0], reglement[1]))
    return reglements_en_tuples


def _montants_lisibles(article_a_reprendre):
    """
    Les montants entiers d'un article du plan, en dict.
    / The integer amounts of a plan item, as a dict.
    """
    return {
        "total_catalogue": article_a_reprendre.total_catalogue,
        "part_offerte": article_a_reprendre.part_offerte,
        "total_ttc": article_a_reprendre.total_ttc,
        "total_ht": article_a_reprendre.total_ht,
        "total_tva": article_a_reprendre.total_tva,
    }


class TestRepriseDesVentesExistantes(FastTenantTestCase):
    """
    Le calcul de la reprise et le passage à blanc, dans un schéma dédié (rollback à la
    fin de chaque test).
    / The takeover computation and the dry run, in a dedicated schema.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_reprise_ventes"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-reprise-ventes.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test reprise des ventes"

    def setUp(self):
        """
        Le lieu du test, le moment de la reprise, et un tarif de billet.
        / The test venue, the takeover moment, and a ticket price.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        self.moment_de_la_reprise = timezone.now()

        # Le produit porte une TVA de 20 % : les lignes portent la leur, souvent
        # différente. La reprise lit TOUJOURS le taux de la ligne.
        # / The product has 20 % VAT; lines carry their own. The takeover reads the line.
        self.billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="12.50",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )

    # ------------------------------------------------------------------
    # Assistants / Helpers
    # ------------------------------------------------------------------

    def _calculer_le_plan(self):
        """
        Le plan de reprise du lieu du test, au moment de la reprise du test.
        / The takeover plan of the test venue.
        """
        from BaseBillet.reprise_des_ventes import calculer_le_plan_de_reprise

        return calculer_le_plan_de_reprise(
            moment_de_la_reprise=self.moment_de_la_reprise
        )

    def _lancer_le_passage_a_blanc(self):
        """
        Lance la commande de reprise sur le lieu du test et rend ce qu'elle affiche.
        / Runs the takeover command on the test venue and returns its output.
        """
        sortie_de_la_commande = io.StringIO()
        call_command(
            "reprendre_les_ventes_existantes",
            "--schema",
            self.tenant.schema_name,
            stdout=sortie_de_la_commande,
        )
        return sortie_de_la_commande.getvalue()

    def _creer_un_paiement_stripe(
        self,
        statut,
        utilisateur=None,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        jours_depuis_la_commande=1,
        jours_depuis_la_derniere_action=None,
        metadata_stripe=None,
    ):
        """
        Un ancien paiement Stripe. `order_date` (`auto_now_add`), `last_action` et
        `datetime` (`auto_now`) sont reposés par `.update()`.
        / An old Stripe payment; its dates are set by .update().

        :param jours_depuis_la_derniere_action: None = même âge que la commande
        """
        paiement = Paiement_stripe.objects.create(
            status=statut,
            source=source,
            user=utilisateur,
            metadata_stripe=metadata_stripe,
        )
        if jours_depuis_la_derniere_action is None:
            jours_depuis_la_derniere_action = jours_depuis_la_commande
        date_de_la_commande = self.moment_de_la_reprise - timedelta(
            days=jours_depuis_la_commande
        )
        date_de_la_derniere_action = self.moment_de_la_reprise - timedelta(
            days=jours_depuis_la_derniere_action
        )
        Paiement_stripe.objects.filter(pk=paiement.pk).update(
            order_date=date_de_la_commande,
            last_action=date_de_la_derniere_action,
            datetime=date_de_la_derniere_action,
        )
        paiement.refresh_from_db()
        return paiement

    def _creer_une_ancienne_ligne(
        self,
        statut,
        montant,
        quantite,
        tarif_vendu=None,
        taux_tva="0",
        moyen=None,
        origine=SaleOrigin.LESPASS,
        paiement_stripe=None,
        metadata=None,
        asset=None,
        credit_note_for=None,
        reservation=None,
        membership=None,
        minutes_avant_la_reprise=60,
    ):
        """
        Une ancienne ligne d'article, telle que l'ancien code l'écrivait : sans vente,
        sans montants entiers. Sa date et son taux de TVA sont reposés par `.update()`.
        / An old sale line, as the old code wrote it: no sale, no integer amounts.

        :param montant: `amount`, en centimes (int)
        :param quantite: `qty` (texte, ex. "0.6" ou "-1")
        :param taux_tva: le taux écrit sur la ligne (texte, ex. "5.5")
        """
        if tarif_vendu is None:
            tarif_vendu = self.billet
        ligne = LigneArticle.objects.create(
            pricesold=tarif_vendu,
            status=statut,
            amount=montant,
            qty=Decimal(quantite),
            payment_method=moyen,
            sale_origin=origine,
            paiement_stripe=paiement_stripe,
            metadata=metadata,
            asset=asset,
            credit_note_for=credit_note_for,
            reservation=reservation,
            membership=membership,
        )
        date_de_la_ligne = self.moment_de_la_reprise - timedelta(
            minutes=minutes_avant_la_reprise
        )
        LigneArticle.objects.filter(pk=ligne.pk).update(
            datetime=date_de_la_ligne,
            vat=Decimal(taux_tva),
        )
        ligne.refresh_from_db()
        return ligne

    def _vente_du_groupe(self, plan, cle_du_groupe):
        """
        La vente du plan qui porte cette clé de groupe. Le test échoue s'il n'y en a pas
        exactement une.
        / The plan sale with this group key; fails unless there is exactly one.
        """
        ventes_trouvees = []
        for vente_a_reprendre in plan.ventes:
            if vente_a_reprendre.cle_du_groupe == str(cle_du_groupe):
                ventes_trouvees.append(vente_a_reprendre)
        assert len(ventes_trouvees) == 1, (
            f"{len(ventes_trouvees)} vente(s) de clé {cle_du_groupe} dans le plan"
        )
        return ventes_trouvees[0]

    def _cles_des_ventes(self, plan):
        """Les clés de groupe de toutes les ventes du plan, triées.
        / The group keys of all plan sales, sorted."""
        cles = []
        for vente_a_reprendre in plan.ventes:
            cles.append(vente_a_reprendre.cle_du_groupe)
        cles.sort()
        return cles

    def _article_de_la_ligne(self, vente_a_reprendre, ligne):
        """
        L'article du plan qui reprend cette ancienne ligne. Le test échoue s'il n'y en a
        pas exactement un.
        / The plan item that takes over this old line; exactly one.
        """
        articles_trouves = []
        for article in vente_a_reprendre.articles:
            if article.ligne is not None and article.ligne.uuid == ligne.uuid:
                articles_trouves.append(article)
        assert len(articles_trouves) == 1, (
            f"{len(articles_trouves)} article(s) pour la ligne {ligne.uuid}"
        )
        return articles_trouves[0]

    def _monnaie_fed_de_la_plateforme(self):
        """
        La monnaie fédérée (FED) de `fedow_public`. Elle est unique en base
        (contrainte) : on prend celle qui existe, sinon on la crée dans la transaction
        du test.
        / The federated currency (FED), unique: reuse it or create it in the test.
        """
        monnaie_fed = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if monnaie_fed is not None:
            return monnaie_fed
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille FED reprise {uuid.uuid4().hex[:8]}"
        )
        return AssetFedowPublic.objects.create(
            name=f"FED reprise {uuid.uuid4().hex[:8]}",
            currency_code="EUR",
            wallet_origin=portefeuille_d_origine,
            origin=self.tenant,
            category=AssetFedowPublic.STRIPE_FED_FIAT,
        )

    def _creer_une_monnaie_cadeau(self):
        """
        Une monnaie cadeau (TNF) du lieu, dans `fedow_public`.
        / A gift currency (TNF) of the venue.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille TNF reprise {uuid.uuid4().hex[:8]}"
        )
        return AssetFedowPublic.objects.create(
            name=f"Cadeau reprise {uuid.uuid4().hex[:8]}",
            currency_code="TNF",
            wallet_origin=portefeuille_d_origine,
            origin=self.tenant,
            category=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
        )

    def _creer_un_paiement_de_transfert(self, montant_en_centimes):
        """
        Un ancien paiement `T` (« Versement de monnaie globale ») : statut `V`, sans
        ligne, sans utilisateur. Son montant et sa date ne sont que dans
        `metadata_stripe`, un TEXTE JSON (`json.dumps(payload)`, ApiBillet/views.py,
        webhook `transfer.created`). Son `order_date` porte l'heure de réception du
        webhook, pas celle du transfert.
        / An old T payment: amount and date only in metadata_stripe, a JSON TEXT.
        """
        message_de_stripe = {
            "type": "transfer.created",
            "data": {
                "object": {
                    "id": f"tr_test_{uuid.uuid4().hex[:8]}",
                    "amount": montant_en_centimes,
                    "created": HORODATAGE_DU_TRANSFERT,
                    "destination": "acct_test_reprise",
                }
            },
        }
        return self._creer_un_paiement_stripe(
            statut=Paiement_stripe.VALID,
            source=Paiement_stripe.TRANSFERT,
            jours_depuis_la_commande=2,
            metadata_stripe=json.dumps(message_de_stripe),
        )

    # ------------------------------------------------------------------
    # 1. Le passage à blanc n'écrit rien
    # ------------------------------------------------------------------

    def test_reprise_passage_a_blanc_n_ecrit_rien(self):
        """
        La commande, sans option, lit le lieu et affiche son rapport. Elle n'écrit
        aucune vente, aucun règlement, aucun produit ; elle ne touche ni aux lignes ni
        aux paiements Stripe ; elle ne demande aucune tâche Celery.
        / The command writes nothing and requests no Celery task.
        """
        acheteur = creer_utilisateur()
        paiement_paye = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        ligne_payee = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="2",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_paye,
        )
        ligne_remboursee = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_paye,
            metadata={"original_lignearticle_uuid": str(ligne_payee.uuid)},
        )
        ligne_admin = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)
        self._monnaie_fed_de_la_plateforme()

        nombre_de_ventes_avant = Vente.objects.count()
        nombre_de_reglements_avant = Reglement.objects.count()
        nombre_de_produits_avant = Product.objects.count()
        champs_des_lignes = [
            "uuid",
            "vente_id",
            "credit_note_for_id",
            "status",
            "total_catalogue",
            "part_offerte",
            "total_ttc",
            "total_ht",
            "total_tva",
            "hors_chiffre_affaires",
        ]
        lignes_avant = list(
            LigneArticle.objects.filter(
                pk__in=[ligne_payee.pk, ligne_remboursee.pk, ligne_admin.pk]
            )
            .order_by("uuid")
            .values(*champs_des_lignes)
        )
        champs_des_paiements = [
            "uuid",
            "status",
            "vente_id",
            "moyen",
            "montant_encaisse",
        ]
        paiements_avant = list(
            Paiement_stripe.objects.filter(
                pk__in=[paiement_paye.pk, paiement_de_transfert.pk]
            )
            .order_by("uuid")
            .values(*champs_des_paiements)
        )

        with taches_celery_enregistrees() as taches_demandees:
            sortie_de_la_commande = self._lancer_le_passage_a_blanc()

        assert sortie_de_la_commande.strip() != ""
        assert Vente.objects.count() == nombre_de_ventes_avant
        assert Reglement.objects.count() == nombre_de_reglements_avant
        # Le produit « virement reçu » est seulement NOMMÉ par le plan.
        # / The "transfer received" product is only NAMED by the plan.
        assert Product.objects.count() == nombre_de_produits_avant
        lignes_apres = list(
            LigneArticle.objects.filter(
                pk__in=[ligne_payee.pk, ligne_remboursee.pk, ligne_admin.pk]
            )
            .order_by("uuid")
            .values(*champs_des_lignes)
        )
        assert lignes_apres == lignes_avant
        paiements_apres = list(
            Paiement_stripe.objects.filter(
                pk__in=[paiement_paye.pk, paiement_de_transfert.pk]
            )
            .order_by("uuid")
            .values(*champs_des_paiements)
        )
        assert paiements_apres == paiements_avant
        assert noms_des_taches(taches_demandees) == []

    # ------------------------------------------------------------------
    # 2. Une vente par paiement Stripe
    # ------------------------------------------------------------------

    def test_reprise_une_vente_par_paiement_stripe(self):
        """
        Les lignes d'un même paiement Stripe forment UNE vente réglée, datée de sa
        ligne la plus récente. Les montants de chaque article suivent la formule unique,
        avec le taux de TVA ÉCRIT SUR LA LIGNE (5,5 %), jamais celui du produit (20 %).
        Un règlement Stripe carte du total, relié au paiement, qui reçoit son moyen et
        son montant encaissé.
        / One Stripe payment = one settled sale, VAT read on the line.
        """
        acheteur = creer_utilisateur()
        paiement = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        ligne_de_deux_billets = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="2",
            taux_tva="5.5",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement,
            minutes_avant_la_reprise=120,
        )
        ligne_d_un_billet = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=800,
            quantite="1",
            taux_tva="5.5",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement,
            minutes_avant_la_reprise=60,
        )

        plan = self._calculer_le_plan()

        assert self._cles_des_ventes(plan) == [str(paiement.uuid)]
        vente = self._vente_du_groupe(plan, paiement.uuid)
        assert vente.nature == Vente.Nature.VENTE
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.unite == "EUR"
        assert vente.paiement_stripe == paiement
        assert vente.datetime_de_la_vente == ligne_d_un_billet.datetime
        assert len(vente.articles) == 2

        # 2 500 TTC à 5,5 % : HT = 2 500 × 100 / 105,5 = 2 369,67 → 2 370.
        # / 2,500 incl. 5.5 % VAT: excl. tax 2,370.
        article_de_deux_billets = self._article_de_la_ligne(
            vente, ligne_de_deux_billets
        )
        assert _montants_lisibles(article_de_deux_billets) == {
            "total_catalogue": 2500,
            "part_offerte": 0,
            "total_ttc": 2500,
            "total_ht": 2370,
            "total_tva": 130,
        }
        # 800 TTC à 5,5 % : HT = 758,29 → 758.
        # / 800 incl. 5.5 % VAT: excl. tax 758.
        article_d_un_billet = self._article_de_la_ligne(vente, ligne_d_un_billet)
        assert _montants_lisibles(article_d_un_billet) == {
            "total_catalogue": 800,
            "part_offerte": 0,
            "total_ttc": 800,
            "total_ht": 758,
            "total_tva": 42,
        }

        assert _reglements_lisibles(vente) == [
            (PaymentMethod.STRIPE_NOFED, 3300, None, paiement, ""),
        ]
        assert vente.moyen_du_paiement_stripe == PaymentMethod.STRIPE_NOFED
        assert vente.montant_encaisse_du_paiement_stripe == 3300

    # ------------------------------------------------------------------
    # 3. Les parts QR d'un même paiement
    # ------------------------------------------------------------------

    def test_reprise_parts_qr_d_un_meme_paiement_en_une_vente(self):
        """
        Les parts d'un paiement QR / NFC portent le MÊME texte `metadata` : elles forment
        une seule vente (clé : le plus petit uuid des parts), avec un règlement par
        couple (moyen, monnaie). Un autre paiement QR (autre texte) fait une autre vente.
        / Parts with the same metadata text form one sale; another QR payment, another.
        """
        tarif_du_qr = creer_tarif_vendu(
            nom="Paiement QR",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.QRCODE_MA,
        )
        monnaie_fed = self._monnaie_fed_de_la_plateforme()
        uuid_de_la_monnaie_locale = uuid.uuid4()
        texte_du_premier_paiement = json.dumps(
            {"transactions": [{"amount": 600}, {"amount": 400}], "test": "premier"}
        )
        texte_du_second_paiement = json.dumps(
            {"transactions": [{"amount": 900}], "test": "second"}
        )
        part_en_monnaie_fed = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=600,
            quantite="0.6",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.STRIPE_FED,
            origine=SaleOrigin.QRCODE_MA,
            metadata=texte_du_premier_paiement,
            asset=monnaie_fed.uuid,
        )
        part_en_monnaie_locale = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=400,
            quantite="0.4",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.QRCODE_MA,
            metadata=texte_du_premier_paiement,
            asset=uuid_de_la_monnaie_locale,
        )
        part_du_second_paiement = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=900,
            quantite="1",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.NFC_MA,
            metadata=texte_du_second_paiement,
            asset=uuid_de_la_monnaie_locale,
        )

        plan = self._calculer_le_plan()

        cle_du_premier_paiement = str(
            min(part_en_monnaie_fed.uuid, part_en_monnaie_locale.uuid)
        )
        assert self._cles_des_ventes(plan) == sorted(
            [cle_du_premier_paiement, str(part_du_second_paiement.uuid)]
        )
        vente_du_premier_paiement = self._vente_du_groupe(plan, cle_du_premier_paiement)
        assert vente_du_premier_paiement.statut == Vente.Statut.REGLEE
        assert vente_du_premier_paiement.paiement_stripe is None
        assert len(vente_du_premier_paiement.articles) == 2
        assert _reglements_lisibles(vente_du_premier_paiement) == [
            (PaymentMethod.LOCAL_EURO, 400, uuid_de_la_monnaie_locale, None, ""),
            (PaymentMethod.STRIPE_FED, 600, monnaie_fed.uuid, None, ""),
        ]

    # ------------------------------------------------------------------
    # 4. Les lignes négatives : des avoirs, même sur un paiement Stripe
    # ------------------------------------------------------------------

    def test_reprise_ligne_negative_ou_remboursee_devient_un_avoir_meme_avec_un_paiement_stripe(
        self,
    ):
        """
        L'ancien code recopiait `paiement_stripe` sur les lignes négatives. La règle
        « avoir » passe donc AVANT la règle « paiement Stripe » : un remboursement
        (`R`) et un avoir admin (`N`) font chacun leur vente AVOIR, à la date de leur
        ligne, avec un règlement négatif marqué « reprise ». La vente du paiement ne
        garde que la ligne payée.
        / Credit notes first: each negative line is its own AVOIR sale.
        """
        acheteur = creer_utilisateur()
        paiement_rembourse = self._creer_un_paiement_stripe(
            Paiement_stripe.REFUNDED, utilisateur=acheteur
        )
        ligne_de_deux_billets = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="2",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_rembourse,
            minutes_avant_la_reprise=300,
        )
        ligne_du_remboursement_stripe = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_rembourse,
            metadata={"original_lignearticle_uuid": str(ligne_de_deux_billets.uuid)},
            minutes_avant_la_reprise=100,
        )
        ligne_de_l_avoir_admin = self._creer_une_ancienne_ligne(
            LigneArticle.CREDIT_NOTE,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            origine=SaleOrigin.ADMIN,
            paiement_stripe=paiement_rembourse,
            credit_note_for=ligne_de_deux_billets,
            minutes_avant_la_reprise=50,
        )

        plan = self._calculer_le_plan()

        assert self._cles_des_ventes(plan) == sorted(
            [
                str(paiement_rembourse.uuid),
                str(ligne_du_remboursement_stripe.uuid),
                str(ligne_de_l_avoir_admin.uuid),
            ]
        )

        vente_du_paiement = self._vente_du_groupe(plan, paiement_rembourse.uuid)
        assert vente_du_paiement.nature == Vente.Nature.VENTE
        assert vente_du_paiement.statut == Vente.Statut.REGLEE
        assert len(vente_du_paiement.articles) == 1
        self._article_de_la_ligne(vente_du_paiement, ligne_de_deux_billets)

        avoir_du_remboursement = self._vente_du_groupe(
            plan, ligne_du_remboursement_stripe.uuid
        )
        assert avoir_du_remboursement.nature == Vente.Nature.AVOIR
        assert avoir_du_remboursement.statut == Vente.Statut.REGLEE
        assert (
            avoir_du_remboursement.datetime_de_la_vente
            == ligne_du_remboursement_stripe.datetime
        )
        assert avoir_du_remboursement.uuid_de_la_ligne_d_origine == (
            ligne_de_deux_billets.uuid
        )
        assert avoir_du_remboursement.credit_note_for_a_poser is True
        article_du_remboursement = self._article_de_la_ligne(
            avoir_du_remboursement, ligne_du_remboursement_stripe
        )
        assert article_du_remboursement.total_ttc == -1250
        assert _reglements_lisibles(avoir_du_remboursement) == [
            (PaymentMethod.STRIPE_NOFED, -1250, None, paiement_rembourse, "reprise"),
        ]

        avoir_de_l_admin = self._vente_du_groupe(plan, ligne_de_l_avoir_admin.uuid)
        assert avoir_de_l_admin.nature == Vente.Nature.AVOIR
        assert avoir_de_l_admin.statut == Vente.Statut.REGLEE
        assert avoir_de_l_admin.uuid_de_la_ligne_d_origine == ligne_de_deux_billets.uuid
        # `credit_note_for` est déjà posé sur la ligne : rien à poser.
        # / credit_note_for is already set on the line: nothing to set.
        assert avoir_de_l_admin.credit_note_for_a_poser is False
        assert _reglements_lisibles(avoir_de_l_admin) == [
            (PaymentMethod.STRIPE_NOFED, -1250, None, paiement_rembourse, "reprise"),
        ]

    # ------------------------------------------------------------------
    # 5. Le statut suit le paiement Stripe
    # ------------------------------------------------------------------

    def test_reprise_statut_suit_le_paiement_stripe(self):
        """
        Paiement `V`, `P`, `R` → vente réglée. `W` commandé il y a moins de 30 jours →
        en attente ; `W` plus vieux, et `E` → annulée. L'âge se lit sur `order_date`,
        jamais sur `last_action` ni `datetime` (déplacés par tout enregistrement) : ici,
        les deux dates disent le contraire l'une de l'autre.
        / The sale status follows the Stripe payment; age is read on order_date.
        """
        paiement_valide = self._creer_un_paiement_stripe(Paiement_stripe.VALID)
        paiement_paye = self._creer_un_paiement_stripe(Paiement_stripe.PAID)
        paiement_rembourse = self._creer_un_paiement_stripe(Paiement_stripe.REFUNDED)
        paiement_en_cours_recent = self._creer_un_paiement_stripe(
            Paiement_stripe.PENDING,
            jours_depuis_la_commande=10,
            jours_depuis_la_derniere_action=40,
        )
        paiement_en_cours_ancien = self._creer_un_paiement_stripe(
            Paiement_stripe.PENDING,
            jours_depuis_la_commande=40,
            jours_depuis_la_derniere_action=1,
        )
        paiement_expire = self._creer_un_paiement_stripe(Paiement_stripe.EXPIRE)

        statut_de_ligne_par_paiement = [
            (paiement_valide, LigneArticle.VALID),
            (paiement_paye, LigneArticle.PAID),
            (paiement_rembourse, LigneArticle.VALID),
            (paiement_en_cours_recent, LigneArticle.UNPAID),
            (paiement_en_cours_ancien, LigneArticle.UNPAID),
            (paiement_expire, LigneArticle.UNPAID),
        ]
        for paiement, statut_de_la_ligne in statut_de_ligne_par_paiement:
            self._creer_une_ancienne_ligne(
                statut_de_la_ligne,
                montant=1250,
                quantite="1",
                moyen=PaymentMethod.STRIPE_NOFED,
                paiement_stripe=paiement,
            )

        plan = self._calculer_le_plan()

        assert self._vente_du_groupe(plan, paiement_valide.uuid).statut == (
            Vente.Statut.REGLEE
        )
        assert self._vente_du_groupe(plan, paiement_paye.uuid).statut == (
            Vente.Statut.REGLEE
        )
        assert self._vente_du_groupe(plan, paiement_rembourse.uuid).statut == (
            Vente.Statut.REGLEE
        )
        vente_en_attente = self._vente_du_groupe(plan, paiement_en_cours_recent.uuid)
        assert vente_en_attente.statut == Vente.Statut.EN_ATTENTE
        # Reliée au paiement : le webhook l'encaissera après la bascule.
        # / Linked to the payment: the webhook settles it after the switch.
        assert vente_en_attente.paiement_stripe == paiement_en_cours_recent
        assert self._vente_du_groupe(plan, paiement_en_cours_ancien.uuid).statut == (
            Vente.Statut.ANNULEE
        )
        assert self._vente_du_groupe(plan, paiement_expire.uuid).statut == (
            Vente.Statut.ANNULEE
        )

    # ------------------------------------------------------------------
    # 6. Hors Stripe, une ligne restée « créée » : vente annulée
    # ------------------------------------------------------------------

    def test_reprise_ligne_creee_hors_stripe_vente_annulee(self):
        """
        Hors Stripe, le statut suit les lignes. Un QR code généré jamais payé laisse une
        ligne `O` (créée), d'origine QR ou « en ligne » : vente annulée. Une ligne
        validée de l'admin : vente réglée.
        / Off Stripe, a line left "created" (QR never paid) gives a cancelled sale.
        """
        tarif_du_qr = creer_tarif_vendu(
            nom="Paiement QR",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.QRCODE_MA,
        )
        demande_qr_jamais_payee = self._creer_une_ancienne_ligne(
            LigneArticle.CREATED,
            montant=1500,
            quantite="1",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.QRCODE_MA,
            origine=SaleOrigin.QRCODE_MA,
            metadata=json.dumps({"test": "qr jamais payé"}),
        )
        demande_en_ligne_jamais_payee = self._creer_une_ancienne_ligne(
            LigneArticle.CREATED,
            montant=700,
            quantite="1",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.QRCODE_MA,
            origine=SaleOrigin.LESPASS,
        )
        ligne_validee_de_l_admin = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

        plan = self._calculer_le_plan()

        assert self._vente_du_groupe(plan, demande_qr_jamais_payee.uuid).statut == (
            Vente.Statut.ANNULEE
        )
        assert (
            self._vente_du_groupe(plan, demande_en_ligne_jamais_payee.uuid).statut
            == Vente.Statut.ANNULEE
        )
        assert self._vente_du_groupe(plan, ligne_validee_de_l_admin.uuid).statut == (
            Vente.Statut.REGLEE
        )

    # ------------------------------------------------------------------
    # 7. L'argent d'une part QR est son montant
    # ------------------------------------------------------------------

    def test_reprise_parts_qr_argent_egal_au_montant_de_la_part(self):
        """
        L'argent réel d'une part QR / NFC est son `amount`, jamais `amount × qty`
        (Q-R10) : 600 avec `qty` 0,6 vaut 600, pas 360. Les lignes `LE` / `SF` à
        quantité non entière hors QR sont traitées comme des parts (QO-12).
        / A QR part's money is its amount, never amount × qty; same for QO-12 lines.
        """
        tarif_du_qr = creer_tarif_vendu(
            nom="Paiement QR",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.QRCODE_MA,
        )
        uuid_de_la_monnaie_locale = uuid.uuid4()
        part_qr = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=600,
            quantite="0.6",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.QRCODE_MA,
            metadata=json.dumps({"transactions": [{"amount": 600}]}),
            asset=uuid_de_la_monnaie_locale,
        )
        ligne_en_monnaie_locale_hors_qr = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=800,
            quantite="0.5",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.LESPASS,
            asset=uuid_de_la_monnaie_locale,
        )

        plan = self._calculer_le_plan()

        vente_de_la_part_qr = self._vente_du_groupe(plan, part_qr.uuid)
        article_de_la_part_qr = self._article_de_la_ligne(vente_de_la_part_qr, part_qr)
        assert _montants_lisibles(article_de_la_part_qr) == {
            "total_catalogue": 600,
            "part_offerte": 0,
            "total_ttc": 600,
            "total_ht": 600,
            "total_tva": 0,
        }
        assert _reglements_lisibles(vente_de_la_part_qr) == [
            (PaymentMethod.LOCAL_EURO, 600, uuid_de_la_monnaie_locale, None, ""),
        ]

        vente_hors_qr = self._vente_du_groupe(
            plan, ligne_en_monnaie_locale_hors_qr.uuid
        )
        article_hors_qr = self._article_de_la_ligne(
            vente_hors_qr, ligne_en_monnaie_locale_hors_qr
        )
        assert article_hors_qr.total_catalogue == 800
        assert article_hors_qr.total_ttc == 800
        assert _reglements_lisibles(vente_hors_qr) == [
            (PaymentMethod.LOCAL_EURO, 800, uuid_de_la_monnaie_locale, None, ""),
        ]

    # ------------------------------------------------------------------
    # 8. Un offert à montant non nul
    # ------------------------------------------------------------------

    def test_reprise_offert_a_montant_non_nul_part_offerte_et_reglement_free(self):
        """
        Une recharge cadeau (`TNF`) offerte (moyen `NA`) de 15 € : part offerte = total
        catalogue, source « offert », net 0, hors chiffre d'affaires, unité EUR, et un
        règlement FREE de 15 € (QO-10). Une ligne offerte à 0 € : vente réglée sans
        aucun règlement.
        / An offered gift top-up: offered part = total, one FREE payment; a free 0 line:
        no payment.
        """
        monnaie_cadeau = self._creer_une_monnaie_cadeau()
        recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="15.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        )
        ligne_de_la_recharge_offerte = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1500,
            quantite="1",
            tarif_vendu=recharge_cadeau,
            moyen=PaymentMethod.FREE,
            asset=monnaie_cadeau.uuid,
        )
        ligne_offerte_a_zero = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=0,
            quantite="1",
            moyen=PaymentMethod.FREE,
            origine=SaleOrigin.ADMIN,
        )

        plan = self._calculer_le_plan()

        vente_de_la_recharge = self._vente_du_groupe(
            plan, ligne_de_la_recharge_offerte.uuid
        )
        assert vente_de_la_recharge.statut == Vente.Statut.REGLEE
        assert vente_de_la_recharge.unite == "EUR"
        article_de_la_recharge = self._article_de_la_ligne(
            vente_de_la_recharge, ligne_de_la_recharge_offerte
        )
        assert _montants_lisibles(article_de_la_recharge) == {
            "total_catalogue": 1500,
            "part_offerte": 1500,
            "total_ttc": 0,
            "total_ht": 0,
            "total_tva": 0,
        }
        assert article_de_la_recharge.source_offert == (
            LigneArticle.SourceOffert.OFFRIR
        )
        assert article_de_la_recharge.hors_chiffre_affaires is True
        assert _reglements_lisibles(vente_de_la_recharge) == [
            (PaymentMethod.FREE, 1500, None, None, ""),
        ]

        vente_offerte_a_zero = self._vente_du_groupe(plan, ligne_offerte_a_zero.uuid)
        assert vente_offerte_a_zero.statut == Vente.Statut.REGLEE
        assert _reglements_lisibles(vente_offerte_a_zero) == []
        assert plan.anomalies == {}

    # ------------------------------------------------------------------
    # 9. Un paiement T devient une vente « virement reçu »
    # ------------------------------------------------------------------

    def test_reprise_paiement_t_devient_une_vente_virement_recu(self):
        """
        Un paiement `T` (retour en banque de monnaie FED) sans ligne donne une vente
        « virement reçu » (QO-9, option B). Son montant et sa date sont lus dans le
        TEXTE JSON `metadata_stripe` (`data.object.amount`, `data.object.created`),
        jamais sur `order_date`. Un article `VR` à créer : quantité 1, TVA 0, hors
        chiffre d'affaires, monnaie FED. Un règlement Stripe en ligne (SN) relié au
        paiement, qui reçoit le moyen SN et son montant encaissé.
        / A T payment becomes a "transfer received" sale, read from metadata_stripe.
        """
        monnaie_fed = self._monnaie_fed_de_la_plateforme()
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)

        plan = self._calculer_le_plan()

        vente = self._vente_du_groupe(plan, paiement_de_transfert.uuid)
        assert vente.nature == Vente.Nature.VENTE
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.datetime_de_la_vente == DATE_DU_TRANSFERT
        assert vente.client is None
        assert vente.paiement_stripe == paiement_de_transfert
        assert len(vente.articles) == 1
        article_du_virement = vente.articles[0]
        assert article_du_virement.ligne is None
        assert article_du_virement.methode_caisse_du_produit_a_creer == (
            Product.VIREMENT_RECU
        )
        assert article_du_virement.quantite == 1
        assert article_du_virement.prix_unitaire == 4200
        assert article_du_virement.taux_tva == 0
        assert article_du_virement.asset == monnaie_fed.uuid
        assert article_du_virement.hors_chiffre_affaires is True
        assert _montants_lisibles(article_du_virement) == {
            "total_catalogue": 4200,
            "part_offerte": 0,
            "total_ttc": 4200,
            "total_ht": 4200,
            "total_tva": 0,
        }
        assert _reglements_lisibles(vente) == [
            (PaymentMethod.STRIPE_NOFED, 4200, None, paiement_de_transfert, ""),
        ]
        assert vente.moyen_du_paiement_stripe == PaymentMethod.STRIPE_NOFED
        assert vente.montant_encaisse_du_paiement_stripe == 4200

    # ------------------------------------------------------------------
    # 10. Moyen vide sur un paiement Stripe
    # ------------------------------------------------------------------

    def test_reprise_moyen_vide_sur_paiement_stripe_devient_stripe_carte(self):
        """
        Une ligne d'un paiement Stripe sans moyen écrit (API v1, billets en ligne) est
        payée par Stripe carte (Q-R9) : règlement SN relié au paiement, moyen SN posé sur
        le paiement.
        / An empty payment method on a Stripe payment becomes Stripe card (SN).
        """
        acheteur = creer_utilisateur()
        paiement = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1000,
            quantite="1",
            moyen=None,
            paiement_stripe=paiement,
        )

        plan = self._calculer_le_plan()

        vente = self._vente_du_groupe(plan, paiement.uuid)
        assert _reglements_lisibles(vente) == [
            (PaymentMethod.STRIPE_NOFED, 1000, None, paiement, ""),
        ]
        assert vente.moyen_du_paiement_stripe == PaymentMethod.STRIPE_NOFED
        assert vente.montant_encaisse_du_paiement_stripe == 1000
        assert plan.anomalies == {}

    # ------------------------------------------------------------------
    # 11. Le client de la vente
    # ------------------------------------------------------------------

    def test_reprise_client_reservation_puis_adhesion_puis_paiement(self):
        """
        Le client d'une vente reprise (QO-3) est l'utilisateur de la réservation, sinon
        celui de l'adhésion, sinon celui du paiement Stripe, sinon personne.
        / The client: reservation user, else membership user, else payment user, else none.
        """
        personne_qui_reserve = creer_utilisateur(prenom="Reserve")
        adherent = creer_utilisateur(prenom="Adherent")
        payeur = creer_utilisateur(prenom="Payeur")
        billetterie = creer_evenement_avec_tarif(prix="12.50")
        reservation = Reservation.objects.create(
            user_commande=personne_qui_reserve,
            event=billetterie.evenement,
        )
        adhesion = Membership.objects.create(user=adherent)

        paiement_avec_reservation = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=payeur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_avec_reservation,
            reservation=reservation,
            membership=adhesion,
        )
        paiement_avec_adhesion = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=payeur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=2000,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_avec_adhesion,
            membership=adhesion,
        )
        paiement_seul = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=payeur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_seul,
        )
        ligne_sans_personne = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=300,
            quantite="1",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

        plan = self._calculer_le_plan()

        assert self._vente_du_groupe(plan, paiement_avec_reservation.uuid).client == (
            personne_qui_reserve
        )
        assert self._vente_du_groupe(plan, paiement_avec_adhesion.uuid).client == (
            adherent
        )
        assert self._vente_du_groupe(plan, paiement_seul.uuid).client == payeur
        assert self._vente_du_groupe(plan, ligne_sans_personne.uuid).client is None

    # ------------------------------------------------------------------
    # 12. Les anomalies
    # ------------------------------------------------------------------

    def test_reprise_anomalies_comptees_sans_donnee_personnelle(self):
        """
        Une forme absente de la production (paiement Stripe `S`) est une anomalie
        « forme non prévue » : son groupe n'est pas dans le plan. Un avoir dont la ligne
        d'origine est introuvable est signalé, mais repris sans origine. Le reste du
        lieu est repris. Le rapport compte les anomalies par type, sans aucune donnée
        personnelle (ni mail, ni texte de `metadata`).
        / Anomalies are counted by type, without personal data; the rest goes on.
        """
        acheteur = creer_utilisateur()
        paiement_d_une_forme_non_prevue = self._creer_un_paiement_stripe(
            Paiement_stripe.NOTSYNC, utilisateur=acheteur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_d_une_forme_non_prevue,
        )
        paiement_ordinaire = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_ordinaire,
        )
        avoir_sans_origine = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_ordinaire,
            metadata=json.dumps(
                {
                    "original_lignearticle_uuid": str(uuid.uuid4()),
                    "email": acheteur.email,
                }
            ),
        )

        plan = self._calculer_le_plan()

        assert plan.anomalies == {
            ANOMALIE_FORME_NON_PREVUE: 1,
            ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE: 1,
        }
        assert self._cles_des_ventes(plan) == sorted(
            [str(paiement_ordinaire.uuid), str(avoir_sans_origine.uuid)]
        )
        avoir_repris = self._vente_du_groupe(plan, avoir_sans_origine.uuid)
        assert avoir_repris.nature == Vente.Nature.AVOIR
        assert avoir_repris.uuid_de_la_ligne_d_origine is None

        sortie_de_la_commande = self._lancer_le_passage_a_blanc()
        assert ANOMALIE_FORME_NON_PREVUE in sortie_de_la_commande
        assert ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE in sortie_de_la_commande
        assert acheteur.email not in sortie_de_la_commande

    # ------------------------------------------------------------------
    # 13. Les totaux, ancien et nouveau calcul
    # ------------------------------------------------------------------

    def test_reprise_totaux_identiques_a_l_ancien_calcul_hors_parts_qr(self):
        """
        Le nouveau total (Σ `total_ttc`) vaut l'ancien (Σ `amount × qty`), avoirs
        compris, sauf pour une part QR : là, l'écart est attendu (360 avant, 600 après).
        / New total = old total, credit notes included, except for QR parts.
        """
        tarif_du_qr = creer_tarif_vendu(
            nom="Paiement QR",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.QRCODE_MA,
        )
        paiement = self._creer_un_paiement_stripe(Paiement_stripe.VALID)
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="2",
            taux_tva="5.5",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement,
        )
        ligne_admin = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=333,
            quantite="3",
            taux_tva="20",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
            minutes_avant_la_reprise=200,
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.CREDIT_NOTE,
            montant=333,
            quantite="-1",
            taux_tva="20",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
            credit_note_for=ligne_admin,
            minutes_avant_la_reprise=100,
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=600,
            quantite="0.6",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.QRCODE_MA,
            metadata=json.dumps({"transactions": [{"amount": 600}]}),
            asset=uuid.uuid4(),
        )

        plan = self._calculer_le_plan()

        assert plan.nombre_de_lignes_lues == 4
        # Ancien : 2 500 + 999 − 333 + 360 = 3 526.
        # Nouveau : 2 500 + 999 − 333 + 600 = 3 766.
        assert plan.total_ancien_calcul == 3526
        assert plan.total_nouveau_calcul == 3766
        assert plan.anomalies == {}

    # ------------------------------------------------------------------
    # 14. `metadata` lu en dict et en texte
    # ------------------------------------------------------------------

    def test_reprise_metadata_lue_en_dict_et_en_texte(self):
        """
        Selon l'ancien producteur, `metadata` est un dict OU un texte JSON. L'origine
        d'un remboursement (`original_lignearticle_uuid`) se lit dans les deux formes,
        et `credit_note_for` est à poser.
        / metadata is a dict OR a JSON text: the refund origin is read in both.
        """
        paiement_au_dict = self._creer_un_paiement_stripe(Paiement_stripe.REFUNDED)
        origine_du_dict = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_au_dict,
            minutes_avant_la_reprise=200,
        )
        remboursement_au_dict = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_au_dict,
            metadata={"original_lignearticle_uuid": str(origine_du_dict.uuid)},
            minutes_avant_la_reprise=100,
        )
        paiement_au_texte = self._creer_un_paiement_stripe(Paiement_stripe.REFUNDED)
        origine_du_texte = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=900,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_au_texte,
            minutes_avant_la_reprise=200,
        )
        remboursement_au_texte = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=900,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_au_texte,
            metadata=json.dumps(
                {"original_lignearticle_uuid": str(origine_du_texte.uuid)}
            ),
            minutes_avant_la_reprise=100,
        )

        plan = self._calculer_le_plan()

        avoir_au_dict = self._vente_du_groupe(plan, remboursement_au_dict.uuid)
        assert avoir_au_dict.uuid_de_la_ligne_d_origine == origine_du_dict.uuid
        assert avoir_au_dict.credit_note_for_a_poser is True
        avoir_au_texte = self._vente_du_groupe(plan, remboursement_au_texte.uuid)
        assert avoir_au_texte.uuid_de_la_ligne_d_origine == origine_du_texte.uuid
        assert avoir_au_texte.credit_note_for_a_poser is True
        assert plan.anomalies == {}

    # ------------------------------------------------------------------
    # 15. Les paiements Stripe sans ligne
    # ------------------------------------------------------------------

    def test_reprise_paiement_sans_ligne_aucune_vente_compte_dans_le_rapport(self):
        """
        Un paiement Stripe sans aucune ligne, hors `T` (panier abandonné `F` / `W`, vieux
        paiement QR `Q` / `P`), ne donne aucune vente : il est seulement compté. Le
        paiement `T`, lui, donne sa vente « virement reçu ».
        / A Stripe payment without lines (other than T) gives no sale; it is counted.
        """
        self._monnaie_fed_de_la_plateforme()
        self._creer_un_paiement_stripe(Paiement_stripe.FAILED)
        self._creer_un_paiement_stripe(Paiement_stripe.PENDING)
        self._creer_un_paiement_stripe(
            Paiement_stripe.PAID, source=Paiement_stripe.QRCODE
        )
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)

        plan = self._calculer_le_plan()

        assert plan.nombre_de_paiements_stripe_sans_ligne == 3
        assert self._cles_des_ventes(plan) == [str(paiement_de_transfert.uuid)]

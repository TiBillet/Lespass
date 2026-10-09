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
- `plan.informations` : un dict {type d'information (texte) : nombre}, sans effet ;
- `plan.total_ancien_calcul_hors_parts_qr` : Σ `amount × qty` des anciennes lignes
  reprises, hors parts QR ;
- `plan.total_catalogue_hors_parts_qr` : Σ `total_catalogue` des mêmes lignes ;
- `plan.total_ttc` et `plan.total_part_offerte` : Σ `total_ttc` et Σ `part_offerte` de
  tous les articles du plan.

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

L'ÉCRITURE DU PLAN (session R-2)
La seconde moitié des tests porte sur l'écriture : le plan devient de vraies ventes, sans
être recalculé. Ces tests lisent :
- `ecrire_le_plan_de_reprise(plan)` (BaseBillet/reprise_des_ventes_ecriture.py) : écrit
  le plan du lieu courant et rend un résultat qui porte `nombre_de_ventes_ecrites`,
  `nombre_de_ventes_sautees` (ventes déjà reprises) et `chaine_valide` (vrai ou faux) ;
- la commande `reprendre_les_ventes_existantes --schema <lieu> --executer`. Son rapport
  affiche, en plus du passage à blanc, les lignes « Ventes écrites : <nombre> » et
  « Chaîne des ventes valide : oui » (ou « non »). Un lieu qui a déjà une vente réglée
  hors reprise est refusé : rien n'est écrit, et le rapport le dit par un message qui
  contient « vente réglée hors reprise ». La commande ne s'arrête pas en erreur : elle
  passe au lieu suivant.
Chaque vente écrite porte `idempotency_key = "reprise-<clé du groupe>"` : c'est ainsi que
les tests la retrouvent. Le singleton `LaboutikConfiguration` est créé à la main dans
`setUp` (tests/PIEGES.md 9.86) : il porte la clé de l'empreinte des ventes.
/ Second half: the plan is written as real sales, found by their "reprise-<key>"
idempotency key, through the writing function or the command with --executer.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§3 à
§10, §13 R-1 et R-2, §14, §17) et les briefs CHANTIER-05-briefs/05-R-1.md et 05-R-2.md.

Lancer / Run : make test ARGS="tests/pytest/test_reprise_des_ventes.py"
"""

import io
import json
import uuid
from datetime import datetime, timedelta
from datetime import timezone as fuseau_horaire
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

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
from BaseBillet.services_vente import encaisser_vente_stripe
from fabriques_panier import (
    creer_evenement_avec_tarif,
    creer_utilisateur,
    noms_des_taches,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_public.models import AssetFedowPublic
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration

# Les types d'anomalie lus dans `plan.anomalies` (textes du rapport).
# / The anomaly types read in plan.anomalies (report texts).
ANOMALIE_FORME_NON_PREVUE = "forme non prévue"
ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE = "origine d'avoir introuvable"

# La date d'un transfert Stripe de test : 14/11/2023 22:13:20 UTC, en horodatage Unix.
# / A test Stripe transfer date, as a Unix timestamp.
HORODATAGE_DU_TRANSFERT = 1700000000
DATE_DU_TRANSFERT = datetime(2023, 11, 14, 22, 13, 20, tzinfo=fuseau_horaire.utc)

# Le début de la clé d'idempotence d'une vente reprise : "reprise-<clé du groupe>".
# / The idempotency key prefix of a sale taken over.
PREFIXE_DE_LA_CLE_DE_REPRISE = "reprise-"

# Les morceaux du rapport d'exécution lus par les tests.
# / The pieces of the execution report read by the tests.
RAPPORT_CHAINE_VALIDE = "Chaîne des ventes valide : oui"
RAPPORT_VENTES_ECRITES = "Ventes écrites : "
MESSAGE_DU_LIEU_DEJA_VENDU = "vente réglée hors reprise"

# Les huit montants qu'une ancienne ligne reçoit de la reprise.
# / The eight amounts an old line receives from the takeover.
CHAMPS_DE_MONTANTS_D_UNE_LIGNE = [
    "total_catalogue",
    "part_offerte",
    "source_offert",
    "part_en_jetons",
    "total_ttc",
    "total_ht",
    "total_tva",
    "hors_chiffre_affaires",
]


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


def _montants_prevus_par_le_plan(article_a_reprendre):
    """
    Les huit montants qu'un article du plan doit écrire sur sa ligne, en dict.
    / The eight amounts a plan item must write on its line, as a dict.
    """
    montants_prevus = {}
    for nom_du_champ in CHAMPS_DE_MONTANTS_D_UNE_LIGNE:
        montants_prevus[nom_du_champ] = getattr(article_a_reprendre, nom_du_champ)
    return montants_prevus


def _montants_ecrits_sur_la_ligne(ligne):
    """
    Les huit montants d'une ligne, relus en base, en dict.
    / The eight amounts of a line, read back from the database, as a dict.
    """
    return (
        LigneArticle.objects.filter(pk=ligne.pk)
        .values(*CHAMPS_DE_MONTANTS_D_UNE_LIGNE)
        .get()
    )


def _reglements_ecrits(vente):
    """
    Les règlements d'une vente, relus en base, en tuples triés : (moyen, montant,
    paiement Stripe, référence externe).
    / The sale's payments read back, as sorted tuples.
    """
    reglements_en_tuples = []
    for reglement in Reglement.objects.filter(vente=vente).select_related(
        "paiement_stripe"
    ):
        reglements_en_tuples.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.paiement_stripe,
                reglement.reference_externe,
            )
        )
    reglements_en_tuples.sort(key=lambda reglement: (reglement[0], reglement[1]))
    return reglements_en_tuples


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

        # Le singleton de la caisse doit exister en base (PIEGES 9.86) : il porte la
        # clé de l'empreinte des ventes que l'écriture encaisse.
        # / The register singleton must exist in the database: it holds the HMAC key.
        LaboutikConfiguration.get_solo().save()

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
        # Le montant encaissé du paiement remboursé est le total d'origine de ses
        # articles positifs, avoirs non déduits (Q-R4) : 2 500.
        # / The refunded payment's collected amount is its original total (Q-R4).
        assert vente_du_paiement.moyen_du_paiement_stripe == PaymentMethod.STRIPE_NOFED
        assert vente_du_paiement.montant_encaisse_du_paiement_stripe == 2500

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
        vente_du_paiement_en_cours_ancien = self._vente_du_groupe(
            plan, paiement_en_cours_ancien.uuid
        )
        assert vente_du_paiement_en_cours_ancien.statut == Vente.Statut.ANNULEE
        vente_du_paiement_expire = self._vente_du_groupe(plan, paiement_expire.uuid)
        assert vente_du_paiement_expire.statut == Vente.Statut.ANNULEE

        # Une vente en attente ou annulée n'a reçu aucun argent : aucun règlement, et
        # rien à poser sur son paiement.
        # / A pending or cancelled sale received no money: no payment, nothing to set.
        ventes_sans_argent_recu = [
            vente_en_attente,
            vente_du_paiement_en_cours_ancien,
            vente_du_paiement_expire,
        ]
        for vente_sans_argent_recu in ventes_sans_argent_recu:
            assert _reglements_lisibles(vente_sans_argent_recu) == []
            assert vente_sans_argent_recu.moyen_du_paiement_stripe is None
            assert vente_sans_argent_recu.montant_encaisse_du_paiement_stripe is None

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
        Une forme absente de la production (paiement Stripe `S` ; ligne validée sur un
        paiement en cours `W`, qui n'accepte que des lignes `U` ou `O`) est une anomalie
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
        paiement_en_cours_avec_une_ligne_validee = self._creer_un_paiement_stripe(
            Paiement_stripe.PENDING, utilisateur=acheteur
        )
        self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_en_cours_avec_une_ligne_validee,
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
            ANOMALIE_FORME_NON_PREVUE: 2,
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
        Hors parts QR, le nouveau total catalogue (Σ `total_catalogue`) vaut l'ancien
        calcul (Σ `amount × qty`), avoirs et offerts compris. Le rapport donne aussi
        Σ `total_ttc` et Σ `part_offerte` de tous les articles : un offert y sort du net,
        et une part QR y compte pour son montant (600, là où l'ancien calcul disait 360).
        / Off QR parts, new catalogue total = old total; net and offered totals apart.
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
            montant=500,
            quantite="1",
            moyen=PaymentMethod.FREE,
            origine=SaleOrigin.ADMIN,
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

        assert plan.nombre_de_lignes_lues == 5
        # Hors part QR, ancien et nouveau : 2 500 + 999 − 333 + 500 = 3 666.
        # / Off the QR part, old and new: 3,666.
        assert plan.total_ancien_calcul_hors_parts_qr == 3666
        assert plan.total_catalogue_hors_parts_qr == 3666
        # Net de tous les articles : 2 500 + 999 − 333 + 0 (offert) + 600 (part QR).
        # / Net of all items: the offered line is 0, the QR part counts 600.
        assert plan.total_ttc == 3766
        assert plan.total_part_offerte == 500
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

    # ==================================================================
    # L'ÉCRITURE DU PLAN (session R-2)
    # / WRITING THE PLAN
    # ==================================================================

    # ------------------------------------------------------------------
    # Assistants de l'écriture / Writing helpers
    # ------------------------------------------------------------------

    def _executer_la_reprise(self):
        """
        Lance la commande de reprise AVEC écriture (`--executer`) sur le lieu du test,
        et rend tout ce qu'elle affiche (sortie et erreurs).
        / Runs the takeover command WITH writing on the test venue; returns its output.
        """
        sortie_de_la_commande = io.StringIO()
        erreurs_de_la_commande = io.StringIO()
        call_command(
            "reprendre_les_ventes_existantes",
            "--schema",
            self.tenant.schema_name,
            "--executer",
            stdout=sortie_de_la_commande,
            stderr=erreurs_de_la_commande,
        )
        return sortie_de_la_commande.getvalue() + erreurs_de_la_commande.getvalue()

    def _ecrire_le_plan(self, plan):
        """
        Écrit un plan déjà calculé, par la fonction d'écriture, et rend son résultat.
        / Writes an already computed plan through the writing function.
        """
        from BaseBillet.reprise_des_ventes_ecriture import ecrire_le_plan_de_reprise

        return ecrire_le_plan_de_reprise(plan)

    def _cle_de_l_empreinte_du_lieu(self):
        """La clé de l'empreinte du lieu, celle qu'utilise `encaisser_vente`.
        / The venue fingerprint key, the one used by encaisser_vente."""
        return LaboutikConfiguration.get_solo().get_or_create_hmac_key()

    def _vente_reprise(self, cle_du_groupe):
        """
        La vente écrite pour ce groupe, retrouvée par sa clé "reprise-<clé>".
        / The sale written for this group, found by its "reprise-<key>" key.
        """
        return Vente.objects.get(
            idempotency_key=f"{PREFIXE_DE_LA_CLE_DE_REPRISE}{cle_du_groupe}"
        )

    def _creer_l_historique_d_un_lieu(self):
        """
        L'historique d'un lieu, avec les formes principales de la production (fiche R
        §3 et §14). Les lignes sont créées dans un ordre qui N'EST PAS celui du temps :
        l'écriture doit suivre l'ordre du plan, pas l'ordre de création.
        / A venue history with the main production shapes, created out of time order.

        Ventes attendues (12), du plus ancien au plus récent :
        - réglées et numérotées (9) : le virement reçu (2023), le paiement payé
          (5 h avant la reprise), le paiement SEPA (4 h 20), le paiement `P` à ligne `P`
          (4 h 10), la recharge offerte (3 h 40), la vente admin en espèces (3 h 20),
          son avoir à la même minute, la part QR (2 h 30), le remboursement Stripe
          (1 h 40) ;
        - annulées, sans numéro (2) : la demande QR jamais payée, le paiement expiré ;
        - en attente (1) : le paiement en cours commandé il y a 10 jours.
        / Expected: 9 settled sales, 2 cancelled, 1 pending.

        :return: un `SimpleNamespace` qui nomme chaque objet créé, et la liste
            `cles_des_ventes_reglees_dans_l_ordre_du_temps`
        """
        acheteur = creer_utilisateur()
        monnaie_fed = self._monnaie_fed_de_la_plateforme()
        monnaie_cadeau = self._creer_une_monnaie_cadeau()
        uuid_de_la_monnaie_locale = uuid.uuid4()
        tarif_du_qr = creer_tarif_vendu(
            nom="Paiement QR",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.QRCODE_MA,
        )
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="15.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        )

        # Une vente admin en espèces, et son avoir admin à la même minute : à date
        # égale, l'avoir passe après sa vente.
        # / An admin cash sale and its admin credit note at the same minute.
        ligne_admin_en_especes = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            taux_tva="20",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
            minutes_avant_la_reprise=200,
        )
        avoir_admin_en_especes = self._creer_une_ancienne_ligne(
            LigneArticle.CREDIT_NOTE,
            montant=500,
            quantite="-1",
            taux_tva="20",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
            credit_note_for=ligne_admin_en_especes,
            minutes_avant_la_reprise=200,
        )

        # Un paiement Stripe payé, et le remboursement Stripe d'un de ses billets :
        # l'origine du remboursement n'est écrite que dans `metadata`.
        # / A paid Stripe payment, and the Stripe refund of one of its tickets.
        paiement_paye = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        ligne_de_deux_billets = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="2",
            taux_tva="5.5",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_paye,
            minutes_avant_la_reprise=300,
        )
        remboursement_d_un_billet = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            taux_tva="5.5",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_paye,
            metadata={"original_lignearticle_uuid": str(ligne_de_deux_billets.uuid)},
            minutes_avant_la_reprise=100,
        )

        # Une part QR en monnaie locale, et une demande QR jamais payée.
        # / A QR part in local currency, and a QR request never paid.
        part_qr = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=600,
            quantite="0.6",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.LOCAL_EURO,
            origine=SaleOrigin.QRCODE_MA,
            metadata=json.dumps({"transactions": [{"amount": 600}]}),
            asset=uuid_de_la_monnaie_locale,
            minutes_avant_la_reprise=150,
        )
        demande_qr_jamais_payee = self._creer_une_ancienne_ligne(
            LigneArticle.CREATED,
            montant=1500,
            quantite="1",
            tarif_vendu=tarif_du_qr,
            moyen=PaymentMethod.QRCODE_MA,
            origine=SaleOrigin.QRCODE_MA,
            metadata=json.dumps({"test": "qr jamais payé"}),
            minutes_avant_la_reprise=120,
        )

        # Un paiement en cours commandé il y a 10 jours (en attente) et un paiement
        # expiré (annulé).
        # / A recent pending payment (pending sale) and an expired one (cancelled).
        paiement_en_cours_recent = self._creer_un_paiement_stripe(
            Paiement_stripe.PENDING,
            utilisateur=acheteur,
            jours_depuis_la_commande=10,
        )
        ligne_en_attente = self._creer_une_ancienne_ligne(
            LigneArticle.UNPAID,
            montant=1250,
            quantite="2",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_en_cours_recent,
            minutes_avant_la_reprise=80,
        )
        paiement_expire = self._creer_un_paiement_stripe(
            Paiement_stripe.EXPIRE, utilisateur=acheteur
        )
        ligne_expiree = self._creer_une_ancienne_ligne(
            LigneArticle.UNPAID,
            montant=900,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_expire,
            minutes_avant_la_reprise=90,
        )

        # Un paiement SEPA, et un paiement `P` dont la ligne est restée `P` (payée, pas
        # validée). Un `save()` sur cette ligne relancerait la machine à statuts
        # (`P` → `P` : envoi à l'ancien LaBoutik).
        # / A SEPA payment, and a P payment whose line stayed P: a save() on it would
        # run the status machine again.
        paiement_sepa = self._creer_un_paiement_stripe(
            Paiement_stripe.VALID, utilisateur=acheteur
        )
        ligne_sepa = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=2000,
            quantite="1",
            moyen=PaymentMethod.STRIPE_SEPA_NOFED,
            paiement_stripe=paiement_sepa,
            minutes_avant_la_reprise=260,
        )
        paiement_paye_non_valide = self._creer_un_paiement_stripe(
            Paiement_stripe.PAID, utilisateur=acheteur
        )
        ligne_payee_non_validee = self._creer_une_ancienne_ligne(
            LigneArticle.PAID,
            montant=800,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_paye_non_valide,
            minutes_avant_la_reprise=250,
        )

        # Une recharge cadeau offerte (règlement FREE) et un virement reçu (paiement T).
        # / An offered gift top-up and a received transfer.
        recharge_offerte = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1500,
            quantite="1",
            tarif_vendu=tarif_de_la_recharge_cadeau,
            moyen=PaymentMethod.FREE,
            asset=monnaie_cadeau.uuid,
            minutes_avant_la_reprise=220,
        )
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)

        cles_des_ventes_reglees_dans_l_ordre_du_temps = [
            str(paiement_de_transfert.uuid),
            str(paiement_paye.uuid),
            str(paiement_sepa.uuid),
            str(paiement_paye_non_valide.uuid),
            str(recharge_offerte.uuid),
            str(ligne_admin_en_especes.uuid),
            str(avoir_admin_en_especes.uuid),
            str(part_qr.uuid),
            str(remboursement_d_un_billet.uuid),
        ]

        return SimpleNamespace(
            acheteur=acheteur,
            monnaie_fed=monnaie_fed,
            ligne_admin_en_especes=ligne_admin_en_especes,
            avoir_admin_en_especes=avoir_admin_en_especes,
            paiement_paye=paiement_paye,
            ligne_de_deux_billets=ligne_de_deux_billets,
            remboursement_d_un_billet=remboursement_d_un_billet,
            part_qr=part_qr,
            demande_qr_jamais_payee=demande_qr_jamais_payee,
            paiement_en_cours_recent=paiement_en_cours_recent,
            ligne_en_attente=ligne_en_attente,
            paiement_expire=paiement_expire,
            ligne_expiree=ligne_expiree,
            paiement_sepa=paiement_sepa,
            ligne_sepa=ligne_sepa,
            paiement_paye_non_valide=paiement_paye_non_valide,
            ligne_payee_non_validee=ligne_payee_non_validee,
            recharge_offerte=recharge_offerte,
            paiement_de_transfert=paiement_de_transfert,
            cles_des_ventes_reglees_dans_l_ordre_du_temps=(
                cles_des_ventes_reglees_dans_l_ordre_du_temps
            ),
        )

    # ------------------------------------------------------------------
    # R-2 1. Toutes les lignes ont une vente
    # ------------------------------------------------------------------

    def test_reprise_toutes_les_lignes_ont_une_vente(self):
        """
        Après `--executer`, plus aucune ligne n'est sans vente. Chaque vente du plan est
        écrite une fois, avec la clé "reprise-<clé du groupe>", sa nature, son statut,
        son unité et son client. Chaque ancienne ligne est rattachée à la vente de son
        groupe et porte les huit montants du plan ; son statut ne change pas.
        / After --executer, no line is left without a sale; each line carries its
        group's sale and the plan's amounts; its status does not change.
        """
        self._creer_l_historique_d_un_lieu()
        plan_avant_l_ecriture = self._calculer_le_plan()
        assert plan_avant_l_ecriture.anomalies == {}
        assert len(plan_avant_l_ecriture.ventes) == 12

        self._executer_la_reprise()

        assert LigneArticle.objects.filter(vente__isnull=True).count() == 0
        assert Vente.objects.count() == 12
        for vente_a_reprendre in plan_avant_l_ecriture.ventes:
            vente_ecrite = self._vente_reprise(vente_a_reprendre.cle_du_groupe)
            assert vente_ecrite.nature == vente_a_reprendre.nature
            assert vente_ecrite.statut == vente_a_reprendre.statut
            assert vente_ecrite.unite == vente_a_reprendre.unite
            assert vente_ecrite.client == vente_a_reprendre.client
            for article in vente_a_reprendre.articles:
                if article.ligne is None:
                    continue
                ligne_relue = LigneArticle.objects.get(pk=article.ligne.pk)
                assert ligne_relue.vente_id == vente_ecrite.pk
                assert ligne_relue.status == article.ligne.status
                assert _montants_ecrits_sur_la_ligne(ligne_relue) == (
                    _montants_prevus_par_le_plan(article)
                )

    # ------------------------------------------------------------------
    # R-2 2. Les deux égalités de chaque vente
    # ------------------------------------------------------------------

    def test_reprise_egalites_tenues_pour_chaque_vente(self):
        """
        Chaque vente réglée reprise tient les deux égalités, relues en base
        (Σ règlements = Σ totaux catalogue ; Σ règlements hors offert = Σ nets), et
        ses totaux valent les sommes de ses articles. Une vente annulée ou en attente
        n'a aucun règlement (aucun argent reçu).
        / Every settled sale holds both equalities; cancelled or pending: no payment.
        """
        self._creer_l_historique_d_un_lieu()

        self._executer_la_reprise()

        ventes_reglees = Vente.objects.filter(statut=Vente.Statut.REGLEE)
        assert ventes_reglees.count() == 9
        for vente_reglee in ventes_reglees:
            verifier_egalites(vente_reglee)
        reglements_de_ventes_sans_argent = Reglement.objects.filter(
            vente__statut__in=[Vente.Statut.EN_ATTENTE, Vente.Statut.ANNULEE]
        )
        assert reglements_de_ventes_sans_argent.count() == 0

    # ------------------------------------------------------------------
    # R-2 3. Les numéros suivent l'ordre du temps, la chaîne est valide
    # ------------------------------------------------------------------

    def test_reprise_numeros_dans_l_ordre_chronologique_et_chaine_valide(self):
        """
        Les ventes réglées reprises sont numérotées 1, 2, 3… dans l'ordre du temps
        (date du plan) ; à date égale, l'avoir passe après sa vente. La chaîne des
        empreintes est valide (`verifier_chaine_ventes`), et le rapport le dit.
        / Settled sales are numbered in time order; the fingerprint chain is valid.
        """
        historique = self._creer_l_historique_d_un_lieu()

        sortie_de_la_commande = self._executer_la_reprise()

        ventes_reglees_par_numero = list(
            Vente.objects.filter(statut=Vente.Statut.REGLEE).order_by("numero")
        )
        numeros = []
        cles_des_ventes = []
        for vente_reglee in ventes_reglees_par_numero:
            numeros.append(vente_reglee.numero)
            cles_des_ventes.append(
                vente_reglee.idempotency_key.removeprefix(PREFIXE_DE_LA_CLE_DE_REPRISE)
            )
        assert numeros == [1, 2, 3, 4, 5, 6, 7, 8, 9]
        assert cles_des_ventes == (
            historique.cles_des_ventes_reglees_dans_l_ordre_du_temps
        )
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []
        assert RAPPORT_CHAINE_VALIDE in sortie_de_la_commande
        assert f"{RAPPORT_VENTES_ECRITES}12" in sortie_de_la_commande

    # ------------------------------------------------------------------
    # R-2 4. La date d'origine est gardée
    # ------------------------------------------------------------------

    def test_reprise_date_d_origine_gardee_sur_vente_et_reglements(self):
        """
        Chaque vente reprise porte la date du plan, jamais « maintenant » : date de
        création (toutes les ventes), date d'encaissement (ventes réglées, elle est dans
        l'empreinte), date de chaque règlement. L'article « virement reçu » créé par la
        reprise porte la date du transfert.
        / Every sale keeps the plan date: creation, settlement, each payment; the
        received transfer item keeps the transfer date.
        """
        historique = self._creer_l_historique_d_un_lieu()
        plan_avant_l_ecriture = self._calculer_le_plan()

        self._executer_la_reprise()

        for vente_a_reprendre in plan_avant_l_ecriture.ventes:
            date_du_plan = vente_a_reprendre.datetime_de_la_vente
            vente_ecrite = self._vente_reprise(vente_a_reprendre.cle_du_groupe)
            assert vente_ecrite.datetime_creation == date_du_plan
            if vente_ecrite.statut == Vente.Statut.REGLEE:
                assert vente_ecrite.datetime_encaissement == date_du_plan
            for reglement in Reglement.objects.filter(vente=vente_ecrite):
                assert reglement.datetime == date_du_plan

        vente_du_virement = self._vente_reprise(historique.paiement_de_transfert.uuid)
        article_du_virement = LigneArticle.objects.get(vente=vente_du_virement)
        assert article_du_virement.datetime == DATE_DU_TRANSFERT

    # ------------------------------------------------------------------
    # R-2 5. L'avoir est lié à sa vente d'origine
    # ------------------------------------------------------------------

    def test_reprise_avoir_lie_a_la_vente_d_origine_et_credit_note_for_pose(self):
        """
        Une vente AVOIR reprise est liée (`vente_liee`) à la vente de sa ligne
        d'origine, écrite plus tôt dans l'ordre du plan. Un remboursement Stripe, dont
        l'origine n'était écrite que dans `metadata`, reçoit aussi `credit_note_for` :
        sinon un avoir fait après la bascule pourrait rembourser deux fois. Un avoir
        admin garde son `credit_note_for`. Un avoir dont l'origine est introuvable est
        repris sans vente liée.
        / A credit note is linked to its origin's sale; a refund gets credit_note_for.
        """
        historique = self._creer_l_historique_d_un_lieu()
        avoir_sans_origine = self._creer_une_ancienne_ligne(
            LigneArticle.REFUNDED,
            montant=1250,
            quantite="-1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=historique.paiement_paye,
            metadata=json.dumps({"original_lignearticle_uuid": str(uuid.uuid4())}),
            minutes_avant_la_reprise=70,
        )

        self._executer_la_reprise()

        vente_des_deux_billets = self._vente_reprise(historique.paiement_paye.uuid)
        avoir_du_remboursement = self._vente_reprise(
            historique.remboursement_d_un_billet.uuid
        )
        assert avoir_du_remboursement.nature == Vente.Nature.AVOIR
        assert avoir_du_remboursement.vente_liee == vente_des_deux_billets
        remboursement_relu = LigneArticle.objects.get(
            pk=historique.remboursement_d_un_billet.pk
        )
        assert remboursement_relu.credit_note_for_id == (
            historique.ligne_de_deux_billets.pk
        )

        vente_admin_en_especes = self._vente_reprise(
            historique.ligne_admin_en_especes.uuid
        )
        avoir_de_l_admin = self._vente_reprise(historique.avoir_admin_en_especes.uuid)
        assert avoir_de_l_admin.vente_liee == vente_admin_en_especes
        avoir_admin_relu = LigneArticle.objects.get(
            pk=historique.avoir_admin_en_especes.pk
        )
        assert avoir_admin_relu.credit_note_for_id == (
            historique.ligne_admin_en_especes.pk
        )

        avoir_sans_origine_ecrit = self._vente_reprise(avoir_sans_origine.uuid)
        assert avoir_sans_origine_ecrit.nature == Vente.Nature.AVOIR
        assert avoir_sans_origine_ecrit.vente_liee is None
        avoir_sans_origine_relu = LigneArticle.objects.get(pk=avoir_sans_origine.pk)
        assert avoir_sans_origine_relu.credit_note_for_id is None

    # ------------------------------------------------------------------
    # R-2 6. L'avoir Stripe est marqué « reprise »
    # ------------------------------------------------------------------

    def test_reprise_avoir_stripe_reference_reprise(self):
        """
        Le règlement d'un ancien avoir relié à un paiement Stripe est négatif, au
        moyen Stripe, relié au paiement, avec la référence « reprise » (Q-R6) : le
        rapport ne le compte pas « remboursement Stripe à faire à la main ». Un avoir
        hors Stripe (espèces) a une référence vide.
        / A Stripe credit note's payment has the "reprise" reference; off Stripe: empty.
        """
        historique = self._creer_l_historique_d_un_lieu()

        self._executer_la_reprise()

        avoir_du_remboursement = self._vente_reprise(
            historique.remboursement_d_un_billet.uuid
        )
        assert _reglements_ecrits(avoir_du_remboursement) == [
            (PaymentMethod.STRIPE_NOFED, -1250, historique.paiement_paye, "reprise"),
        ]
        avoir_de_l_admin = self._vente_reprise(historique.avoir_admin_en_especes.uuid)
        assert _reglements_ecrits(avoir_de_l_admin) == [
            (PaymentMethod.CASH, -500, None, ""),
        ]

    # ------------------------------------------------------------------
    # R-2 7. Le paiement Stripe reçoit sa vente, son moyen et son montant encaissé
    # ------------------------------------------------------------------

    def test_reprise_paiement_stripe_moyen_et_montant_encaisse_poses(self):
        """
        Chaque paiement Stripe repris est relié à sa vente d'origine
        (`Paiement_stripe.vente`). Un paiement payé reçoit son moyen (B-3 : `SP` si une
        ligne est en SEPA, sinon `SN`) et son montant encaissé (Q-R4 : total d'origine
        des articles, avoirs non déduits). Un paiement en attente ou expiré garde son
        moyen et son montant encaissé : le webhook les posera.
        / Each Stripe payment gets its sale; a paid one gets its method and amount.
        """
        historique = self._creer_l_historique_d_un_lieu()

        self._executer_la_reprise()

        paiements_payes_attendus = [
            (historique.paiement_paye, PaymentMethod.STRIPE_NOFED, 2500),
            (historique.paiement_sepa, PaymentMethod.STRIPE_SEPA_NOFED, 2000),
            (historique.paiement_paye_non_valide, PaymentMethod.STRIPE_NOFED, 800),
        ]
        for paiement, moyen_attendu, montant_encaisse_attendu in (
            paiements_payes_attendus
        ):
            paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
            assert paiement_relu.vente == self._vente_reprise(paiement.uuid)
            assert paiement_relu.moyen == moyen_attendu
            assert paiement_relu.montant_encaisse == montant_encaisse_attendu

        # La vente prend l'origine de ses anciennes lignes : ici, « en ligne ».
        # / The sale takes its old lines' origin: here, online.
        vente_du_paiement_paye = self._vente_reprise(historique.paiement_paye.uuid)
        assert vente_du_paiement_paye.origine == SaleOrigin.LESPASS

        paiements_sans_argent_recu = [
            historique.paiement_en_cours_recent,
            historique.paiement_expire,
        ]
        for paiement in paiements_sans_argent_recu:
            paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
            assert paiement_relu.vente == self._vente_reprise(paiement.uuid)
            assert paiement_relu.moyen == paiement.moyen
            assert paiement_relu.montant_encaisse == paiement.montant_encaisse

    # ------------------------------------------------------------------
    # R-2 8. Une vente en attente est encaissée par le webhook, sans écart
    # ------------------------------------------------------------------

    def test_reprise_vente_en_attente_encaissee_par_le_webhook_sans_ecart(self):
        """
        Après la reprise, le webhook Stripe d'un paiement en cours encaisse sa vente
        en attente (`encaisser_vente_stripe`) : ses lignes portent déjà leurs montants
        (I-5), donc aucun article « écart d'encaissement » n'est ajouté. La vente est
        réglée, numérotée après les ventes reprises, et la chaîne reste valide.
        / After the takeover, the Stripe webhook settles the pending sale with no gap.
        """
        historique = self._creer_l_historique_d_un_lieu()
        self._executer_la_reprise()

        # Le webhook pose le montant reçu et le moyen sur le paiement, puis encaisse.
        # / The webhook sets the received amount and the method, then settles.
        paiement_en_cours = Paiement_stripe.objects.get(
            pk=historique.paiement_en_cours_recent.pk
        )
        paiement_en_cours.montant_encaisse = 2500
        paiement_en_cours.moyen = PaymentMethod.STRIPE_NOFED
        vente_encaissee = encaisser_vente_stripe(paiement_en_cours)

        assert vente_encaissee == self._vente_reprise(paiement_en_cours.uuid)
        assert vente_encaissee.statut == Vente.Statut.REGLEE
        assert vente_encaissee.numero == 10
        articles_de_la_vente = list(LigneArticle.objects.filter(vente=vente_encaissee))
        assert articles_de_la_vente == [historique.ligne_en_attente]
        assert _reglements_ecrits(vente_encaissee) == [
            (PaymentMethod.STRIPE_NOFED, 2500, paiement_en_cours, ""),
        ]
        verifier_egalites(vente_encaissee)
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []

    # ------------------------------------------------------------------
    # R-2 9. Rien ne part : ni tâche, ni réseau, ni mail
    # ------------------------------------------------------------------

    def test_reprise_ne_declenche_ni_mail_ni_fedow_ni_laboutik(self):
        """
        L'écriture ne demande aucune tâche Celery (ni mail, ni envoi à l'ancien
        LaBoutik), même après la validation de la transaction ; elle ne fait aucun
        appel réseau (ni Stripe, ni Fedow) et n'envoie aucun mail. L'historique
        contient une ligne `P` : un `save()` sur elle relancerait la machine à statuts.
        / Writing requests no Celery task, makes no network call and sends no mail.
        """
        self._creer_l_historique_d_un_lieu()

        appels_reseau_tentes = []
        mails_envoyes = []

        def appel_reseau_interdit(*arguments, **arguments_nommes):
            appels_reseau_tentes.append(arguments)
            raise AssertionError("Appel réseau interdit pendant la reprise.")

        def mail_interdit(courriel, *arguments, **arguments_nommes):
            mails_envoyes.append(courriel.subject)
            return 0

        with (
            taches_celery_enregistrees() as taches_demandees,
            mock.patch(
                "requests.sessions.Session.request",
                autospec=True,
                side_effect=appel_reseau_interdit,
            ),
            mock.patch(
                "fedow_connect.fedow_api._post", side_effect=appel_reseau_interdit
            ),
            mock.patch(
                "fedow_connect.fedow_api._get", side_effect=appel_reseau_interdit
            ),
            mock.patch(
                "django.core.mail.message.EmailMessage.send",
                autospec=True,
                side_effect=mail_interdit,
            ),
        ):
            # Les tâches demandées « après validation » (`on_commit`) partent ici.
            # / Tasks requested "on commit" run here.
            with self.captureOnCommitCallbacks(execute=True):
                self._executer_la_reprise()

        # L'écriture a bien eu lieu : sinon ce test ne prouverait rien.
        # / The writing did happen: otherwise this test would prove nothing.
        assert Vente.objects.count() == 12
        assert noms_des_taches(taches_demandees) == []
        assert appels_reseau_tentes == []
        assert mails_envoyes == []

    # ------------------------------------------------------------------
    # R-2 10. Rejouer la reprise ne double rien
    # ------------------------------------------------------------------

    def test_reprise_rejouee_ne_double_rien(self):
        """
        Le même plan écrit deux fois : la seconde fois, chaque vente déjà reprise
        (même clé "reprise-<clé>") est sautée ; aucune vente, aucun règlement, aucun
        numéro de plus. Relancer la commande ensuite ne trouve plus rien à écrire.
        / The same plan written twice: the second time every sale is skipped.
        """
        self._creer_l_historique_d_un_lieu()
        plan = self._calculer_le_plan()

        premier_resultat = self._ecrire_le_plan(plan)
        assert premier_resultat.nombre_de_ventes_ecrites == 12
        assert premier_resultat.nombre_de_ventes_sautees == 0
        nombre_de_ventes_apres_la_premiere_ecriture = Vente.objects.count()
        nombre_de_reglements_apres_la_premiere_ecriture = Reglement.objects.count()
        nombre_d_articles_apres_la_premiere_ecriture = LigneArticle.objects.count()

        second_resultat = self._ecrire_le_plan(plan)

        assert second_resultat.nombre_de_ventes_ecrites == 0
        assert second_resultat.nombre_de_ventes_sautees == 12
        assert second_resultat.chaine_valide is True
        assert Vente.objects.count() == nombre_de_ventes_apres_la_premiere_ecriture
        assert Reglement.objects.count() == (
            nombre_de_reglements_apres_la_premiere_ecriture
        )
        assert LigneArticle.objects.count() == (
            nombre_d_articles_apres_la_premiere_ecriture
        )

        self._executer_la_reprise()

        assert Vente.objects.count() == nombre_de_ventes_apres_la_premiere_ecriture
        assert Vente.objects.filter(statut=Vente.Statut.REGLEE).count() == 9
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []

    # ------------------------------------------------------------------
    # R-2 11. Un lieu qui a déjà vendu avec le nouveau code est refusé
    # ------------------------------------------------------------------

    def test_reprise_refusee_si_le_lieu_a_deja_une_vente_hors_reprise(self):
        """
        Un lieu qui a déjà une vente réglée hors reprise (une vente du nouveau code,
        sans clé "reprise-") est refusé : les ventes reprises prendraient des numéros
        après elle, hors de l'ordre du temps. Rien n'est écrit (ni vente, ni règlement,
        ni produit, ni lien sur un paiement) et le rapport le dit.
        / A venue that already has a settled non-takeover sale is refused; nothing written.
        """
        fabriquer_vente_encaissee(
            origine=SaleOrigin.ADMIN,
            articles=[
                {
                    "pricesold": self.billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1250,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 1250}],
        )
        ancienne_ligne = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )
        self._monnaie_fed_de_la_plateforme()
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)
        nombre_de_ventes_avant = Vente.objects.count()
        nombre_de_reglements_avant = Reglement.objects.count()
        nombre_de_produits_avant = Product.objects.count()

        sortie_de_la_commande = self._executer_la_reprise()

        assert MESSAGE_DU_LIEU_DEJA_VENDU in sortie_de_la_commande
        assert Vente.objects.count() == nombre_de_ventes_avant
        assert Reglement.objects.count() == nombre_de_reglements_avant
        assert Product.objects.count() == nombre_de_produits_avant
        assert LigneArticle.objects.get(pk=ancienne_ligne.pk).vente_id is None
        assert Paiement_stripe.objects.get(pk=paiement_de_transfert.pk).vente_id is None

    # ------------------------------------------------------------------
    # R-2 12. Un groupe en anomalie n'est pas écrit, le reste l'est
    # ------------------------------------------------------------------

    def test_reprise_groupe_en_anomalie_non_ecrit_le_reste_ecrit(self):
        """
        Un groupe en anomalie (paiement Stripe `S`, forme non prévue) n'est pas dans le
        plan : ses lignes restent sans vente et sans montants, son paiement sans vente.
        Le reste du lieu est écrit, et la chaîne est valide.
        / A group in anomaly is not written; the rest of the venue is.
        """
        paiement_d_une_forme_non_prevue = self._creer_un_paiement_stripe(
            Paiement_stripe.NOTSYNC
        )
        ligne_en_anomalie = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=1250,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_d_une_forme_non_prevue,
        )
        paiement_ordinaire = self._creer_un_paiement_stripe(Paiement_stripe.VALID)
        ligne_ordinaire = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=900,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_ordinaire,
        )

        self._executer_la_reprise()

        ligne_en_anomalie_relue = LigneArticle.objects.get(pk=ligne_en_anomalie.pk)
        assert ligne_en_anomalie_relue.vente_id is None
        assert ligne_en_anomalie_relue.total_catalogue == 0
        assert ligne_en_anomalie_relue.total_ttc == 0
        paiement_en_anomalie_relu = Paiement_stripe.objects.get(
            pk=paiement_d_une_forme_non_prevue.pk
        )
        assert paiement_en_anomalie_relu.vente_id is None

        vente_ordinaire = self._vente_reprise(paiement_ordinaire.uuid)
        assert vente_ordinaire.statut == Vente.Statut.REGLEE
        assert vente_ordinaire.numero == 1
        assert LigneArticle.objects.get(pk=ligne_ordinaire.pk).vente == (
            vente_ordinaire
        )
        assert Vente.objects.count() == 1
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []

    # ------------------------------------------------------------------
    # R-2 13. Les lignes jamais payées : vente annulée, sans numéro
    # ------------------------------------------------------------------

    def test_reprise_lignes_jamais_payees_vente_annulee_sans_numero(self):
        """
        Une demande QR jamais payée, un paiement expiré, un paiement en cours trop
        vieux (40 jours) : leurs ventes sont ANNULEE, sans numéro, sans heure
        d'encaissement, sans règlement. Leurs lignes reçoivent quand même leur vente et
        leurs montants (I-5). Elles ne prennent aucun numéro : la vente réglée du lieu
        reste la n° 1.
        / Never-paid lines: cancelled sales, no number, no payment; lines still get
        their sale and amounts.
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
            minutes_avant_la_reprise=300,
        )
        paiement_expire = self._creer_un_paiement_stripe(Paiement_stripe.EXPIRE)
        ligne_expiree = self._creer_une_ancienne_ligne(
            LigneArticle.UNPAID,
            montant=900,
            quantite="1",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_expire,
            minutes_avant_la_reprise=200,
        )
        paiement_en_cours_trop_vieux = self._creer_un_paiement_stripe(
            Paiement_stripe.PENDING, jours_depuis_la_commande=40
        )
        ligne_trop_vieille = self._creer_une_ancienne_ligne(
            LigneArticle.UNPAID,
            montant=1250,
            quantite="2",
            moyen=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement_en_cours_trop_vieux,
            minutes_avant_la_reprise=150,
        )
        ligne_admin_en_especes = self._creer_une_ancienne_ligne(
            LigneArticle.VALID,
            montant=500,
            quantite="1",
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
            minutes_avant_la_reprise=100,
        )

        self._executer_la_reprise()

        lignes_et_totaux_attendus = [
            (demande_qr_jamais_payee, str(demande_qr_jamais_payee.uuid), 1500),
            (ligne_expiree, str(paiement_expire.uuid), 900),
            (ligne_trop_vieille, str(paiement_en_cours_trop_vieux.uuid), 2500),
        ]
        for ligne, cle_du_groupe, total_attendu in lignes_et_totaux_attendus:
            vente_annulee = self._vente_reprise(cle_du_groupe)
            assert vente_annulee.statut == Vente.Statut.ANNULEE
            assert vente_annulee.numero is None
            assert vente_annulee.datetime_encaissement is None
            assert Reglement.objects.filter(vente=vente_annulee).count() == 0
            ligne_relue = LigneArticle.objects.get(pk=ligne.pk)
            assert ligne_relue.vente == vente_annulee
            assert ligne_relue.total_catalogue == total_attendu
            assert ligne_relue.total_ttc == total_attendu

        vente_admin = self._vente_reprise(ligne_admin_en_especes.uuid)
        assert vente_admin.statut == Vente.Statut.REGLEE
        assert vente_admin.numero == 1

    # ------------------------------------------------------------------
    # R-2 14. `encaisser_vente` sans date : maintenant, comme aujourd'hui
    # ------------------------------------------------------------------

    def test_encaisser_vente_sans_date_garde_maintenant(self):
        """
        Caractérisation de l'appel d'aujourd'hui : `encaisser_vente(vente)` sans date
        pose l'heure d'encaissement à « maintenant » (entre l'avant et l'après de
        l'appel), et l'empreinte est valide. Le paramètre ajouté pour la reprise ne
        change rien aux ventes d'aujourd'hui.
        / Today's call: no date means "now", and the fingerprint is valid.
        """
        moment_avant_l_encaissement = timezone.now()

        vente_encaissee = fabriquer_vente_encaissee(
            origine=SaleOrigin.ADMIN,
            articles=[
                {
                    "pricesold": self.billet,
                    "quantite": Decimal("2"),
                    "prix_unitaire": 1250,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2500}],
        )

        moment_apres_l_encaissement = timezone.now()
        vente_relue = Vente.objects.get(pk=vente_encaissee.pk)
        assert vente_relue.statut == Vente.Statut.REGLEE
        assert vente_relue.numero == 1
        assert moment_avant_l_encaissement <= vente_relue.datetime_encaissement
        assert vente_relue.datetime_encaissement <= moment_apres_l_encaissement
        verifier_egalites(vente_relue)
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []

    # ------------------------------------------------------------------
    # R-2 15. Le virement reçu : vente VR, règlement SN, paiement relié
    # ------------------------------------------------------------------

    def test_reprise_virement_recu_ecrit_vente_vr_reglement_sn_et_paiement_relie(
        self,
    ):
        """
        Un paiement `T` devient une vente réglée « virement reçu » (QO-9, option B) :
        un seul article, créé par la reprise, du produit système « virement reçu »
        (`VR`) : quantité 1, montant du transfert, TVA 0, hors chiffre d'affaires,
        monnaie FED, ligne validée. Un règlement Stripe en ligne (`SN`) du même montant,
        relié au paiement `T`, sans référence. Le paiement reçoit sa vente, le moyen
        `SN` et son montant encaissé. Vente et règlement sont à la date du transfert.
        / A T payment becomes a settled "transfer received" sale with one SN payment.
        """
        monnaie_fed = self._monnaie_fed_de_la_plateforme()
        paiement_de_transfert = self._creer_un_paiement_de_transfert(4200)

        self._executer_la_reprise()

        vente_du_virement = self._vente_reprise(paiement_de_transfert.uuid)
        assert vente_du_virement.nature == Vente.Nature.VENTE
        assert vente_du_virement.statut == Vente.Statut.REGLEE
        assert vente_du_virement.numero == 1
        assert vente_du_virement.datetime_encaissement == DATE_DU_TRANSFERT
        # Le webhook Stripe `transfer.created` a produit ce virement.
        # / The Stripe transfer.created webhook produced this transfer.
        assert vente_du_virement.origine == SaleOrigin.WEBHOOK

        articles_du_virement = list(
            LigneArticle.objects.filter(vente=vente_du_virement).select_related(
                "pricesold__productsold__product"
            )
        )
        assert len(articles_du_virement) == 1
        article_du_virement = articles_du_virement[0]
        produit_du_virement = article_du_virement.pricesold.productsold.product
        assert produit_du_virement.methode_caisse == Product.VIREMENT_RECU
        assert article_du_virement.qty == 1
        assert article_du_virement.amount == 4200
        assert article_du_virement.vat == 0
        assert article_du_virement.asset == monnaie_fed.uuid
        assert article_du_virement.status == LigneArticle.VALID
        # Pas de moyen sur l'article : c'est le règlement `SN` qui le porte.
        # / No method on the item: the SN payment carries it.
        assert article_du_virement.payment_method is None
        assert article_du_virement.hors_chiffre_affaires is True
        assert _montants_ecrits_sur_la_ligne(article_du_virement) == {
            "total_catalogue": 4200,
            "part_offerte": 0,
            "source_offert": "",
            "part_en_jetons": 0,
            "total_ttc": 4200,
            "total_ht": 4200,
            "total_tva": 0,
            "hors_chiffre_affaires": True,
        }

        assert _reglements_ecrits(vente_du_virement) == [
            (PaymentMethod.STRIPE_NOFED, 4200, paiement_de_transfert, ""),
        ]
        paiement_relu = Paiement_stripe.objects.get(pk=paiement_de_transfert.pk)
        assert paiement_relu.vente == vente_du_virement
        assert paiement_relu.moyen == PaymentMethod.STRIPE_NOFED
        assert paiement_relu.montant_encaisse == 4200
        verifier_egalites(vente_du_virement)
        assert verifier_chaine_ventes(self._cle_de_l_empreinte_du_lieu()) == []

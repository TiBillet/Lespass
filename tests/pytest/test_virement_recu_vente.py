"""
tests/pytest/test_virement_recu_vente.py
La vente « virement reçu » : sa fabrique et la commande de rattrapage.
/ The "transfer received" sale: its factory and the catch-up command.

LOCALISATION : tests/pytest/test_virement_recu_vente.py

LE BESOIN
Quand la plateforme vire de vrais euros (monnaie fédérée FED) au compte Stripe Connect
d'un lieu, le webhook Stripe `transfer.created` crée un `Paiement_stripe` de source `T`,
validé. Ce virement est une vente « virement reçu » : un article `VR` et un règlement
Stripe en ligne (`SN`). Une seule fabrique l'écrit, pour le webhook, la reprise et la
commande de rattrapage.
/ A Stripe transfer to the venue is a "transfer received" sale: one VR item and one SN
payment. A single factory writes it.

CE QUE LES TESTS LISENT
- La fabrique : `ecrire_la_vente_d_un_virement_recu(paiement_stripe, montant_en_centimes,
  cle_d_idempotence, datetime_encaissement=None)` (BaseBillet/services_vente.py). Elle rend
  la vente écrite, ou la vente qui porte déjà cette clé.
- La commande : `rattraper_les_virements_recus --schema <lieu> [--executer]`
  (comptabilite/management/commands/). À blanc par défaut. Chaque vente écrite porte la
  clé `virement-recu-<uuid du paiement>`. Son rapport affiche, par lieu puis au total,
  des lignes « libellé : valeur » (constantes `RAPPORT_*` ci-dessous). Les montants sont
  en euros, avec deux décimales et un point : « Montant : 1893.00 € ».
/ The factory returns the written sale (or the one already holding the key). The command
is a dry run by default; its report shows "label : value" lines.

LA DATE D'UNE VENTE RATTRAPÉE (décision du mainteneur, 2026-10-12)
Le `created` du transfert s'il est APRÈS la fin de la dernière clôture du lieu, tous
niveaux confondus (`comptabilite.models.ClotureCaisse`, J, H, M ou A : le plus grand
`datetime_fin`). Sinon « maintenant », et le rapport compte ce cas (« période close »).
Une vente datée dans une période déjà clôturée n'entre dans aucune clôture J.
/ The transfer date if after the end of the last closure (any level), else "now".

ISOLATION
Chaque test est `django_db` : sa transaction est annulée à la fin (tests/PIEGES.md 13.1).
Une vente encaissée est scellée : sans ce rollback, elle resterait dans la base de dev.
Les tests tournent dans le lieu `lespass` de la base de dev. La commande est toujours
lancée avec `--schema lespass`, jamais sur tous les lieux. Les comptes du rapport
supposent que `lespass` n'a aucun paiement `T` à rattraper avant le test : la fixture
`lieu_sans_virement_a_rattraper` le vérifie et fait échouer le test avec un message clair
sinon.
/ Every test is rolled back. The command always runs on `lespass` only.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-VR-1.md

Lancer / Run :
    make test ARGS="tests/pytest/test_virement_recu_vente.py"
"""

import io
import json
import uuid as uuid_module
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import ecrire_la_vente_d_un_virement_recu
from comptabilite.models import ClotureCaisse
from Customers.models import Client as TenantClient
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_public.models import AssetFedowPublic
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration

pytestmark = pytest.mark.django_db

# Le lieu des tests, dans la base de dev. / The test venue, in the dev database.
SCHEMA_DU_LIEU = "lespass"

# Le montant du cas réel de La Filature (1 893,00 €), en centimes.
# / The real La Filature case amount, in cents.
MONTANT_DU_VIREMENT = 189300

# Le début de la clé d'idempotence d'une vente « virement reçu » écrite par le webhook
# ou par le rattrapage : "virement-recu-<uuid du paiement>".
# / Idempotency key prefix of a sale written by the webhook or the catch-up.
PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU = "virement-recu-"

# Le nom de la commande de rattrapage. / The catch-up command name.
COMMANDE_DE_RATTRAPAGE = "rattraper_les_virements_recus"

# Les libellés du rapport de la commande, lus par les tests.
# / The command report labels read by the tests.
RAPPORT_PAIEMENTS_TROUVES = "Paiements trouvés : "
RAPPORT_MONTANT = "Montant : "
RAPPORT_VENTES_ECRITES = "Ventes écrites : "
RAPPORT_VENTES_DATEES_MAINTENANT = "Ventes datées maintenant (période close) : "
RAPPORT_ILLISIBLES = "Illisibles : "
RAPPORT_ERREURS = "Erreurs : "


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lieu():
    """Le lieu `lespass` de la base de dev. / The dev database `lespass` venue."""
    return TenantClient.objects.get(schema_name=SCHEMA_DU_LIEU)


@pytest.fixture
def lieu_sans_virement_a_rattraper(lieu):
    """
    Le lieu `lespass`, vérifié sans paiement à rattraper : le filtre est exactement
    celui de la commande (`T`, validé, sans vente, sans ligne). Les comptes du rapport
    ne lisent alors que les paiements créés par le test.
    / The `lespass` venue, checked with the command's exact filter.
    """
    with tenant_context(lieu):
        nombre_de_virements_deja_a_rattraper = Paiement_stripe.objects.filter(
            source=Paiement_stripe.TRANSFERT,
            status=Paiement_stripe.VALID,
            vente__isnull=True,
            lignearticles__isnull=True,
        ).count()
    if nombre_de_virements_deja_a_rattraper > 0:
        pytest.fail(
            f"Le lieu {SCHEMA_DU_LIEU} de la base de dev a déjà "
            f"{nombre_de_virements_deja_a_rattraper} paiement(s) T sans vente : les "
            f"comptes du rapport seraient faux. Les rattraper (ou refaire la base) "
            f"avant de lancer ces tests."
        )
    return lieu


# ---------------------------------------------------------------------------
# Assistants / Helpers
# ---------------------------------------------------------------------------


def _date_a_la_seconde(decalage_dans_le_passe):
    """
    Un moment passé, sans microsecondes : le `created` d'un transfert Stripe est un
    horodatage Unix à la seconde.
    / A past moment without microseconds: Stripe's `created` is a Unix timestamp.
    """
    moment = timezone.now() - decalage_dans_le_passe
    return moment.replace(microsecond=0)


def _monnaie_fed():
    """
    La monnaie fédérée (FED) de `fedow_public`, unique en base. Le test échoue avec un
    message clair si la base de dev ne l'a pas.
    / The federated currency (FED), unique; fails clearly if missing.
    """
    monnaie_fed = AssetFedowPublic.objects.filter(
        category=AssetFedowPublic.STRIPE_FED_FIAT
    ).first()
    if monnaie_fed is None:
        pytest.fail("La base de dev n'a pas de monnaie FED (STRIPE_FED_FIAT).")
    return monnaie_fed


def _creer_un_paiement_de_virement(
    montant_en_centimes,
    date_du_transfert,
    statut=Paiement_stripe.VALID,
):
    """
    Un paiement `T` tel que le webhook `transfer.created` l'écrit (ApiBillet/views.py) :
    le message de Stripe est rangé en TEXTE JSON dans `metadata_stripe`. Le montant et
    la date du transfert ne sont que là. Appelé dans le `tenant_context` du lieu.
    / A T payment as the webhook writes it: amount and date only in metadata_stripe.
    """
    message_de_stripe = {
        "id": f"evt_TEST_{uuid_module.uuid4().hex[:12]}",
        "type": "transfer.created",
        "data": {
            "object": {
                "id": f"tr_TEST_{uuid_module.uuid4().hex[:16]}",
                "object": "transfer",
                "amount": montant_en_centimes,
                "currency": "eur",
                "destination": "acct_TEST_rattrapage",
                "created": int(date_du_transfert.timestamp()),
                "metadata": {},
            },
        },
        "fedow_transaction_hash": uuid_module.uuid4().hex,
        "fedow_transaction_uuid": str(uuid_module.uuid4()),
    }
    return Paiement_stripe.objects.create(
        detail="Versement de monnaie globale",
        payment_intent_id=message_de_stripe["data"]["object"]["id"],
        metadata_stripe=json.dumps(message_de_stripe),
        status=statut,
        source=Paiement_stripe.TRANSFERT,
        source_traitement=Paiement_stripe.WEBHOOK,
    )


def _creer_une_cloture(niveau, debut, fin):
    """
    Une clôture du lieu (`comptabilite`), avec le numéro suivant du compteur global.
    Seules ses dates comptent pour le rattrapage. Appelé dans le `tenant_context`.
    / A venue closure with the next global number. Only its dates matter here.
    """
    derniere_cloture_par_numero = ClotureCaisse.objects.order_by(
        "-numero_sequentiel"
    ).first()
    numero_suivant = 1
    if derniere_cloture_par_numero is not None:
        numero_suivant = derniere_cloture_par_numero.numero_sequentiel + 1
    return ClotureCaisse.objects.create(
        niveau=niveau,
        numero_sequentiel=numero_suivant,
        datetime_debut=debut,
        datetime_fin=fin,
    )


def _date_du_transfert_apres_les_clotures_existantes():
    """
    La date d'un transfert de test : il y a un jour, ou une seconde après la fin de la
    dernière clôture DÉJÀ en base si elle est plus tardive. La base de dev reçoit des
    clôtures J automatiques (filet horaire), parfois dans les dernières 24 heures : un
    transfert placé avant leur fin serait déjà en période close, et le test ne vérifierait
    plus que ses propres clôtures. Sans microsecondes : le `created` d'un transfert
    Stripe est à la seconde. Appelé dans le `tenant_context`.
    / A test transfer date after every closure already in the dev database.
    """
    date_du_transfert = _date_a_la_seconde(timedelta(days=1))
    fin_de_la_derniere_cloture_existante = (
        ClotureCaisse.objects.order_by("-datetime_fin")
        .values_list("datetime_fin", flat=True)
        .first()
    )
    if fin_de_la_derniere_cloture_existante is not None:
        date_juste_apres_la_derniere_cloture = (
            fin_de_la_derniere_cloture_existante + timedelta(seconds=1)
        ).replace(microsecond=0)
        if date_juste_apres_la_derniere_cloture > date_du_transfert:
            date_du_transfert = date_juste_apres_la_derniere_cloture
    return date_du_transfert


def _cle_du_virement(paiement):
    """La clé d'idempotence attendue pour ce paiement. / The expected key."""
    return f"{PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU}{paiement.uuid}"


def _lancer_le_rattrapage(executer):
    """
    Lance la commande de rattrapage sur le seul lieu `lespass` et rend tout ce qu'elle
    affiche (sortie et erreurs).
    / Runs the catch-up command on `lespass` only and returns its whole output.
    """
    sortie_de_la_commande = io.StringIO()
    erreurs_de_la_commande = io.StringIO()
    arguments_de_la_commande = ["--schema", SCHEMA_DU_LIEU]
    if executer:
        arguments_de_la_commande.append("--executer")
    call_command(
        COMMANDE_DE_RATTRAPAGE,
        *arguments_de_la_commande,
        stdout=sortie_de_la_commande,
        stderr=erreurs_de_la_commande,
    )
    return sortie_de_la_commande.getvalue() + erreurs_de_la_commande.getvalue()


def _le_rapport_affiche(rapport, ligne_attendue):
    """
    Vrai si une ligne du rapport, sans ses espaces autour, est exactement la ligne
    attendue. Une ligne entière : « Ventes écrites : 1 » ne doit pas trouver
    « Ventes écrites : 10 ».
    / True if a report line, stripped, is exactly the expected line.
    """
    for ligne_du_rapport in rapport.splitlines():
        if ligne_du_rapport.strip() == ligne_attendue:
            return True
    return False


def _cle_de_l_empreinte_du_lieu():
    """La clé de l'empreinte du lieu courant. / The current venue fingerprint key."""
    return LaboutikConfiguration.get_solo().get_or_create_hmac_key()


# ---------------------------------------------------------------------------
# 1 à 4. La fabrique
# ---------------------------------------------------------------------------


def test_fabrique_ecrit_une_vente_virement_recu_reglee_et_reliee_au_paiement(lieu):
    """
    La fabrique écrit une vente réglée « virement reçu » :
    - un seul article, du produit système `VR` : quantité 1, prix = montant, TVA 0,
      hors chiffre d'affaires, monnaie FED, ligne validée, sans moyen ;
    - un seul règlement Stripe en ligne (`SN`) du montant, relié au paiement ;
    - origine webhook Stripe (`WK`), nature VENTE, unité EUR ;
    - le paiement reçoit sa vente, le moyen `SN` et son montant encaissé.
    Sans date, la vente est encaissée « maintenant ».
    / The factory writes a settled VR sale with one SN payment, linked to the payment.
    """
    with tenant_context(lieu):
        monnaie_fed = _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        cle_de_la_vente = _cle_du_virement(paiement)

        moment_avant_l_appel = timezone.now()
        vente_rendue = ecrire_la_vente_d_un_virement_recu(
            paiement, MONTANT_DU_VIREMENT, cle_de_la_vente
        )
        moment_apres_l_appel = timezone.now()

        vente = Vente.objects.get(idempotency_key=cle_de_la_vente)
        assert vente_rendue.pk == vente.pk
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.nature == Vente.Nature.VENTE
        assert vente.origine == SaleOrigin.WEBHOOK
        assert vente.unite == "EUR"
        assert moment_avant_l_appel <= vente.datetime_encaissement
        assert vente.datetime_encaissement <= moment_apres_l_appel

        articles_de_la_vente = list(
            LigneArticle.objects.filter(vente=vente).select_related(
                "pricesold__productsold__product"
            )
        )
        assert len(articles_de_la_vente) == 1
        article_du_virement = articles_de_la_vente[0]
        produit_du_virement = article_du_virement.pricesold.productsold.product
        assert produit_du_virement.methode_caisse == Product.VIREMENT_RECU
        assert article_du_virement.qty == 1
        assert article_du_virement.amount == MONTANT_DU_VIREMENT
        assert article_du_virement.vat == 0
        assert article_du_virement.hors_chiffre_affaires is True
        assert article_du_virement.asset == monnaie_fed.uuid
        assert article_du_virement.status == LigneArticle.VALID
        # Pas de moyen sur l'article : c'est le règlement `SN` qui le porte.
        # / No method on the item: the SN payment carries it.
        assert article_du_virement.payment_method is None

        reglements_de_la_vente = list(Reglement.objects.filter(vente=vente))
        assert len(reglements_de_la_vente) == 1
        reglement_du_virement = reglements_de_la_vente[0]
        assert reglement_du_virement.moyen == PaymentMethod.STRIPE_NOFED
        assert reglement_du_virement.montant == MONTANT_DU_VIREMENT
        assert reglement_du_virement.paiement_stripe_id == paiement.pk

        paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
        assert paiement_relu.vente_id == vente.pk
        assert paiement_relu.moyen == PaymentMethod.STRIPE_NOFED
        assert paiement_relu.montant_encaisse == MONTANT_DU_VIREMENT

        verifier_egalites(vente)


def test_fabrique_avec_une_date_pose_cette_date_sur_vente_article_et_reglement(lieu):
    """
    Avec une date d'encaissement, la vente est encaissée à cette date. Sa date de
    création, la date de son article et celle de son règlement sont aussi cette date
    (champs hors de l'empreinte de la vente).
    / With a date: settlement, creation, item and payment dates are all that date.
    """
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=3))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        cle_de_la_vente = _cle_du_virement(paiement)

        ecrire_la_vente_d_un_virement_recu(
            paiement,
            MONTANT_DU_VIREMENT,
            cle_de_la_vente,
            datetime_encaissement=date_du_transfert,
        )

        vente = Vente.objects.get(idempotency_key=cle_de_la_vente)
        assert vente.datetime_encaissement == date_du_transfert
        assert vente.datetime_creation == date_du_transfert
        article_du_virement = LigneArticle.objects.get(vente=vente)
        assert article_du_virement.datetime == date_du_transfert
        reglement_du_virement = Reglement.objects.get(vente=vente)
        assert reglement_du_virement.datetime == date_du_transfert


def test_fabrique_appelee_deux_fois_avec_la_meme_cle_n_ecrit_qu_une_vente(lieu):
    """
    Deux appels avec la même clé : la seconde rend la vente déjà écrite. Une seule
    vente, un seul article, un seul règlement (Stripe rejoue ses webhooks).
    / Two calls with the same key: one sale, one item, one payment.
    """
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        cle_de_la_vente = _cle_du_virement(paiement)

        premiere_vente = ecrire_la_vente_d_un_virement_recu(
            paiement, MONTANT_DU_VIREMENT, cle_de_la_vente
        )
        seconde_vente = ecrire_la_vente_d_un_virement_recu(
            paiement, MONTANT_DU_VIREMENT, cle_de_la_vente
        )

        assert seconde_vente.pk == premiere_vente.pk
        assert Vente.objects.filter(idempotency_key=cle_de_la_vente).count() == 1
        assert LigneArticle.objects.filter(vente=premiere_vente).count() == 1
        assert Reglement.objects.filter(paiement_stripe=paiement).count() == 1


def test_fabrique_garde_la_chaine_des_ventes_du_lieu_valide(lieu):
    """
    Après deux ventes « virement reçu » (l'une encaissée maintenant, l'autre à une date
    passée), la chaîne des ventes du lieu est valide : pas de trou de numéro, pas de
    maillon cassé, pas d'empreinte fausse, égalités tenues.
    / After two VR sales, the venue sale chain is valid.
    """
    with tenant_context(lieu):
        _monnaie_fed()
        assert verifier_chaine_ventes(_cle_de_l_empreinte_du_lieu()) == [], (
            "La chaîne des ventes du lieu est déjà invalide avant le test."
        )

        date_du_premier_transfert = _date_a_la_seconde(timedelta(days=1))
        premier_paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_premier_transfert
        )
        ecrire_la_vente_d_un_virement_recu(
            premier_paiement, MONTANT_DU_VIREMENT, _cle_du_virement(premier_paiement)
        )

        date_du_second_transfert = _date_a_la_seconde(timedelta(days=2))
        second_paiement = _creer_un_paiement_de_virement(4200, date_du_second_transfert)
        ecrire_la_vente_d_un_virement_recu(
            second_paiement,
            4200,
            _cle_du_virement(second_paiement),
            datetime_encaissement=date_du_second_transfert,
        )

        assert verifier_chaine_ventes(_cle_de_l_empreinte_du_lieu()) == []


def test_fabrique_sans_monnaie_fed_leve_une_erreur_et_n_ecrit_rien(lieu):
    """
    La monnaie FED est introuvable : la fabrique lève une erreur explicite. Rien n'est
    écrit : ni vente, ni article, ni règlement, et le paiement reste sans vente.
    La monnaie est cachée en changeant sa catégorie par `.update()` : la transaction
    du test l'annule à la fin, et aucun signal ne part.
    / No FED currency: the factory raises a clear error and writes nothing.
    """
    with tenant_context(lieu):
        _monnaie_fed()
        AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).update(category=AssetFedowPublic.TOKEN_LOCAL_FIAT)

        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        cle_de_la_vente = _cle_du_virement(paiement)
        nombre_de_ventes_avant = Vente.objects.count()
        nombre_de_lignes_avant = LigneArticle.objects.count()
        nombre_de_reglements_avant = Reglement.objects.count()

        with pytest.raises(ValueError, match="monnaie FED"):
            ecrire_la_vente_d_un_virement_recu(
                paiement, MONTANT_DU_VIREMENT, cle_de_la_vente
            )

        assert Vente.objects.count() == nombre_de_ventes_avant
        assert LigneArticle.objects.count() == nombre_de_lignes_avant
        assert Reglement.objects.count() == nombre_de_reglements_avant
        assert not Vente.objects.filter(idempotency_key=cle_de_la_vente).exists()
        paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
        assert paiement_relu.vente_id is None


def test_fabrique_qui_echoue_en_cours_d_ecriture_n_ecrit_rien(lieu):
    """
    La fabrique échoue APRÈS avoir ouvert la vente et écrit l'article (l'ajout du
    règlement est simulé en panne). Tout est annulé : aucune vente ne porte la clé,
    aucun article « virement reçu » n'est ajouté, et le paiement reste sans vente.
    C'est la transaction de la fabrique qui le garantit : une vente à moitié écrite
    resterait en attente pour toujours.
    / The factory fails after opening the sale and writing the item: everything is
    rolled back by the factory transaction.
    """
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        cle_de_la_vente = _cle_du_virement(paiement)
        articles_virement_recu = LigneArticle.objects.filter(
            pricesold__productsold__product__methode_caisse=Product.VIREMENT_RECU
        )
        nombre_d_articles_virement_recu_avant = articles_virement_recu.count()

        with mock.patch(
            "BaseBillet.services_vente.ajouter_reglement",
            side_effect=RuntimeError("panne simulée du règlement"),
        ):
            with pytest.raises(RuntimeError):
                ecrire_la_vente_d_un_virement_recu(
                    paiement, MONTANT_DU_VIREMENT, cle_de_la_vente
                )

        assert not Vente.objects.filter(idempotency_key=cle_de_la_vente).exists()
        assert articles_virement_recu.count() == nombre_d_articles_virement_recu_avant
        paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
        assert paiement_relu.vente_id is None


# ---------------------------------------------------------------------------
# 5 à 9. La commande de rattrapage
# ---------------------------------------------------------------------------


def test_rattrapage_a_blanc_n_ecrit_rien_et_compte_le_paiement_et_son_montant(
    lieu_sans_virement_a_rattraper,
):
    """
    Sans `--executer`, la commande n'écrit rien. Son rapport compte le paiement à
    rattraper et son montant, et nomme le lieu par son schéma et son domaine. Il ne
    montre rien du message de Stripe (identifiant du virement, compte destinataire).
    / Dry run by default: nothing written; the report counts the payment and amount.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        nombre_de_ventes_avant = Vente.objects.count()
        domaine_principal_du_lieu = lieu.get_primary_domain().domain

    rapport = _lancer_le_rattrapage(executer=False)

    with tenant_context(lieu):
        assert Vente.objects.count() == nombre_de_ventes_avant
        assert not Vente.objects.filter(
            idempotency_key=_cle_du_virement(paiement)
        ).exists()
        paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
        assert paiement_relu.vente_id is None

    assert _le_rapport_affiche(rapport, f"{RAPPORT_PAIEMENTS_TROUVES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_MONTANT}1893.00 €")
    assert SCHEMA_DU_LIEU in rapport
    assert domaine_principal_du_lieu in rapport
    # Aucune donnée du message de Stripe dans le rapport.
    # / No Stripe message data in the report.
    assert paiement.payment_intent_id not in rapport
    assert "acct_TEST_rattrapage" not in rapport


def test_rattrapage_executer_ecrit_la_vente_du_seul_paiement_valide_sans_vente(
    lieu_sans_virement_a_rattraper,
):
    """
    Avec `--executer`, trois paiements `T` :
    - validé, sans vente → il reçoit sa vente « virement reçu », de clé
      `virement-recu-<uuid>` ;
    - validé, qui a déjà une vente → laissé tel quel ;
    - non validé (en attente) → ignoré.
    Une seule vente est écrite.
    / With --executer, only the validated T payment without a sale gets one.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement_a_rattraper = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )

        # Un paiement `T` qui a déjà sa vente (comme ceux de la reprise).
        # / A T payment that already has its sale (like the takeover ones).
        paiement_deja_vendu = _creer_un_paiement_de_virement(500, date_du_transfert)
        tarif_vendu = creer_tarif_vendu(nom="Déjà vendu", prix_en_euros="5.00")
        vente_deja_ecrite = fabriquer_vente_encaissee(
            origine=SaleOrigin.ADMIN,
            articles=[
                {
                    "pricesold": tarif_vendu,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        Paiement_stripe.objects.filter(pk=paiement_deja_vendu.pk).update(
            vente=vente_deja_ecrite
        )

        paiement_non_valide = _creer_un_paiement_de_virement(
            700, date_du_transfert, statut=Paiement_stripe.PENDING
        )
        nombre_de_ventes_avant = Vente.objects.count()

    rapport = _lancer_le_rattrapage(executer=True)

    with tenant_context(lieu):
        vente_ecrite = Vente.objects.get(
            idempotency_key=_cle_du_virement(paiement_a_rattraper)
        )
        assert vente_ecrite.statut == Vente.Statut.REGLEE
        paiement_rattrape_relu = Paiement_stripe.objects.get(pk=paiement_a_rattraper.pk)
        assert paiement_rattrape_relu.vente_id == vente_ecrite.pk
        verifier_egalites(vente_ecrite)

        paiement_deja_vendu_relu = Paiement_stripe.objects.get(
            pk=paiement_deja_vendu.pk
        )
        assert paiement_deja_vendu_relu.vente_id == vente_deja_ecrite.pk
        assert not Vente.objects.filter(
            idempotency_key=_cle_du_virement(paiement_deja_vendu)
        ).exists()

        paiement_non_valide_relu = Paiement_stripe.objects.get(
            pk=paiement_non_valide.pk
        )
        assert paiement_non_valide_relu.vente_id is None
        assert not Vente.objects.filter(
            idempotency_key=_cle_du_virement(paiement_non_valide)
        ).exists()

        assert Vente.objects.count() == nombre_de_ventes_avant + 1
        assert verifier_chaine_ventes(_cle_de_l_empreinte_du_lieu()) == []

    assert _le_rapport_affiche(rapport, f"{RAPPORT_PAIEMENTS_TROUVES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_ECRITES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_ERREURS}0")


def test_rattrapage_transfert_apres_la_derniere_cloture_encaisse_a_la_date_du_transfert(
    lieu_sans_virement_a_rattraper,
):
    """
    La dernière clôture du lieu (une J) finit AVANT le transfert : la période du
    transfert n'est pas close. La vente est encaissée à la date du transfert, et le
    rapport ne compte aucune vente datée « maintenant ».

    Le transfert est placé après les clôtures déjà en base
    (`_date_du_transfert_apres_les_clotures_existantes`). La clôture créée par le test
    finit une seconde avant le transfert.
    / The last closure ends before the transfer: the sale is dated at the transfer.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_du_transfert_apres_les_clotures_existantes()
        _creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            debut=date_du_transfert - timedelta(days=1),
            fin=date_du_transfert - timedelta(seconds=1),
        )
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )

    rapport = _lancer_le_rattrapage(executer=True)

    with tenant_context(lieu):
        vente_ecrite = Vente.objects.get(idempotency_key=_cle_du_virement(paiement))
        assert vente_ecrite.datetime_encaissement == date_du_transfert

    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_ECRITES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_DATEES_MAINTENANT}0")


@pytest.mark.parametrize(
    "niveau_de_la_cloture_qui_couvre_le_transfert",
    [ClotureCaisse.NIVEAU_JOURNALIER, ClotureCaisse.NIVEAU_MENSUEL],
)
def test_rattrapage_transfert_dans_une_periode_close_encaisse_maintenant(
    lieu_sans_virement_a_rattraper,
    niveau_de_la_cloture_qui_couvre_le_transfert,
):
    """
    Une clôture finit APRÈS le transfert : la période du transfert est close. Une
    vente datée du transfert n'entrerait dans aucune clôture J. La vente est encaissée
    « maintenant », et le rapport la compte « période close ».

    Deux cas : la clôture qui couvre le transfert est une J, puis une M. Dans le cas M,
    la dernière J finit AVANT le transfert : seule la fin de la M le couvre. La règle
    lit la dernière clôture de TOUS les niveaux, pas seulement les J.

    Le transfert est placé après les clôtures déjà en base
    (`_date_du_transfert_apres_les_clotures_existantes`) : sinon une J du filet de dev
    couvrirait le transfert à la place de la M, et le cas M ne vérifierait plus que la
    règle lit tous les niveaux.
    / A closure ends after the transfer: the sale is settled "now", counted as closed
    period. Covered by a J, then by an M while the last J ends before the transfer.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_du_transfert_apres_les_clotures_existantes()

        if niveau_de_la_cloture_qui_couvre_le_transfert == ClotureCaisse.NIVEAU_MENSUEL:
            # Une J qui finit avant le transfert, puis une M qui le couvre.
            # / A J ending before the transfer, then an M covering it.
            _creer_une_cloture(
                ClotureCaisse.NIVEAU_JOURNALIER,
                debut=date_du_transfert - timedelta(days=1),
                fin=date_du_transfert - timedelta(seconds=1),
            )
            _creer_une_cloture(
                ClotureCaisse.NIVEAU_MENSUEL,
                debut=date_du_transfert - timedelta(days=20),
                fin=date_du_transfert + timedelta(hours=12),
            )
        else:
            _creer_une_cloture(
                ClotureCaisse.NIVEAU_JOURNALIER,
                debut=date_du_transfert - timedelta(days=1),
                fin=date_du_transfert + timedelta(hours=12),
            )
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )

    moment_avant_le_rattrapage = timezone.now()
    rapport = _lancer_le_rattrapage(executer=True)
    moment_apres_le_rattrapage = timezone.now()

    with tenant_context(lieu):
        vente_ecrite = Vente.objects.get(idempotency_key=_cle_du_virement(paiement))
        assert moment_avant_le_rattrapage <= vente_ecrite.datetime_encaissement
        assert vente_ecrite.datetime_encaissement <= moment_apres_le_rattrapage

    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_ECRITES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_DATEES_MAINTENANT}1")


def test_rattrapage_relance_n_ecrit_rien_de_plus(lieu_sans_virement_a_rattraper):
    """
    Un second `--executer` ne trouve plus rien à rattraper : aucune vente de plus.
    / A second --executer writes nothing more.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )

    _lancer_le_rattrapage(executer=True)
    with tenant_context(lieu):
        nombre_de_ventes_apres_le_premier_rattrapage = Vente.objects.count()

    second_rapport = _lancer_le_rattrapage(executer=True)

    with tenant_context(lieu):
        assert Vente.objects.count() == nombre_de_ventes_apres_le_premier_rattrapage
        assert (
            Vente.objects.filter(idempotency_key=_cle_du_virement(paiement)).count()
            == 1
        )
    assert _le_rapport_affiche(second_rapport, f"{RAPPORT_VENTES_ECRITES}0")


def test_rattrapage_metadata_illisible_comptee_sans_vente(
    lieu_sans_virement_a_rattraper,
):
    """
    Un paiement `T` dont `metadata_stripe` n'a ni montant ni date lisibles : il est
    compté « illisible », aucune vente n'est écrite, et la commande ne s'arrête pas.
    / A T payment with unreadable metadata: counted, no sale written.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        paiement_illisible = Paiement_stripe.objects.create(
            detail="Versement de monnaie globale",
            payment_intent_id=f"tr_TEST_{uuid_module.uuid4().hex[:16]}",
            metadata_stripe=json.dumps({"type": "transfer.created", "data": {}}),
            status=Paiement_stripe.VALID,
            source=Paiement_stripe.TRANSFERT,
            source_traitement=Paiement_stripe.WEBHOOK,
        )
        nombre_de_ventes_avant = Vente.objects.count()

    rapport = _lancer_le_rattrapage(executer=True)

    with tenant_context(lieu):
        assert Vente.objects.count() == nombre_de_ventes_avant
        paiement_relu = Paiement_stripe.objects.get(pk=paiement_illisible.pk)
        assert paiement_relu.vente_id is None

    assert _le_rapport_affiche(rapport, f"{RAPPORT_ILLISIBLES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_ECRITES}0")


def test_rattrapage_une_erreur_sur_un_paiement_est_comptee_et_le_suivant_est_ecrit(
    lieu_sans_virement_a_rattraper,
):
    """
    Deux paiements à rattraper. La fabrique échoue (simulée) sur le premier appel : la
    commande compte l'erreur et continue. L'autre paiement reçoit sa vente.
    Le simulacre remplace la fabrique dans le module de la commande, qui l'importe en
    tête de fichier.
    / Two payments; the factory fails on the first call: the error is counted and the
    other payment still gets its sale.
    """
    lieu = lieu_sans_virement_a_rattraper
    with tenant_context(lieu):
        _monnaie_fed()
        date_du_transfert = _date_a_la_seconde(timedelta(days=1))
        premier_paiement = _creer_un_paiement_de_virement(
            MONTANT_DU_VIREMENT, date_du_transfert
        )
        second_paiement = _creer_un_paiement_de_virement(4200, date_du_transfert)

    appels_de_la_fabrique = []

    def fabrique_qui_echoue_au_premier_appel(*arguments, **arguments_nommes):
        appels_de_la_fabrique.append(arguments)
        if len(appels_de_la_fabrique) == 1:
            raise RuntimeError("panne simulée de la vente")
        return ecrire_la_vente_d_un_virement_recu(*arguments, **arguments_nommes)

    with mock.patch(
        f"comptabilite.management.commands.{COMMANDE_DE_RATTRAPAGE}"
        ".ecrire_la_vente_d_un_virement_recu",
        side_effect=fabrique_qui_echoue_au_premier_appel,
    ):
        rapport = _lancer_le_rattrapage(executer=True)

    assert len(appels_de_la_fabrique) == 2
    with tenant_context(lieu):
        paiements_avec_une_vente = 0
        for paiement in [premier_paiement, second_paiement]:
            paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
            if paiement_relu.vente_id is not None:
                paiements_avec_une_vente += 1
        assert paiements_avec_une_vente == 1

    assert _le_rapport_affiche(rapport, f"{RAPPORT_PAIEMENTS_TROUVES}2")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_VENTES_ECRITES}1")
    assert _le_rapport_affiche(rapport, f"{RAPPORT_ERREURS}1")

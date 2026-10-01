"""
Tests des ventes faites dans l'ADMIN : chaque vente écrite par un gestionnaire est une
`Vente` d'origine « admin », écrite par le service de vente, et encaissée dans la même
transaction que ses lignes.
/ Sales made in the ADMIN: every sale written by a manager is an "admin" `Vente`, written
by the sale service, and settled in the same transaction as its lines.

LOCALISATION : tests/pytest/test_admin_ecrit_la_vente.py

LA RÈGLE TESTÉE
Une vente faite dans l'admin n'attend aucun paiement en ligne : l'argent est déclaré
reçu par le gestionnaire. Donc :
- une vente de nature VENTE, origine ADMIN, opérateur vide ;
- ses lignes sont ses articles, écrits par le service (`ajouter_article`) ;
- un seul règlement, au moyen choisi, du montant total ; rien pour une vente à 0 ;
- la vente est encaissée (REGLEE, numérotée) en dernier, après les déclencheurs.
/ No online payment: one VENTE, origin ADMIN, empty operator; one payment at the chosen
method for the total (none at 0); settled last, after the triggers.

LES TROIS CHEMINS
- Billets vendus dans l'admin (`ReservationAddAdmin.save`) : client = l'acheteur. Un
  billet « offert » est écrit comme un offert de la caisse (décision D32) : au prix du
  tarif, part offerte = total, source OFFRIR, un règlement FREE du même montant.
- Paiement d'adhésion dans l'admin (`MembershipMVT.ajouter_paiement`) : la ligne passe
  « payée » (déclencheur `trigger_A`), PUIS la vente est encaissée. Elle est encaissée
  même si le déclencheur échoue : l'argent est déclaré reçu. Ligne, vente et
  encaissement sont écrits ensemble ou pas du tout.
- Adhésion créée (ou renouvelée) dans l'admin (signal
  `create_lignearticle_if_membership_created_on_admin`) : même ordre ; une adhésion
  offerte vaut 0 : vente à 0, aucun règlement.
Le formulaire d'ajout d'adhésion refuse une contribution sans moyen de paiement.
/ Three paths: tickets (offered = written at price, fully offered), membership payment
(trigger first, then settle, even if the trigger fails, all or nothing), membership
created in the admin (same order; offered = 0). The add form refuses a contribution
without payment method.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev (tests/PIEGES.md 13.1). Stripe (catalogue), Fedow et Celery sont simulés :
aucun appel réseau, aucune tâche envoyée au worker.
/ Rolled-back transaction per test. Stripe, Fedow and Celery are faked.

CODE PARCOURU / CODE EXERCISED
- Administration/admin_tenant.py — ReservationAddAdmin.save, MembershipAddForm ;
- BaseBillet/views.py — MembershipMVT.ajouter_paiement ;
- BaseBillet/signals.py — create_lignearticle_if_membership_created_on_admin ;
- BaseBillet/triggers.py — trigger_A (adhésion payée) ;
- BaseBillet/services_vente.py — ouvrir_vente, ajouter_article, ajouter_reglement,
  encaisser_vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-D-en-ligne-avoirs.md (§3,
§5 test 11, trous T12 et T15) ; brief CHANTIER-05-briefs/05-D-2b.md.

Lancer / Run : make test ARGS="tests/pytest/test_admin_ecrit_la_vente.py"
"""

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db.models.signals import pre_save
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle,
    Membership,
    PaymentMethod,
    Product,
    Reservation,
    SaleOrigin,
    Tva,
)
from BaseBillet.models_vente import Vente
from fabriques_panier import (
    catalogue_stripe_simule,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from test_caracterisation_admin_api import (
    creer_une_adhesion_depuis_l_admin,
    vendre_des_billets_depuis_l_admin,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session + catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe (session + catalogue) and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Assistants communs
# / Shared helpers
# --------------------------------------------------------------------------


def donner_un_taux_de_tva_au_produit(produit, taux_en_pour_cent):
    """
    Rattache un taux de TVA au produit. `update()` : aucun signal de Product ne part.
    / Attaches a VAT rate to the product. update(): no Product signal fires.
    """
    tva, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal(taux_en_pour_cent))
    Product.objects.filter(pk=produit.pk).update(tva=tva)


def la_vente_unique_des_lignes(lignes):
    """
    Rend LA vente dont les articles sont ces lignes. Échoue si une ligne n'a pas de
    vente, ou si les lignes sont dans plusieurs ventes.
    / Returns THE sale whose items are these lines. Fails on a line without sale, or
    on lines spread over several sales.
    """
    ventes_trouvees = set()
    for ligne in lignes:
        assert ligne.vente_id is not None, (
            f"La ligne {ligne.uuid} n'a pas de vente (LigneArticle.vente vide)."
        )
        ventes_trouvees.add(ligne.vente_id)
    assert len(ventes_trouvees) == 1, (
        f"Les lignes sont dans {len(ventes_trouvees)} vente(s), une attendue."
    )
    return Vente.objects.get(pk=ventes_trouvees.pop())


def verifier_la_vente_admin_encaissee(vente, client_attendu):
    """
    Relit la vente en base et vérifie la règle d'une vente faite dans l'admin : une
    VENTE, origine ADMIN, encaissée (REGLEE), numérotée, opérateur vide, client attendu.
    / Reads the sale back: VENTE, origin ADMIN, settled, numbered, no operator, client.

    :return: la vente relue, pour les vérifications propres à chaque test
    """
    vente_relue = Vente.objects.get(pk=vente.pk)
    assert vente_relue.nature == Vente.Nature.VENTE
    assert vente_relue.origine == SaleOrigin.ADMIN
    assert vente_relue.statut == Vente.Statut.REGLEE, (
        f"La vente admin n'est pas encaissée (statut {vente_relue.statut})."
    )
    assert vente_relue.numero is not None
    assert vente_relue.operateur is None
    assert vente_relue.client == client_attendu
    return vente_relue


def moyens_et_montants_des_reglements(vente):
    """
    Les règlements de la vente, relus en base : une liste de couples (moyen, montant),
    triée.
    / The sale's payments, read back: a sorted list of (method, amount) pairs.
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append((reglement.moyen, reglement.montant))
    return sorted(reglements_lus)


@contextmanager
def statuts_des_articles_a_l_encaissement():
    """
    Relève, au moment où une vente passe REGLEE, le statut EN BASE de chacun de ses
    articles. Sert à prouver l'ORDRE : le déclencheur de la ligne a tourné AVANT
    l'encaissement.
    / Records, when a sale turns REGLEE, the database status of each of its items.
    Proves the ORDER: the line's trigger ran BEFORE the settlement.

    Un `pre_save` sur `Vente` : il ne dépend pas de l'endroit d'où le code appelle
    `encaisser_vente`. La liste rendue reçoit une liste triée de statuts par
    encaissement.
    / A pre_save on Vente: independent of where the code imports encaisser_vente.
    """
    statuts_releves = []

    def relever_les_statuts_des_articles(sender, instance, **kwargs):
        vente_qui_passe_reglee = instance.statut == Vente.Statut.REGLEE
        if not vente_qui_passe_reglee:
            return
        statuts_des_articles = []
        for ligne in LigneArticle.objects.filter(vente_id=instance.pk):
            statuts_des_articles.append(ligne.status)
        statuts_releves.append(sorted(statuts_des_articles))

    identifiant_du_receveur = f"test-admin-ordre-{identifiant_unique()}"
    pre_save.connect(
        relever_les_statuts_des_articles,
        sender=Vente,
        dispatch_uid=identifiant_du_receveur,
    )
    try:
        yield statuts_releves
    finally:
        pre_save.disconnect(sender=Vente, dispatch_uid=identifiant_du_receveur)


class EncaissementImpossible(Exception):
    """L'encaissement simulé en échec par le test.
    / The settlement the test makes fail."""


@contextmanager
def encaissement_qui_echoue():
    """
    Fait échouer tout encaissement : la vente lève `EncaissementImpossible` au moment
    où elle passerait REGLEE. Indépendant de l'endroit d'où `encaisser_vente` est
    appelée.
    / Makes every settlement fail when the sale would turn REGLEE.
    """

    def refuser_l_encaissement(sender, instance, **kwargs):
        if instance.statut == Vente.Statut.REGLEE:
            raise EncaissementImpossible("Encaissement refusé par le test.")

    identifiant_du_receveur = f"test-admin-echec-{identifiant_unique()}"
    pre_save.connect(
        refuser_l_encaissement,
        sender=Vente,
        dispatch_uid=identifiant_du_receveur,
    )
    try:
        yield
    finally:
        pre_save.disconnect(sender=Vente, dispatch_uid=identifiant_du_receveur)


# --------------------------------------------------------------------------
# Billets vendus dans l'admin
# / Tickets sold in the admin
# --------------------------------------------------------------------------


def vendre_et_relire(lieu, prix, quantite, moyen_de_paiement, taux_tva=None):
    """
    Un administrateur vend `quantite` billets d'un tarif à `prix` euros, au moyen
    donné, par le formulaire « Ajouter une réservation ». Rend la réservation, sa
    ligne unique, l'acheteur et la réponse.
    / An admin sells tickets through the "Add reservation" form. Returns the
    reservation, its single line, the buyer and the response.
    """
    concert = creer_evenement_avec_tarif(prix=prix)
    if taux_tva is not None:
        donner_un_taux_de_tva_au_produit(concert.produit, taux_tva)
    email_de_l_acheteur = f"test+adminvente{identifiant_unique()}@mock.test"
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = vendre_des_billets_depuis_l_admin(
        client_de_l_admin,
        email=email_de_l_acheteur,
        billetterie=concert,
        quantite=quantite,
        moyen_de_paiement=moyen_de_paiement,
    )

    # Succès de l'admin : redirection vers la liste (302). Un 200 = formulaire en erreur.
    # / Admin success = redirect (302). A 200 means form errors.
    assert reponse.status_code == 302
    acheteur = TibilletUser.objects.get(email=email_de_l_acheteur)
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    ligne = LigneArticle.objects.get(reservation=reservation)
    return SimpleNamespace(
        reservation=reservation, ligne=ligne, acheteur=acheteur, reponse=reponse
    )


def test_vente_admin_billets_especes_encaissee(lieu):
    """
    Fiche test 11. L'admin vend deux billets à 10 € (TVA du produit 5,5 %), payés en
    espèces. UNE vente : origine ADMIN, REGLEE, numérotée, opérateur vide, client =
    l'acheteur. Son unique article est la ligne des billets (VALID, 2 × 1000 = 2000 au
    catalogue, TVA 5,5 % : HT 1896, TVA 104). Un seul règlement : espèces, 2000.
    / Test 11. Two 10 € tickets sold in the admin for cash: one ADMIN sale, settled,
    numbered, no operator, client = buyer; one cash payment of 2000.
    """
    vente_admin = vendre_et_relire(
        lieu,
        prix="10.00",
        quantite=2,
        moyen_de_paiement=PaymentMethod.CASH,
        taux_tva="5.50",
    )

    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([vente_admin.ligne]),
        client_attendu=vente_admin.acheteur,
    )
    article = vente.articles.get()
    assert article.pk == vente_admin.ligne.pk
    assert article.status == LigneArticle.VALID
    assert article.amount == 1000
    assert article.total_catalogue == 2000
    assert article.part_offerte == 0
    assert article.total_ttc == 2000
    assert article.vat == Decimal("5.50")
    assert article.total_ht == 1896
    assert article.total_tva == 104
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.CASH, 2000)]
    verifier_egalites(vente)


def test_billet_offert_admin_part_offerte_totale(lieu):
    """
    T12 / D32. L'admin vend deux billets d'un tarif à 15 € et choisit « Offert ».
    Le billet est écrit comme un offert de la caisse : prix unitaire 1500 (le prix du
    tarif, plus 0), total catalogue 3000, part offerte 3000, net 0, source OFFRIR.
    La vente ADMIN est encaissée avec UN règlement FREE de 3000 (la trace de l'offert),
    aucun règlement d'argent.
    / T12 / D32. Two 15 € tickets "Offered" in the admin: written at the rate's price,
    fully offered (OFFRIR), one FREE payment of 3000, no money payment.
    """
    vente_admin = vendre_et_relire(
        lieu,
        prix="15.00",
        quantite=2,
        moyen_de_paiement=PaymentMethod.FREE,
    )

    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([vente_admin.ligne]),
        client_attendu=vente_admin.acheteur,
    )
    article = vente.articles.get()
    assert article.status == LigneArticle.VALID
    assert article.amount == 1500
    assert article.total_catalogue == 3000
    assert article.part_offerte == 3000
    assert article.total_ttc == 0
    assert article.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.FREE, 3000)]
    assert vente.total_catalogue == 3000
    assert vente.total_offert == 3000
    assert vente.total_ttc == 0
    verifier_egalites(vente)


def test_vente_admin_billets_virement_encaissee(lieu):
    """
    L'admin vend trois billets à 12 €, payés par virement. La vente ADMIN est encaissée
    avec UN règlement « virement » (TR) de 3600 : le moyen choisi, jamais un moyen par
    défaut.
    / Three 12 € tickets paid by bank transfer: one TR payment of 3600.
    """
    vente_admin = vendre_et_relire(
        lieu,
        prix="12.00",
        quantite=3,
        moyen_de_paiement=PaymentMethod.TRANSFER,
    )

    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([vente_admin.ligne]),
        client_attendu=vente_admin.acheteur,
    )
    article = vente.articles.get()
    assert article.total_catalogue == 3600
    assert article.part_offerte == 0
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.TRANSFER, 3600)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# Paiement d'adhésion dans l'admin (`ajouter_paiement`)
# / Membership payment in the admin
# --------------------------------------------------------------------------


def preparer_une_adhesion_en_attente_de_paiement():
    """
    Une adhésion à 20 € « en attente de paiement » : l'état qu'exige `ajouter_paiement`.
    Rend l'adhésion et l'adhérente.
    / A 20 € membership awaiting payment: the state ajouter_paiement requires.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    adhesion_en_attente = Membership.objects.create(
        user=adherente,
        price=adhesion.tarif,
        first_name="Ada",
        last_name="Lovelace",
        status=Membership.WAITING_PAYMENT,
    )
    return SimpleNamespace(adhesion=adhesion_en_attente, adherente=adherente)


def poster_un_paiement_d_adhesion(client_de_l_admin, adhesion, montant, moyen):
    """
    L'admin enregistre un paiement hors ligne sur l'adhésion, par le panneau de
    l'admin (`/memberships/<pk>/ajouter_paiement/`).
    / The admin records an offline payment through the admin panel.
    """
    return client_de_l_admin.post(
        f"/memberships/{adhesion.pk}/ajouter_paiement/",
        {"amount": montant, "payment_method": moyen},
    )


def test_ajouter_paiement_vente_reglee_et_ligne_valide_en_sortie(lieu):
    """
    T15 (remplace le test 12 de la fiche). L'admin enregistre 20 € payés par chèque.
    En sortie : la ligne de l'adhésion est VALID (le déclencheur `trigger_A` a tourné)
    et sa vente ADMIN est REGLEE, avec UN règlement chèque de 2000.
    L'ORDRE est vérifié : au moment où la vente passe REGLEE, la ligne est déjà VALID
    en base. Le déclencheur tourne d'abord, l'encaissement vient en dernier.
    / T15. 20 € paid by cheque: line VALID, sale settled with one cheque payment. ORDER:
    when the sale turns REGLEE, the line is already VALID (trigger first, settle last).
    """
    adhesion_en_attente = preparer_une_adhesion_en_attente_de_paiement()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    with statuts_des_articles_a_l_encaissement() as statuts_a_l_encaissement:
        reponse = poster_un_paiement_d_adhesion(
            client_de_l_admin,
            adhesion_en_attente.adhesion,
            montant="20.00",
            moyen=PaymentMethod.CHEQUE,
        )

    assert reponse.status_code == 200
    ligne = LigneArticle.objects.get(membership=adhesion_en_attente.adhesion)
    assert ligne.status == LigneArticle.VALID

    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([ligne]),
        client_attendu=adhesion_en_attente.adherente,
    )
    assert vente.articles.get().total_catalogue == 2000
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.CHEQUE, 2000)]

    # Un seul encaissement, et la ligne était déjà VALID à ce moment-là.
    # / One settlement, and the line was already VALID at that moment.
    assert statuts_a_l_encaissement == [[LigneArticle.VALID]]
    verifier_egalites(vente)


def test_ajouter_paiement_encaisse_meme_si_le_declencheur_echoue(lieu):
    """
    Le déclencheur `trigger_A` échoue (son exception est avalée et journalisée par la
    machine à états) : la ligne reste « payée » (PAID), pas VALID. L'argent est
    pourtant déclaré reçu : la vente ADMIN est encaissée quand même, avec UN règlement
    espèces de 2000.
    / trigger_A fails (swallowed and logged): the line stays PAID. The money is declared
    received: the sale is settled anyway, with one cash payment of 2000.
    """
    adhesion_en_attente = preparer_une_adhesion_en_attente_de_paiement()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    with patch(
        "BaseBillet.triggers.appliquer_les_effets_d_une_adhesion_payee",
        side_effect=RuntimeError("Déclencheur en échec (simulé par le test)."),
    ):
        reponse = poster_un_paiement_d_adhesion(
            client_de_l_admin,
            adhesion_en_attente.adhesion,
            montant="20.00",
            moyen=PaymentMethod.CASH,
        )

    assert reponse.status_code == 200
    ligne = LigneArticle.objects.get(membership=adhesion_en_attente.adhesion)
    # Témoin : le déclencheur a bien échoué (la ligne n'est pas passée VALID).
    # / Control: the trigger did fail (the line did not turn VALID).
    assert ligne.status == LigneArticle.PAID

    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([ligne]),
        client_attendu=adhesion_en_attente.adherente,
    )
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.CASH, 2000)]
    verifier_egalites(vente)


def test_ajouter_paiement_encaissement_impossible_rien_n_est_ecrit(lieu):
    """
    L'encaissement échoue (simulé : la vente refuse de passer REGLEE). Ligne, vente et
    mise à jour de l'adhésion sont écrites ensemble ou pas du tout : après l'erreur,
    l'adhésion est toujours « en attente de paiement », sans contribution, et il
    n'existe ni ligne ni vente pour elle.
    / The settlement fails: line, sale and membership update are all-or-nothing. After
    the error, the membership is still awaiting payment, with no line and no sale.
    """
    adhesion_en_attente = preparer_une_adhesion_en_attente_de_paiement()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    with encaissement_qui_echoue():
        with pytest.raises(EncaissementImpossible):
            poster_un_paiement_d_adhesion(
                client_de_l_admin,
                adhesion_en_attente.adhesion,
                montant="20.00",
                moyen=PaymentMethod.CASH,
            )

    adhesion_relue = Membership.objects.get(pk=adhesion_en_attente.adhesion.pk)
    assert adhesion_relue.status == Membership.WAITING_PAYMENT
    assert adhesion_relue.last_contribution is None
    assert not LigneArticle.objects.filter(
        membership=adhesion_en_attente.adhesion
    ).exists()
    assert not Vente.objects.filter(
        articles__membership=adhesion_en_attente.adhesion
    ).exists()


# --------------------------------------------------------------------------
# Adhésion créée (ou renouvelée) dans l'admin
# / Membership created (or renewed) in the admin
# --------------------------------------------------------------------------


def creer_l_adhesion_et_relire(lieu, contribution, moyen_de_paiement):
    """
    Un administrateur ajoute une adhésion à 20 € par le formulaire « Ajouter une
    adhésion », avec la contribution et le moyen donnés. Rend l'adhésion créée,
    l'adhérente, la réponse et les statuts relevés à l'encaissement.
    / An admin adds a membership through the "Add membership" form. Returns the
    created membership, the member, the response and the statuses at settlement.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    with statuts_des_articles_a_l_encaissement() as statuts_a_l_encaissement:
        reponse = creer_une_adhesion_depuis_l_admin(
            client_de_l_admin,
            email=adherente.email,
            tarif=adhesion.tarif,
            contribution=contribution,
            moyen_de_paiement=moyen_de_paiement,
        )

    # Succès de l'admin : redirection vers la liste (302). Un 200 = formulaire en erreur.
    # / Admin success = redirect (302). A 200 means form errors.
    assert reponse.status_code == 302
    adhesion_creee = Membership.objects.get(user=adherente, price=adhesion.tarif)
    return SimpleNamespace(
        adhesion=adhesion_creee,
        adherente=adherente,
        reponse=reponse,
        statuts_a_l_encaissement=statuts_a_l_encaissement,
    )


def test_adhesion_creee_dans_l_admin_vente_encaissee(lieu):
    """
    L'admin ajoute une adhésion de 20 €, payée par virement. La ligne de l'adhésion
    est VALID (déclencheur `trigger_A`) et sa vente ADMIN est REGLEE, avec UN règlement
    virement de 2000 : le moyen de l'adhésion, jamais un moyen par défaut. L'ORDRE : la
    ligne est déjà VALID quand la vente passe REGLEE.
    / A 20 € membership paid by bank transfer: line VALID, sale settled with one TR
    payment of 2000; the line is already VALID when the sale turns REGLEE.
    """
    adhesion_admin = creer_l_adhesion_et_relire(
        lieu, contribution="20", moyen_de_paiement=PaymentMethod.TRANSFER
    )

    ligne = LigneArticle.objects.get(membership=adhesion_admin.adhesion)
    assert ligne.status == LigneArticle.VALID
    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([ligne]),
        client_attendu=adhesion_admin.adherente,
    )
    assert vente.articles.get().total_catalogue == 2000
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.TRANSFER, 2000)]
    assert adhesion_admin.statuts_a_l_encaissement == [[LigneArticle.VALID]]
    verifier_egalites(vente)


def test_adhesion_creee_dans_l_admin_gratuite_vente_a_zero(lieu):
    """
    L'admin ajoute une adhésion offerte (contribution 0, moyen « Offert »). Offert ne
    vaut que 0 ici : la vente ADMIN est encaissée à 0 (REGLEE, numérotée), SANS aucun
    règlement. Sa ligne est VALID, total catalogue 0.
    / An offered membership (0, FREE) added in the admin: the sale is settled at 0,
    numbered, with NO payment. Its line is VALID, catalogue total 0.
    """
    adhesion_admin = creer_l_adhesion_et_relire(
        lieu, contribution="0", moyen_de_paiement=PaymentMethod.FREE
    )

    ligne = LigneArticle.objects.get(membership=adhesion_admin.adhesion)
    assert ligne.status == LigneArticle.VALID
    vente = verifier_la_vente_admin_encaissee(
        la_vente_unique_des_lignes([ligne]),
        client_attendu=adhesion_admin.adherente,
    )
    assert vente.articles.get().total_catalogue == 0
    assert vente.total_catalogue == 0
    assert vente.reglements.count() == 0
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# Formulaire d'ajout d'adhésion : une contribution sans moyen de paiement
# / Membership add form: a contribution without payment method
# --------------------------------------------------------------------------


def test_formulaire_adhesion_contribution_sans_moyen_refuse(lieu):
    """
    L'admin saisit une contribution de 20 € sans choisir de moyen de paiement. Le
    formulaire est refusé (réponse 200 : le formulaire revient avec son erreur) : aucune
    adhésion, aucune ligne, aucune vente. L'erreur porte sur le moyen de paiement (ou
    sur le formulaire entier), jamais sur un autre champ.
    / A 20 € contribution without payment method is refused: the form comes back with
    its error; no membership, no line, no sale.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = creer_une_adhesion_depuis_l_admin(
        client_de_l_admin,
        email=adherente.email,
        tarif=adhesion.tarif,
        contribution="20",
        moyen_de_paiement="",
    )

    assert reponse.status_code == 200, (
        f"Le formulaire a été accepté (code {reponse.status_code}) : une contribution "
        f"sans moyen de paiement doit être refusée."
    )
    formulaire = reponse.context["adminform"].form
    assert formulaire.errors, "Le formulaire revient sans aucune erreur."
    champs_en_erreur = set(formulaire.errors.keys())
    assert champs_en_erreur <= {"__all__", "payment_method"}, (
        f"L'erreur porte sur d'autres champs : {sorted(champs_en_erreur)}."
    )
    assert not Membership.objects.filter(user=adherente).exists()
    assert not LigneArticle.objects.filter(membership__user=adherente).exists()

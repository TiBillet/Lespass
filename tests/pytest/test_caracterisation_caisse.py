"""
Tests de caractérisation : les ventes à la CAISSE (parcours P9, P12), la protection
contre le double envoi (effet E23) et la clôture de caisse (trou T11, décision D29).
/ Characterization tests: CASH REGISTER sales (flows P9, P12), the double-submit
guard (effect E23) and the register closure (gap T11, decision D29).

LOCALISATION : tests/pytest/test_caracterisation_caisse.py

À QUOI SERVENT CES TESTS
Un test de caractérisation FIGE le comportement d'aujourd'hui. Il ne dit pas si ce
comportement est bon : il dit « voilà ce que fait le code ». Il est vert sur le code
actuel. S'il tombe pendant le chantier 05 « montants entiers », c'est qu'une logique
métier a changé sans le vouloir : on s'arrête et on pose la question au mainteneur.
Seuls les tests listés dans la fiche A′ §4 ont le droit de changer, dans la fiche qui
change volontairement le comportement (leur docstring le dit).
/ A characterization test FREEZES today's behaviour. It is green on the current code.
Only the tests listed in sheet A′ §4 may change, in the sheet that changes the behaviour.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A2-caracterisation.md
Détail des parcours : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-machine-a-etats.md (§4, §6).

CE QUE CES TESTS REGARDENT (et rien d'autre)
- les statuts finaux, relus en base : lignes de vente, adhésion, commandes de table,
  articles de commande, tables ;
- les tâches Celery demandées : leur nom et leurs arguments.
Ils ne lisent JAMAIS directement sur la ligne un champ que le chantier retire
(`payment_method`, `uuid_transaction`, `carte`, `wallet`, `point_de_vente`…). Les
lignes d'une vente sont retrouvées par leur TARIF, créé pour le test.
/ They only read final statuses and requested Celery tasks. Sale lines are found by
their price, created for the test, never by a column the work removes.

CODE PARCOURU / CODE EXERCISED
- laboutik/views.py — PaiementViewSet.payer, _executer_avec_cle_idempotence (double
  envoi), _payer_en_especes, _payer_par_nfc, _creer_adhesions_depuis_panier,
  _creer_ou_renouveler_adhesion ;
- laboutik/views.py — CommandeViewSet.payer_commande (commande de table) ;
- laboutik/views.py — CaisseViewSet.cloturer (bouton de clôture).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev (clôture comprise). La caisse est activée par `configuration_modifiee()`,
jamais enregistrée (tests/PIEGES.md 13.22). Fedow et Celery sont simulés : aucun appel
réseau, aucune tâche envoyée au worker. Les tâches lancées en `transaction.on_commit`
sont exécutées par `django_capture_on_commit_callbacks(execute=True)` (tests/PIEGES.md 13.14).
/ Rolled-back transaction per test. The register module is switched on in memory only.
Fedow and Celery are faked. on_commit tasks are run by the capture fixture.

L'assistant `etat_metier()` vient du premier fichier de caractérisation,
`test_caracterisation_en_ligne.py`.
/ `etat_metier()` comes from the first characterization file.

Lancer / Run : make test ARGS="tests/pytest/test_caracterisation_caisse.py"
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, Membership, Price, Product
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService
from laboutik.models import (
    ArticleCommandeSauvegarde,
    CommandeSauvegarde,
    PointDeVente,
    Table,
)
from QrcodeCashless.models import CarteCashless
from test_caracterisation_en_ligne import (
    arguments_des_taches,
    creer_un_administrateur_du_lieu,
    etat_metier,
)

pytestmark = pytest.mark.django_db

# Adresses de la caisse (laboutik/urls.py).
# / Cash register addresses.
URL_DU_PAIEMENT_CAISSE = "/laboutik/paiement/payer/"
URL_DE_LA_CLOTURE_CAISSE = "/laboutik/caisse/cloturer/"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée, avec Celery simulé pendant tout le test.
    / The `lespass` venue, register switched on, with Celery faked for the whole test.

    La caisse n'est accessible que si le module caisse (et donc le module monnaie
    locale) est actif. On l'active EN MÉMOIRE : `configuration_modifiee()` ne sauve
    jamais la `Configuration`, dont le cache est partagé avec le serveur live.
    / The register needs its module on. It is switched on in memory only.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `taches_demandees` fills up during the test: one (short name, args) pair per task.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def statuts_des_lignes_du_tarif(tarif):
    """
    Les statuts des lignes de vente d'un tarif, triés.
    Chaque test crée ses propres tarifs : leurs lignes sont celles du test.
    / Sorted statuses of the sale lines of one price. Each test creates its own prices.
    """
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(pricesold__price=tarif):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


def statuts_des_articles_de_la_commande(commande):
    """Les statuts des articles d'une commande de table, triés.
    / Sorted statuses of the articles of a table order."""
    statuts_des_articles = []
    for article in commande.articles.all():
        statuts_des_articles.append(article.statut)
    return sorted(statuts_des_articles)


# --------------------------------------------------------------------------
# Ce qu'il faut pour vendre : un point de vente, des articles, le geste du caissier
# / What selling needs: a point of sale, articles, the cashier's action
# --------------------------------------------------------------------------


def creer_une_biere_vendue_a_la_caisse(prix="5.00"):
    """
    Un article de bar vendu à la caisse (« vente » simple), avec un tarif en euros.
    Rend un objet avec `produit` et `tarif`.
    / A bar article sold at the register, with a euro price.
    """
    identifiant = identifiant_unique()
    produit = Product.objects.create(
        name=f"TEST_caracterisation biere {identifiant}",
        methode_caisse=Product.VENTE,
    )
    tarif = Price.objects.create(
        product=produit,
        name="Pinte",
        prix=Decimal(prix),
        publish=True,
    )
    return SimpleNamespace(produit=produit, tarif=tarif)


def creer_un_point_de_vente(produits):
    """
    Un point de vente « service direct » qui accepte les espèces et la carte bancaire,
    et qui propose les produits donnés.
    Il est caché (`hidden=True`) : d'autres tests cherchent le premier point de vente
    visible (tests/PIEGES.md, « PointDeVente de test : toujours hidden=True »).
    / A direct-service point of sale offering the given products. Hidden, like every
    test point of sale.
    """
    point_de_vente = PointDeVente.objects.create(
        name=f"TEST_caracterisation comptoir {identifiant_unique()}",
        comportement=PointDeVente.DIRECT,
        service_direct=True,
        accepte_especes=True,
        accepte_carte_bancaire=True,
        hidden=True,
    )
    for produit in produits:
        point_de_vente.products.add(produit)
    return point_de_vente


def payer_a_la_caisse(
    client_du_caissier,
    point_de_vente,
    article,
    quantite,
    moyen_de_paiement,
    autres_champs=None,
):
    """
    Le caissier valide un panier d'un seul article, avec un moyen de paiement.
    Même formulaire que l'écran de la caisse (#addition-form) : une clé
    `repid-<produit>--<tarif>` porte la quantité.
    / The cashier validates a one-article cart with a payment method.

    `client_du_caissier` : un administrateur du lieu connecté. Sans carte primaire, la
    caisse accepte la session d'un administrateur du lieu (BaseBillet/permissions.py,
    `HasLaBoutikAccess`).
    / A logged-in venue admin: the register accepts an admin session.

    `moyen_de_paiement` : "espece", "carte_bancaire", "CH" ou "nfc".
    `autres_champs` : champs en plus (e-mail de l'adhérent, clé d'idempotence…).
    Paiement exact : `given_sum` vaut 0, il n'y a pas de monnaie à rendre.
    / Exact payment: no change to give back.
    """
    prix_de_l_article_en_centimes = int(article.tarif.prix * 100)
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "moyen_paiement": moyen_de_paiement,
        "total": str(prix_de_l_article_en_centimes * quantite),
        "given_sum": "0",
        f"repid-{article.produit.uuid}--{article.tarif.uuid}": str(quantite),
    }
    if autres_champs is not None:
        donnees_du_formulaire.update(autres_champs)
    return client_du_caissier.post(URL_DU_PAIEMENT_CAISSE, donnees_du_formulaire)


# --------------------------------------------------------------------------
# P9 — Une adhésion vendue à la caisse
# / P9 — A membership sold at the register
# --------------------------------------------------------------------------


def test_vente_caisse_adhesion_facture_et_recompense_sans_envoi_laboutik(
    lieu, django_capture_on_commit_callbacks
):
    """
    P9 : le caissier vend une adhésion à 20 € en espèces à une adhérente identifiée
    par son e-mail. Une ligne de vente validée (`V`) est créée ; l'adhésion est créée
    au statut « caisse » (`LABOUTIK`), avec une échéance.
    Trois tâches sont demandées, toutes APRÈS la validation en base, dans cet ordre :
    le webhook d'adhésion (l'adhésion est enregistrée avec une échéance), la facture
    par mail, la récompense en monnaie. AUCUN envoi à l'ancien LaBoutik : la caisse V2
    ne parle pas à la caisse legacy.
    Ce test fait partie des tests qui ont le droit de changer (fiche A′ §4) : une
    adhésion payée a les mêmes effets en ligne et en caisse, par le même code
    (BaseBillet/triggers.py, fiche B §2 bis). Le détail de ces effets est testé dans
    tests/pytest/test_caisse_effets_adhesion.py.
    / P9: a 20 € membership sold in cash. One VALID line, membership LABOUTIK with a
    deadline. Three tasks, all after the commit: membership webhook, invoice mail,
    currency reward. No legacy LaBoutik sale. A paid membership has the same effects
    online and at the register, through the same code (sheet B §2 bis).
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    champs_de_l_adherente = {
        "email_adhesion": adherente.email,
        "prenom_adhesion": "Ada",
        "nom_adhesion": "Lovelace",
    }
    # On ne garde que les tâches demandées par la vente.
    # / Keep only the tasks requested by the sale.
    lieu.taches_demandees.clear()

    # La caisse déclare l'adhérente au réseau Fedow avant d'enregistrer l'adhésion
    # (laboutik/views.py, `_declarer_adherent_au_reseau`). Le lieu est dit « branché
    # à Fedow », et la déclaration est simulée : aucun appel réseau.
    # / The register declares the member to Fedow first: the venue is said to be
    # connected, and the declaration is faked.
    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch("fedow_connect.services.declarer_wallet_user_a_fedow"):
            with django_capture_on_commit_callbacks(execute=True):
                reponse = payer_a_la_caisse(
                    client_du_caissier,
                    point_de_vente,
                    adhesion,
                    quantite=1,
                    moyen_de_paiement="espece",
                    autres_champs=champs_de_l_adherente,
                )

    assert reponse.status_code == 200
    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    etat_attendu = {
        "adhesion": Membership.LABOUTIK,
        "adhesion_a_une_echeance": True,
        "taches": [
            "webhook_membership",
            "send_membership_invoice_to_email",
            "refill_from_lespass_to_user_wallet_from_price_solded",
        ],
    }
    assert (
        etat_metier(adhesion=adhesion_vendue, taches_demandees=lieu.taches_demandees)
        == etat_attendu
    )
    assert statuts_des_lignes_du_tarif(adhesion.tarif) == [LigneArticle.VALID]
    ligne_de_l_adhesion = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_vendue
    )
    assert arguments_des_taches(lieu.taches_demandees, "webhook_membership") == [
        (adhesion_vendue.pk,)
    ]
    assert arguments_des_taches(
        lieu.taches_demandees, "send_membership_invoice_to_email"
    ) == [(str(adhesion_vendue.uuid),)]
    assert arguments_des_taches(
        lieu.taches_demandees, "refill_from_lespass_to_user_wallet_from_price_solded"
    ) == [(ligne_de_l_adhesion.pk,)]


# --------------------------------------------------------------------------
# E23 — Le même paiement envoyé deux fois (double appui sur « Valider »)
# / E23 — The same payment sent twice (double tap on "Validate")
# --------------------------------------------------------------------------


def test_rejeu_meme_cle_caisse_rien_en_double(lieu, django_capture_on_commit_callbacks):
    """
    E23 : le caissier appuie deux fois sur « Valider » pour 2 bières à 5 € en espèces.
    Les deux envois portent la MÊME clé d'idempotence (posée par l'écran des moyens de
    paiement). Les deux réponses sont des succès (200), mais la vente n'est enregistrée
    qu'une fois : une seule ligne de vente, validée (`V`). Aucune tâche n'est demandée.
    / E23: the same cash payment posted twice with the SAME idempotency key. Both answers
    are 200, but only one VALID line exists. No task is requested.
    """
    biere = creer_une_biere_vendue_a_la_caisse(prix="5.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    champ_de_la_cle_d_idempotence = {"cle_idempotence_paiement": str(uuid.uuid4())}
    # On ne garde que les tâches demandées par les deux envois.
    # / Keep only the tasks requested by the two submits.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        premiere_reponse = payer_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            biere,
            quantite=2,
            moyen_de_paiement="espece",
            autres_champs=champ_de_la_cle_d_idempotence,
        )
        deuxieme_reponse = payer_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            biere,
            quantite=2,
            moyen_de_paiement="espece",
            autres_champs=champ_de_la_cle_d_idempotence,
        )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    assert statuts_des_lignes_du_tarif(biere.tarif) == [LigneArticle.VALID]
    assert etat_metier(taches_demandees=lieu.taches_demandees) == {"taches": []}


# --------------------------------------------------------------------------
# P12 — Une commande de table payée avec la carte NFC du client
# / P12 — A table order paid with the customer's NFC card
# --------------------------------------------------------------------------


def creer_une_carte_nfc_chargee(lieu, solde_en_centimes):
    """
    ÉTAT DE DÉPART : une carte NFC anonyme, dont le portefeuille porte
    `solde_en_centimes` de monnaie locale.
    / STARTING STATE: an anonymous NFC card holding some local currency.

    La caisse lit le solde dans la PREMIÈRE monnaie locale du lieu, par ordre de nom
    (laboutik/views.py `_payer_par_nfc`, fedow_core/services.py
    `obtenir_assets_accessibles`). On crédite donc la carte dans cette monnaie-là, lue
    par la même requête (tests/PIEGES.md 9.97) : une autre monnaie ne serait pas vue.
    / The register reads the FIRST local currency of the venue, by name: the card is
    credited in that very currency, read by the same query.

    `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31) ; `uuid` est
    posé, comme sur toute carte réellement fabriquée.
    / tag_id and number are 8 characters max; uuid is set, like on any real card.
    """
    monnaie_locale_de_la_caisse = (
        AssetService.obtenir_assets_accessibles(lieu.tenant)
        .filter(category=Asset.TLF)
        .first()
    )
    portefeuille_de_la_carte = Wallet.objects.create(
        name=f"TEST_caracterisation carte {identifiant_unique()}",
        origin=lieu.tenant,
    )
    identifiant_de_la_carte = identifiant_unique().upper()
    carte = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
        wallet_ephemere=portefeuille_de_la_carte,
    )
    Token.objects.create(
        wallet=portefeuille_de_la_carte,
        asset=monnaie_locale_de_la_caisse,
        value=solde_en_centimes,
    )
    return carte


def test_paiement_table_nfc_libere_la_table(lieu, django_capture_on_commit_callbacks):
    """
    P12, chemin NFC : une table occupée porte une commande ouverte (`OP`) de 2 bières
    à 5 €. Le caissier la paie avec la carte NFC du client, chargée de 20 €.
    `payer_commande` appelle le paiement NFC de la caisse (`_payer_par_nfc`), puis lit
    le HTML qu'il rend pour savoir s'il a réussi. Résultat : commande payée (`PA`),
    son article servi (`SV`), table libre (`L`), une ligne de vente validée (`V`).
    Aucune tâche n'est demandée.
    / P12 NFC path: an open table order paid by NFC card. Order PAID, article SERVED,
    table FREE, one VALID line. No task requested.
    """
    biere = creer_une_biere_vendue_a_la_caisse(prix="5.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=2000)

    # ÉTAT DE DÉPART : la table 12 est occupée par une commande ouverte.
    # / STARTING STATE: table 12 is occupied by an open order.
    table = Table.objects.create(
        name=f"TEST_caracterisation table 12 {identifiant_unique()}",
        statut=Table.OCCUPEE,
    )
    commande = CommandeSauvegarde.objects.create(
        table=table,
        statut=CommandeSauvegarde.OPEN,
    )
    ArticleCommandeSauvegarde.objects.create(
        commande=commande,
        product=biere.produit,
        price=biere.tarif,
        qty=2,
        statut=ArticleCommandeSauvegarde.EN_ATTENTE,
    )
    # On ne garde que les tâches demandées par le paiement.
    # / Keep only the tasks requested by the payment.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_du_caissier.post(
            f"/laboutik/commande/payer/{commande.uuid}/",
            {
                "uuid_pv": str(point_de_vente.uuid),
                "moyen_paiement": "nfc",
                "tag_id": carte_du_client.tag_id,
            },
        )

    assert reponse.status_code == 200
    commande.refresh_from_db()
    table.refresh_from_db()
    assert commande.statut == CommandeSauvegarde.PAID
    assert statuts_des_articles_de_la_commande(commande) == [
        ArticleCommandeSauvegarde.SERVI
    ]
    assert table.statut == Table.LIBRE
    assert statuts_des_lignes_du_tarif(biere.tarif) == [LigneArticle.VALID]
    assert etat_metier(taches_demandees=lieu.taches_demandees) == {"taches": []}


# --------------------------------------------------------------------------
# T11 (D29) — Le bouton de clôture de caisse
# / T11 (D29) — The register closure button
# --------------------------------------------------------------------------


def test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables(
    lieu, django_capture_on_commit_callbacks
):
    """
    T11 (décision D29) : deux tables. La table A est occupée par une commande ouverte
    (`OP`) ; la table B est servie, avec une commande servie mais pas encore payée
    (`SV`). Le caissier clôture la caisse.
    Résultat : la commande ouverte est annulée (`AN`), la commande servie reste servie
    (`SV`), et les DEUX tables sont libres (`L`) — la table B aussi, alors que sa
    commande n'est pas payée. Aucune tâche n'est demandée.
    Reste vert en G : le nouveau bouton de clôture garde ces deux effets (D29).
    / T11 (D29): closing the register cancels the open order, keeps the served one, and
    frees BOTH tables, even the one whose served order is unpaid. Stays green in G.
    """
    biere = creer_une_biere_vendue_a_la_caisse(prix="5.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    # La clôture refuse de clôturer une caisse sans vente (tests/PIEGES.md 9.61) :
    # on vend d'abord une bière en espèces.
    # / The closure refuses a register without sales: sell one beer first.
    payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        biere,
        quantite=1,
        moyen_de_paiement="espece",
    )

    # ÉTAT DE DÉPART : table A occupée (commande ouverte), table B servie (commande
    # servie, pas encore payée).
    # / STARTING STATE: table A occupied (open order), table B served (served order).
    table_a = Table.objects.create(
        name=f"TEST_caracterisation table A {identifiant_unique()}",
        statut=Table.OCCUPEE,
    )
    commande_ouverte = CommandeSauvegarde.objects.create(
        table=table_a,
        statut=CommandeSauvegarde.OPEN,
    )
    table_b = Table.objects.create(
        name=f"TEST_caracterisation table B {identifiant_unique()}",
        statut=Table.SERVIE,
    )
    commande_servie = CommandeSauvegarde.objects.create(
        table=table_b,
        statut=CommandeSauvegarde.SERVED,
    )
    # On ne garde que les tâches demandées par la clôture.
    # / Keep only the tasks requested by the closure.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_du_caissier.post(
            URL_DE_LA_CLOTURE_CAISSE, {"uuid_pv": str(point_de_vente.uuid)}
        )

    assert reponse.status_code == 200
    commande_ouverte.refresh_from_db()
    commande_servie.refresh_from_db()
    table_a.refresh_from_db()
    table_b.refresh_from_db()
    assert commande_ouverte.statut == CommandeSauvegarde.CANCEL
    assert commande_servie.statut == CommandeSauvegarde.SERVED
    assert table_a.statut == Table.LIBRE
    assert table_b.statut == Table.LIBRE
    assert etat_metier(taches_demandees=lieu.taches_demandees) == {"taches": []}

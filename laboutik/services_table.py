"""
Addition d'une table du mode restaurant
/ Restaurant mode table bill

LOCALISATION : laboutik/services_table.py

Une table qui commande a UNE addition : une `Vente` EN_ATTENTE, sans article ni
reglement. Chaque envoi (« Ajouter a la table ») cree une `CommandeSauvegarde`
rattachee a cette vente (`commande.vente`), avec ses `ArticleCommandeSauvegarde`.

Les `LigneArticle` et les `Reglement` ne s'ecrivent qu'au paiement, par les flux
de paiement de la caisse (laboutik/views.py). Ils reprennent la vente de
l'addition au lieu d'en ouvrir une (`reprendre_la_vente_de_l_addition`).
Ainsi le stock, la cascade NFC et les rapports ne voient rien avant le paiement.

CYCLE DE VIE :
1. 1er envoi : ouverture de la Vente EN_ATTENTE, commande OPEN, table OCCUPEE.
2. Envois suivants : nouvelle commande OPEN, meme vente.
3. Paiement : lignes + reglements ecrits dans la vente, vente REGLEE.
4. `cloturer_l_addition` : commandes PAID, articles SERVI, table LIBRE.

Appele par / Called by : laboutik/views.py (point_de_vente, ajouter_a_la_table,
moyens_paiement, _executer_paiement, _ouvrir_la_vente_de_caisse...).
"""

from django.db import transaction
from django.utils.translation import gettext as _

from BaseBillet.models import Product, SaleOrigin
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import ouvrir_vente
from laboutik.models import ArticleCommandeSauvegarde, CommandeSauvegarde, Table

# Une commande dans ces statuts fait encore partie de l'addition a payer.
# / An order in these statuses is still part of the bill to pay.
STATUTS_DES_COMMANDES_A_PAYER = (
    CommandeSauvegarde.OPEN,
    CommandeSauvegarde.SERVED,
)

# Un article dans ces statuts est encore du. Un article ANNULE ne se paie pas.
# / An article in these statuses is still owed. A cancelled one is not paid.
STATUTS_DES_ARTICLES_A_PAYER = (
    ArticleCommandeSauvegarde.EN_ATTENTE,
    ArticleCommandeSauvegarde.EN_COURS,
    ArticleCommandeSauvegarde.PRET,
    ArticleCommandeSauvegarde.SERVI,
)

# Methodes de caisse des recharges : elles demandent la carte du client.
# / Top-up methods: they need the customer's card.
METHODES_DE_RECHARGE = (
    Product.RECHARGE_EUROS,
    Product.RECHARGE_CADEAU,
    Product.RECHARGE_TEMPS,
)

# Classe CSS du statut de la table (restaurant_interface.css, .table-statut--*)
# / CSS class of the table status
CLASSES_CSS_DES_STATUTS = {
    Table.LIBRE: "libre",
    Table.OCCUPEE: "occupee",
    Table.SERVIE: "servie",
}


def _libelle_du_statut(statut_de_la_table):
    """
    Le statut ecrit en clair, avec les memes mots que la grille des tables
    (cotton/tables_definition.html). Les choix du modele ont des msgids anglais.
    / The status in plain words, same as the table grid legend.
    """
    if statut_de_la_table == Table.OCCUPEE:
        return _("Occupée")
    if statut_de_la_table == Table.SERVIE:
        return _("Servie")
    return _("Libre")


def raison_du_refus_d_un_article_de_table(article_du_panier):
    """
    Dit pourquoi un article du panier ne peut pas aller sur une addition de table.
    / Tells why a cart article cannot go on a table bill.

    LOCALISATION : laboutik/services_table.py

    Une addition est payee plus tard, sans la carte du client ni aucune saisie.
    On refuse donc ce qui ne se regle qu'au comptoir :
    - un tarif en points ou en temps (paye par la carte du client) ;
    - un retour de consigne (rend de l'argent, se regle seul) ;
    - un tarif au poids, au volume ou a prix libre (demande une saisie) ;
    - une recharge, une adhesion, un billet (demandent le client).

    :param article_du_panier: dict de `_extraire_articles_du_panier` (product, price...)
    :return: le message de refus (str), ou None si l'article est accepte
    """
    produit = article_du_panier["product"]
    tarif = article_du_panier["price"]

    tarif_en_points = tarif.asset_id is not None or tarif.non_fiduciaire
    if tarif_en_points:
        return _(
            "Un tarif en points ou en temps ne passe pas par une "
            "commande de table : encaissez-le au comptoir."
        )

    if produit.methode_caisse == Product.RETOUR_CONSIGNE:
        return _("Un retour de consigne se règle au comptoir, pas depuis une commande.")

    tarif_avec_saisie = (
        tarif.poids_mesure
        or tarif.free_price
        or article_du_panier.get("custom_amount_centimes") is not None
        or article_du_panier.get("weight_amount") is not None
    )
    if tarif_avec_saisie:
        return _(
            "Un tarif au poids, au volume ou à prix libre ne passe pas "
            "par une commande de table : encaissez-le au comptoir."
        )

    produit_qui_demande_le_client = (
        produit.methode_caisse in METHODES_DE_RECHARGE
        or produit.categorie_article == Product.ADHESION
        or article_du_panier.get("est_billet", False)
    )
    if produit_qui_demande_le_client:
        return _(
            "Une recharge, une adhésion ou un billet se règle au comptoir, "
            "pas depuis une commande de table."
        )

    return None


def commandes_a_payer_de_la_table(table):
    """
    Les commandes de la table qui ne sont pas encore payees.
    / The table's orders not paid yet.

    :param table: `Table`
    :return: QuerySet de `CommandeSauvegarde`
    """
    return CommandeSauvegarde.objects.filter(
        table=table,
        statut__in=STATUTS_DES_COMMANDES_A_PAYER,
    )


def vente_de_l_addition_de_la_table(table):
    """
    La Vente EN_ATTENTE de l'addition de la table, ou None.
    / The table bill's PENDING sale, or None.

    LOCALISATION : laboutik/services_table.py

    On la retrouve par les commandes non payees de la table : elles portent
    toutes la meme vente (`ajouter_le_panier_a_la_table`).

    :param table: `Table`
    :return: `Vente` ou None
    """
    commande_rattachee = (
        commandes_a_payer_de_la_table(table)
        .filter(vente__statut=Vente.Statut.EN_ATTENTE)
        .select_related("vente")
        .first()
    )
    if commande_rattachee is None:
        return None
    return commande_rattachee.vente


def vente_reglee_de_l_addition_de_la_table(table):
    """
    La vente de l'addition, si elle vient d'etre reglee, ou None.
    / The bill's sale if it has just been settled, or None.

    LOCALISATION : laboutik/services_table.py

    Juste apres un paiement reussi, la vente est REGLEE mais les commandes ne
    sont pas encore marquees payees : c'est le signe qu'il faut cloturer
    l'addition (`cloturer_l_addition`). Une fois cloturee, plus rien a trouver.

    :param table: `Table`
    :return: `Vente` REGLEE ou None
    """
    commande_rattachee = (
        commandes_a_payer_de_la_table(table)
        .filter(vente__statut=Vente.Statut.REGLEE)
        .select_related("vente")
        .first()
    )
    if commande_rattachee is None:
        return None
    return commande_rattachee.vente


def ajouter_le_panier_a_la_table(
    table, point_de_vente, articles_panier, operateur, vente_de_l_addition=None
):
    """
    Ajoute le panier a l'addition de la table : une nouvelle commande.
    / Adds the cart to the table bill: one new order.

    LOCALISATION : laboutik/services_table.py

    FLUX (une seule transaction) :
    1. La vente de l'addition : celle donnee, sinon celle de la table,
       sinon une Vente EN_ATTENTE ouverte ici (sans cle d'idempotence).
    2. Une `CommandeSauvegarde` OPEN, rattachee a la table et a la vente.
    3. Un `ArticleCommandeSauvegarde` par article du panier.
    4. La table passe OCCUPEE.

    L'appelant a deja verifie chaque article (raison_du_refus_d_un_article_de_table).

    :param table: `Table`
    :param point_de_vente: `PointDeVente` de la caisse
    :param articles_panier: liste de dicts (product, price, quantite, prix_centimes)
    :param operateur: l'utilisateur qui prend la commande, ou None
    :param vente_de_l_addition: vente a utiliser (paiement d'une table), ou None
    :return: la `CommandeSauvegarde` creee
    """
    with transaction.atomic():
        if vente_de_l_addition is None:
            vente_de_l_addition = vente_de_l_addition_de_la_table(table)
        if vente_de_l_addition is None:
            vente_de_l_addition = ouvrir_vente(
                origine=SaleOrigin.LABOUTIK,
                nature=Vente.Nature.VENTE,
                point_de_vente=point_de_vente,
                operateur=operateur,
            )

        commande = CommandeSauvegarde.objects.create(
            table=table,
            statut=CommandeSauvegarde.OPEN,
            responsable=operateur,
            vente=vente_de_l_addition,
        )

        for article_du_panier in articles_panier:
            quantite = int(article_du_panier["quantite"])
            prix_unitaire_en_centimes = article_du_panier["prix_centimes"]
            ArticleCommandeSauvegarde.objects.create(
                commande=commande,
                product=article_du_panier["product"],
                price=article_du_panier["price"],
                qty=quantite,
                reste_a_payer=prix_unitaire_en_centimes * quantite,
                reste_a_servir=quantite,
                statut=ArticleCommandeSauvegarde.EN_ATTENTE,
            )

        table.statut = Table.OCCUPEE
        table.save(update_fields=["statut"])

    return commande


def _articles_a_payer_de_la_table(table):
    """
    Les articles encore dus de la table, avec leur produit et leur tarif.
    / The table's articles still owed, with product and price.
    """
    return ArticleCommandeSauvegarde.objects.filter(
        commande__table=table,
        commande__statut__in=STATUTS_DES_COMMANDES_A_PAYER,
        statut__in=STATUTS_DES_ARTICLES_A_PAYER,
    ).select_related("product", "price")


def articles_panier_de_l_addition(table):
    """
    Les articles de l'addition, au format du panier de la caisse.
    / The bill's articles, in the POS cart format.

    LOCALISATION : laboutik/services_table.py

    Meme format que `_extraire_articles_du_panier` (laboutik/views.py) : les flux
    de paiement les traitent comme un panier ordinaire. Un meme produit au meme
    tarif, envoye en plusieurs fois, donne une seule ligne (quantites additionnees).

    Le prix unitaire est le prix ACTUEL du tarif, comme `payer_commande`.

    :param table: `Table`
    :return: liste de dicts (product, price, quantite, prix_centimes, ...)
    """
    articles_par_tarif = {}
    for article_de_commande in _articles_a_payer_de_la_table(table):
        cle_du_tarif = article_de_commande.price_id
        article_deja_vu = articles_par_tarif.get(cle_du_tarif)
        if article_deja_vu is not None:
            article_deja_vu["quantite"] += article_de_commande.qty
            continue

        articles_par_tarif[cle_du_tarif] = {
            "product": article_de_commande.product,
            "price": article_de_commande.price,
            "quantite": article_de_commande.qty,
            "prix_centimes": int(round(article_de_commande.price.prix * 100)),
            "custom_amount_centimes": None,
            "weight_amount": None,
            "est_billet": False,
            "event": None,
        }

    articles_panier = []
    for article_du_panier in articles_par_tarif.values():
        articles_panier.append(article_du_panier)
    return articles_panier


def resume_de_l_addition(table):
    """
    Ce que le bandeau de table affiche dans le ticket.
    / What the table banner shows in the ticket.

    LOCALISATION : laboutik/services_table.py

    Utilise par partial/_addition_de_table.html.

    :param table: `Table`
    :return: dict (uuid, nom, statut_css, statut_libelle, lignes, nombre_d_articles,
             total_centimes)
    """
    lignes_deja_envoyees = []
    nombre_d_articles = 0
    total_en_centimes = 0
    for article_du_panier in articles_panier_de_l_addition(table):
        quantite = article_du_panier["quantite"]
        prix_unitaire_en_centimes = article_du_panier["prix_centimes"]
        total_de_la_ligne_en_centimes = prix_unitaire_en_centimes * quantite
        lignes_deja_envoyees.append(
            {
                "nom": article_du_panier["product"].name,
                "nom_du_tarif": article_du_panier["price"].name,
                "quantite": quantite,
                "prix_unitaire_centimes": prix_unitaire_en_centimes,
                "total_centimes": total_de_la_ligne_en_centimes,
            }
        )
        nombre_d_articles += quantite
        total_en_centimes += total_de_la_ligne_en_centimes

    return {
        "uuid": str(table.uuid),
        "nom": table.name,
        "statut_css": CLASSES_CSS_DES_STATUTS.get(table.statut, "libre"),
        "statut_libelle": _libelle_du_statut(table.statut),
        "lignes": lignes_deja_envoyees,
        "nombre_d_articles": nombre_d_articles,
        "total_centimes": total_en_centimes,
    }


def reprendre_la_vente_de_l_addition(vente, idempotency_key, client=None, carte=None):
    """
    Prepare la vente de l'addition pour son paiement.
    / Prepares the bill's sale for its payment.

    LOCALISATION : laboutik/services_table.py

    Appelee par les flux de paiement a la place de `ouvrir_vente`. La vente doit
    etre EN_ATTENTE (relue sous verrou), sinon ValueError.
    On pose ce que l'ouverture n'a pas pu connaitre : la cle d'idempotence du
    paiement (un rejeu retrouve cette vente, comme avec `ouvrir_vente`), le client
    et la carte du client.

    :param vente: la `Vente` EN_ATTENTE de l'addition
    :param idempotency_key: l'identifiant du paiement (str)
    :param client: l'acheteur, ou None
    :param carte: la `CarteCashless` du client, ou None
    :return: la `Vente` relue en base
    """
    with transaction.atomic():
        vente_verrouillee = Vente.objects.select_for_update().get(pk=vente.pk)
        if vente_verrouillee.statut != Vente.Statut.EN_ATTENTE:
            raise ValueError(
                f"L'addition {vente_verrouillee.uuid} n'est plus en attente "
                f"(statut {vente_verrouillee.statut})."
            )

        champs_modifies = []
        if vente_verrouillee.idempotency_key != idempotency_key:
            vente_verrouillee.idempotency_key = idempotency_key
            champs_modifies.append("idempotency_key")
        if client is not None:
            vente_verrouillee.client = client
            champs_modifies.append("client")
        if carte is not None:
            vente_verrouillee.carte = carte
            champs_modifies.append("carte")
        if champs_modifies:
            vente_verrouillee.save(update_fields=champs_modifies)

    return vente_verrouillee


def cloturer_l_addition(table, vente):
    """
    Termine l'addition d'une table payee.
    / Closes the bill of a paid table.

    LOCALISATION : laboutik/services_table.py

    - commandes non payees de la table → PAID, rattachees a la vente ;
    - articles encore dus → SERVI, reste a payer 0 (les annules restent annules) ;
    - table → LIBRE.

    :param table: `Table`
    :param vente: la `Vente` REGLEE du paiement
    """
    with transaction.atomic():
        commandes_payees = list(commandes_a_payer_de_la_table(table))
        for commande in commandes_payees:
            ArticleCommandeSauvegarde.objects.filter(
                commande=commande,
                statut__in=STATUTS_DES_ARTICLES_A_PAYER,
            ).update(
                statut=ArticleCommandeSauvegarde.SERVI,
                reste_a_payer=0,
                reste_a_servir=0,
            )
            commande.statut = CommandeSauvegarde.PAID
            commande.vente = vente
            commande.save(update_fields=["statut", "vente"])

        table.statut = Table.LIBRE
        table.save(update_fields=["statut"])

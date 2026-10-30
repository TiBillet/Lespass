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
Ainsi la cascade NFC et les rapports ne voient rien avant le paiement.

Le stock reel ne bouge qu'au paiement, mais les articles encore dus sont COMPTES
comme reserves (`quantites_reservees_des_additions`) : ni une autre table, ni le
comptoir ne peuvent vendre ce qu'une table a deja commande.

Le prix d'une addition est FIGE a la commande : `reste_a_payer` le garde. Un tarif
modifie ensuite ne change pas ce que la table doit.

Un article demande une preparation si la categorie de son produit a une imprimante
(`article_demande_une_preparation`). Sans imprimante (boisson servie au bar...),
il n'y a rien a envoyer, et il n'attend aucun « Envoi prepa ».

CYCLE DE VIE :
1. 1er envoi : ouverture de la Vente EN_ATTENTE, commande OPEN, table OCCUPEE.
2. Envois suivants : nouvelle commande OPEN, meme vente.
3. Paiement : lignes + reglements ecrits dans la vente, vente REGLEE.
4. `cloturer_l_addition` : commandes PAID, articles SERVI, table LIBRE.

Appele par / Called by : laboutik/views.py (point_de_vente, ajouter_a_la_table,
moyens_paiement, _executer_paiement, _ouvrir_la_vente_de_caisse...).
"""

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from BaseBillet.models import Product, SaleOrigin
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import annuler_vente, ouvrir_vente
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

# Un article dans ces statuts est parti en preparation et n'est pas encore servi.
# / An article in these statuses went to preparation and is not served yet.
STATUTS_DES_ARTICLES_EN_PREPARATION = (
    ArticleCommandeSauvegarde.EN_COURS,
    ArticleCommandeSauvegarde.PRET,
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


class AdditionDejaReglee(ValueError):
    """
    L'addition n'est plus en attente : un autre terminal vient de l'encaisser.
    / The bill is no longer pending: another terminal has just settled it.

    Interceptee par PaiementViewSet.payer() et payer_complementaire().
    """


class AdditionModifiee(ValueError):
    """
    L'addition a change pendant le paiement : le total lu n'est plus le bon.
    / The bill changed during the payment: the total read is no longer right.

    Interceptee par PaiementViewSet.payer() et payer_complementaire().
    """


class TableAvecUnSoldeDu(ValueError):
    """
    La table doit encore de l'argent : elle ne peut pas etre supprimee.
    / The table still owes money: it cannot be deleted.
    """


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


def article_demande_une_preparation(article_de_commande):
    """
    L'article part-il en preparation ? Oui si sa categorie a une imprimante.
    / Does the article go to preparation? Yes if its category has a printer.

    LOCALISATION : laboutik/services_table.py

    Meme regle que l'impression (printing/tasks.py:imprimer_commande).
    Une imprimante desactivee compte : la preparation est attendue, mais son
    ticket ne sort pas. La vue le signale (`noms_des_imprimantes_desactivees`).

    :param article_de_commande: `ArticleCommandeSauvegarde`
    :return: bool
    """
    return produit_demande_une_preparation(article_de_commande.product)


def produit_demande_une_preparation(produit):
    """
    Le produit part-il en preparation ? Oui si sa categorie a une imprimante.
    / Does the product go to preparation? Yes if its category has a printer.

    :param produit: `Product`
    :return: bool
    """
    categorie = produit.categorie_pos
    if categorie is None:
        return False
    return categorie.printer_id is not None


def _prix_unitaire_fige_en_centimes(article_de_commande):
    """
    Le prix unitaire de la commande, garde par `reste_a_payer`.
    / The unit price at order time, kept by `reste_a_payer`.
    """
    return article_de_commande.reste_a_payer // article_de_commande.qty


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
        # Le verrou de la table garantit une seule vente d'addition, meme si deux
        # terminaux envoient la premiere commande en meme temps.
        # / The table lock guarantees a single bill sale across terminals.
        Table.objects.select_for_update().get(pk=table.pk)

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
    ).select_related("product__categorie_pos", "price")


def quantites_reservees_des_additions(uuids_des_produits):
    """
    Ce que les additions en attente ont commande, par produit.
    / What pending table bills have ordered, per product.

    LOCALISATION : laboutik/services_table.py

    Le stock reel ne baisse qu'au paiement : ces quantites sont encore dedans.
    La garde de stock (views.py:_valider_stock_panier) les retire du disponible.
    On ne compte que les ventes EN_ATTENTE : une addition reglee a deja sorti son
    stock, et une addition annulee ne reserve plus rien.

    :param uuids_des_produits: liste d'uuid de `Product`
    :return: dict {uuid du produit: quantite}, en unite de stock (quantite x contenance)
    """
    articles_reserves = ArticleCommandeSauvegarde.objects.filter(
        product_id__in=uuids_des_produits,
        commande__statut__in=STATUTS_DES_COMMANDES_A_PAYER,
        commande__vente__statut=Vente.Statut.EN_ATTENTE,
        statut__in=STATUTS_DES_ARTICLES_A_PAYER,
    ).select_related("price")

    quantites_par_produit = {}
    for article_reserve in articles_reserves:
        contenance = article_reserve.price.contenance or 1
        quantite_deja_vue = quantites_par_produit.get(article_reserve.product_id, 0)
        quantites_par_produit[article_reserve.product_id] = (
            quantite_deja_vue + article_reserve.qty * contenance
        )
    return quantites_par_produit


def articles_panier_de_l_addition(table):
    """
    Les articles de l'addition, au format du panier de la caisse.
    / The bill's articles, in the POS cart format.

    LOCALISATION : laboutik/services_table.py

    Meme format que `_extraire_articles_du_panier` (laboutik/views.py) : les flux
    de paiement les traitent comme un panier ordinaire. Un meme produit au meme
    tarif et au meme prix, envoye en plusieurs fois, donne une seule ligne (quantites
    additionnees).

    Le prix unitaire est celui de la COMMANDE, pas le prix actuel du tarif.
    `deja_commande` dit a la garde de stock de ne pas bloquer ces articles.

    :param table: `Table`
    :return: liste de dicts (product, price, quantite, prix_centimes, ...)
    """
    articles_par_tarif = {}
    for article_de_commande in _articles_a_payer_de_la_table(table):
        prix_unitaire_en_centimes = _prix_unitaire_fige_en_centimes(article_de_commande)
        cle_du_tarif = (article_de_commande.price_id, prix_unitaire_en_centimes)
        article_deja_vu = articles_par_tarif.get(cle_du_tarif)
        if article_deja_vu is not None:
            article_deja_vu["quantite"] += article_de_commande.qty
            continue

        articles_par_tarif[cle_du_tarif] = {
            "product": article_de_commande.product,
            "price": article_de_commande.price,
            "quantite": article_de_commande.qty,
            "prix_centimes": prix_unitaire_en_centimes,
            "custom_amount_centimes": None,
            "weight_amount": None,
            "est_billet": False,
            "event": None,
            "deja_commande": True,
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

    Une ligne par tarif, par prix ET par etat d'envoi : les articles deja partis en
    preparation, ceux qui attendent l'envoi (« Envoi prepa ») et ceux qui n'ont pas
    de preparation ne sont jamais melanges, le serveur voit ce qui reste a envoyer.

    `nombre_a_envoyer` pilote le badge « X a envoyer » et le blocage de l'encaissement.
    Il ne compte que les articles qui demandent une preparation.

    :param table: `Table`
    :return: dict (uuid, nom, statut_css, statut_libelle, lignes, nombre_d_articles,
             nombre_a_envoyer, articles_en_preparation, total_centimes)
    """
    lignes_par_tarif_et_envoi = {}
    nombre_d_articles = 0
    nombre_a_envoyer = 0
    articles_en_preparation = False
    total_en_centimes = 0
    for article_de_commande in _articles_a_payer_de_la_table(table):
        envoye_en_preparation = (
            article_de_commande.statut != ArticleCommandeSauvegarde.EN_ATTENTE
        )
        sans_preparation = (
            not envoye_en_preparation
            and not article_demande_une_preparation(article_de_commande)
        )
        quantite = article_de_commande.qty
        prix_unitaire_en_centimes = _prix_unitaire_fige_en_centimes(article_de_commande)

        cle_de_la_ligne = (
            article_de_commande.price_id,
            prix_unitaire_en_centimes,
            envoye_en_preparation,
            sans_preparation,
        )
        ligne = lignes_par_tarif_et_envoi.get(cle_de_la_ligne)
        if ligne is None:
            ligne = {
                "nom": article_de_commande.product.name,
                "nom_du_tarif": article_de_commande.price.name,
                "quantite": 0,
                "prix_unitaire_centimes": prix_unitaire_en_centimes,
                "total_centimes": 0,
                "envoye_en_preparation": envoye_en_preparation,
                "sans_preparation": sans_preparation,
            }
            lignes_par_tarif_et_envoi[cle_de_la_ligne] = ligne
        ligne["quantite"] += quantite
        ligne["total_centimes"] += prix_unitaire_en_centimes * quantite

        nombre_d_articles += quantite
        total_en_centimes += prix_unitaire_en_centimes * quantite
        if not envoye_en_preparation and not sans_preparation:
            nombre_a_envoyer += quantite
        if article_de_commande.statut in STATUTS_DES_ARTICLES_EN_PREPARATION:
            articles_en_preparation = True

    lignes_de_l_addition = []
    for ligne in lignes_par_tarif_et_envoi.values():
        lignes_de_l_addition.append(ligne)

    return {
        "uuid": str(table.uuid),
        "nom": table.name,
        "statut_css": CLASSES_CSS_DES_STATUTS.get(table.statut, "libre"),
        "statut_libelle": _libelle_du_statut(table.statut),
        "lignes": lignes_de_l_addition,
        "nombre_d_articles": nombre_d_articles,
        "nombre_a_envoyer": nombre_a_envoyer,
        "articles_en_preparation": articles_en_preparation,
        "total_centimes": total_en_centimes,
    }


def envoyer_l_addition_en_preparation(table):
    """
    Envoie en preparation les articles de l'addition qui ne sont pas encore partis.
    / Sends to preparation the bill's articles not sent yet.

    LOCALISATION : laboutik/services_table.py

    Les articles EN_ATTENTE des commandes non payees, s'ils demandent une preparation,
    passent EN_COURS. L'appelant imprime ensuite le ticket de chaque commande renvoyee
    (laboutik/printing/tasks.py:imprimer_commande, une imprimante par categorie).
    Un 2e appui n'envoie rien de plus : les articles sont deja EN_COURS.

    Appele par / Called by : views.py:CommandeViewSet.envoyer_en_preparation

    :param table: `Table`
    :return: liste des `CommandeSauvegarde` dont des articles viennent de partir
    """
    with transaction.atomic():
        articles_a_envoyer = (
            ArticleCommandeSauvegarde.objects.select_for_update().filter(
                commande__table=table,
                commande__statut__in=STATUTS_DES_COMMANDES_A_PAYER,
                statut=ArticleCommandeSauvegarde.EN_ATTENTE,
                product__categorie_pos__printer__isnull=False,
            )
        )
        uuids_des_commandes_envoyees = set()
        cles_des_articles_envoyes = []
        for article_a_envoyer in articles_a_envoyer:
            uuids_des_commandes_envoyees.add(article_a_envoyer.commande_id)
            cles_des_articles_envoyes.append(article_a_envoyer.pk)

        ArticleCommandeSauvegarde.objects.filter(
            pk__in=cles_des_articles_envoyes,
        ).update(statut=ArticleCommandeSauvegarde.EN_COURS)

    commandes_envoyees = list(
        CommandeSauvegarde.objects.filter(uuid__in=uuids_des_commandes_envoyees)
    )
    return commandes_envoyees


def commandes_a_reimprimer_de_la_table(table):
    """
    Les commandes non payees de la table qui ont des articles en preparation.
    / The table's unpaid orders with articles in preparation.

    Appele par / Called by : views.py:CommandeViewSet.reimprimer

    :param table: `Table`
    :return: liste de `CommandeSauvegarde`
    """
    return list(
        commandes_a_payer_de_la_table(table)
        .filter(articles__statut__in=STATUTS_DES_ARTICLES_EN_PREPARATION)
        .distinct()
    )


def noms_des_imprimantes_desactivees(commandes):
    """
    Les imprimantes desactivees qui devraient imprimer ces commandes.
    / Disabled printers that should print these orders.

    Le ticket de ces imprimantes ne sort pas : le serveur doit le savoir tout de
    suite. Une categorie SANS imprimante n'est pas concernee : c'est normal.

    :param commandes: liste de `CommandeSauvegarde`
    :return: liste triee de noms (str)
    """
    noms_trouves = ArticleCommandeSauvegarde.objects.filter(
        commande__in=commandes,
        product__categorie_pos__printer__active=False,
    ).values_list("product__categorie_pos__printer__name", flat=True)
    return sorted(set(noms_trouves))


def reprendre_la_vente_de_l_addition(
    table,
    vente,
    total_de_l_addition_lu_centimes,
    idempotency_key,
    client=None,
    carte=None,
):
    """
    Prepare la vente de l'addition pour son paiement.
    / Prepares the bill's sale for its payment.

    LOCALISATION : laboutik/services_table.py

    Appelee par les flux de paiement a la place de `ouvrir_vente`, DANS leur
    transaction. La vente doit etre EN_ATTENTE (relue sous verrou), sinon
    AdditionDejaReglee.

    Le verrou de la table est garde jusqu'a la fin du paiement : une commande envoyee
    pendant ce temps attend, voit la vente reglee et ouvre sa propre vente. Une commande
    arrivee AVANT le verrou porte la meme vente, sans etre dans les articles encaisses :
    le total relu sous verrou doit donc valoir le total lu, sinon AdditionModifiee.
    Ces deux verifications empechent de cloturer un article qui n'a pas ete paye.
    On pose ce que l'ouverture n'a pas pu connaitre : la cle d'idempotence du
    paiement (un rejeu retrouve cette vente, comme avec `ouvrir_vente`), le client
    et la carte du client.

    :param table: la `Table` de l'addition
    :param vente: la `Vente` EN_ATTENTE de l'addition
    :param total_de_l_addition_lu_centimes: le total des articles lus par le paiement
    :param idempotency_key: l'identifiant du paiement (str)
    :param client: l'acheteur, ou None
    :param carte: la `CarteCashless` du client, ou None
    :return: la `Vente` relue en base
    """
    with transaction.atomic():
        Table.objects.select_for_update().get(pk=table.pk)
        vente_verrouillee = Vente.objects.select_for_update().get(pk=vente.pk)
        if vente_verrouillee.statut != Vente.Statut.EN_ATTENTE:
            raise AdditionDejaReglee(
                f"L'addition {vente_verrouillee.uuid} n'est plus en attente "
                f"(statut {vente_verrouillee.statut})."
            )

        total_de_l_addition_relu = resume_de_l_addition(table)["total_centimes"]
        if total_de_l_addition_relu != total_de_l_addition_lu_centimes:
            raise AdditionModifiee(
                f"L'addition {vente_verrouillee.uuid} vaut "
                f"{total_de_l_addition_relu} au lieu de "
                f"{total_de_l_addition_lu_centimes}."
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

    - commandes de cette vente (ou sans vente) → PAID ;
    - articles encore dus → SERVI, reste a payer 0 (les annules restent annules) ;
    - table → LIBRE, sauf si une commande arrivee pendant le paiement reste a payer.

    Le filtre sur la vente est indispensable : une commande envoyee par un autre
    terminal pendant le paiement porte une autre vente, et elle n'a pas ete payee.

    :param table: `Table`
    :param vente: la `Vente` REGLEE du paiement
    """
    with transaction.atomic():
        Table.objects.select_for_update().get(pk=table.pk)

        commandes_payees = list(
            commandes_a_payer_de_la_table(table).filter(
                Q(vente=vente) | Q(vente__isnull=True)
            )
        )
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

        reste_une_commande_a_payer = commandes_a_payer_de_la_table(table).exists()
        if not reste_une_commande_a_payer:
            table.statut = Table.LIBRE
            table.save(update_fields=["statut"])


def supprimer_la_table(table):
    """
    Retire une table de la salle, si elle ne doit rien.
    / Removes a table from the room, if it owes nothing.

    LOCALISATION : laboutik/services_table.py

    La table est archivee, pas effacee : ses commandes gardent leur historique, et
    `ajouter_table` la fait revenir si son nom est repris.

    Une table qui doit de l'argent est refusee (TableAvecUnSoldeDu). Ses commandes
    restantes ne contiennent que des articles a 0 € : elles sont annulees, et la
    vente en attente de l'addition avec elles (ANNULEE, sans numero).

    Appele par / Called by : views.py:CommandeViewSet.supprimer_table

    :param table: `Table`
    :raises TableAvecUnSoldeDu: si le total de l'addition n'est pas nul
    """
    with transaction.atomic():
        Table.objects.select_for_update().get(pk=table.pk)

        if resume_de_l_addition(table)["total_centimes"] > 0:
            raise TableAvecUnSoldeDu(f"La table {table.pk} doit encore de l'argent.")

        vente_de_l_addition = vente_de_l_addition_de_la_table(table)

        for commande in commandes_a_payer_de_la_table(table):
            commande.articles.exclude(
                statut=ArticleCommandeSauvegarde.ANNULE,
            ).update(statut=ArticleCommandeSauvegarde.ANNULE)
            commande.statut = CommandeSauvegarde.CANCEL
            commande.save(update_fields=["statut"])

        if vente_de_l_addition is not None:
            annuler_vente(vente_de_l_addition)

        table.statut = Table.LIBRE
        table.archive = True
        table.save(update_fields=["statut", "archive"])

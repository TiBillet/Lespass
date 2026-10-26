"""
Fabrique de ventes pour les tests, et vérification des deux égalités d'une vente.
/ Sale factory for the tests, and check of the two equalities of a sale.

LOCALISATION : tests/pytest/fabriques_vente.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_vente import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

CE QUE PORTE CE MODULE
- `creer_tarif_vendu(...)` : un produit, son tarif et le tarif vendu qu'une ligne d'article
  référence (`LigneArticle.pricesold`). Le produit a TOUJOURS un compte de vente, sauf si
  le test demande le contraire (`avec_compte=False`) : sinon toute clôture qui contient sa
  vente serait refusée (FEC, API comptable, Dolibarr).
- `categorie_de_caisse_de_test()` : la catégorie de caisse des produits de test, reliée
  au compte 707000 ; `donner_un_compte_au_produit(produit)` y range un produit qui n'a
  pas de compte (aussi appelée par le code shell des tests E2E, qui vendent pour de vrai).
- `fabriquer_vente_encaissee(...)` : une vente complète, écrite PAR LE SERVICE DE VENTE
  (`BaseBillet/services_vente.py`). Une fabrique qui écrirait les tables à la main rendrait
  les tests aveugles aux deux égalités : le service est le seul à les vérifier.
- `verifier_egalites(vente)` : relit la vente en base et vérifie les deux égalités, puis
  les totaux stockés sur la vente. Chaque test qui encaisse une vente l'appelle à la fin
  (fiches B à H).
/ A price factory, a sale factory that goes THROUGH the sale service, and the check of the
two equalities (called at the end of every test that settles a sale).

LES DEUX ÉGALITÉS, vraies pour TOUTE vente réglée :
    Σ règlements                    = Σ totaux catalogue des articles
    Σ règlements hors « offert »    = Σ nets vendus des articles
Un règlement « offert » (FREE : bouton OFFRIR, recharge cadeau) garde la trace d'un
cadeau : il compte dans la 1ʳᵉ égalité, pas dans la 2ᵉ. Le règlement « jetons » (LG) est
un vrai règlement (D8 bis) : il compte dans les deux.
La liste des moyens offerts est écrite ICI, jamais importée du service : l'oracle ne
doit pas changer avec le code qu'il vérifie (une erreur dans `MOYENS_OFFERTS` doit se
voir).
/ The two equalities: all payments = catalogue totals; payments except "offered" (FREE)
= net sold. The offered list is written HERE, never imported from the service.

Les fabriques sont appelées DANS un test qui annule sa transaction à la fin (marque
`django_db`, ou `FastTenantTestCase`) et DANS le lieu du test : rien ne reste en base.
/ Called inside a rolled-back test and inside the test venue: nothing stays in the database.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md (§6)
et CHANTIER-05-montants-entiers.md (§2, §5, §8).
"""

from decimal import Decimal

from BaseBillet.models import (
    CategorieProduct,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    Tva,
)
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from fabriques_panier import identifiant_unique
from laboutik.models import CompteComptable
from laboutik.plan_comptable import CompteComptableManquant, compte_pour_produit

PREFIXE_DE_TEST_VENTE = "TEST_vente"

# La catégorie de caisse des produits de test : le préfixe la range avec eux (un
# nettoyage par préfixe la trouve).
# / The test products' POS category, named with their prefix.
NOM_DE_LA_CATEGORIE_DE_CAISSE_DE_TEST = f"{PREFIXE_DE_TEST_VENTE} Caisse 707000"


def categorie_de_caisse_de_test():
    """
    La catégorie de caisse des produits de test, reliée au compte des ventes de
    marchandises (707000) du plan du lieu. Créée si elle manque, réutilisée sinon.
    / The test products' POS category, linked to 707000; created if missing.

    :return: la `CategorieProduct`, ou None si le plan du lieu n'a pas de 707000
    """
    compte_des_ventes = CompteComptable.objects.filter(numero_de_compte="707000").first()
    if compte_des_ventes is None:
        return None
    categorie, _categorie_creee = CategorieProduct.objects.get_or_create(
        name=NOM_DE_LA_CATEGORIE_DE_CAISSE_DE_TEST,
        defaults={"compte_comptable": compte_des_ventes},
    )
    return categorie


def donner_un_compte_au_produit(produit):
    """
    Range le produit dans la catégorie de caisse de test s'il n'a pas de compte de vente
    (la règle du FEC, `compte_pour_produit`, lève `CompteComptableManquant`). Un produit
    qui a déjà un compte (par son type, son mode de caisse, une recharge…) n'est pas
    touché.
    / Files the product in the test POS category when it has no sales account.
    """
    try:
        compte_pour_produit(produit)
    except CompteComptableManquant:
        categorie = categorie_de_caisse_de_test()
        if categorie is None:
            return
        produit.categorie_pos = categorie
        produit.save(update_fields=["categorie_pos"])

# Les moyens « offerts » de l'oracle, écrits à la main (pas importés du service).
# / The oracle's "offered" methods, written by hand (not imported from the service).
MOYENS_OFFERTS_DE_L_ORACLE = [PaymentMethod.FREE]


def creer_tarif_vendu(
    nom="Article",
    prix_en_euros="5.00",
    taux_tva="20.00",
    methode_caisse=None,
    categorie_article=Product.NONE,
    avec_compte=True,
):
    """
    Crée un produit, son tarif, et le tarif vendu qu'une ligne d'article référence.
    / Creates a product, its price, and the sold price that a sale line points to.

    Le produit a un compte de vente : s'il n'en a pas par ses règles (type, mode de
    caisse…), il est rangé dans la catégorie de caisse de test (707000). Une vente
    encaissée par un test peut rester dans la base de dev (le lieu `lespass`) : sans
    compte, elle bloquerait l'export de la vraie journée.
    / The product has a sales account (test POS category when needed): a sale left in
    the dev database would otherwise block the real day's export.

    LOCALISATION : tests/pytest/fabriques_vente.py

    Le taux de TVA posé sur le produit n'est PAS celui de la ligne : le service de vente
    écrit le taux qu'on lui passe (`taux_tva` d'`ajouter_article`).
    / The product VAT is NOT the line VAT: the service writes the rate it is given.

    :param nom: début du nom du produit (un identifiant unique est ajouté)
    :param prix_en_euros: prix du tarif, en euros (texte, ex. "3.50")
    :param taux_tva: taux de TVA du produit, en pour cent (texte, ex. "20.00")
    :param methode_caisse: `Product.methode_caisse` (ex. `Product.RECHARGE_EUROS`), ou None
    :param categorie_article: `Product.categorie_article` (ex. `Product.RECHARGE_CASHLESS`)
    :param avec_compte: False pour un test qui veut un produit SANS compte (refus du FEC,
        « Plan complet ? »…)
    :return: le `PriceSold` créé
    """
    # Le taux est unique en base : on réutilise celui qui existe déjà.
    # / The rate is unique in the database: reuse the existing one.
    tva_du_produit, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal(taux_tva))
    produit = Product.objects.create(
        name=f"{PREFIXE_DE_TEST_VENTE} {nom} {identifiant_unique()}",
        categorie_article=categorie_article,
        methode_caisse=methode_caisse,
        tva=tva_du_produit,
    )
    if avec_compte:
        donner_un_compte_au_produit(produit)
    tarif = Price.objects.create(
        product=produit,
        name="Tarif unique",
        prix=Decimal(prix_en_euros),
        publish=True,
    )
    produit_vendu = ProductSold.objects.create(product=produit)
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu,
        price=tarif,
        prix=tarif.prix,
    )
    return tarif_vendu


def fabriquer_vente_encaissee(
    origine,
    articles=None,
    reglements=None,
    nature=Vente.Nature.VENTE,
    point_de_vente=None,
    operateur=None,
    carte=None,
    client=None,
):
    """
    Écrit une vente complète par le service de vente, puis l'encaisse.
    / Writes a full sale through the sale service, then settles it.

    LOCALISATION : tests/pytest/fabriques_vente.py

    FLUX :
    1. `ouvrir_vente(origine, nature, point_de_vente, operateur, client, carte)` : la vente
       naît « en attente » ;
    2. `ajouter_article(vente, **article)` pour chaque article ;
    3. `ajouter_reglement(vente, **reglement)` pour chaque règlement ;
    4. `encaisser_vente(vente)` : vérifie les deux égalités, pose le numéro.
    Si les égalités ne tiennent pas, l'étape 4 lève l'erreur du service : la fabrique ne
    l'attrape pas.
    / If the equalities do not hold, step 4 raises the service error, not caught here.

    :param origine: `SaleOrigin` (ex. `SaleOrigin.LABOUTIK`)
    :param articles: liste de dictionnaires, chacun passé tel quel à `ajouter_article`
        (ex. `{"pricesold": tarif_vendu, "quantite": Decimal("3"), "prix_unitaire": 350,
        "taux_tva": Decimal("20")}`) ; None = aucun article
    :param reglements: liste de dictionnaires, chacun passé tel quel à `ajouter_reglement`
        (ex. `{"moyen": PaymentMethod.CASH, "montant": 1050}`) ; None = aucun règlement
    :param nature: `Vente.Nature` (VENTE par défaut)
    :param point_de_vente: `laboutik.PointDeVente` de la vente, ou None (défaut)
    :param operateur: l'utilisateur qui fait la vente, ou None (défaut)
    :param carte: la `CarteCashless` du client de la vente, ou None (défaut)
    :param client: le `TibilletUser` acheteur de la vente, ou None (défaut)
    :return: la vente encaissée
    """
    # None plutôt qu'une liste vide en valeur par défaut : une liste par défaut serait
    # partagée entre tous les appels de la fonction.
    # / None rather than an empty list default: a default list is shared between calls.
    if articles is None:
        articles = []
    if reglements is None:
        reglements = []

    vente = ouvrir_vente(
        origine=origine,
        nature=nature,
        point_de_vente=point_de_vente,
        operateur=operateur,
        client=client,
        carte=carte,
    )

    for article in articles:
        ajouter_article(vente, **article)

    for reglement in reglements:
        ajouter_reglement(vente, **reglement)

    vente_encaissee = encaisser_vente(vente)
    return vente_encaissee


def verifier_egalites(vente):
    """
    Relit la vente en base et vérifie ses deux égalités, puis les totaux stockés.
    / Reads the sale back and checks its two equalities, then its stored totals.

    LOCALISATION : tests/pytest/fabriques_vente.py

    Vérifie, avec les valeurs relues en base (jamais celles gardées en mémoire) :
    1. Σ règlements                    = Σ totaux catalogue des articles ;
    2. Σ règlements hors « offert »    = Σ nets vendus des articles ;
    3. chaque total de la vente = la somme du même montant sur ses articles
       (catalogue, offert, net, HT, TVA).
    / Checks, with values read back from the database: both equalities, then each sale
    total equals the sum of its items.

    Pendant la transition (fiches B à G), un article payé avec deux moyens est coupé en
    « parts ». Le HT d'une part peut différer d'un centime du HT de l'article entier
    (tronc §5) : on ne compare donc JAMAIS le HT d'une part à un HT recalculé. On
    compare seulement le HT de la vente à la somme des HT écrits sur ses lignes.
    / During the transition, a part's HT may differ by one cent from the whole item's HT:
    only the sale HT is compared with the sum of the line HTs.

    :param vente: la vente à vérifier (seule sa clé est utilisée)
    """
    vente_relue = Vente.objects.get(pk=vente.pk)

    # Sommes des règlements, relues en base.
    # / Sums of the payments, read back.
    somme_de_tous_les_reglements = 0
    somme_des_reglements_hors_offert = 0
    for reglement in vente_relue.reglements.all():
        somme_de_tous_les_reglements += reglement.montant
        reglement_offert = reglement.moyen in MOYENS_OFFERTS_DE_L_ORACLE
        if not reglement_offert:
            somme_des_reglements_hors_offert += reglement.montant

    # Sommes des articles, relues en base.
    # / Sums of the items, read back.
    somme_des_totaux_catalogue = 0
    somme_des_parts_offertes = 0
    somme_des_nets_vendus = 0
    somme_des_totaux_ht = 0
    somme_des_totaux_tva = 0
    for article in vente_relue.articles.all():
        somme_des_totaux_catalogue += article.total_catalogue
        somme_des_parts_offertes += article.part_offerte
        somme_des_nets_vendus += article.total_ttc
        somme_des_totaux_ht += article.total_ht
        somme_des_totaux_tva += article.total_tva

    # 1ʳᵉ égalité : tout ce qui est réglé couvre le prix catalogue.
    # / 1st equality: all payments cover the catalogue price.
    assert somme_de_tous_les_reglements == somme_des_totaux_catalogue, (
        f"Σ règlements ({somme_de_tous_les_reglements}) doit valoir "
        f"Σ totaux catalogue ({somme_des_totaux_catalogue})."
    )

    # 2ᵉ égalité : l'argent réglé (hors offert) couvre le net vendu.
    # / 2nd equality: the money paid (offered excluded) covers the net sold.
    assert somme_des_reglements_hors_offert == somme_des_nets_vendus, (
        f"Σ règlements hors offert ({somme_des_reglements_hors_offert}) doit valoir "
        f"Σ nets vendus ({somme_des_nets_vendus})."
    )

    # Les totaux stockés sur la vente sont les sommes de ses articles.
    # / The totals stored on the sale are the sums of its items.
    assert vente_relue.total_catalogue == somme_des_totaux_catalogue, (
        f"Vente.total_catalogue ({vente_relue.total_catalogue}) doit valoir "
        f"Σ articles ({somme_des_totaux_catalogue})."
    )
    assert vente_relue.total_offert == somme_des_parts_offertes, (
        f"Vente.total_offert ({vente_relue.total_offert}) doit valoir "
        f"Σ parts offertes ({somme_des_parts_offertes})."
    )
    assert vente_relue.total_ttc == somme_des_nets_vendus, (
        f"Vente.total_ttc ({vente_relue.total_ttc}) doit valoir "
        f"Σ nets vendus ({somme_des_nets_vendus})."
    )
    assert vente_relue.total_ht == somme_des_totaux_ht, (
        f"Vente.total_ht ({vente_relue.total_ht}) doit valoir "
        f"Σ HT des articles ({somme_des_totaux_ht})."
    )
    assert vente_relue.total_tva == somme_des_totaux_tva, (
        f"Vente.total_tva ({vente_relue.total_tva}) doit valoir "
        f"Σ TVA des articles ({somme_des_totaux_tva})."
    )


def abonner_aux_envois_des_rapports(
    *adresses,
    recap_quotidien=True,
    hebdomadaire=True,
    mensuel=True,
    annuel=True,
):
    """
    Règle les envois du lieu courant (`ConfigurationDesRapports`) : les quatre cases,
    TOUJOURS écrites, puis une personne du lieu par adresse, ajoutée aux destinataires.
    / Sets the current venue's mail settings: the four ticks, always written, then one
    venue person per address, added to the recipients.

    LOCALISATION : tests/pytest/fabriques_vente.py

    Les quatre cases sont écrites à chaque appel : le cache de django-solo survit au
    rollback d'un test, une case décochée par un test précédent resterait sinon en cache.
    Chaque personne est mise dans `client_achat` du lieu : le M2M vise le proxy
    HumanUser, dont le manager ne rend que les personnes du lieu.
    / The four ticks are always written: the solo cache survives a test's rollback.
    Each person joins the venue's client_achat: the M2M targets HumanUser.

    :return: la liste des personnes créées / the created people
    """
    from django.db import connection

    from AuthBillet.models import TibilletUser
    from comptabilite.models import ConfigurationDesRapports

    reglages_des_envois = ConfigurationDesRapports.get_solo()
    reglages_des_envois.envoyer_le_recap_quotidien = recap_quotidien
    reglages_des_envois.envoyer_le_rapport_hebdomadaire = hebdomadaire
    reglages_des_envois.envoyer_le_rapport_mensuel = mensuel
    reglages_des_envois.envoyer_le_rapport_annuel = annuel
    reglages_des_envois.save()

    personnes = []
    for adresse in adresses:
        personne, _cree = TibilletUser.objects.get_or_create(
            email=adresse, defaults={"username": adresse}
        )
        personne.client_achat.add(connection.tenant)
        reglages_des_envois.destinataires.add(personne.pk)
        personnes.append(personne)
    return personnes

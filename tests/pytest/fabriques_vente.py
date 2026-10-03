"""
Fabrique de ventes pour les tests, et vérification des deux égalités d'une vente.
/ Sale factory for the tests, and check of the two equalities of a sale.

LOCALISATION : tests/pytest/fabriques_vente.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_vente import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

CE QUE PORTE CE MODULE
- `creer_tarif_vendu(...)` : un produit, son tarif et le tarif vendu qu'une ligne d'article
  référence (`LigneArticle.pricesold`).
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

from BaseBillet.models import PaymentMethod, Price, PriceSold, Product, ProductSold, Tva
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from fabriques_panier import identifiant_unique

PREFIXE_DE_TEST_VENTE = "TEST_vente"

# Les moyens « offerts » de l'oracle, écrits à la main (pas importés du service).
# / The oracle's "offered" methods, written by hand (not imported from the service).
MOYENS_OFFERTS_DE_L_ORACLE = [PaymentMethod.FREE]


def creer_tarif_vendu(
    nom="Article",
    prix_en_euros="5.00",
    taux_tva="20.00",
    methode_caisse=None,
    categorie_article=Product.NONE,
):
    """
    Crée un produit, son tarif, et le tarif vendu qu'une ligne d'article référence.
    / Creates a product, its price, and the sold price that a sale line points to.

    LOCALISATION : tests/pytest/fabriques_vente.py

    Le taux de TVA posé sur le produit n'est PAS celui de la ligne : le service de vente
    écrit le taux qu'on lui passe (`taux_tva` d'`ajouter_article`).
    / The product VAT is NOT the line VAT: the service writes the rate it is given.

    :param nom: début du nom du produit (un identifiant unique est ajouté)
    :param prix_en_euros: prix du tarif, en euros (texte, ex. "3.50")
    :param taux_tva: taux de TVA du produit, en pour cent (texte, ex. "20.00")
    :param methode_caisse: `Product.methode_caisse` (ex. `Product.RECHARGE_EUROS`), ou None
    :param categorie_article: `Product.categorie_article` (ex. `Product.RECHARGE_CASHLESS`)
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
):
    """
    Écrit une vente complète par le service de vente, puis l'encaisse.
    / Writes a full sale through the sale service, then settles it.

    LOCALISATION : tests/pytest/fabriques_vente.py

    FLUX :
    1. `ouvrir_vente(origine, nature)` : la vente naît « en attente » ;
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
    :return: la vente encaissée
    """
    # None plutôt qu'une liste vide en valeur par défaut : une liste par défaut serait
    # partagée entre tous les appels de la fonction.
    # / None rather than an empty list default: a default list is shared between calls.
    if articles is None:
        articles = []
    if reglements is None:
        reglements = []

    vente = ouvrir_vente(origine=origine, nature=nature)

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

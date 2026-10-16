"""
Une vente TiBillet telle qu'un logiciel de facturation (Dolibarr) la recopie.
/ A TiBillet sale as an invoicing software (Dolibarr) copies it.

LOCALISATION : comptabilite/ventes_a_facturer.py

Spec : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/
CHANTIER-06-D-ventes.md (mode « articles et ventes »).

LA RÈGLE DE DÉCOUPE (FALC)
1. Les lignes de la facture : les articles du chiffre d'affaires dont le TTC n'est pas
   nul. La part payée en jetons cadeau devient une ligne à part (compte 707900, TVA 0,
   sans tarif). Le reste garde le tarif vendu, son compte et son taux. Un retour de
   consigne porte le premier tarif en euros du gobelet.
2. Les soldes de trésorerie : les règlements de la vente ET de ses ventes CORRECTION,
   additionnés par compte de trésorerie (`compte_pour_reglement`). L'offert et les
   points n'ont pas de compte : ils ne comptent pas.
3. Une recharge (article hors chiffre d'affaires, `est_une_recharge`) fait baisser le
   solde du compte de la monnaie. Sa part offerte devient un paiement divers sur ce
   compte, contrepartie « cadeaux à la clientèle » (623400).
4. Les autres articles hors chiffre d'affaires (écart d'encaissement, jetons repris,
   virement reçu…) sont des besoins : leur TTC, avec leur compte en contrepartie.
5. La répartition : chaque besoin (les hors chiffre d'affaires d'abord, la facture
   ensuite) prend sur les soldes de même signe, dans l'ordre. Ce qui reste est pris
   sur le premier solde. Un besoin hors chiffre d'affaires donne des paiements divers,
   la facture donne ses paiements.
6. Les virements : ce qui reste des soldes fait zéro au total. Un solde négatif envoie
   vers un solde positif, jusqu'à ce que tout soit nul.
Compte par compte, le résultat est celui du FEC de la même J : seuls les règlements
et les articles sont lus, et toute somme est gardée (test :
tests/pytest/test_fec_equilibre.py, `test_ventes_a_facturer_egales_au_fec_compte_par_compte`).
/ The split rule: invoice lines, treasury balances, top-ups, other off-revenue items,
allocation, then transfers. Per account, the result equals the FEC.

LU PAR : api_v2/views.py (`ClosureViewSet.sales`).
"""

from decimal import Decimal

from django.db.models import Prefetch

from BaseBillet.models import LigneArticle, Product
from BaseBillet.models_vente import Vente
from laboutik.plan_comptable import (
    compte_de_tva_pour_taux,
    compte_des_cadeaux_a_la_clientele,
    compte_des_ventes_reglees_en_jetons,
    compte_pour_article,
    compte_pour_reglement,
    comptes_du_plan_par_defaut_du_lieu,
    est_une_recharge,
)

# La nature d'une vente, telle que l'API la publie.
# / A sale's nature, as the API publishes it.
NATURE_PUBLIEE = {
    Vente.Nature.VENTE: "sale",
    Vente.Nature.AVOIR: "refund",
    Vente.Nature.VIDAGE_CARTE: "card_emptying",
}

LIBELLE_DE_LA_RECHARGE_OFFERTE = "Recharge offerte"
LIBELLE_DU_VIREMENT_DE_RECHARGE = "Recharge cashless"
LIBELLE_DU_VIREMENT_DE_VIDAGE = "Vidage de carte"


class RepartitionImpossible(Exception):
    """
    Les règlements d'une vente ne couvrent pas ses articles : la vente ne peut pas
    être recopiée.
    / A sale's payments do not cover its items.
    """


def _libelle_du_tarif(tarif):
    """« Produit — Tarif », comme le catalogue (06-C). / "Product — Price"."""
    return f"{tarif.product.name} — {tarif.name}"


def _premier_tarif_en_euros(produit):
    """
    Le premier tarif en euros (sans monnaie TiBillet) d'un produit, dans l'ordre du
    catalogue, ou None.
    / A product's first euro price, in catalogue order, or None.
    """
    return produit.prices.filter(asset__isnull=True).order_by("order", "uuid").first()


def _compte_de_tva(taux, compte_de_tva_par_taux):
    """Le compte de TVA d'un taux, lu une fois par taux. / VAT account, once per rate."""
    if taux not in compte_de_tva_par_taux:
        compte_de_tva_par_taux[taux] = compte_de_tva_pour_taux(taux)
    return compte_de_tva_par_taux[taux]


def _lignes_de_la_facture(vente, comptes_du_plan_par_defaut, compte_de_tva_par_taux):
    """
    Les lignes de la facture d'une vente (point 1 de la règle).
    / A sale's invoice lines (rule point 1).
    """
    lignes = []
    for article in vente.articles.all():
        if article.hors_chiffre_affaires:
            continue
        if article.total_ttc == 0:
            continue

        produit = article.pricesold.productsold.product
        libelle = _libelle_du_tarif(article.pricesold.price)

        # Le compte d'abord : pour un retour de consigne sans gobelet relié, c'est la
        # règle du compte qui lève sa phrase (comme le FEC), avant toute lecture du
        # gobelet.
        # / The account first: the rule raises its sentence for an orphan return.
        compte_de_l_article = compte_pour_article(article, comptes_du_plan_par_defaut)

        # Le tarif recopié : le tarif vendu, sauf pour un retour de consigne, qui
        # reprend le premier tarif en euros du gobelet (spec Q6).
        # / The copied price: the sold one, except for a deposit return.
        tarif = article.pricesold.price
        if produit.methode_caisse == Product.RETOUR_CONSIGNE:
            tarif = _premier_tarif_en_euros(produit.consigne_remboursee)

        part_en_jetons = article.part_en_jetons
        if part_en_jetons != 0:
            lignes.append(
                {
                    "tarif": None,
                    "libelle": f"Part payée en jetons — {libelle}",
                    "quantite": Decimal("1"),
                    "prix_unitaire_ttc": part_en_jetons,
                    "total_ttc": part_en_jetons,
                    "total_ht": part_en_jetons,
                    "total_tva": 0,
                    "taux_de_tva": Decimal("0"),
                    "compte": compte_des_ventes_reglees_en_jetons(
                        comptes_du_plan_par_defaut
                    ),
                    "compte_de_tva": None,
                }
            )

        total_ttc_du_reste = article.total_ttc - part_en_jetons
        if total_ttc_du_reste == 0:
            continue

        compte_de_tva = None
        if article.vat != 0:
            compte_de_tva = _compte_de_tva(article.vat, compte_de_tva_par_taux)

        lignes.append(
            {
                "tarif": tarif,
                "libelle": libelle,
                "quantite": article.qty,
                "prix_unitaire_ttc": article.amount,
                "total_ttc": total_ttc_du_reste,
                "total_ht": article.total_ht - part_en_jetons,
                "total_tva": article.total_tva,
                "taux_de_tva": article.vat,
                "compte": compte_de_l_article,
                "compte_de_tva": compte_de_tva,
            }
        )
    return lignes


def _reglements_nets(vente):
    """
    Les règlements de la vente et ceux de ses ventes CORRECTION : la même règle que
    `laboutik/affichage_des_ventes.py` `reglements_nets_de_la_vente`, sans les
    additionner par moyen.
    / The sale's payments plus its CORRECTION sales' payments.
    """
    reglements = list(vente.reglements.all())
    for vente_derivee in vente.ventes_derivees.all():
        if vente_derivee.nature != Vente.Nature.CORRECTION:
            continue
        for reglement_de_la_correction in vente_derivee.reglements.all():
            reglements.append(reglement_de_la_correction)
    return reglements


def _ajouter_au_solde(soldes, compte, moyen, montant):
    """
    Ajoute un montant au solde d'un compte de trésorerie. Le compte garde le moyen de
    son premier règlement (None pour un compte vu par une recharge seulement).
    / Adds a sum to a treasury account's balance; keeps its first payment method.
    """
    numero_du_compte = compte.numero_de_compte
    if numero_du_compte not in soldes:
        soldes[numero_du_compte] = {"compte": compte, "moyen": moyen, "solde": 0}
    if soldes[numero_du_compte]["moyen"] is None:
        soldes[numero_du_compte]["moyen"] = moyen
    soldes[numero_du_compte]["solde"] += montant


def _prendre_sur_les_soldes(soldes, montant_du_besoin):
    """
    Prend un besoin sur les soldes (point 5 de la règle) : d'abord sur les soldes de
    même signe, dans l'ordre ; ce qui reste, sur le premier solde.
    / Takes a need from the balances: same sign first, the rest from the first one.

    :return: liste de (solde, montant pris)
    """
    prises = []
    reste = montant_du_besoin
    for solde in soldes.values():
        if reste == 0:
            break
        meme_signe = (solde["solde"] > 0 and reste > 0) or (
            solde["solde"] < 0 and reste < 0
        )
        if not meme_signe:
            continue
        if reste > 0:
            montant_pris = min(reste, solde["solde"])
        else:
            montant_pris = max(reste, solde["solde"])
        solde["solde"] -= montant_pris
        reste -= montant_pris
        prises.append((solde, montant_pris))

    if reste != 0:
        premier_solde = next(iter(soldes.values()))
        premier_solde["solde"] -= reste
        prises.append((premier_solde, reste))
    return prises


def _virements_qui_soldent(soldes, libelle):
    """
    Les virements internes qui mettent tous les soldes à zéro (point 6 de la règle) :
    chaque solde négatif envoie vers les soldes positifs, dans l'ordre.
    / The internal transfers that bring every balance to zero.
    """
    virements = []
    soldes_negatifs = []
    soldes_positifs = []
    for solde in soldes.values():
        if solde["solde"] < 0:
            soldes_negatifs.append(solde)
        if solde["solde"] > 0:
            soldes_positifs.append(solde)

    for depuis in soldes_negatifs:
        for vers in soldes_positifs:
            if depuis["solde"] == 0:
                break
            montant = min(-depuis["solde"], vers["solde"])
            if montant == 0:
                continue
            virements.append(
                {
                    "depuis": depuis["compte"],
                    "moyen_depuis": depuis["moyen"],
                    "vers": vers["compte"],
                    "moyen_vers": vers["moyen"],
                    "montant": montant,
                    "libelle": libelle,
                }
            )
            depuis["solde"] += montant
            vers["solde"] -= montant
    return virements


def vente_a_facturer(
    vente,
    comptes_du_plan_par_defaut,
    compte_par_moyen_et_monnaie,
    compte_de_tva_par_taux,
):
    """
    Une vente découpée pour un logiciel de facturation (la règle en tête du module).
    / A sale split for an invoicing software.

    LES DICT DES COMPTES DÉJÀ LUS : comme `ventiler_cloture`, l'appelant qui découpe
    plusieurs ventes les crée une fois et les passe à chaque vente.
    / Already-read account dicts, shared by the caller like ventiler_cloture.

    :param vente: une `Vente` REGLEE en euros, d'une autre nature que CORRECTION, avec
        ses articles (et leur produit), ses règlements et ses ventes dérivées (et leurs
        règlements) préchargés pour ne faire aucune requête par vente
    :param comptes_du_plan_par_defaut: dict de `comptes_du_plan_par_defaut_du_lieu()`
    :param compte_par_moyen_et_monnaie: dict {(moyen, monnaie): compte}
    :param compte_de_tva_par_taux: dict {taux: compte}
    :return: None si la vente n'a rien à écrire ; sinon un dict
        {"vente", "nature", "client", "lignes_de_la_facture",
         "paiements_de_la_facture", "virements", "paiements_divers"} (voir
        CHANTIER-06-D-PLAN.md, tâche 2) ; montants en centimes entiers
    :raises RepartitionImpossible: si les règlements ne couvrent pas les articles
    :raises CompteComptableManquant: si un compte manque (règle du FEC)
    """
    lignes_de_la_facture = _lignes_de_la_facture(
        vente, comptes_du_plan_par_defaut, compte_de_tva_par_taux
    )

    # 2. Les soldes de trésorerie. / 2. Treasury balances.
    soldes = {}
    for reglement in _reglements_nets(vente):
        cle_du_moyen_et_de_la_monnaie = (reglement.moyen, reglement.asset)
        if cle_du_moyen_et_de_la_monnaie not in compte_par_moyen_et_monnaie:
            compte_par_moyen_et_monnaie[cle_du_moyen_et_de_la_monnaie] = (
                compte_pour_reglement(reglement.moyen, reglement.asset)
            )
        compte_du_reglement = compte_par_moyen_et_monnaie[cle_du_moyen_et_de_la_monnaie]
        if compte_du_reglement is None:
            continue
        _ajouter_au_solde(
            soldes, compte_du_reglement, reglement.moyen, reglement.montant
        )

    # 3 et 4. Les articles hors chiffre d'affaires. / 3 and 4. Off-revenue items.
    paiements_divers = []
    besoins_hors_facture = []
    for article in vente.articles.all():
        if not article.hors_chiffre_affaires:
            continue
        produit = article.pricesold.productsold.product
        compte_de_l_article = compte_pour_article(article, comptes_du_plan_par_defaut)

        if est_une_recharge(produit):
            if article.total_ttc != 0:
                _ajouter_au_solde(soldes, compte_de_l_article, None, -article.total_ttc)
            if article.part_offerte != 0:
                paiements_divers.append(
                    {
                        "compte_de_tresorerie": compte_de_l_article,
                        "moyen": None,
                        "montant": -article.part_offerte,
                        "contrepartie": compte_des_cadeaux_a_la_clientele(
                            comptes_du_plan_par_defaut
                        ),
                        "libelle": LIBELLE_DE_LA_RECHARGE_OFFERTE,
                    }
                )
            continue

        if article.total_ttc != 0:
            besoins_hors_facture.append(
                {
                    "montant": article.total_ttc,
                    "contrepartie": compte_de_l_article,
                    "libelle": _libelle_du_tarif(article.pricesold.price),
                }
            )

    total_de_la_facture = 0
    for ligne in lignes_de_la_facture:
        total_de_la_facture += ligne["total_ttc"]

    # Rien à écrire : ni ligne, ni besoin, ni mouvement d'argent.
    # / Nothing to write.
    aucun_solde = True
    for solde in soldes.values():
        if solde["solde"] != 0:
            aucun_solde = False
    if (
        not lignes_de_la_facture
        and not besoins_hors_facture
        and not paiements_divers
        and aucun_solde
    ):
        return None

    # Les règlements couvrent-ils les articles ? / Do payments cover the items?
    total_des_soldes = 0
    for solde in soldes.values():
        total_des_soldes += solde["solde"]
    total_des_besoins = total_de_la_facture
    for besoin in besoins_hors_facture:
        total_des_besoins += besoin["montant"]
    if total_des_soldes != total_des_besoins or (total_des_besoins != 0 and not soldes):
        raise RepartitionImpossible(
            f"Vente n° {vente.numero} : les règlements ({total_des_soldes} centimes) "
            f"ne couvrent pas les articles ({total_des_besoins} centimes)."
        )

    # 5. La répartition. / 5. Allocation.
    for besoin in besoins_hors_facture:
        for solde, montant_pris in _prendre_sur_les_soldes(soldes, besoin["montant"]):
            paiements_divers.append(
                {
                    "compte_de_tresorerie": solde["compte"],
                    "moyen": solde["moyen"],
                    "montant": montant_pris,
                    "contrepartie": besoin["contrepartie"],
                    "libelle": besoin["libelle"],
                }
            )

    paiements_de_la_facture = []
    if total_de_la_facture != 0:
        for solde, montant_pris in _prendre_sur_les_soldes(soldes, total_de_la_facture):
            paiements_de_la_facture.append(
                {
                    "compte": solde["compte"],
                    "moyen": solde["moyen"],
                    "montant": montant_pris,
                }
            )

    # 6. Les virements. / 6. Transfers.
    libelle_des_virements = LIBELLE_DU_VIREMENT_DE_RECHARGE
    if vente.nature == Vente.Nature.VIDAGE_CARTE:
        libelle_des_virements = LIBELLE_DU_VIREMENT_DE_VIDAGE
    virements = _virements_qui_soldent(soldes, libelle_des_virements)

    return {
        "vente": vente,
        "nature": NATURE_PUBLIEE[vente.nature],
        "client": vente.client,
        "lignes_de_la_facture": lignes_de_la_facture,
        "paiements_de_la_facture": paiements_de_la_facture,
        "virements": virements,
        "paiements_divers": paiements_divers,
    }


def ventes_a_facturer_de_la_cloture(
    cloture_j, apres_le_numero=None, nombre_au_plus=None
):
    """
    Les ventes d'une clôture J, découpées pour un logiciel de facturation, dans
    l'ordre des numéros. Les ventes sans montant sont retirées.
    / A J closure's sales, split for an invoicing software, by number.

    LOCALISATION : comptabilite/ventes_a_facturer.py

    Ventes lues : REGLEE, en euros, de la plage de numéros de la J, sauf les
    CORRECTION (leurs règlements sont ajoutés à la vente corrigée). Toutes les
    données sont lues en un nombre fixe de requêtes (préchargement).
    / Settled euro sales of the J's range, except CORRECTION ones; fixed query count.

    :param cloture_j: une `ClotureCaisse` J avec une plage de ventes
    :param apres_le_numero: ne garder que les ventes de numéro plus grand, ou None
    :param nombre_au_plus: au plus ce nombre de ventes LUES, ou None
    :return: (liste des dict de `vente_a_facturer`, sans les None ; numéro de la
        dernière vente LUE, ou None si aucune). Le numéro sert de curseur : une vente
        sans montant est lue mais pas rendue.
    """
    articles_avec_leur_produit = LigneArticle.objects.select_related(
        "pricesold__price__product",
        "pricesold__productsold__product__categorie_pos__compte_comptable",
        "pricesold__productsold__product__consigne_remboursee__categorie_pos__compte_comptable",
    )
    ventes_de_la_j = (
        Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            unite="EUR",
            numero__gte=cloture_j.numero_premiere_vente,
            numero__lte=cloture_j.numero_derniere_vente,
        )
        .exclude(nature=Vente.Nature.CORRECTION)
        .select_related("client", "vente_liee")
        .prefetch_related(
            "reglements",
            "ventes_derivees__reglements",
            Prefetch("articles", queryset=articles_avec_leur_produit),
        )
        .order_by("numero")
    )
    if apres_le_numero is not None:
        ventes_de_la_j = ventes_de_la_j.filter(numero__gt=apres_le_numero)
    if nombre_au_plus is not None:
        ventes_de_la_j = ventes_de_la_j[:nombre_au_plus]

    comptes_du_plan_par_defaut = comptes_du_plan_par_defaut_du_lieu()
    compte_par_moyen_et_monnaie = {}
    compte_de_tva_par_taux = {}
    ventes_decoupees = []
    numero_de_la_derniere_vente_lue = None
    for vente in ventes_de_la_j:
        numero_de_la_derniere_vente_lue = vente.numero
        decoupe = vente_a_facturer(
            vente,
            comptes_du_plan_par_defaut,
            compte_par_moyen_et_monnaie,
            compte_de_tva_par_taux,
        )
        if decoupe is not None:
            ventes_decoupees.append(decoupe)
    return ventes_decoupees, numero_de_la_derniere_vente_lue

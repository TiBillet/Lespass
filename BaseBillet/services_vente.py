"""
Service de vente : le seul point d'entrée pour écrire l'argent d'une vente.
/ Sale service: the only entry point to write the money of a sale.

LOCALISATION : BaseBillet/services_vente.py

Ce module porte LA formule d'argent du projet : `calculer_montants_article`. Toute ligne
d'article vendu reçoit ses montants de cette fonction, et de nulle part ailleurs.
/ This module holds THE money formula of the project.

LA RÈGLE D'OR
L'argent n'est jamais recalculé. Il est écrit une seule fois, en centimes entiers, au
moment de la vente, puis il est seulement additionné. Jamais `amount × qty` dans un
rapport, jamais `round()` (arrondi au pair), jamais `int()` (troncature).
/ Money is never recomputed: written once in whole cents, then only summed.

FLUX D'UNE VENTE / FLOW OF A SALE :
1. `ouvrir_vente(...)` : la vente naît EN_ATTENTE, sans numéro ;
2. `ajouter_article(vente, ...)` pour chaque article : appelle
   `calculer_montants_article`, puis crée la `LigneArticle` en un seul INSERT ;
3. `ajouter_reglement(vente, ...)` pour chaque règlement (montant copié de sa source) ;
4. `encaisser_vente(vente)` : sous verrou, vérifie les deux égalités, pose le numéro,
   les totaux et l'empreinte chaînée, passe la vente à REGLEE. Ou
   `annuler_vente(vente)` : ANNULEE.
/ open, add items, add payments, then settle (or cancel).

Les modèles sont dans BaseBillet/models_vente.py (`Vente`, `Reglement`) et
BaseBillet/models.py (`LigneArticle`). Une fois la vente REGLEE, leurs `save()`
refusent toute modification de l'argent (garde d'immutabilité).
/ Models live in models_vente.py and models.py; their save() guard a settled sale.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-montants-entiers.md (§2)
et CHANTIER-05-A-vente-reglement.md (§3).
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from BaseBillet.models import (
    CategorieProduct,
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from laboutik.integrity import calculer_hmac_vente
from laboutik.models import LaboutikConfiguration

logger = logging.getLogger(__name__)

# Les moyens « offerts » : ils gardent la trace d'un cadeau (bouton OFFRIR, recharge
# cadeau), mais ce n'est pas de l'argent encaissé. Un règlement « offert » compte dans
# « Σ règlements = Σ totaux catalogue », pas dans « Σ règlements = Σ nets vendus ».
# FREE vaut "NA" en base.
# Les jetons cadeau (LG) n'en font PAS partie : un jeton dépensé solde la dette du lieu
# envers le porteur (D8 bis). Son règlement est un vrai règlement, il compte dans les
# deux égalités.
# / "Offered" payment methods: a trace of a gift, not collected money. Gift tokens (LG)
# are NOT offered: a spent token settles the venue's debt (D8 bis).
MOYENS_OFFERTS = [PaymentMethod.FREE]

# Les moyens qui ne sont pas des encaissements, pour les rapports : les moyens offerts,
# et les points ou le temps (NM), qui ne sont pas de l'argent.
# TODO fiche H : aucun lecteur, à retirer.
# / Payment methods that are not collections. TODO sheet H: no reader, to remove.
MOYENS_HORS_ENCAISSEMENT = MOYENS_OFFERTS + [PaymentMethod.NON_MONETAIRE]

# Les méthodes de caisse d'un produit dont la vente est hors chiffre d'affaires :
# recharges (euros, cadeau, temps), virement du pot central, fidélité. Hors chiffre
# d'affaires ne veut pas dire invisible : ces articles restent dans le Z et le FEC.
# Les catégories RECHARGE_CASHLESS et RECHARGE_CASHLESS_FED (recharges en ligne, sans
# méthode de caisse) sont aussi hors chiffre d'affaires : voir `ajouter_article`.
# / POS methods whose sale is off revenue (still visible in the Z report and the FEC).
METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES = [
    Product.RECHARGE_EUROS,
    Product.RECHARGE_CADEAU,
    Product.RECHARGE_TEMPS,
    Product.VIREMENT_RECU,
    Product.FIDELITE,
]

# Les natures de vente qui peuvent n'avoir aucun article : leurs règlements s'annulent.
# / Sale natures that may have no item: their payments cancel each other out.
NATURES_SANS_ARTICLE_ACCEPTEES = [Vente.Nature.VIDAGE_CARTE, Vente.Nature.CORRECTION]

# Les noms des deux produits système « Écart d'encaissement » (et de leurs catégories).
# Ce sont des DONNÉES en base, comme tout nom de produit : jamais `_()`. Traduits, ils
# changeraient avec la langue active, et `get_or_create` créerait un second produit
# par langue (la fiche E relie chaque catégorie à un compte : 758 / 658).
# / Names of the two "collection gap" system products: database DATA, never `_()`,
# otherwise `get_or_create` would create one product per language.
NOM_ECART_RECU_EN_PLUS = "Écart d'encaissement — reçu en plus"
NOM_ECART_RECU_EN_MOINS = "Écart d'encaissement — reçu en moins"

# Le nom du produit système des jetons cadeau repris au vidage d'une carte (et de sa
# catégorie). Une DONNÉE, jamais `_()`, pour la même raison que les écarts. Le plan
# comptable le reconnaît par ce nom (623400 : la dette des jetons perdus est annulée,
# D8 bis) ; `laboutik/plan_comptable_par_defaut.py` en garde une copie.
# / Name of the "gift tokens taken back at card emptying" system product: DATA, never
# `_()`. The chart of accounts recognises it by this name (623400).
NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE = "Jetons cadeau repris au vidage"


class EgaliteDeVenteRompue(Exception):
    """
    Les règlements d'une vente ne couvrent pas exactement ses articles : la vente ne
    peut pas être encaissée. Le message donne les deux sommes comparées.
    / The payments of a sale do not exactly match its items: it cannot be settled.

    LOCALISATION : BaseBillet/services_vente.py (levée par `encaisser_vente`)
    """


def arrondir_au_centime_demi_haut(montant_exact):
    """
    Arrondit un montant exact (Decimal) au centime entier, 0,5 vers le haut.
    / Rounds an exact amount to a whole cent, 0.5 going up.

    LOCALISATION : BaseBillet/services_vente.py

    451,5 → 452 ; 92,5 → 93 ; −833,3 → −833. Sur un nombre négatif, 0,5 s'éloigne de
    zéro (−0,5 → −1) : un avoir est l'exact opposé de la vente.
    / On negatives, 0.5 goes away from zero: a credit note mirrors the sale.
    """
    montant_arrondi = montant_exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    # Ce `int()` ne tronque rien : le `Decimal` est déjà arrondi au centime entier.
    # / This int() truncates nothing: the Decimal is already rounded to a whole cent.
    return int(montant_arrondi)


def calculer_montants_article(
    prix_unitaire,
    quantite,
    taux_tva,
    part_offerte=0,
    prix_achat=0,
    total_catalogue_impose=None,
    quantite_pour_cout=None,
):
    """
    Calcule les montants d'un article vendu, en centimes entiers.
    C'est la SEULE formule d'argent du projet.
    / Computes the amounts of a sold item, in whole cents. The ONLY money formula.

    LOCALISATION : BaseBillet/services_vente.py

    LA FORMULE :
        total_catalogue = arrondi_demi_haut(prix_unitaire × quantite)
        net_vendu       = total_catalogue − part_offerte
        total_ht        = arrondi_demi_haut(net_vendu × 100 / (100 + taux_tva))
        total_tva       = net_vendu − total_ht
        cout_achat      = arrondi_demi_haut(quantité réelle × prix_achat), vide si prix_achat = 0

    La TVA est la DIFFÉRENCE entre le net et le HT : HT + TVA = net, toujours.
    / VAT is the DIFFERENCE between net and excl. tax: HT + VAT = net, always.

    LES TYPES REÇUS (sinon ValueError, avant tout calcul) :
    - les centimes (`prix_unitaire`, `part_offerte`, `prix_achat`,
      `total_catalogue_impose`) sont des `int`, et rien d'autre ;
    - `quantite`, `quantite_pour_cout` et `taux_tva` sont des `Decimal` ou des `int`,
      jamais des `float`.
    / Cents are int only; quantities and VAT rate are Decimal or int, never float.

    :param prix_unitaire: prix unitaire TTC en centimes (int), comme `LigneArticle.amount`
    :param quantite: la quantité vendue (Decimal ou int) ; négative pour un avoir
    :param taux_tva: le taux de TVA en pour cent (Decimal ou int, ex. Decimal("5.5"))
    :param part_offerte: les centimes offerts (int), entre 0 et le total catalogue (même
        signe que lui pour un avoir) ; sinon ValueError
    :param prix_achat: prix d'achat du produit en centimes (int), dans l'unité de vente
        (pièce, kg, L) ; 0 veut dire « inconnu »
    :param total_catalogue_impose: pendant la transition (fiches B, C), l'argent réel
        d'une « part » d'article payée avec plusieurs moyens (int) ; repris tel quel au
        lieu de prix × quantité. Retiré en fiche H.
    :param quantite_pour_cout: la quantité réellement servie (Decimal ou int), dans
        l'unité du prix d'achat, quand `quantite` ne l'est pas (vente au poids avec
        qty = 1, part) ; None → `quantite`
    :return: dict d'entiers : total_catalogue, part_offerte, total_ttc, total_ht,
        total_tva, cout_achat (None si le prix d'achat est inconnu)
    """
    # 0. Les centimes reçus sont des `int`. Un `Decimal` ou un `float` serait un montant
    # recalculé ailleurs, qu'on refuse au lieu de l'arrondir ici en silence.
    # `type(...) is int` et non `isinstance` : un booléen est aussi un `int` en Python.
    # / 0. Received cents are int only (a bool is also an int in Python: refused).
    centimes_recus = {
        "prix_unitaire": prix_unitaire,
        "part_offerte": part_offerte,
        "prix_achat": prix_achat,
    }
    for nom_du_montant, montant_recu in centimes_recus.items():
        if type(montant_recu) is not int:
            raise ValueError(
                f"Le montant « {nom_du_montant} » doit être un entier en centimes, "
                f"reçu : {montant_recu!r}"
            )

    # 0 bis. La quantité, la quantité pour le coût et le taux de TVA sont exacts : des
    # `Decimal` ou des `int`. Un `float` n'est pas exact : `Decimal(0.35)` vaut
    # 0,34999…, et 1290 × 0,35 donnerait 451 au lieu de 452. Le refus vaut toujours,
    # même quand la valeur ne sert pas au calcul (quantité pour le coût sans prix
    # d'achat) : une seule règle.
    # / 0 bis. Quantities and VAT rate must be exact (Decimal or int), never float.
    valeurs_exactes_recues = {
        "quantite": quantite,
        "taux_tva": taux_tva,
        "quantite_pour_cout": quantite_pour_cout,
    }
    for nom_de_la_valeur, valeur_recue in valeurs_exactes_recues.items():
        quantite_pour_cout_absente = (
            nom_de_la_valeur == "quantite_pour_cout" and valeur_recue is None
        )
        if quantite_pour_cout_absente:
            continue
        valeur_exacte = type(valeur_recue) is int or type(valeur_recue) is Decimal
        if not valeur_exacte:
            raise ValueError(
                f"« {nom_de_la_valeur} » doit être un Decimal ou un int, reçu : "
                f"{valeur_recue!r}. Un float n'est pas exact : passer par exemple "
                f'Decimal("0.35").'
            )

    # 1. Total catalogue : imposé par le producteur (part), sinon prix × quantité.
    # / 1. Catalogue total: imposed by the producer (a part), otherwise price × quantity.
    if total_catalogue_impose is None:
        montant_exact_du_catalogue = Decimal(prix_unitaire) * Decimal(quantite)
        total_catalogue = arrondir_au_centime_demi_haut(montant_exact_du_catalogue)
    else:
        # L'argent réel est déjà en centimes entiers : un autre type serait un
        # montant recalculé, qu'on refuse au lieu de l'arrondir en silence.
        # / Real money is already whole cents: any other type is refused.
        if type(total_catalogue_impose) is not int:
            raise ValueError(
                f"Le total catalogue imposé doit être un entier en centimes, "
                f"reçu : {total_catalogue_impose!r}"
            )
        total_catalogue = total_catalogue_impose

    # 2. La part offerte reste entre 0 et le total catalogue (même signe pour un avoir).
    # / 2. The offered part stays between 0 and the catalogue total (same sign).
    if total_catalogue >= 0:
        part_offerte_minimum = 0
        part_offerte_maximum = total_catalogue
    else:
        part_offerte_minimum = total_catalogue
        part_offerte_maximum = 0
    part_offerte_hors_bornes = (
        part_offerte < part_offerte_minimum or part_offerte > part_offerte_maximum
    )
    if part_offerte_hors_bornes:
        raise ValueError(
            f"La part offerte ({part_offerte}) doit être comprise entre "
            f"{part_offerte_minimum} et {part_offerte_maximum} centimes."
        )

    # 3. Net vendu, puis HT arrondi une fois, puis TVA par différence.
    # / 3. Net sold, then excl. tax rounded once, then VAT by difference.
    net_vendu = total_catalogue - part_offerte
    montant_exact_hors_taxes = (
        Decimal(net_vendu) * Decimal("100") / (Decimal("100") + Decimal(taux_tva))
    )
    total_ht = arrondir_au_centime_demi_haut(montant_exact_hors_taxes)
    total_tva = net_vendu - total_ht

    # 4. Coût d'achat, sur la quantité réellement servie. Prix d'achat 0 = inconnu.
    # / 4. Purchase cost, on the quantity really served. Purchase price 0 = unknown.
    prix_d_achat_inconnu = prix_achat == 0
    if prix_d_achat_inconnu:
        cout_achat = None
    else:
        if quantite_pour_cout is None:
            quantite_reellement_servie = quantite
        else:
            quantite_reellement_servie = quantite_pour_cout
        montant_exact_du_cout = Decimal(quantite_reellement_servie) * Decimal(
            prix_achat
        )
        cout_achat = arrondir_au_centime_demi_haut(montant_exact_du_cout)

    return {
        "total_catalogue": total_catalogue,
        "part_offerte": part_offerte,
        "total_ttc": net_vendu,
        "total_ht": total_ht,
        "total_tva": total_tva,
        "cout_achat": cout_achat,
    }


def ouvrir_vente(
    origine,
    nature,
    unite="EUR",
    point_de_vente=None,
    operateur=None,
    client=None,
    carte=None,
    vente_liee=None,
    idempotency_key=None,
):
    """
    Ouvre une vente EN_ATTENTE, sans numéro. Première étape de toute vente.
    / Opens a PENDING sale, without number. First step of every sale.

    LOCALISATION : BaseBillet/services_vente.py

    Anti double clic : si une vente porte déjà la même clé d'idempotence, c'est elle
    qui est rendue, et aucune vente n'est créée.
    / Anti double-click: a known idempotency key returns the existing sale.

    Refuse (ValueError) une origine hors de `SaleOrigin` et une nature hors de
    `Vente.Nature`.
    / Refuses an origin or a nature outside their choices.

    :param origine: `SaleOrigin` (caisse, tireuse, en ligne, admin, API…)
    :param nature: `Vente.Nature` (VENTE, AVOIR, VIDAGE_CARTE, CORRECTION)
    :param unite: "EUR", ou l'uuid (texte) de la monnaie de points de la vente
    :param point_de_vente: `laboutik.PointDeVente`, ou None
    :param operateur: l'utilisateur de la carte primaire, ou None
    :param client: l'utilisateur acheteur, ou None
    :param carte: la `CarteCashless` de la vente, ou None
    :param vente_liee: la vente d'origine d'un avoir ou d'une correction, ou None
    :param idempotency_key: clé anti double clic, ou None
    :return: la `Vente` ouverte (ou déjà ouverte avec cette clé)
    """
    # La base ne vérifie pas les choix d'un champ texte : sans ce refus, une valeur
    # inconnue serait écrite telle quelle, puis scellée dans l'empreinte de la vente.
    # / The database does not check a text field's choices: refused here.
    if origine not in SaleOrigin.values:
        raise ValueError(
            f"Origine de vente inconnue : {origine!r}. Attendu : une valeur de "
            f"SaleOrigin ({', '.join(SaleOrigin.values)})."
        )
    if nature not in Vente.Nature.values:
        raise ValueError(
            f"Nature de vente inconnue : {nature!r}. Attendu : une valeur de "
            f"Vente.Nature ({', '.join(Vente.Nature.values)})."
        )

    champs_de_la_vente = {
        "origine": origine,
        "nature": nature,
        "unite": unite,
        "point_de_vente": point_de_vente,
        "operateur": operateur,
        "client": client,
        "carte": carte,
        "vente_liee": vente_liee,
    }

    if idempotency_key is None:
        vente = Vente.objects.create(**champs_de_la_vente)
        return vente

    # `get_or_create` relit la vente si un autre clic l'a créée au même instant
    # (contrainte d'unicité sur la clé) : deux clics simultanés rendent la même vente.
    # / get_or_create reads the sale back if another click created it at the same time.
    vente, _vente_creee = Vente.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults=champs_de_la_vente,
    )
    return vente


def ajouter_article(
    vente,
    pricesold,
    quantite,
    prix_unitaire,
    taux_tva,
    part_offerte=0,
    source_offert="",
    prix_achat=0,
    offert_en_totalite=False,
    total_catalogue_impose=None,
    quantite_pour_cout=None,
    hors_chiffre_affaires=False,
    cout_achat_impose=None,
    **champs_de_la_ligne,
):
    """
    Ajoute un article vendu à la vente : une `LigneArticle` écrite en UN SEUL INSERT,
    avec tous ses montants entiers et sa TVA.
    / Adds a sold item to the sale: one LigneArticle, written in ONE INSERT.

    LOCALISATION : BaseBillet/services_vente.py

    FLUX :
    0. La vente, relue en base, doit être EN_ATTENTE : une vente réglée ou annulée ne
       reçoit plus rien (ValueError).
    1. Vente en points (`unite` ≠ "EUR") : la TVA doit valoir 0, sinon refus.
    2. Montants par `calculer_montants_article` (la seule formule d'argent).
    3. Règle « offert à montant non nul » : si l'article est entièrement offert et que
       son total catalogue n'est pas 0, alors part offerte = total catalogue,
       source OFFRIR, et un règlement FREE du même montant est ajouté.
    3b. Coût d'achat : celui imposé par l'appelant (un avoir reprend le coût figé de la
       ligne qu'il annule), sinon celui de la formule.
    4. `hors_chiffre_affaires` calculé depuis le produit, ou forcé par l'appelant.
    5. Création de la ligne, avec le marqueur `_tva_explicite` : `LigneArticle.save()`
       garde alors la TVA passée, même 0. La ligne porte l'origine de la vente
       (`sale_origin`), sauf si le producteur en passe une.

    La ligne est CRÉÉE, jamais modifiée ensuite par le service. Les déclencheurs
    (Fedow, e-mails, ancien LaBoutik) partent sur une TRANSITION de statut faite par
    un `save()` (BaseBillet/signals.py) : le producteur garde la sienne. Un `save()` de
    plus ici relancerait ces déclencheurs.
    / The line is created, never saved again by the service: a second save() would
    run the status machine triggers again.

    :param vente: la `Vente` EN_ATTENTE (sinon ValueError)
    :param pricesold: le `PriceSold` vendu
    :param quantite: la quantité (Decimal), négative pour un avoir
    :param prix_unitaire: prix unitaire TTC en centimes (int), écrit dans `amount`
    :param taux_tva: taux de TVA en pour cent (Decimal), écrit dans `vat`
    :param part_offerte: centimes offerts sur l'article (voir `calculer_montants_article`)
    :param source_offert: `LigneArticle.SourceOffert` (OFFRIR, JETONS), vide sinon
    :param prix_achat: prix d'achat du produit en centimes ; 0 = inconnu
    :param offert_en_totalite: True pour un article entièrement offert (règle ci-dessus)
    :param total_catalogue_impose: l'argent réel d'une « part » (transition, retiré en H)
    :param quantite_pour_cout: la quantité réellement servie, pour le coût d'achat
    :param hors_chiffre_affaires: True pour forcer l'article hors chiffre d'affaires
        (écart d'encaissement) ; sinon calculé depuis le produit
    :param cout_achat_impose: le coût d'achat de l'article en centimes (int), repris
        tel quel au lieu de la formule (article d'avoir) ; None = la formule
    :param champs_de_la_ligne: champs historiques de la ligne posés pendant la
        transition (`payment_method`, `asset`, `status`, `reservation`…)
    :return: la `LigneArticle` créée
    """
    # 0. Une vente encaissée ne se modifie plus (D14), une vente annulée non plus.
    # On lit le statut EN BASE : l'objet reçu peut être ancien.
    # / 0. A settled or cancelled sale takes nothing more. Status read in the database.
    statut_de_la_vente_en_base = (
        Vente.objects.filter(pk=vente.pk).values_list("statut", flat=True).first()
    )
    if statut_de_la_vente_en_base != Vente.Statut.EN_ATTENTE:
        raise ValueError(
            f"La vente {vente.uuid} n'est plus en attente (statut "
            f"{statut_de_la_vente_en_base}) : on ne peut plus lui ajouter d'article."
        )

    # 1. Une vente en points n'est pas de l'argent : pas de TVA (D9).
    # / 1. A points sale is not money: no VAT.
    vente_en_points = vente.unite != "EUR"
    if vente_en_points and Decimal(taux_tva) != Decimal("0"):
        raise ValueError(
            f"Une vente en points n'a pas de TVA : taux reçu {taux_tva} %, attendu 0."
        )

    # 2. Les montants, par la seule formule d'argent du projet.
    # / 2. The amounts, by the only money formula of the project.
    montants = calculer_montants_article(
        prix_unitaire=prix_unitaire,
        quantite=quantite,
        taux_tva=taux_tva,
        part_offerte=part_offerte,
        prix_achat=prix_achat,
        total_catalogue_impose=total_catalogue_impose,
        quantite_pour_cout=quantite_pour_cout,
    )

    # 3. Règle « offert à montant non nul ». Pendant la transition, le moyen historique
    # FREE sur la ligne la déclenche aussi (retiré en fiche H).
    # / 3. "Offered at a non-zero price" rule. FREE on the line also triggers it (until H).
    moyen_historique_de_la_ligne = champs_de_la_ligne.get("payment_method")
    ligne_offerte_par_le_moyen_historique = (
        moyen_historique_de_la_ligne == PaymentMethod.FREE
    )
    article_entierement_offert = (
        offert_en_totalite or ligne_offerte_par_le_moyen_historique
    )
    reglement_offert_a_ajouter = (
        article_entierement_offert and montants["total_catalogue"] != 0
    )
    if reglement_offert_a_ajouter:
        montants = calculer_montants_article(
            prix_unitaire=prix_unitaire,
            quantite=quantite,
            taux_tva=taux_tva,
            part_offerte=montants["total_catalogue"],
            prix_achat=prix_achat,
            total_catalogue_impose=total_catalogue_impose,
            quantite_pour_cout=quantite_pour_cout,
        )
        source_offert = LigneArticle.SourceOffert.OFFRIR

    # 3b. Le coût d'achat : imposé par l'appelant, sinon celui de la formule. Un coût
    # imposé est déjà en centimes entiers : un autre type serait un montant recalculé,
    # qu'on refuse au lieu de l'arrondir en silence.
    # / 3b. The purchase cost: imposed by the caller, else the formula's. Int only.
    if cout_achat_impose is None:
        cout_achat_de_l_article = montants["cout_achat"]
    else:
        if type(cout_achat_impose) is not int:
            raise ValueError(
                f"Le coût d'achat imposé doit être un entier en centimes, "
                f"reçu : {cout_achat_impose!r}"
            )
        cout_achat_de_l_article = cout_achat_impose

    # 4. Hors chiffre d'affaires : figé ici, depuis le produit tel qu'il est
    # maintenant. Un changement ultérieur du produit ne change pas la ligne.
    # / 4. Off revenue: frozen now, from the product as it is today.
    # Une recharge n'est jamais une vente : les deux recharges en ligne (`R` cashless,
    # `E` FED) sont hors chiffre d'affaires, comme les recharges de caisse.
    # / A top-up is never a sale: both online top-ups (R, E) are off revenue.
    produit_vendu = pricesold.productsold.product
    produit_hors_chiffre_affaires = (
        produit_vendu.methode_caisse in METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES
        or produit_vendu.categorie_article
        in [Product.RECHARGE_CASHLESS, Product.RECHARGE_CASHLESS_FED]
    )
    ligne_hors_chiffre_affaires = hors_chiffre_affaires or produit_hors_chiffre_affaires

    # La ligne porte l'origine de sa vente, sauf si le producteur en passe une : sans
    # cela, le défaut du champ (« en ligne ») marquerait à tort une vente de caisse.
    # / The line carries its sale's origin unless the producer passes one.
    origine_passee_par_le_producteur = "sale_origin" in champs_de_la_ligne
    if not origine_passee_par_le_producteur:
        champs_de_la_ligne["sale_origin"] = vente.origine

    # 5. La ligne et son éventuel règlement FREE sont écrits ensemble, ou pas du tout.
    # / 5. The line and its possible FREE payment are written together, or not at all.
    with transaction.atomic():
        ligne = LigneArticle(
            vente=vente,
            pricesold=pricesold,
            qty=quantite,
            amount=prix_unitaire,
            vat=taux_tva,
            total_catalogue=montants["total_catalogue"],
            part_offerte=montants["part_offerte"],
            source_offert=source_offert,
            total_ttc=montants["total_ttc"],
            total_ht=montants["total_ht"],
            total_tva=montants["total_tva"],
            cout_achat=cout_achat_de_l_article,
            hors_chiffre_affaires=ligne_hors_chiffre_affaires,
            **champs_de_la_ligne,
        )
        # La TVA passée ici est voulue, même 0 : `LigneArticle.save()` la garde.
        # / The VAT given here is intended, even 0: LigneArticle.save() keeps it.
        ligne._tva_explicite = True
        ligne.save()

        if reglement_offert_a_ajouter:
            ajouter_reglement(
                vente,
                moyen=PaymentMethod.FREE,
                montant=montants["total_catalogue"],
            )

    return ligne


def ajouter_l_article_d_avoir(vente_avoir, ligne_d_origine, quantite):
    """
    Ajoute à une vente AVOIR l'article qui annule `quantite` unités d'une ligne vendue :
    le miroir négatif de la ligne d'origine.
    / Adds to an AVOIR sale the item that cancels `quantite` units of a sold line: the
    negative mirror of the original line.

    LOCALISATION : BaseBillet/services_vente.py

    L'ARTICLE ÉCRIT (par `ajouter_article`) :
    - même tarif vendu, même prix unitaire, même taux de TVA ;
    - quantité NÉGATIVE (−quantite) ;
    - toute la quantité rendue, ligne écrite par le service (total catalogue non nul) :
      total catalogue = −total d'origine et part offerte = −part offerte d'origine,
      recopiés tels quels. Une « part » d'article (caisse en cascade) a un total imposé
      que prix × quantité ne redonne pas toujours au centime : on rend exactement ce
      qui a été vendu ;
    - ligne écrite avant le chantier (total catalogue 0) : calculé prix × −quantité ;
    - une partie de la quantité d'une ligne ENTIÈREMENT offerte (part offerte = total
      catalogue, non nul) : calculé prix × −quantité, et part offerte = ce total
      (entièrement offert lui aussi, sans prorata) ;
    - coût d'achat : le coût FIGÉ de la ligne d'origine, en négatif, au prorata de la
      quantité rendue : arrondi_demi_haut(coût d'origine × −quantité / quantité
      vendue). Ligne sans coût (inconnu) : avoir sans coût. Le coût n'est jamais
      recalculé depuis le produit : son prix d'achat a pu changer, et le coût d'un
      article au poids ou d'une part porte sur la quantité réellement servie, que la
      ligne ne garde pas. Limite : plusieurs avoirs partiels d'une même ligne peuvent
      s'écarter d'un centime de son coût total (chacun est arrondi) ;
    - statut CREATED : l'appelant fait la transition (CREDIT_NOTE, REFUNDED) par un
      `save()`, après l'encaissement.
    Champs recopiés : `credit_note_for` (la ligne d'origine), `payment_method`,
    `asset`, `wallet`, `carte`, `paiement_stripe`, `membership`, `reservation`,
    `booking`, `metadata` (avec `original_lignearticle_uuid`), `hors_chiffre_affaires`.
    / Same sold price, unit price and VAT, negative quantity; a full return of a line
    written by the service mirrors its totals exactly; status CREATED.

    RÈGLEMENTS : cette fonction n'en écrit AUCUN, c'est l'appelant. Seule exception :
    la règle « offert à montant non nul » d'`ajouter_article` (moyen historique FREE)
    écrit déjà le règlement FREE de l'article. L'appelant ne l'écrit donc pas une
    seconde fois.
    / Writes NO payment (the caller does), except the FREE one written by the
    "offered" rule of ajouter_article: the caller must not write it twice.

    Refuse (ValueError) :
    - une vente qui n'est pas de nature AVOIR ;
    - une ligne payée en points ou en temps (`ligne_payee_en_points`) : l'avoir est
      une vente en euros, il rendrait de l'argent pour des points. Ce refus vaut pour
      tous les producteurs d'avoir, qui passent tous par cette fonction ;
    - une quantité nulle, négative, ou plus grande que celle de la ligne ;
    - une quantité partielle d'une ligne EN PARTIE offerte : le projet ne fait aucun
      prorata d'offert, il faut rembourser l'article entier. Une ligne entièrement
      offerte, elle, accepte une quantité partielle (aucun prorata à faire).
    / Refuses a non-AVOIR sale, a line paid in points or time, a wrong quantity, and a
    partial return of a partly offered item (no prorata: refund the whole item). A fully
    offered line accepts it.

    :param vente_avoir: la `Vente` AVOIR EN_ATTENTE qui reçoit l'article
    :param ligne_d_origine: la `LigneArticle` vendue que l'avoir annule
    :param quantite: la quantité rendue (Decimal), positive, au plus celle de la ligne
    :return: la `LigneArticle` d'avoir créée
    """
    if vente_avoir.nature != Vente.Nature.AVOIR:
        raise ValueError(
            f"La vente {vente_avoir.uuid} est de nature {vente_avoir.nature} : un "
            f"article d'avoir va dans une vente AVOIR."
        )

    if ligne_payee_en_points(ligne_d_origine):
        raise ValueError(
            f"La ligne {ligne_d_origine.uuid} a été payée en points ou en temps : un "
            f"avoir est impossible (il rendrait de l'argent pour des points)."
        )

    quantite_vendue = ligne_d_origine.qty
    quantite_hors_bornes = quantite <= 0 or quantite > quantite_vendue
    if quantite_hors_bornes:
        raise ValueError(
            f"La quantité rendue ({quantite}) doit être positive et au plus égale à "
            f"la quantité vendue ({quantite_vendue})."
        )

    toute_la_quantite_rendue = quantite == quantite_vendue
    ligne_avec_une_part_offerte = ligne_d_origine.part_offerte != 0
    ligne_ecrite_par_le_service = ligne_d_origine.total_catalogue != 0
    ligne_entierement_offerte_par_ses_montants = (
        ligne_ecrite_par_le_service
        and ligne_d_origine.part_offerte == ligne_d_origine.total_catalogue
    )
    ligne_en_partie_offerte = (
        ligne_avec_une_part_offerte and not ligne_entierement_offerte_par_ses_montants
    )
    if ligne_en_partie_offerte and not toute_la_quantite_rendue:
        raise ValueError(
            "Cet article a une part offerte : il faut rembourser l'article entier "
            "(pas de remboursement d'une partie de la quantité)."
        )

    # Les montants : recopiés en négatif quand toute la ligne est rendue et que le
    # service l'a écrite ; sinon calculés par la formule (prix × −quantité). Une partie
    # d'une ligne entièrement offerte reste entièrement offerte : part offerte = total.
    # / Amounts: mirrored for a full return of a service-written line, else computed;
    # a part of a fully offered line stays fully offered.
    if toute_la_quantite_rendue and ligne_ecrite_par_le_service:
        total_catalogue_de_l_avoir = -ligne_d_origine.total_catalogue
        part_offerte_de_l_avoir = -ligne_d_origine.part_offerte
    elif ligne_entierement_offerte_par_ses_montants:
        montants_de_la_partie_rendue = calculer_montants_article(
            prix_unitaire=ligne_d_origine.amount,
            quantite=-quantite,
            taux_tva=ligne_d_origine.vat,
        )
        total_catalogue_de_l_avoir = None
        part_offerte_de_l_avoir = montants_de_la_partie_rendue["total_catalogue"]
    else:
        total_catalogue_de_l_avoir = None
        part_offerte_de_l_avoir = 0

    if part_offerte_de_l_avoir != 0:
        source_de_l_offert = ligne_d_origine.source_offert
    else:
        source_de_l_offert = ""

    # Le coût d'achat : le coût figé de la ligne d'origine, en négatif, au prorata de la
    # quantité rendue. On multiplie avant de diviser (plus exact), puis on arrondit une
    # seule fois. Ligne sans coût : l'avoir n'a pas de coût (inconnu, jamais 0).
    # / The purchase cost: the original line's frozen cost, negative, prorated; no cost
    # gives no cost (unknown, never 0).
    cout_achat_d_origine = ligne_d_origine.cout_achat
    if cout_achat_d_origine is None:
        cout_achat_de_l_avoir = None
    else:
        cout_exact_de_la_partie_rendue = (
            Decimal(cout_achat_d_origine) * -quantite / quantite_vendue
        )
        cout_achat_de_l_avoir = arrondir_au_centime_demi_haut(
            cout_exact_de_la_partie_rendue
        )

    # La trace de la ligne d'origine dans les métadonnées de l'avoir. Une copie : le
    # dictionnaire de la ligne d'origine n'est jamais modifié.
    # / The original line's trace in the credit note metadata, on a copy.
    metadonnees_de_l_avoir = {}
    if ligne_d_origine.metadata:
        metadonnees_de_l_avoir.update(ligne_d_origine.metadata)
    metadonnees_de_l_avoir["original_lignearticle_uuid"] = str(ligne_d_origine.uuid)

    article_d_avoir = ajouter_article(
        vente_avoir,
        pricesold=ligne_d_origine.pricesold,
        quantite=-quantite,
        prix_unitaire=ligne_d_origine.amount,
        taux_tva=ligne_d_origine.vat,
        part_offerte=part_offerte_de_l_avoir,
        source_offert=source_de_l_offert,
        total_catalogue_impose=total_catalogue_de_l_avoir,
        cout_achat_impose=cout_achat_de_l_avoir,
        hors_chiffre_affaires=ligne_d_origine.hors_chiffre_affaires,
        credit_note_for=ligne_d_origine,
        payment_method=ligne_d_origine.payment_method,
        asset=ligne_d_origine.asset,
        wallet=ligne_d_origine.wallet,
        carte=ligne_d_origine.carte,
        paiement_stripe=ligne_d_origine.paiement_stripe,
        membership=ligne_d_origine.membership,
        reservation=ligne_d_origine.reservation,
        booking=ligne_d_origine.booking,
        metadata=metadonnees_de_l_avoir,
        status=LigneArticle.CREATED,
    )
    return article_d_avoir


def ligne_entierement_offerte(ligne):
    """
    Dit si une ligne vendue a été entièrement offerte : aucun argent n'est à rendre.
    / Tells whether a sold line was fully offered: no money to give back.

    LOCALISATION : BaseBillet/services_vente.py

    Deux façons de le savoir :
    - ses montants : part offerte = total catalogue, non nul (ligne écrite par le
      service) ;
    - son moyen historique « offert » (FREE) : ligne écrite avant le chantier, montants
      à 0. Même règle que celle d'`ajouter_article` (retirée en fiche H).
    / By its amounts (offered = catalogue, non-zero) or by its historical FREE method.

    Lue par `ligne_sans_argent_a_rendre` (ce module).
    / Read by `ligne_sans_argent_a_rendre`.
    """
    ligne_offerte_par_ses_montants = (
        ligne.total_catalogue != 0 and ligne.part_offerte == ligne.total_catalogue
    )
    ligne_offerte_par_son_moyen = ligne.payment_method == PaymentMethod.FREE
    return ligne_offerte_par_ses_montants or ligne_offerte_par_son_moyen


def ligne_payee_en_jetons(ligne):
    """
    Dit si une ligne vendue a été payée en jetons cadeau.
    / Tells whether a sold line was paid in gift tokens.

    LOCALISATION : BaseBillet/services_vente.py

    Reconnue par son moyen historique « jetons » (LG) jusqu'à la fiche H.
    / Recognised by its historical LG method until sheet H.
    """
    return ligne.payment_method == PaymentMethod.LOCAL_GIFT


def ligne_payee_en_points(ligne):
    """
    Dit si une ligne vendue a été payée en points ou en temps : une telle ligne ne
    reçoit jamais d'avoir.
    / Tells whether a sold line was paid in points or time: it never gets a credit note.

    LOCALISATION : BaseBillet/services_vente.py

    Deux façons de le savoir :
    - sa vente n'est pas en euros (`unite` ≠ "EUR") : vente en points de la caisse,
      recharge offerte en points ou en temps de l'API v2 (moyen FREE, pas NM) ;
    - son moyen historique est « points ou temps » (NM), avec ou sans vente : c'est le
      seul indice d'une ligne écrite sans vente.
    / Its sale is not in euros, or its historical method is NM (with or without sale).

    Lue par `ajouter_l_article_d_avoir` (ce module, le refus commun à tous les avoirs),
    le bouton « Avoir » (Administration/admin_tenant.py `emettre_avoir`) et le
    formulaire d'annulation d'adhésion (BaseBillet/views.py, MembershipMVT).
    / Read by the shared credit note function, the admin button and the membership
    cancellation form.
    """
    vente_de_la_ligne_en_points = (
        ligne.vente_id is not None and ligne.vente.unite != "EUR"
    )
    ligne_au_moyen_points_ou_temps = (
        ligne.payment_method == PaymentMethod.NON_MONETAIRE
    )
    return vente_de_la_ligne_en_points or ligne_au_moyen_points_ou_temps


def ligne_sans_argent_a_rendre(ligne):
    """
    Dit si l'avoir d'une ligne vendue ne rend aucun argent : la ligne a été entièrement
    offerte, ou payée en jetons cadeau.
    / Tells whether a sold line's credit note gives no money back: fully offered, or
    paid in gift tokens.

    LOCALISATION : BaseBillet/services_vente.py

    Une part payée en jetons est une vente ordinaire (D8 bis), mais l'avoir rend la
    dette au lieu, pas de l'argent ni les jetons (règlement « jetons » négatif, aucun
    recrédit de la carte).
    / A token part is an ordinary sale, but its credit note gives back the debt, not
    money nor tokens.

    Lue par les écrans qui décident d'afficher le champ « Remboursé par » : l'écran
    « Émettre un avoir » et l'écran d'annulation des actions admin
    (Administration/admin_tenant.py), le formulaire d'annulation d'adhésion
    (BaseBillet/views.py), et les messages d'annulation de l'utilisateur
    (BaseBillet/models.py, booking/models.py).
    / Read by the screens that decide whether to show the "Refunded by" field.
    """
    return ligne_entierement_offerte(ligne) or ligne_payee_en_jetons(ligne)


# Les moyens proposés par le champ « Remboursé par » : de l'argent rendu à la main. Le
# recrédit d'une carte cashless n'en fait pas partie.
# Lus par les écrans de l'admin (Administration/admin_tenant.py : avoir, annulations) et
# par le formulaire d'annulation d'adhésion (BaseBillet/views.py, MembershipMVT).
# / The methods offered by the "Refunded by" field: money given back by hand. Read by
# the admin screens and the membership cancellation form.
MOYENS_DU_CHAMP_REMBOURSE_PAR = [
    PaymentMethod.CASH,
    PaymentMethod.CC,
    PaymentMethod.CHEQUE,
    PaymentMethod.TRANSFER,
]


def choix_du_champ_rembourse_par():
    """
    Les choix du champ « Remboursé par » : une ligne vide, puis les quatre moyens.
    / The "Refunded by" choices: an empty line, then the four methods.
    """
    choix = [("", "---------")]
    for moyen in MOYENS_DU_CHAMP_REMBOURSE_PAR:
        choix.append((moyen.value, moyen.label))
    return choix


def quantite_restante_de_la_ligne_sous_verrou(ligne):
    """
    Verrouille une ligne vendue et rend la quantité qui reste à rendre : la quantité
    vendue, moins celle de ses avoirs et de ses remboursements Stripe (les lignes qui la
    citent dans `credit_note_for`, de quantité négative).
    / Locks a sold line and returns the quantity left to give back: the sold quantity
    minus its credit notes and Stripe refunds.

    LOCALISATION : BaseBillet/services_vente.py

    À appeler DANS une transaction, AVANT toute écriture et tout appel à Stripe. Le
    verrou (`select_for_update`) tient jusqu'à la fin de la transaction : une seconde
    demande pour la même ligne (double clic, nouvel essai) attend que la première
    finisse, puis relit la quantité déjà rendue. Sans lui, deux demandes simultanées
    lisent la même quantité restante et rendent deux fois.
    / Call INSIDE a transaction, BEFORE any write or Stripe call. The lock holds until the
    transaction ends: a second request for the same line waits, then reads again.

    APPELÉE PAR : `ecrire_la_vente_d_avoir_d_une_ligne` (ce module) et
    PaiementStripe/utils.py `partial_refund_payment`.

    :param ligne: la `LigneArticle` vendue (l'objet peut être périmé : on relit en base)
    :return: la quantité restante (Decimal), 0 si tout est déjà rendu
    """
    ligne_verrouillee = LigneArticle.objects.select_for_update().get(pk=ligne.pk)
    quantite_restante = ligne_verrouillee.qty
    for ligne_qui_rend_une_partie in ligne_verrouillee.credit_notes.all():
        # Un avoir ou un remboursement a une quantité négative : on l'ajoute.
        # / A credit note or a refund has a negative quantity: it is added.
        quantite_restante += ligne_qui_rend_une_partie.qty
    return quantite_restante


def ecrire_la_vente_d_avoir_d_une_ligne(ligne, quantite, moyen_rembourse, origine):
    """
    Écrit l'avoir de `quantite` unités d'une ligne vendue : une vente AVOIR complète,
    encaissée, puis la ligne d'avoir passe CREDIT_NOTE. Tout ou rien.
    / Writes the credit note of `quantite` units of a sold line: a full, settled AVOIR
    sale, then the credit note line turns CREDIT_NOTE. All or nothing.

    LOCALISATION : BaseBillet/services_vente.py

    APPELÉE PAR :
    - Administration/admin_tenant.py `LigneArticleAdmin.emettre_avoir` (bouton « Avoir ») ;
    - BaseBillet/models.py `Reservation.cancel_and_refund_resa` et
      `cancel_and_refund_ticket`, quand l'ADMIN annule des lignes hors Stripe.
    / Called by the "Credit note" button and by the admin cancellations.

    FLUX (dans UNE transaction ; un point de sauvegarde si l'appelant en a une) :
    1. refus si la vente d'origine existe et n'est pas réglée ;
    1b. la ligne est verrouillée et la quantité déjà rendue relue
       (`quantite_restante_de_la_ligne_sous_verrou`) : refus si `quantite` dépasse ce
       qui reste. Deux demandes pour la même ligne (double clic) n'écrivent jamais deux
       avoirs ;
    2. vente AVOIR, origine `origine`, liée à la vente de la ligne (vide pour une ligne
       d'avant le chantier), client = celui de la vente liée ;
    3. l'article d'avoir : `ajouter_l_article_d_avoir` ;
    4. UN règlement du net rendu, s'il n'est pas nul :
       - ligne payée en jetons cadeau (LG) : un règlement « jetons » négatif, avec la
         monnaie et la carte de la ligne ; aucun moyen demandé, aucun recrédit de la
         carte (la dette revient, les jetons ne reviennent pas) ;
       - ligne payée par Stripe : au moyen Stripe d'origine, relié au paiement, sans
         référence externe (aucun appel à Stripe : l'admin rembourse depuis Stripe) ;
       - sinon : au moyen `moyen_rembourse` (« Remboursé par »), obligatoire ici ;
    5. un règlement FREE négatif pour la part offerte, sauf la partie déjà tracée par la
       règle « offert » d'`ajouter_article` (jamais deux fois) ;
    6. `encaisser_vente` ;
    7. PUIS la transition CREDIT_NOTE par `save()` : elle déclenche l'envoi à l'ancien
       LaBoutik (BaseBillet/signals.py).
    / Refuse an unsettled original sale; AVOIR sale; mirrored item; one payment (LG for a
    token line, the original Stripe method, or the chosen one); one FREE payment for the
    offered part; settle; THEN CREDIT_NOTE.

    Refuse (ValueError, rien n'est écrit) : vente d'origine pas réglée ; quantité plus
    grande que ce qui reste à rendre ; argent hors Stripe à rendre sans moyen ; toute
    règle du service (quantité, avoir partiel d'un article en partie offert…).
    / Refuses (ValueError, nothing written): unsettled original sale, more than what is
    left to give back, money to give back without a method, any service rule.

    :param ligne: la `LigneArticle` vendue (VALID ou PAID)
    :param quantite: la quantité rendue (Decimal), positive, au plus celle de la ligne
    :param moyen_rembourse: `PaymentMethod` de l'argent rendu (espèces, CB, chèque,
        virement), ou None quand il n'y a pas d'argent hors Stripe à rendre (ligne
        offerte, payée en jetons)
    :param origine: `SaleOrigin` de la vente AVOIR (ADMIN pour l'admin)
    :return: la `LigneArticle` d'avoir, au statut CREDIT_NOTE
    """
    vente_d_origine = ligne.vente
    vente_d_origine_pas_reglee = (
        vente_d_origine is not None and vente_d_origine.statut != Vente.Statut.REGLEE
    )
    if vente_d_origine_pas_reglee:
        raise ValueError(
            "La vente d'origine n'est pas réglée : l'avoir est impossible."
        )

    # Le moyen de l'argent rendu : le moyen Stripe d'origine, ou le moyen choisi.
    # / The money method: the original Stripe one, or the chosen one.
    ligne_payee_par_stripe = ligne.paiement_stripe_id is not None
    if ligne_payee_par_stripe:
        paiement_d_origine = ligne.paiement_stripe
        moyen_de_l_argent_rendu = paiement_d_origine.moyen or ligne.payment_method
    else:
        paiement_d_origine = None
        moyen_de_l_argent_rendu = moyen_rembourse

    with transaction.atomic():
        # 1b. Sous verrou, la quantité qui reste à rendre. / 1b. Under lock, what is left.
        quantite_restante = quantite_restante_de_la_ligne_sous_verrou(ligne)
        if quantite > quantite_restante:
            raise ValueError(
                f"La quantité rendue ({quantite}) dépasse ce qui reste à rendre sur la "
                f"ligne {ligne.uuid} ({quantite_restante}) : un avoir ou un "
                f"remboursement a déjà été fait."
            )

        # 2. La vente AVOIR. / 2. The AVOIR sale.
        if vente_d_origine is not None:
            client_de_la_vente_liee = vente_d_origine.client
        else:
            client_de_la_vente_liee = None
        vente_d_avoir = ouvrir_vente(
            origine=origine,
            nature=Vente.Nature.AVOIR,
            client=client_de_la_vente_liee,
            vente_liee=vente_d_origine,
        )

        # 3. L'article d'avoir. / 3. The credit note item.
        article_d_avoir = ajouter_l_article_d_avoir(vente_d_avoir, ligne, quantite)

        # 4. UN règlement du net rendu, s'il n'est pas nul.
        # Ligne payée en jetons : un règlement « jetons » (LG) négatif, avec la monnaie
        # et la carte de la ligne. Aucun argent n'est rendu et la carte n'est pas
        # recréditée : la dette du lieu revient, les jetons ne reviennent pas.
        # Sinon : un règlement d'argent.
        # / 4. ONE payment of the net given back. Token line: a negative LG payment,
        # no money, no credit back on the card. Otherwise: a money payment.
        net_rendu = article_d_avoir.total_ttc
        if net_rendu != 0 and ligne_payee_en_jetons(ligne):
            ajouter_reglement(
                vente_d_avoir,
                moyen=PaymentMethod.LOCAL_GIFT,
                montant=net_rendu,
                asset=ligne.asset,
                carte=ligne.carte,
            )
        elif net_rendu != 0:
            if not moyen_de_l_argent_rendu:
                raise ValueError(
                    "De l'argent est à rendre : le moyen « Remboursé par » est "
                    "obligatoire."
                )
            ajouter_reglement(
                vente_d_avoir,
                moyen=moyen_de_l_argent_rendu,
                montant=net_rendu,
                paiement_stripe=paiement_d_origine,
            )

        # 5. La part offerte annulée, tracée par un règlement FREE. La règle « offert »
        # du service a pu l'écrire déjà (moyen historique FREE) : on n'écrit que ce qui
        # manque.
        # / 5. The cancelled offered part, as a FREE payment, never twice.
        part_offerte_deja_tracee = 0
        reglements_offerts_deja_ecrits = Reglement.objects.filter(
            vente=vente_d_avoir, moyen=PaymentMethod.FREE
        )
        for reglement_offert in reglements_offerts_deja_ecrits:
            part_offerte_deja_tracee += reglement_offert.montant
        part_offerte_a_tracer = article_d_avoir.part_offerte - part_offerte_deja_tracee
        if part_offerte_a_tracer != 0:
            ajouter_reglement(
                vente_d_avoir,
                moyen=PaymentMethod.FREE,
                montant=part_offerte_a_tracer,
            )

        # 6. L'encaissement. / 6. Settlement.
        encaisser_vente(vente_d_avoir)

        # 7. PUIS la transition : elle déclenche la machine à états.
        # / 7. THEN the transition: it triggers the state machine.
        article_d_avoir.status = LigneArticle.CREDIT_NOTE
        article_d_avoir.save()

    return article_d_avoir


def ajouter_reglement(
    vente,
    moyen,
    montant,
    asset=None,
    carte=None,
    wallet=None,
    fedow_transaction_uuid=None,
    paiement_stripe=None,
    reference_externe="",
):
    """
    Ajoute un règlement à la vente. Le montant est COPIÉ de sa source (transaction
    Fedow, paiement Stripe, somme encaissée) : jamais calculé.
    / Adds a payment to the sale. The amount is COPIED from its source, never computed.

    LOCALISATION : BaseBillet/services_vente.py

    Refuse (ValueError) :
    - une vente qui n'est plus EN_ATTENTE (réglée ou annulée, statut relu en base) ;
    - un montant qui n'est pas un entier (`Decimal`, `float`) ou qui vaut 0 : une
      vente gratuite n'a aucun règlement ;
    - un moyen hors de `PaymentMethod`.
    / Refuses a sale no longer pending, a non-int amount, 0, or an unknown method.

    :param vente: la `Vente` EN_ATTENTE (sinon ValueError)
    :param moyen: `PaymentMethod` (CA, CC, LE, LG, FREE, NM, SN…)
    :param montant: centimes entiers, signés, non nuls (int)
    :param asset: uuid de la monnaie (cashless), ou None
    :param carte: `CarteCashless` (cashless), ou None
    :param wallet: `Wallet` (cashless), ou None
    :param fedow_transaction_uuid: uuid de la transaction Fedow, ou None
    :param paiement_stripe: `Paiement_stripe`, ou None
    :param reference_externe: id de remboursement Stripe, numéro de chèque… ou ""
    :return: le `Reglement` créé
    """
    # Une vente encaissée ne se modifie plus (D14), une vente annulée non plus.
    # On lit le statut EN BASE : l'objet reçu peut être ancien.
    # / A settled or cancelled sale takes nothing more. Status read in the database.
    statut_de_la_vente_en_base = (
        Vente.objects.filter(pk=vente.pk).values_list("statut", flat=True).first()
    )
    if statut_de_la_vente_en_base != Vente.Statut.EN_ATTENTE:
        raise ValueError(
            f"La vente {vente.uuid} n'est plus en attente (statut "
            f"{statut_de_la_vente_en_base}) : on ne peut plus lui ajouter de règlement."
        )

    # `type(...) is int` et non `isinstance` : un booléen est aussi un `int` en Python.
    # / `type(...) is int`, not isinstance: a bool is also an int in Python.
    montant_est_un_entier = type(montant) is int
    if not montant_est_un_entier:
        raise ValueError(
            f"Le montant d'un règlement doit être un entier en centimes, "
            f"reçu : {montant!r}"
        )
    if montant == 0:
        raise ValueError(
            "Un règlement de 0 n'existe pas : une vente gratuite n'a aucun règlement."
        )

    # La base ne vérifie pas les choix d'un champ texte : sans ce refus, un moyen
    # inconnu serait écrit tel quel, puis scellé dans l'empreinte de la vente.
    # / The database does not check a text field's choices: refused here.
    if moyen not in PaymentMethod.values:
        raise ValueError(
            f"Moyen de règlement inconnu : {moyen!r}. Attendu : une valeur de "
            f"PaymentMethod ({', '.join(PaymentMethod.values)})."
        )

    reglement = Reglement.objects.create(
        vente=vente,
        moyen=moyen,
        montant=montant,
        asset=asset,
        carte=carte,
        wallet=wallet,
        fedow_transaction_uuid=fedow_transaction_uuid,
        paiement_stripe=paiement_stripe,
        reference_externe=reference_externe,
    )
    return reglement


def encaisser_vente(vente):
    """
    Encaisse la vente : vérifie les deux égalités, pose le numéro, l'heure et les
    totaux, et passe la vente à REGLEE. Tout ou rien.
    / Settles the sale: checks both equalities, sets number, time and totals. All or nothing.

    LOCALISATION : BaseBillet/services_vente.py

    FLUX (dans une transaction ; un point de sauvegarde si l'appelant en a déjà une) :
    1. Verrou du lieu : `pg_advisory_xact_lock`. Deux encaissements du même lieu
       passent l'un après l'autre : deux ventes n'ont jamais le même numéro.
    2. Relecture de la vente sous verrou (`select_for_update`) :
       - déjà REGLEE → rendue telle quelle (webhook Stripe + retour de l'acheteur) ;
       - ANNULEE → refus (ValueError) : pas de retour arrière.
    3. Une vente sans article est refusée (ValueError), sauf VIDAGE_CARTE et
       CORRECTION.
    4. Les deux égalités, relues en base (sinon `EgaliteDeVenteRompue`) :
          Σ règlements                    = Σ totaux catalogue des articles
          Σ règlements hors « offert »    = Σ nets vendus des articles
    5. Numéro = plus grand numéro du lieu + 1 ; heure d'encaissement ; totaux de la
       vente = sommes des articles ; statut REGLEE.
    6. Empreinte chaînée (`laboutik/integrity.py` `calculer_hmac_vente`) :
       `previous_hmac` = empreinte de la vente numéro − 1 ("" pour la première),
       clé du lieu dans `LaboutikConfiguration`. Puis l'enregistrement.

    Le verrou est tenu jusqu'à la fin de la transaction la plus extérieure. L'appelant
    encaisse donc EN DERNIER, après tout appel réseau : sinon toute la caisse du lieu
    attend.
    / The lock is held until the outermost commit: settle LAST, after any network call.

    :param vente: la `Vente` à encaisser
    :return: la vente relue en base, REGLEE
    """
    # Le `atomic()` est indispensable même si l'appelant n'a pas de transaction : le
    # verrou du lieu ne dure que jusqu'à la fin de la transaction. Sans lui, deux
    # encaissements simultanés liraient le même plus grand numéro.
    # / atomic() is required: the venue lock only lasts until the end of the transaction.
    with transaction.atomic():
        # 1. Verrou du lieu, relâché à la fin de la transaction.
        # / 1. Venue lock, released at the end of the transaction.
        nom_du_verrou_du_lieu = f"vente-{connection.schema_name}"
        with connection.cursor() as curseur:
            curseur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [nom_du_verrou_du_lieu],
            )

        # 2. Relecture sous verrou : l'état en base fait foi, pas l'objet reçu.
        # / 2. Read back under lock: the database state rules, not the given object.
        vente_verrouillee = Vente.objects.select_for_update().get(pk=vente.pk)

        vente_deja_reglee = vente_verrouillee.statut == Vente.Statut.REGLEE
        if vente_deja_reglee:
            return vente_verrouillee

        vente_annulee = vente_verrouillee.statut == Vente.Statut.ANNULEE
        if vente_annulee:
            raise ValueError(
                f"La vente {vente_verrouillee.uuid} est annulée : elle ne peut plus "
                f"être encaissée."
            )

        articles_de_la_vente = list(
            LigneArticle.objects.filter(vente=vente_verrouillee)
        )
        reglements_de_la_vente = list(Reglement.objects.filter(vente=vente_verrouillee))

        # 3. Sans article : seulement un vidage de carte ou une correction.
        # / 3. No item: only a card emptying or a correction.
        vente_sans_article = len(articles_de_la_vente) == 0
        nature_sans_article_acceptee = (
            vente_verrouillee.nature in NATURES_SANS_ARTICLE_ACCEPTEES
        )
        if vente_sans_article and not nature_sans_article_acceptee:
            raise ValueError(
                f"Une vente de nature {vente_verrouillee.nature} doit avoir au moins "
                f"un article."
            )

        # Sommes des articles.
        # / Sums of the items.
        somme_des_totaux_catalogue = 0
        somme_des_parts_offertes = 0
        somme_des_nets_vendus = 0
        somme_des_totaux_ht = 0
        somme_des_totaux_tva = 0
        for article in articles_de_la_vente:
            somme_des_totaux_catalogue += article.total_catalogue
            somme_des_parts_offertes += article.part_offerte
            somme_des_nets_vendus += article.total_ttc
            somme_des_totaux_ht += article.total_ht
            somme_des_totaux_tva += article.total_tva

        # Sommes des règlements : tous, puis hors « offert ».
        # / Sums of the payments: all, then without "offered" ones.
        somme_de_tous_les_reglements = 0
        somme_des_reglements_hors_offert = 0
        for reglement in reglements_de_la_vente:
            somme_de_tous_les_reglements += reglement.montant
            reglement_offert = reglement.moyen in MOYENS_OFFERTS
            if not reglement_offert:
                somme_des_reglements_hors_offert += reglement.montant

        # 4. Les deux égalités.
        # / 4. The two equalities.
        if somme_de_tous_les_reglements != somme_des_totaux_catalogue:
            raise EgaliteDeVenteRompue(
                f"Vente {vente_verrouillee.uuid} : la somme des règlements "
                f"({somme_de_tous_les_reglements} centimes) ne vaut pas la somme des "
                f"totaux catalogue des articles ({somme_des_totaux_catalogue} centimes)."
            )
        if somme_des_reglements_hors_offert != somme_des_nets_vendus:
            raise EgaliteDeVenteRompue(
                f"Vente {vente_verrouillee.uuid} : la somme des règlements hors "
                f"offert ({somme_des_reglements_hors_offert} centimes) ne vaut pas la "
                f"somme des nets vendus des articles ({somme_des_nets_vendus} centimes)."
            )

        # 5. Numéro sans trou : le plus grand numéro du lieu + 1. Le verrou garantit
        # qu'aucun autre encaissement ne lit le même plus grand numéro en même temps.
        # / 5. Gapless number: highest number of the venue + 1, safe under the lock.
        plus_grand_numero_du_lieu = Vente.objects.aggregate(
            plus_grand_numero=Max("numero")
        )["plus_grand_numero"]
        if plus_grand_numero_du_lieu is None:
            numero_de_la_vente = 1
        else:
            numero_de_la_vente = plus_grand_numero_du_lieu + 1

        vente_verrouillee.numero = numero_de_la_vente
        vente_verrouillee.datetime_encaissement = timezone.now()
        vente_verrouillee.total_catalogue = somme_des_totaux_catalogue
        vente_verrouillee.total_offert = somme_des_parts_offertes
        vente_verrouillee.total_ttc = somme_des_nets_vendus
        vente_verrouillee.total_ht = somme_des_totaux_ht
        vente_verrouillee.total_tva = somme_des_totaux_tva

        vente_verrouillee.statut = Vente.Statut.REGLEE

        # 6. Empreinte chaînée, toujours sous le verrou : la vente numéro − 1 est la
        # dernière réglée du lieu. Le statut REGLEE est posé AVANT le calcul : il fait
        # partie du message, et `verifier_chaine_ventes` le relit REGLEE en base.
        # / 6. Chained fingerprint, under the lock. REGLEE is set BEFORE the computation:
        # the status is part of the message and is read back as REGLEE by the check.
        if numero_de_la_vente == 1:
            empreinte_de_la_vente_precedente = ""
        else:
            empreinte_de_la_vente_precedente = Vente.objects.get(
                numero=numero_de_la_vente - 1
            ).hmac_hash
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        vente_verrouillee.previous_hmac = empreinte_de_la_vente_precedente
        vente_verrouillee.hmac_hash = calculer_hmac_vente(
            vente_verrouillee,
            cle_de_l_empreinte,
            empreinte_de_la_vente_precedente,
        )

        vente_verrouillee.save()

    return vente_verrouillee


def annuler_vente(vente):
    """
    Annule une vente EN_ATTENTE : elle passe à ANNULEE, sans numéro, sans retour
    arrière. Seuls un paiement Stripe annulé (CANCELED) et un prélèvement SEPA refusé
    l'appellent (fiche D) ; une session expirée reste EN_ATTENTE.
    / Cancels a PENDING sale, for good. Only Stripe CANCELED and a refused SEPA call it.

    LOCALISATION : BaseBillet/services_vente.py

    - Vente déjà ANNULEE → rendue telle quelle (même message Stripe reçu deux fois).
    - Vente REGLEE → refus (ValueError) : une vente encaissée ne s'annule pas, on fait
      un avoir.
    / Already cancelled: returned as is. Settled: refused (make a credit note).

    :param vente: la `Vente` à annuler
    :return: la vente relue en base, ANNULEE
    """
    with transaction.atomic():
        vente_verrouillee = Vente.objects.select_for_update().get(pk=vente.pk)

        vente_deja_annulee = vente_verrouillee.statut == Vente.Statut.ANNULEE
        if vente_deja_annulee:
            return vente_verrouillee

        vente_reglee = vente_verrouillee.statut == Vente.Statut.REGLEE
        if vente_reglee:
            raise ValueError(
                f"La vente {vente_verrouillee.uuid} est réglée : elle ne s'annule "
                f"pas, il faut faire un avoir."
            )

        vente_verrouillee.statut = Vente.Statut.ANNULEE
        vente_verrouillee.save()

    return vente_verrouillee


def tarif_vendu_d_ecart_d_encaissement(nom_du_produit):
    """
    Le tarif vendu du produit système « Écart d'encaissement » demandé, créé à la
    première demande avec sa catégorie du même nom.
    / The sold price of the requested "collection gap" system product, created on
    first request with its category of the same name.

    LOCALISATION : BaseBillet/services_vente.py

    Seule `ajouter_l_article_d_ecart_d_encaissement` l'utilise. Le produit est fabriqué
    par `tarif_vendu_d_un_produit_systeme`.
    / Only used by ajouter_l_article_d_ecart_d_encaissement; built by
    tarif_vendu_d_un_produit_systeme.

    :param nom_du_produit: `NOM_ECART_RECU_EN_PLUS` ou `NOM_ECART_RECU_EN_MOINS`
    :return: le `PriceSold` à passer à `ajouter_article`
    """
    return tarif_vendu_d_un_produit_systeme(nom_du_produit)


def tarif_vendu_d_un_produit_systeme(nom_du_produit):
    """
    Le tarif vendu d'un produit système, créé à la première demande avec sa catégorie
    du même nom : les deux écarts d'encaissement et les jetons cadeau repris au vidage.
    / The sold price of a system product, created on first request with its category
    of the same name: the two collection gaps and the gift tokens taken back.

    LOCALISATION : BaseBillet/services_vente.py

    Le produit n'est jamais publié et n'est jamais saisi à la main. Son tarif vaut 0 :
    le montant est porté par la ligne (`amount`), pas par le tarif. La catégorie porte
    le même nom : le chargeur du plan comptable la relie à son compte.
    / Never published, never typed by hand. Its price is 0: the amount is on the line.
    The category has the same name: the plan loader links it to its account.

    APPELÉE PAR : `tarif_vendu_d_ecart_d_encaissement` (ce module) et
    laboutik/views.py `_ecrire_la_vente_du_vidage`.

    :param nom_du_produit: `NOM_ECART_RECU_EN_PLUS`, `NOM_ECART_RECU_EN_MOINS` ou
        `NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE`
    :return: le `PriceSold` à passer à `ajouter_article`
    """
    # `_created` et non `_` : « _ » masquerait gettext si on l'importe un jour.
    # / `_created`, not `_`: "_" would shadow gettext.
    categorie_du_produit_systeme, _created = CategorieProduct.objects.get_or_create(
        name=nom_du_produit
    )
    produit_systeme, _created = Product.objects.get_or_create(
        name=nom_du_produit,
        defaults={
            "categorie_article": Product.NONE,
            "categorie_pos": categorie_du_produit_systeme,
            "publish": False,
        },
    )
    tarif_du_produit_systeme, _created = Price.objects.get_or_create(
        product=produit_systeme,
        defaults={"name": nom_du_produit, "prix": Decimal("0"), "publish": False},
    )
    produit_vendu_systeme, _created = ProductSold.objects.get_or_create(
        product=produit_systeme,
        event=None,
        defaults={"categorie_article": produit_systeme.categorie_article},
    )
    tarif_vendu_systeme, _created = PriceSold.objects.get_or_create(
        productsold=produit_vendu_systeme,
        price=tarif_du_produit_systeme,
        defaults={"prix": tarif_du_produit_systeme.prix},
    )
    return tarif_vendu_systeme


def ajouter_l_article_d_ecart_d_encaissement(vente, ecart_en_centimes):
    """
    Ajoute à la vente l'article « Écart d'encaissement » : la différence entre
    l'argent que Stripe annonce et ce que valent les articles. Rien si l'écart vaut 0.
    / Adds the "collection gap" item to the sale: the difference between the money
    Stripe announces and the items' value. Nothing when the gap is 0.

    LOCALISATION : BaseBillet/services_vente.py

    APPELÉE PAR : `encaisser_vente_stripe` (encaissement d'une vente en ligne) et
    `PaiementStripe/utils.py` `partial_refund_payment` (remboursement Stripe).
    / Called by encaisser_vente_stripe and partial_refund_payment.

    L'ARTICLE : écart positif (Stripe a compté plus que les articles) → produit
    « reçu en plus », quantité +1 ; écart négatif → « reçu en moins », quantité −1.
    Prix unitaire = |écart|, TVA 0, hors chiffre d'affaires. La ligne naît VALID et
    sans paiement Stripe : elle ne bloque pas le passage du paiement à VALID
    (`set_paiement_stripe_valid`) et ne déclenche aucune transition (création, pas de
    changement de statut). L'alerte au journal reste à l'appelant.
    / Positive gap: "received more", qty +1; negative: "received less", qty −1. Unit
    price |gap|, VAT 0, off revenue, born VALID without Stripe payment. The caller logs.

    :param vente: la `Vente` EN_ATTENTE qui reçoit l'article
    :param ecart_en_centimes: argent annoncé par Stripe − valeur des articles (int)
    :return: la `LigneArticle` d'écart, ou None si l'écart vaut 0
    """
    if ecart_en_centimes == 0:
        return None

    if ecart_en_centimes > 0:
        nom_du_produit_d_ecart = NOM_ECART_RECU_EN_PLUS
        quantite_de_l_ecart = Decimal("1")
    else:
        nom_du_produit_d_ecart = NOM_ECART_RECU_EN_MOINS
        quantite_de_l_ecart = Decimal("-1")

    article_d_ecart = ajouter_article(
        vente,
        pricesold=tarif_vendu_d_ecart_d_encaissement(nom_du_produit_d_ecart),
        quantite=quantite_de_l_ecart,
        prix_unitaire=abs(ecart_en_centimes),
        taux_tva=Decimal("0"),
        hors_chiffre_affaires=True,
        status=LigneArticle.VALID,
    )
    return article_d_ecart


def encaisser_vente_stripe(paiement_stripe):
    """
    Encaisse la vente d'origine d'un paiement Stripe, au montant que Stripe a
    réellement encaissé. Le point d'encaissement unique de la vente en ligne.
    / Settles the original sale of a Stripe payment, at the amount Stripe really
    collected. The single settlement point of online sales.

    LOCALISATION : BaseBillet/services_vente.py

    APPELÉE PAR : `BaseBillet/signals.py` `set_ligne_article_paid`, à la fin de la
    transition vers PAID (pre_save de `Paiement_stripe`), dans un `try`. Aussi pour
    rejouer un encaissement qui a échoué : on rappelle cette fonction, car un `save()`
    du paiement, déjà VALID, ne rejoue rien.
    / Called at the end of the PAID transition (pre_save), inside a `try`. Also called
    directly to replay a failed settlement.

    Le montant est lu sur l'OBJET reçu : dans le `pre_save`, il n'est pas encore en base.
    / The amount is read on the RECEIVED object: in the pre_save it is not in the database yet.

    FLUX (tout dans une transaction, un point de sauvegarde si l'appelant en a une) :
    0. Paiement sans vente (antérieur au chantier) : rien, noté au journal (INFO).
    1. Verrou du lieu (le même que `encaisser_vente`), vente relue sous verrou.
    2. Déjà REGLEE → rendue telle quelle, RIEN n'est écrit (rejeu du webhook, retour
       du navigateur). ANNULEE → ValueError (Stripe a dit non, puis « payé » : à
       regarder à la main).
    3. Montant encaissé vide → ValueError. Moyen vide alors qu'il y a un règlement à
       écrire → ValueError.
    4. Écart = montant encaissé − Σ totaux catalogue. Écart non nul : un article
       « Écart d'encaissement » (reçu en plus : quantité +1 ; reçu en moins : −1),
       prix unitaire = |écart|, TVA 0, hors chiffre d'affaires, ligne VALID sans
       paiement Stripe.
    5. Montant non nul : UN règlement au moyen du paiement (`Paiement_stripe.moyen`),
       relié au paiement. Montant 0 (facture payée par le solde du client) : aucun.
    6. `encaisser_vente` en dernier. Puis l'alerte d'écart au journal (ERROR).
    / 0. no sale: nothing; 1. lock, read back; 2. settled: returned as is, cancelled:
    refused; 3. empty amount / method: refused; 4. gap item; 5. one payment unless 0;
    6. settle, then log the gap alert.

    :param paiement_stripe: le `Paiement_stripe` constaté payé
    :return: la vente REGLEE, ou None pour un paiement sans vente
    """
    # 0. Un paiement antérieur au chantier n'a pas de vente : rien à encaisser.
    # / 0. A payment older than the sale model has no sale: nothing to settle.
    paiement_sans_vente = paiement_stripe.vente_id is None
    if paiement_sans_vente:
        logger.info(
            f"Paiement Stripe {paiement_stripe.uuid} sans vente d'origine : "
            f"rien à encaisser."
        )
        return None

    with transaction.atomic():
        # 1. Verrou du lieu, puis la vente relue sous verrou : l'état en base fait foi.
        # / 1. Venue lock, then the sale read back under lock.
        nom_du_verrou_du_lieu = f"vente-{connection.schema_name}"
        with connection.cursor() as curseur:
            curseur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [nom_du_verrou_du_lieu],
            )
        vente = Vente.objects.select_for_update().get(pk=paiement_stripe.vente_id)

        # 2. Rejeu : la vente est déjà encaissée, on ne réécrit rien.
        # / 2. Replay: the sale is already settled, nothing is written again.
        vente_deja_reglee = vente.statut == Vente.Statut.REGLEE
        if vente_deja_reglee:
            return vente

        vente_annulee = vente.statut == Vente.Statut.ANNULEE
        if vente_annulee:
            raise ValueError(
                f"Paiement Stripe {paiement_stripe.uuid} constaté payé, mais sa vente "
                f"{vente.uuid} est annulée : à vérifier à la main."
            )

        # 3. Le montant et le moyen viennent du paiement. Aucun des deux n'est inventé.
        # / 3. Amount and method come from the payment. Neither is invented.
        montant_encaisse = paiement_stripe.montant_encaisse
        if montant_encaisse is None:
            raise ValueError(
                f"Paiement Stripe {paiement_stripe.uuid} : montant encaissé vide, le "
                f"chemin qui l'a constaté payé ne l'a pas posé."
            )
        moyen_du_paiement = paiement_stripe.moyen
        reglement_a_ecrire = montant_encaisse != 0
        if reglement_a_ecrire and not moyen_du_paiement:
            raise ValueError(
                f"Paiement Stripe {paiement_stripe.uuid} : moyen de paiement vide, le "
                f"règlement ne peut pas être écrit."
            )

        # 4. L'écart entre l'argent reçu et le catalogue devient un article.
        # / 4. The gap between money received and catalogue becomes an item.
        somme_des_totaux_catalogue = 0
        for article in LigneArticle.objects.filter(vente=vente):
            somme_des_totaux_catalogue += article.total_catalogue
        ecart_en_centimes = montant_encaisse - somme_des_totaux_catalogue
        ajouter_l_article_d_ecart_d_encaissement(vente, ecart_en_centimes)

        # 5. Un seul règlement, du montant encaissé. Jamais de règlement de 0.
        # / 5. One single payment, of the collected amount. Never a 0 payment.
        if reglement_a_ecrire:
            ajouter_reglement(
                vente,
                moyen=moyen_du_paiement,
                montant=montant_encaisse,
                paiement_stripe=paiement_stripe,
            )

        # 6. Encaisser en dernier.
        # / 6. Settle last.
        vente_encaissee = encaisser_vente(vente)

        if ecart_en_centimes != 0:
            logger.error(
                f"Écart d'encaissement sur la vente {vente_encaissee.uuid} "
                f"(paiement Stripe {paiement_stripe.uuid}) : Stripe a encaissé "
                f"{montant_encaisse} centimes pour {somme_des_totaux_catalogue} "
                f"centimes au catalogue (écart {ecart_en_centimes})."
            )

    return vente_encaissee

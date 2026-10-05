"""
Une vente a lire : ce que l'ecran de la caisse et le ticket imprime montrent d'une
`Vente`, ecrit en un seul endroit.
/ A sale to read: what the register screen and the printed receipt show of a sale,
written in one place.

LOCALISATION : laboutik/affichage_des_ventes.py

QUI LIT CE MODULE :
- laboutik/views.py : la liste des ventes (`lignes_de_la_liste_des_ventes`) et le
  detail d'une vente (articles, reglements, ventes liees) ;
- laboutik/printing/formatters.py : le ticket de vente (`formatter_ticket_vente`),
  avec les memes articles regroupes et les memes reglements ;
- l'admin, l'export des lignes et la facture d'une adhesion : les moyens nets d'une
  vente (`noms_des_moyens_nets_de_la_vente`), et les articles de la facture.
Un ecran et un ticket lisent donc la meme chose, avec les memes libelles.
/ Read by the sales list and detail screens and by the sale receipt.

LES REGLES :
- l'argent n'est jamais recalcule : les montants sont des sommes des montants figes
  sur les lignes (`total_ttc`, `part_offerte`) et sur les reglements (`montant`) ;
- un article paye avec plusieurs moyens est ecrit en plusieurs « parts » : elles
  forment UN article (meme tarif, meme evenement, meme prix unitaire, meme poids) ;
- un moyen d'argent s'ecrit par son nom (`nom_du_moyen_de_paiement`), un reglement
  cashless par le nom de sa monnaie (deux moteurs Fedow, `noms_des_monnaies`) ;
- l'ordre des moyens est celui du rapport (`codes_des_moyens_dans_l_ordre`).
/ Money is never recomputed; parts form one item; one naming and ordering rule.
"""

import uuid as uuid_module
from decimal import Decimal

from django.utils.translation import gettext as _

from BaseBillet.models import Configuration, PaymentMethod
from BaseBillet.models_vente import Vente
from comptabilite.presentation import (
    codes_des_moyens_dans_l_ordre,
    euros_a_la_francaise,
    montant_a_la_francaise_dans_l_unite,
    quantite_au_poids_a_la_francaise,
    quantite_lisible,
)
from comptabilite.rapport import (
    MOYENS_CASHLESS,
    nom_du_moyen_de_paiement,
    unite_d_une_vente_au_poids,
)
from laboutik.plan_comptable import noms_des_monnaies


def nom_d_une_monnaie_de_points_introuvable():
    """
    Le nom ecrit pour une vente en points dont la monnaie est introuvable : jamais
    « € ».
    / The name written for a points sale whose currency is not found: never "€".
    """
    return _("Points ou temps")


def badge_de_la_nature_d_une_vente(nature):
    """
    Le mot court du badge de nature d'une vente : « Vente », « Avoir »,
    « Correction », « Carte vidée ». Ce n'est pas le libelle de `Vente.Nature`
    (plus long, lu dans l'admin) : un badge de la caisse doit tenir dans une
    colonne etroite.
    / The short nature badge word of a sale (not the longer `Vente.Nature` label).

    :param nature: `Vente.Nature`
    :return: le mot du badge (traduit)
    """
    badges_par_nature = {
        Vente.Nature.VENTE: _("Vente"),
        Vente.Nature.AVOIR: _("Avoir"),
        Vente.Nature.CORRECTION: _("Correction"),
        Vente.Nature.VIDAGE_CARTE: _("Carte vidée"),
    }
    return badges_par_nature.get(nature, nature)


def phrase_d_une_vente_derivee(vente_derivee):
    """
    La phrase du detail d'une vente pour une vente qui en derive : « Corrigée par la
    vente n° 12 » (correction), « Remboursée par l'avoir n° 13 » (avoir).
    / The detail sentence for a sale derived from this one.

    :param vente_derivee: la `Vente` dont `vente_liee` est la vente affichee
    :return: le texte (traduit)
    """
    if vente_derivee.nature == Vente.Nature.CORRECTION:
        return _("Corrigée par la vente n° %(numero)s") % {
            "numero": vente_derivee.numero
        }
    if vente_derivee.nature == Vente.Nature.AVOIR:
        return _("Remboursée par l'avoir n° %(numero)s") % {
            "numero": vente_derivee.numero
        }
    return _("Vente liée n° %(numero)s") % {"numero": vente_derivee.numero}


def noms_des_monnaies_des_ventes(ventes):
    """
    Le nom de chaque monnaie lue par ces ventes : l'unite d'une vente en points, et
    la monnaie de chaque reglement cashless. Deux requetes au plus, quel que soit le
    nombre de ventes (`noms_des_monnaies`, la regle du rapport : fedow_core, puis
    l'ancien Fedow).
    / The name of each currency read by these sales, in two queries at most.

    Les reglements des ventes sont lus par `vente.reglements.all()` : la liste les
    precharge (`prefetch_related`), aucune requete par vente.
    / Payments are read through `vente.reglements.all()`, prefetched by the list.

    :param ventes: liste de `Vente`
    :return: dict {uuid de la monnaie en texte: nom} (une monnaie introuvable n'y
        est pas)
    """
    uuids_des_monnaies = set()
    for vente in ventes:
        vente_en_points = vente.unite != "EUR"
        if vente_en_points:
            try:
                uuids_des_monnaies.add(str(uuid_module.UUID(vente.unite)))
            except ValueError:
                pass
        reglements_de_la_vente = vente.reglements.all()
        for reglement in reglements_de_la_vente:
            if reglement.asset is not None:
                uuids_des_monnaies.add(str(reglement.asset))
    return noms_des_monnaies(uuids_des_monnaies)


def nom_de_l_unite_de_la_vente(vente, nom_par_uuid_de_monnaie):
    """
    L'unite des montants d'une vente : "" pour une vente en euros, sinon le nom de
    sa monnaie de points ou de temps.
    / A sale's amount unit: "" for euros, else its points currency name.
    """
    if vente.unite == "EUR":
        return ""
    # Les cles du dictionnaire sont des uuid ecrits par `str(UUID)` (minuscules,
    # avec tirets) : l'unite de la vente est ecrite de la meme facon avant d'etre
    # cherchee.
    # / Keys are `str(UUID)`: the sale unit is normalised the same way.
    try:
        cle_de_l_unite = str(uuid_module.UUID(vente.unite))
    except ValueError:
        cle_de_l_unite = vente.unite
    return nom_par_uuid_de_monnaie.get(
        cle_de_l_unite, nom_d_une_monnaie_de_points_introuvable()
    )


def reglements_pour_l_affichage(reglements, nom_par_uuid_de_monnaie, nom_de_l_unite):
    """
    Les reglements d'une vente, prets a afficher, dans l'ordre des moyens de
    `codes_des_moyens_dans_l_ordre` (comptoir, autres moyens d'argent, cashless).
    / A sale's payments ready to display, in the single method order.

    Deux reglements du meme moyen et de la meme monnaie sont additionnes. Le libelle
    d'un moyen d'argent est son nom (`nom_du_moyen_de_paiement`) ; celui d'un
    reglement cashless est le nom de sa monnaie, comme la section des reglements du
    rapport (monnaie introuvable : « Monnaie fédérée » pour le federe, sinon le nom
    du moyen).
    / Same method and currency are added up; money by method name, cashless by
    currency name.

    :param reglements: les `Reglement` de la vente (deja lus)
    :param nom_par_uuid_de_monnaie: dict de `noms_des_monnaies_des_ventes`
    :param nom_de_l_unite: "" (euros) ou le nom de la monnaie de points de la vente
    :return: liste de dict {moyen, libelle, monnaie, montant, montant_a_la_francaise}
    """
    # Les montants par moyen, puis par monnaie.
    # / Amounts by method, then by currency.
    montants_par_moyen_et_monnaie = {}
    for reglement in reglements:
        if reglement.moyen not in montants_par_moyen_et_monnaie:
            montants_par_moyen_et_monnaie[reglement.moyen] = {}
        montants_de_ce_moyen = montants_par_moyen_et_monnaie[reglement.moyen]
        cle_de_la_monnaie = ""
        if reglement.asset is not None:
            cle_de_la_monnaie = str(reglement.asset)
        montant_deja_compte = montants_de_ce_moyen.get(cle_de_la_monnaie, 0)
        montants_de_ce_moyen[cle_de_la_monnaie] = montant_deja_compte + reglement.montant

    reglements_affiches = []
    codes_dans_l_ordre = codes_des_moyens_dans_l_ordre(montants_par_moyen_et_monnaie)
    for code_du_moyen in codes_dans_l_ordre:
        montants_de_ce_moyen = montants_par_moyen_et_monnaie[code_du_moyen]
        for cle_de_la_monnaie, montant in montants_de_ce_moyen.items():
            nom_de_la_monnaie = nom_par_uuid_de_monnaie.get(cle_de_la_monnaie, "")
            libelle_du_reglement = nom_du_moyen_de_paiement(code_du_moyen)
            reglement_cashless = code_du_moyen in MOYENS_CASHLESS
            if reglement_cashless and nom_de_la_monnaie != "":
                libelle_du_reglement = nom_de_la_monnaie
            elif code_du_moyen == PaymentMethod.STRIPE_FED:
                # La monnaie federee, inconnue du lieu : son nom courant.
                # / The federated currency, unknown to the venue: its common name.
                libelle_du_reglement = _("Monnaie fédérée")
            reglements_affiches.append(
                {
                    "moyen": code_du_moyen,
                    "libelle": libelle_du_reglement,
                    "monnaie": nom_de_la_monnaie,
                    "montant": montant,
                    "montant_a_la_francaise": montant_a_la_francaise_dans_l_unite(
                        montant, nom_de_l_unite
                    ),
                }
            )
    return reglements_affiches


def moyens_en_clair(reglements_affiches):
    """
    Les moyens d'une vente en une phrase : « 5,50 € Carte bancaire + 5,00 € Monnaie
    locale ». L'offert (FREE) n'y est pas : ce n'est pas un moyen de paiement, c'est
    la trace d'un cadeau, montree sur l'article. Un reglement en points ou en temps
    s'ecrit par son montant seul : son unite dit deja la monnaie (« 300,00 Points
    fidélité »).
    / A sale's methods in one sentence; offered is left out; a points payment is its
    amount only.

    :param reglements_affiches: liste de `reglements_pour_l_affichage`
    :return: le texte
    """
    morceaux_de_la_phrase = []
    for reglement_affiche in reglements_affiches:
        if reglement_affiche["moyen"] == PaymentMethod.FREE:
            continue
        if reglement_affiche["moyen"] == PaymentMethod.NON_MONETAIRE:
            morceaux_de_la_phrase.append(reglement_affiche["montant_a_la_francaise"])
        else:
            morceaux_de_la_phrase.append(
                f"{reglement_affiche['montant_a_la_francaise']} "
                f"{reglement_affiche['libelle']}"
            )
    # Aucun moyen (une vente entierement offerte) : un tiret, pas une case vide.
    # / No method (a fully offered sale): a dash, not an empty cell.
    if not morceaux_de_la_phrase:
        return "—"
    return " + ".join(morceaux_de_la_phrase)


def reglements_nets_de_la_vente(vente, nom_par_uuid_de_monnaie):
    """
    Les règlements NETS d'une vente : ceux de la vente ET de ses ventes dérivées
    CORRECTION, additionnés par moyen (et par monnaie).
    / A sale's NET payments: those of the sale AND of its CORRECTION sales, added up by
    method (and currency).

    LOCALISATION : laboutik/affichage_des_ventes.py

    Une vente payée en espèces puis corrigée en CB vaut 0 en espèces et le montant en
    CB. C'est la seule règle « comment cette vente est payée » : seuls les règlements
    le savent (une ligne d'article peut porter plusieurs moyens, ou aucun). Les nets
    nuls et l'offert sont rendus tels quels : chaque lecteur décide ce qu'il garde.
    Libellés et ordre : ceux de `reglements_pour_l_affichage`.
    / The single "how this sale is paid" rule. Zero nets and offered are returned as
    they are: each reader decides what it keeps.

    Aucune requête si l'appelant précharge `reglements` et `ventes_derivees__reglements`
    (les noms des monnaies sont reçus, jamais lus ici).
    / No query when the caller prefetches the payments and the derived sales' payments.

    LU PAR : `noms_des_moyens_nets_de_la_vente` (ce module) ; laboutik/views.py (la
    correction de moyen : moyens corrigeables, montant déplacé, garde anti double
    envoi) ; BaseBillet/services_vente.py (`moyen_d_argent_unique_de_la_vente` :
    le champ « Remboursé par » pré-rempli).
    / Read by the method names, the payment method correction and the "Refunded by"
    pre-fill.

    :param vente: la `Vente`
    :param nom_par_uuid_de_monnaie: dict de `noms_des_monnaies_des_ventes`, ou {} :
        un règlement cashless s'écrit alors par le nom de son moyen
    :return: liste de dict de `reglements_pour_l_affichage` (moyen, libelle, monnaie,
        montant, montant_a_la_francaise)
    """
    reglements_de_la_vente_et_de_ses_corrections = list(vente.reglements.all())
    for vente_derivee in vente.ventes_derivees.all():
        if vente_derivee.nature == Vente.Nature.CORRECTION:
            for reglement_de_la_correction in vente_derivee.reglements.all():
                reglements_de_la_vente_et_de_ses_corrections.append(
                    reglement_de_la_correction
                )

    return reglements_pour_l_affichage(
        reglements_de_la_vente_et_de_ses_corrections, nom_par_uuid_de_monnaie, ""
    )


def noms_des_moyens_nets_de_la_vente(vente, nom_par_uuid_de_monnaie):
    """
    « Payé comment » : les noms des moyens d'une vente, après ses corrections.
    / "Paid how": the names of a sale's methods, after its corrections.

    LOCALISATION : laboutik/affichage_des_ventes.py

    Les règlements nets de la vente (`reglements_nets_de_la_vente` : la vente et ses
    ventes CORRECTION). On garde les moyens dont le net n'est pas nul, sans l'offert
    (FREE : la trace d'un cadeau, pas un moyen de paiement).
    / The sale's net payments; methods with a non-zero net are kept, offered left out.

    LU PAR : Administration/admin_tenant.py (fiche utilisateur, liste des ventes,
    onglet des ventes d'une adhésion), Administration/importers/lignearticle_exporter.py
    (colonne « Moyens de la vente »), BaseBillet/tasks.py (pied de la facture d'une
    adhésion).
    / Read by the admin screens, the lines export and the membership invoice footer.

    :param vente: la `Vente`
    :param nom_par_uuid_de_monnaie: dict de `noms_des_monnaies_des_ventes`, ou {} :
        un règlement cashless s'écrit alors par le nom de son moyen
    :return: liste de libellés, sans doublon, dans l'ordre des moyens
    """
    reglements_affiches = reglements_nets_de_la_vente(vente, nom_par_uuid_de_monnaie)
    noms_des_moyens = []
    for reglement_affiche in reglements_affiches:
        if reglement_affiche["moyen"] == PaymentMethod.FREE:
            continue
        if reglement_affiche["montant"] == 0:
            continue
        if reglement_affiche["libelle"] in noms_des_moyens:
            continue
        noms_des_moyens.append(reglement_affiche["libelle"])
    return noms_des_moyens


def lignes_de_la_liste_des_ventes(ventes):
    """
    Une ligne de la liste par vente : numero, heure locale, badge de nature, point
    de vente, total, moyens en clair, nombre d'articles.
    / One list row per sale.

    Aucune requete par vente : les reglements et le point de vente sont precharges,
    le nombre d'articles est annote (`quantite_d_articles`, somme des quantites, une
    pesee comptant pour un article), les noms des monnaies sont lus par lot.
    / No query per sale: prefetched payments and point of sale, annotated quantity,
    currency names in one batch.

    :param ventes: liste de `Vente` (annotees `quantite_d_articles`)
    :return: liste de dict pour `_ligne_vente.html`
    """
    nom_par_uuid_de_monnaie = noms_des_monnaies_des_ventes(ventes)
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()

    lignes = []
    for vente in ventes:
        nom_de_l_unite = nom_de_l_unite_de_la_vente(vente, nom_par_uuid_de_monnaie)
        reglements_affiches = reglements_pour_l_affichage(
            vente.reglements.all(), nom_par_uuid_de_monnaie, nom_de_l_unite
        )
        quantite_d_articles = vente.quantite_d_articles
        if quantite_d_articles is None:
            quantite_d_articles = 0
        nom_du_point_de_vente = ""
        if vente.point_de_vente is not None:
            nom_du_point_de_vente = vente.point_de_vente.name
        heure_locale = vente.datetime_encaissement.astimezone(fuseau_du_lieu)
        lignes.append(
            {
                "uuid": vente.uuid,
                "numero": vente.numero,
                "heure": heure_locale.strftime("%H:%M"),
                "nature": vente.nature,
                "badge_de_la_nature": badge_de_la_nature_d_une_vente(vente.nature),
                "nom_pv": nom_du_point_de_vente,
                "total_a_la_francaise": montant_a_la_francaise_dans_l_unite(
                    vente.total_ttc, nom_de_l_unite
                ),
                "moyens_en_clair": moyens_en_clair(reglements_affiches),
                "nombre_d_articles": quantite_lisible(str(quantite_d_articles)),
            }
        )
    return lignes


def articles_de_la_vente_pour_l_affichage(lignes_de_la_vente, nom_de_l_unite):
    """
    Les articles d'une vente, prets a afficher (ecran) ou a imprimer (ticket).
    / A sale's items, ready to display or print.

    UN ARTICLE = un tarif du catalogue (`Price`), pour un evenement (un billet de
    deux evenements fait deux articles), a un prix unitaire, et a un poids (vrac,
    tireuse). Les lignes qui partagent tout cela forment UN article, dont la quantite
    est la somme de leurs quantites (les « parts » d'une vente de l'historique,
    1,428571 + 1,571429 = 3 jus).
    / ONE item = one catalogue price, one event, one unit price, one weight.

    VENTE AU POIDS OU AU VOLUME A LA CAISSE (D15, Q-H4) : la quantite de la ligne
    est deja en kg ou en litres, et son prix unitaire est le prix du kg ou du litre.
    L'ecran montre « 0,350 kg » et « 12,90 €/kg » (`quantite_au_poids_a_la_francaise`).
    Une pesee est UN article : deux pesees de 0,350 kg restent deux articles de
    4,52 €, jamais un article de 0,700 kg (la ligne entre dans la cle).
    / Register weight / volume sale: the quantity is in kg or litres, the unit price
    per kg or litre. One weighing is ONE item: two weighings stay two items.

    TIRAGE DE LA TIREUSE : meme forme D15, une ligne en litres au prix du litre. Un
    fut s'affiche toujours en litres (« 0,50 L »), qu'il ait un stock ou non
    (`unite_d_une_vente_au_poids`). Un tirage est UN article, comme une pesee.
    / Tap pour: same D15 form, litres at the price per litre; a keg always shows litres.

    Les montants sont des sommes des montants figes sur les lignes (`total_ttc`,
    `part_offerte`), jamais un prix multiplie par une quantite.
    / Amounts are sums of frozen line amounts, never price × quantity.

    :param lignes_de_la_vente: les `LigneArticle` de la vente (tarif, produit et
        evenement lus par `select_related`)
    :param nom_de_l_unite: "" (euros) ou le nom de la monnaie de points
    :return: liste de dict (nom, tarif, evenement, date_de_l_evenement, quantite,
        est_vrac, prix_unitaire, prix_par_unite, part_offerte, total, et leurs textes
        a la francaise ; `quantite_lisible` porte l'unite d'une vente au poids)
    """
    articles_par_cle = {}
    for ligne in lignes_de_la_vente:
        tarif_vendu = ligne.pricesold
        produit_vendu = tarif_vendu.productsold
        produit_lie = produit_vendu.product
        evenement = produit_vendu.event

        est_vrac = bool(ligne.weight_quantity and ligne.weight_quantity > 0)

        # Une pesee de la caisse ou un tirage de la tireuse (D15) est UN article : la
        # ligne elle-meme entre dans la cle, deux pesees ne se fusionnent jamais.
        # / A weighing or a pour is ONE item: the line itself enters the key.
        ligne_d_une_pesee = None
        if est_vrac:
            ligne_d_une_pesee = ligne.pk

        cle_de_l_article = (
            tarif_vendu.price_id,
            produit_vendu.event_id,
            ligne.amount,
            est_vrac,
            ligne_d_une_pesee,
        )

        if cle_de_l_article not in articles_par_cle:
            # Une ligne au poids ou au volume : le caissier veut voir « 0,350 kg » et
            # « 12,90 €/kg ». L'unite vient du type du produit (fut → L) ou du stock
            # (CL → L, sinon kg). Le prix unitaire de la ligne EST le prix du kg ou du
            # litre (D15).
            # / A bulk line: quantity and price per kg / L; unit from the keg type or
            # the stock; the line's unit price IS the price per kg / litre.
            unite_du_stock = None
            unite_de_la_quantite = ""
            prix_par_unite = None
            if est_vrac:
                stock_lie = getattr(produit_lie, "stock_inventaire", None)
                if stock_lie is not None:
                    unite_du_stock = stock_lie.unite
                unite_de_la_quantite = unite_d_une_vente_au_poids(
                    unite_du_stock, produit_lie.categorie_article
                )
                prix_par_unite = (
                    f"{euros_a_la_francaise(ligne.amount)}/{unite_de_la_quantite}"
                )

            nom_de_l_evenement = ""
            date_de_l_evenement = None
            if evenement is not None:
                nom_de_l_evenement = evenement.name
                date_de_l_evenement = evenement.datetime

            articles_par_cle[cle_de_l_article] = {
                "nom": produit_lie.name,
                "tarif": tarif_vendu.price.name,
                "evenement": nom_de_l_evenement,
                "date_de_l_evenement": date_de_l_evenement,
                "quantite": Decimal("0"),
                "est_vrac": est_vrac,
                "unite_du_stock": unite_du_stock,
                "unite_de_la_quantite": unite_de_la_quantite,
                "prix_unitaire": ligne.amount or 0,
                "prix_par_unite": prix_par_unite,
                "part_offerte": 0,
                "total": 0,
            }
        article = articles_par_cle[cle_de_l_article]
        article["quantite"] += ligne.qty
        article["part_offerte"] += ligne.part_offerte
        article["total"] += ligne.total_ttc

    articles_affiches = []
    for article in articles_par_cle.values():
        # La quantite lisible : « 0,350 kg » ou « 0,50 L » pour une vente au poids ou
        # au volume (D15, tireuse comprise), sinon le nombre d'articles.
        # / Readable quantity: "0,350 kg" or "0,50 L" (D15, tap included), or the
        # number of items.
        if article["est_vrac"]:
            article["quantite_lisible"] = quantite_au_poids_a_la_francaise(
                article["quantite"], article["unite_de_la_quantite"]
            )
        else:
            article["quantite_lisible"] = quantite_lisible(str(article["quantite"]))
        article["prix_unitaire_a_la_francaise"] = montant_a_la_francaise_dans_l_unite(
            article["prix_unitaire"], nom_de_l_unite
        )
        article["part_offerte_a_la_francaise"] = montant_a_la_francaise_dans_l_unite(
            article["part_offerte"], nom_de_l_unite
        )
        article["total_a_la_francaise"] = montant_a_la_francaise_dans_l_unite(
            article["total"], nom_de_l_unite
        )
        articles_affiches.append(article)
    return articles_affiches

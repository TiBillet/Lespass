"""
La balance du plan comptable : le total de chaque compte sur une période.
/ The trial balance: each account's total over a period.

LOCALISATION : comptabilite/balance.py

CE QUE FAIT CE MODULE
`balance_de_la_periode(premier_jour, dernier_jour)` additionne, compte par compte, les
lignes des écritures du FEC des clôtures J DATÉES dans la période. Pour chaque compte
qui a bougé : total au débit, total au crédit, solde (débiteur ou créditeur). Puis le
total de la balance : total débit = total crédit.

LES CHIFFRES SONT CEUX DU FEC
Les écritures viennent de `comptabilite/ventilation.py`, le code même du FEC :
- `journees_datees_entre` choisit les J, avec la règle de date du FEC d'une période
  (le jour local de la première vente de la J, dans le fuseau figé dans son rapport) ;
- `ecritures_des_journees` rend leurs écritures, celles que le FEC écrit ligne à ligne.
Ce module n'additionne que des lignes déjà calculées : aucun prix, aucune quantité,
aucune TVA n'est recalculé ici. Les ventes du service en cours (pas encore clôturé)
ne sont pas dans la balance, comme elles ne sont pas dans le FEC.
/ The figures are the FEC's: same J selection, same entries. This module only adds
up lines already computed. Sales not yet closed are not in it, as in the FEC.

LES REFUS SONT CEUX DU FEC
Un compte manquant (`CompteComptableManquant`) ou une écriture déséquilibrée
(`EcritureDesequilibree`) remonte, avec le message du FEC. L'écran de la balance
l'affiche à la place du tableau.
/ Refusals are the FEC's and go up with its message.

LE NOMBRE DE REQUÊTES
Celui de la ventilation : il ne grandit pas avec le nombre de ventes (trois requêtes
de ventes par J, comptes lus une fois pour toute la période).
/ Query count: the breakdown's, independent of the number of sales.

APPELÉE PAR : Administration/admin/laboutik.py (`CompteComptableAdmin.balance` et
`CompteComptableAdmin.balance_csv`, onglet « Gérer » du plan comptable).
Tests : tests/pytest/test_fec_equilibre.py (section « La balance »),
tests/pytest/test_admin_plan_comptable_aide_et_onglets.py (l'écran).
"""

import csv
import io

from django.utils.translation import gettext, gettext_lazy as _

from comptabilite.csv_export import MARQUE_UTF_8_POUR_EXCEL
from comptabilite.presentation import euros_a_la_francaise, texte_sans_formule
from comptabilite.ventilation import ecritures_des_journees, journees_datees_entre
from laboutik.plan_comptable import s_assurer_que_le_plan_existe

# Le nom de chaque famille de comptes, d'après le premier chiffre du numéro. Une
# famille absente de ce tableau s'appelle « Classe N ».
# / Each account family's name, from the number's first digit.
NOM_DE_LA_FAMILLE_PAR_CLASSE = {
    "4": _("4 · Ce que le lieu doit, ou ce qu'on lui doit (tiers, TVA)"),
    "5": _("5 · Où est l'argent (trésorerie)"),
    "6": _("6 · Ce que le lieu dépense (charges)"),
    "7": _("7 · Ce que le lieu gagne (produits)"),
}


def _nom_de_la_famille(classe_du_compte):
    """
    Le nom d'une famille de comptes, ou « Classe N » si elle n'a pas de nom.
    / A family's name, or "Class N".
    """
    if classe_du_compte in NOM_DE_LA_FAMILLE_PAR_CLASSE:
        return NOM_DE_LA_FAMILLE_PAR_CLASSE[classe_du_compte]
    return gettext("Classe %(classe)s") % {"classe": classe_du_compte}


def balance_de_la_periode(premier_jour, dernier_jour):
    """
    La balance d'une période : une ligne par compte qui a bougé, rangée par famille
    (le premier chiffre du numéro), puis le total.
    / The trial balance of a period: one row per account, grouped by family, then the
    total.

    LOCALISATION : comptabilite/balance.py

    FLUX :
    1. le filet du FEC : un lieu sans aucun compte reçoit le plan par défaut ;
    2. les J datées dans la période (`journees_datees_entre`) ;
    3. leurs écritures (`ecritures_des_journees`, le code du FEC) ;
    4. pour chaque compte, la somme des débits et la somme des crédits de ses lignes.

    :param premier_jour: date (incluse)
    :param dernier_jour: date (incluse)
    :return: dict {
        "familles": [{"classe", "nom", "lignes"}],
        "lignes": [{"numero", "libelle", "debit", "credit", "solde_debiteur",
                    "solde_crediteur"} en centimes, plus les mêmes montants écrits
                    pour l'écran (clés « _affiche »)] (toutes, par numéro),
        "total_debit", "total_credit" (centimes), "equilibree" (bool),
        "nombre_de_clotures" (int), "total_debit_affiche", "total_credit_affiche",
        "ecart_affiche" (textes)}
    :raises CompteComptableManquant: comme le FEC
    :raises EcritureDesequilibree: comme le FEC
    """
    # Le filet, comme le FEC : un lieu sans compte reçoit le plan par défaut.
    # / The safety net, like the FEC.
    s_assurer_que_le_plan_existe()

    journees_de_la_periode = journees_datees_entre(premier_jour, dernier_jour)
    ecritures = ecritures_des_journees(journees_de_la_periode)

    # La somme des lignes, compte par compte. Le libellé est celui écrit dans le FEC.
    # / The sum of the lines, account by account; the label is the FEC's.
    totaux_par_numero = {}
    for ecriture in ecritures:
        for ligne_de_l_ecriture in ecriture["lignes"]:
            numero_du_compte = ligne_de_l_ecriture["compte"]
            if numero_du_compte not in totaux_par_numero:
                totaux_par_numero[numero_du_compte] = {
                    "libelle": ligne_de_l_ecriture["libelle"],
                    "debit": 0,
                    "credit": 0,
                }
            totaux_par_numero[numero_du_compte]["debit"] += ligne_de_l_ecriture["debit"]
            totaux_par_numero[numero_du_compte]["credit"] += ligne_de_l_ecriture[
                "credit"
            ]

    # Une ligne par compte, par numéro, avec son solde du bon côté.
    # / One row per account, by number, with its balance on the right side.
    lignes = []
    for numero_du_compte in sorted(totaux_par_numero.keys()):
        totaux_du_compte = totaux_par_numero[numero_du_compte]
        solde = totaux_du_compte["debit"] - totaux_du_compte["credit"]
        solde_debiteur = 0
        solde_crediteur = 0
        if solde > 0:
            solde_debiteur = solde
        if solde < 0:
            solde_crediteur = -solde
        lignes.append(
            {
                "numero": numero_du_compte,
                "libelle": totaux_du_compte["libelle"],
                "debit": totaux_du_compte["debit"],
                "credit": totaux_du_compte["credit"],
                "solde_debiteur": solde_debiteur,
                "solde_crediteur": solde_crediteur,
                # Les montants écrits pour l'écran, à la française ; un solde nul
                # reste vide (le solde n'est que d'un côté).
                # / Amounts written for the screen; a zero balance stays empty.
                "debit_affiche": euros_a_la_francaise(totaux_du_compte["debit"]),
                "credit_affiche": euros_a_la_francaise(totaux_du_compte["credit"]),
                "solde_debiteur_affiche": (
                    euros_a_la_francaise(solde_debiteur) if solde_debiteur else ""
                ),
                "solde_crediteur_affiche": (
                    euros_a_la_francaise(solde_crediteur) if solde_crediteur else ""
                ),
            }
        )

    # Les familles : les lignes déjà triées par numéro se suivent par classe.
    # / Families: rows sorted by number already follow each other by class.
    familles = []
    for ligne in lignes:
        classe_du_compte = ligne["numero"][:1]
        famille_en_cours = familles[-1] if familles else None
        if famille_en_cours is None or famille_en_cours["classe"] != classe_du_compte:
            famille_en_cours = {
                "classe": classe_du_compte,
                "nom": _nom_de_la_famille(classe_du_compte),
                "lignes": [],
            }
            familles.append(famille_en_cours)
        famille_en_cours["lignes"].append(ligne)

    total_debit = 0
    total_credit = 0
    for ligne in lignes:
        total_debit += ligne["debit"]
        total_credit += ligne["credit"]

    return {
        "familles": familles,
        "lignes": lignes,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "equilibree": total_debit == total_credit,
        "nombre_de_clotures": len(journees_de_la_periode),
        "total_debit_affiche": euros_a_la_francaise(total_debit),
        "total_credit_affiche": euros_a_la_francaise(total_credit),
        "ecart_affiche": euros_a_la_francaise(abs(total_debit - total_credit)),
    }


def _ecrire_une_ligne(ecrivain_csv, textes):
    """
    Une ligne du CSV ; chaque texte est protégé contre les formules
    (`texte_sans_formule`), comme dans l'export CSV d'une clôture.
    / One CSV row; every text is protected against formulas.
    """
    textes_proteges = []
    for texte in textes:
        textes_proteges.append(texte_sans_formule(texte))
    ecrivain_csv.writerow(textes_proteges)


def generer_csv_de_la_balance(balance, premier_jour, dernier_jour):
    """
    Le CSV de la balance, au format des autres exports CSV de la comptabilité
    (comptabilite/csv_export.py) : séparateur « ; », UTF-8 avec BOM (ouverture directe
    dans Excel), montants à la française (« 1 050,00 € »), textes protégés contre les
    formules.
    / The trial balance CSV, in the format of the other accounting CSV exports.

    :param balance: le dict de `balance_de_la_periode`
    :param premier_jour: date (incluse)
    :param dernier_jour: date (incluse)
    :return: (contenu en octets, nom du fichier, type du contenu)
    """
    tampon_du_csv = io.StringIO()
    ecrivain_csv = csv.writer(
        tampon_du_csv, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL
    )

    _ecrire_une_ligne(ecrivain_csv, [gettext("Balance des comptes")])
    _ecrire_une_ligne(
        ecrivain_csv,
        [gettext("Du"), premier_jour.strftime("%d/%m/%Y")],
    )
    _ecrire_une_ligne(
        ecrivain_csv,
        [gettext("Au"), dernier_jour.strftime("%d/%m/%Y")],
    )
    _ecrire_une_ligne(ecrivain_csv, [])
    _ecrire_une_ligne(
        ecrivain_csv,
        [
            gettext("Compte"),
            gettext("Libellé"),
            gettext("Débit"),
            gettext("Crédit"),
            gettext("Solde débiteur"),
            gettext("Solde créditeur"),
        ],
    )
    for ligne in balance["lignes"]:
        _ecrire_une_ligne(
            ecrivain_csv,
            [
                ligne["numero"],
                ligne["libelle"],
                euros_a_la_francaise(ligne["debit"]),
                euros_a_la_francaise(ligne["credit"]),
                euros_a_la_francaise(ligne["solde_debiteur"]),
                euros_a_la_francaise(ligne["solde_crediteur"]),
            ],
        )
    _ecrire_une_ligne(
        ecrivain_csv,
        [
            gettext("Total"),
            "",
            euros_a_la_francaise(balance["total_debit"]),
            euros_a_la_francaise(balance["total_credit"]),
            "",
            "",
        ],
    )

    contenu_en_octets = (MARQUE_UTF_8_POUR_EXCEL + tampon_du_csv.getvalue()).encode(
        "utf-8"
    )
    nom_du_fichier = (
        f"balance-{premier_jour:%Y%m%d}-{dernier_jour:%Y%m%d}.csv"
    )
    return contenu_en_octets, nom_du_fichier, "text/csv; charset=utf-8"

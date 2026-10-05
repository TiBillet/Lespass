"""
Garde : aucun montant de ligne recalculé par « prix × quantité » dans le code.
/ Guard: no line amount recomputed as "price × quantity" in the code.

LOCALISATION : tests/pytest/test_garde_aucun_amount_fois_qty.py

RÈGLE MÉTIER TESTÉE (tronc du chantier 05, §2 « Interdit après le chantier »)
L'argent n'est jamais recalculé : il est écrit une seule fois, en centimes entiers, par
`calculer_montants_article` (BaseBillet/services_vente.py), puis seulement additionné.
Ce test lit le code de production (Python, gabarits, JavaScript ; hors migrations et
tests) et échoue s'il y trouve :
- `F("amount") * F("qty")`, `F("qty") * F("amount")`, `F("pricesold__prix") * F("qty")` ;
- `amount * qty`, `amount*qty`, `qty * amount`, y compris sur des attributs ou des
  variables dérivées (`ligne.amount * ligne.qty`, `amount_eur * qty`) ;
- un `int(` autour d'un calcul (`*` ou `/`) sur un montant de ligne (`amount`,
  `total_ttc`, `total_ht`, `total_tva`, `total_catalogue`, `part_offerte`,
  `part_en_jetons`, `cout_achat`).
Le code commenté compte aussi : il se décommente.
/ Reads the production code and fails on any of these patterns; commented code counts.

CE QUE LA GARDE NE VOIT PAS (connu, laissé hors garde)
La règle « `int(` » ne regarde que les NOMS des montants de ligne ci-dessus. Deux cas
connus passent donc, volontairement :
- `laboutik/integrity.py` `calculer_total_ht` : `int(round(amount_ttc_centimes / ...))`
  (fonction retirée en H-2 avec le HMAC par ligne) ;
- `Administration/management/commands/demo_data_v2.py` : `int(round(amount_eur * 100))`,
  une conversion d'euros en centimes de la démo (réécrite en H-3).
/ Known cases the guard does not see: names outside the list above.

LISTE D'EXCEPTIONS FERMÉE
- les fichiers retirés en H-2 (fiche H §3 : ancien moteur caisse, ancien moteur en
  ligne, ancien FEC, ancienne ventilation, ancien CSV comptable), entiers, avec la
  raison « retiré en H-2 » ;
- UNE occurrence de `laboutik/views.py` : le HT de la branche « vente absente » de
  `_creer_lignes_articles`, avec la raison « retiré en H-3 (branche vente absente) ».
  Elle est reconnue par son extrait, jamais par le fichier entier : toute autre
  occurrence dans `laboutik/views.py` fait échouer le test.
Une exception qui ne trouve plus d'occurrence est périmée : le test échoue pour la
faire retirer.
/ Closed exception list: whole files removed in H-2, plus ONE excerpt of
laboutik/views.py removed in H-3; a stale exception fails the test.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md (§3, §5 test
10) ; CHANTIER-05-montants-entiers.md (§2) ; brief CHANTIER-05-briefs/05-H-1d.md (règle
3, test 7).

Lancer / Run : make test ARGS="tests/pytest/test_garde_aucun_amount_fois_qty.py"
"""

import os
import re
from pathlib import Path

from django.conf import settings

# Les extensions lues : le code Python, les gabarits, le JavaScript.
# / The read extensions: Python, templates, JavaScript.
EXTENSIONS_DU_CODE_LU = (".py", ".html", ".js")

# Les dossiers jamais lus : cachés (.venv, .git…), dépendances, fichiers copiés par
# `collectstatic` (www), migrations, tests, documentation.
# / Never read: hidden folders, dependencies, collectstatic copies, migrations, tests,
# documentation.
DOSSIERS_JAMAIS_LUS = {
    "node_modules",
    "www",
    "migrations",
    "tests",
    "TECH_DOC",
    "__pycache__",
    "venv",
}

# Les fichiers retirés en H-2 (fiche H §3, lignes « Ancien moteur caisse », « Ancien
# moteur en ligne », « Ancien FEC, ancienne ventilation, ancien CSV comptable »).
# Seuls eux peuvent figurer dans la liste d'exceptions.
# / The files removed in H-2 (sheet H §3): the only ones allowed as exceptions.
FICHIERS_RETIRES_EN_H2 = {
    "laboutik/reports.py",
    "comptabilite/services.py",
    "laboutik/fec.py",
    "laboutik/ventilation.py",
    "laboutik/csv_comptable.py",
    "laboutik/profils_csv.py",
}

RAISON_RETIRE_EN_H2 = "retiré en H-2"

# La seule exception hors H-2 : une occurrence de la branche « vente absente » de
# `_creer_lignes_articles` (fiche H §4, retirée en H-3), reconnue par son extrait.
# / The only non-H-2 exception: one excerpt of the "no sale" branch, removed in H-3.
EXCEPTION_BRANCHE_VENTE_ABSENTE = {
    "chemin": "laboutik/views.py",
    "raison": "retiré en H-3 (branche vente absente)",
    "extrait": "ligne_a_chainer.amount * ligne_a_chainer.qty",
}

# La liste d'exceptions fermée. `extrait` vide (None) : tout le fichier est excepté ;
# sinon seules les occurrences dont l'extrait contient ce texte.
# / The closed exception list. No excerpt: the whole file; else matching excerpts only.
EXCEPTIONS = [
    {"chemin": "laboutik/reports.py", "raison": RAISON_RETIRE_EN_H2, "extrait": None},
    {
        "chemin": "comptabilite/services.py",
        "raison": RAISON_RETIRE_EN_H2,
        "extrait": None,
    },
    EXCEPTION_BRANCHE_VENTE_ABSENTE,
]

# Les motifs interdits, ligne par ligne.
# / The forbidden patterns, line by line.
MOTIFS_INTERDITS_SUR_UNE_LIGNE = [
    # F("amount") * F("qty"), F("qty") * F("amount"), F("pricesold__prix") * F("qty")
    re.compile(
        r"""F\(\s*["'](amount|qty|pricesold__prix)["']\s*\)\s*\*\s*F\(\s*["'](qty|amount)["']\s*\)"""
    ),
    # amount * qty, amount*qty, ligne.amount * ligne.qty, amount_eur * qty
    re.compile(r"\bamount\w*\s*\*\s*[\w.]*qty"),
    # qty * amount, ligne.qty * ligne.amount
    re.compile(r"\bqty\w*\s*\*\s*[\w.]*amount"),
]

# Un montant de ligne, dans le contenu d'un `int(...)`.
# / A line amount, inside an `int(...)`.
MONTANT_DE_LIGNE = re.compile(
    r"\b(amount|total_ttc|total_ht|total_tva|total_catalogue|part_offerte|"
    r"part_en_jetons|cout_achat)\b"
)
OPERATEUR_DE_CALCUL = re.compile(r"[*/]")
DEBUT_D_UN_INT = re.compile(r"\bint\(")


def fichiers_du_code_de_production(racine_du_projet):
    """
    Les fichiers du code de production, en chemins relatifs à la racine (séparateur
    « / »), triés : extensions lues, hors dossiers jamais lus, hors fichiers de tests
    (`test_*.py`, `conftest.py`) et hors JavaScript minifié.
    / The production code files, relative paths, sorted.
    """
    chemins = []
    for dossier, sous_dossiers, fichiers in os.walk(racine_du_projet):
        # On retire les dossiers à ne pas parcourir : os.walk ne descend plus dedans.
        # / Remove the folders not to walk: os.walk no longer goes into them.
        sous_dossiers_a_parcourir = []
        for sous_dossier in sous_dossiers:
            if sous_dossier.startswith("."):
                continue
            if sous_dossier in DOSSIERS_JAMAIS_LUS:
                continue
            sous_dossiers_a_parcourir.append(sous_dossier)
        sous_dossiers[:] = sous_dossiers_a_parcourir

        for nom_du_fichier in fichiers:
            if not nom_du_fichier.endswith(EXTENSIONS_DU_CODE_LU):
                continue
            if nom_du_fichier.endswith(".min.js"):
                continue
            if nom_du_fichier.startswith("test_") or nom_du_fichier == "conftest.py":
                continue
            chemin_complet = Path(dossier) / nom_du_fichier
            chemins.append(chemin_complet.relative_to(racine_du_projet).as_posix())
    return sorted(chemins)


def contenu_entre_parentheses(texte, position_apres_la_parenthese):
    """
    Le texte entre une parenthèse ouvrante et SA parenthèse fermante (les parenthèses
    imbriquées sont comptées). La position donnée est celle juste après « ( ».
    / The text between an opening parenthesis and ITS closing one.
    """
    profondeur = 1
    position = position_apres_la_parenthese
    while position < len(texte) and profondeur > 0:
        caractere = texte[position]
        if caractere == "(":
            profondeur += 1
        elif caractere == ")":
            profondeur -= 1
        position += 1
    return texte[position_apres_la_parenthese : position - 1]


def occurrences_interdites_du_fichier(texte_du_fichier):
    """
    Les occurrences interdites d'un fichier : une liste de (numéro de ligne, extrait).
    Un `int(` est lu jusqu'à SA parenthèse fermante, même sur plusieurs lignes.
    / A file's forbidden occurrences: (line number, excerpt) list.
    """
    occurrences = []
    numeros_deja_notes = set()

    lignes_du_fichier = texte_du_fichier.splitlines()
    for numero_de_ligne, ligne in enumerate(lignes_du_fichier, start=1):
        for motif in MOTIFS_INTERDITS_SUR_UNE_LIGNE:
            if motif.search(ligne):
                occurrences.append((numero_de_ligne, ligne.strip()))
                numeros_deja_notes.add(numero_de_ligne)
                break

    for debut in DEBUT_D_UN_INT.finditer(texte_du_fichier):
        contenu = contenu_entre_parentheses(texte_du_fichier, debut.end())
        calcul_sur_un_montant_de_ligne = (
            MONTANT_DE_LIGNE.search(contenu) is not None
            and OPERATEUR_DE_CALCUL.search(contenu) is not None
        )
        if not calcul_sur_un_montant_de_ligne:
            continue
        # Un `int(` sur plusieurs lignes, dont une ligne est déjà notée par un motif
        # ligne à ligne : la même occurrence, notée une seule fois.
        # / A multi-line `int(` with a line already noted: the same occurrence.
        numero_de_ligne = texte_du_fichier.count("\n", 0, debut.start()) + 1
        derniere_ligne_du_int = numero_de_ligne + contenu.count("\n")
        lignes_du_int = set(range(numero_de_ligne, derniere_ligne_du_int + 1))
        if lignes_du_int & numeros_deja_notes:
            continue
        extrait = " ".join(contenu.split())
        occurrences.append((numero_de_ligne, f"int({extrait[:120]})"))
        numeros_deja_notes.add(numero_de_ligne)

    return sorted(occurrences)


def occurrences_interdites_du_projet(racine_du_projet):
    """
    Toutes les occurrences interdites du code de production :
    {chemin relatif : [(numéro de ligne, extrait), ...]}, seulement les fichiers qui en
    ont.
    / All forbidden occurrences of the production code, by file.
    """
    occurrences_par_fichier = {}
    for chemin_relatif in fichiers_du_code_de_production(racine_du_projet):
        chemin_complet = Path(racine_du_projet) / chemin_relatif
        texte_du_fichier = chemin_complet.read_text(encoding="utf-8")
        occurrences = occurrences_interdites_du_fichier(texte_du_fichier)
        if occurrences:
            occurrences_par_fichier[chemin_relatif] = occurrences
    return occurrences_par_fichier


def l_exception_couvre_l_occurrence(exception, chemin_relatif, extrait):
    """Dit si une exception de la liste couvre cette occurrence : même fichier, et
    extrait reconnu quand l'exception en donne un.
    / Tells whether an exception covers this occurrence."""
    if exception["chemin"] != chemin_relatif:
        return False
    if exception["extrait"] is None:
        return True
    return exception["extrait"] in extrait


def test_garde_aucun_amount_fois_qty_dans_le_projet():
    """
    Aucune occurrence interdite hors de la liste d'exceptions fermée ; la liste ne
    contient que des fichiers retirés en H-2 (raison « retiré en H-2 ») et l'extrait de
    la branche « vente absente » (raison « retiré en H-3 ») ; chaque exception couvre
    encore au moins une occurrence (sinon elle est périmée).
    / No forbidden occurrence outside the closed exception list; the list holds only
    H-2 files and the H-3 excerpt, each still needed.
    """
    racine_du_projet = Path(settings.BASE_DIR)

    # La liste d'exceptions est fermée : des fichiers retirés en H-2, entiers, ou
    # l'extrait de la branche « vente absente ».
    # / The exception list is closed: whole H-2 files, or the H-3 excerpt.
    for exception in EXCEPTIONS:
        if exception == EXCEPTION_BRANCHE_VENTE_ABSENTE:
            continue
        assert exception["chemin"] in FICHIERS_RETIRES_EN_H2, (
            f"{exception['chemin']} n'est pas retiré en H-2 : il ne peut pas être excepté."
        )
        assert exception["raison"] == RAISON_RETIRE_EN_H2, (
            f"Raison de l'exception {exception['chemin']} : « {exception['raison']} » "
            f"au lieu de « {RAISON_RETIRE_EN_H2} »."
        )
        assert exception["extrait"] is None, (
            f"L'exception {exception['chemin']} vaut pour le fichier entier."
        )

    occurrences_par_fichier = occurrences_interdites_du_projet(racine_du_projet)

    # Chaque occurrence : couverte par une exception, ou interdite.
    # / Each occurrence: covered by an exception, or forbidden.
    occurrences_hors_exceptions = []
    exceptions_utilisees = []
    for chemin_relatif, occurrences in occurrences_par_fichier.items():
        for numero_de_ligne, extrait in occurrences:
            exception_qui_couvre = None
            for exception in EXCEPTIONS:
                if l_exception_couvre_l_occurrence(exception, chemin_relatif, extrait):
                    exception_qui_couvre = exception
            if exception_qui_couvre is None:
                occurrences_hors_exceptions.append(
                    f"{chemin_relatif}:{numero_de_ligne}  {extrait}"
                )
            elif exception_qui_couvre not in exceptions_utilisees:
                exceptions_utilisees.append(exception_qui_couvre)

    # Une exception qui ne couvre plus rien est périmée : la retirer de la liste.
    # / An exception covering nothing is stale: remove it from the list.
    exceptions_perimees = []
    for exception in EXCEPTIONS:
        if exception not in exceptions_utilisees:
            exceptions_perimees.append(exception["chemin"])
    assert exceptions_perimees == [], (
        f"Exceptions périmées (plus aucune occurrence) : {exceptions_perimees}."
    )

    assert occurrences_hors_exceptions == [], (
        f"{len(occurrences_hors_exceptions)} occurrence(s) de « montant × quantité » "
        f"hors de la liste d'exceptions :\n" + "\n".join(occurrences_hors_exceptions)
    )

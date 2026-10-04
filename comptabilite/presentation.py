"""
La présentation du rapport des ventes : ce qu'un bénévole lit, section par section.
/ Display of the sales report: what a volunteer reads, section by section.

LOCALISATION : comptabilite/presentation.py

Ce module transforme le dictionnaire du rapport (`RapportDesVentes`, stocké dans
`ClotureCaisse.rapport_json`, ou le rapport X temps réel) en une liste de sections prêtes
à afficher. TOUS les lecteurs du rapport lisent cette liste : la fiche de l'admin, le
rapport temps réel, le PDF, le tableur Excel, le CSV. Ils montrent donc les mêmes
sections, dans le même ordre, avec les mêmes montants.
/ Turns the report dictionary into a list of sections ready to display. Every reader
uses it: admin page, real-time report, PDF, Excel, CSV.

FLUX :
- comptabilite/admin.py `changeform_view`, `rapport_temps_reel` → `sections_pour_affichage`
  → gabarit `comptabilite/admin/_sections_rapport.html` ;
- comptabilite/pdf.py, excel_export.py, csv_export.py → `sections_pour_affichage`.

LES RÈGLES D'AFFICHAGE (fiche F §2) :
- L'ordre : d'abord l'essentiel (en-tête, chiffre d'affaires, règlements, caisse
  espèces, réconciliation, offerts), puis, repliés, l'annexe, les points, la marge brute,
  le détail, l'intégrité (et, au rapport X, l'habitus des cartes et les opérateurs).
  Une section absente du rapport n'est pas affichée (la caisse espèces d'une M, par
  exemple).
- Les montants du rapport sont signés (un avoir, des espèces rendues, un remboursement
  sont négatifs). Une ligne dont le libellé dit déjà que l'argent sort (avoirs,
  remboursements, espèces rendues, cartes vidées, sorties de caisse) montre le montant
  en POSITIF. Une somme nette (un moyen de paiement, un solde, un écart) garde son signe.
- La phrase de réconciliation est écrite ici, jamais stockée : « Argent reçu = ventes
  payées en argent + recharges − remboursements − cartes vidées ± écarts
  d'encaissement », avec des montants positifs après « − ».
- L'opérateur d'une correction est stocké par son identifiant : son nom est retrouvé
  ici (nom complet, sinon email), « Compte supprimé » s'il n'existe plus.
- Un montant s'écrit à la française par `euros_a_la_francaise` (« 1 050,00 € ») : la
  seule fonction qui écrit un montant, pour tous les lecteurs.
- Les heures d'un rapport s'écrivent dans le fuseau figé dans son en-tête au moment du
  calcul (`fuseau_horaire`) : un lieu qui change de fuseau voit ses anciens Z dans leur
  fuseau d'origine. Repli : le fuseau actuel du lieu (une ancienne clôture sans ce
  champ).
/ Display rules: order, signs, the reconciliation sentence, the operator's name, one
single amount formatter, the time zone frozen in the report.

LA FORME D'UNE SECTION (un dictionnaire) :
    {
        "cle": "chiffre_affaires",          # la clé du rapport
        "testid": "chiffre-affaires",       # pour data-testid
        "titre": "Chiffre d'affaires",
        "repliee": False,                    # True : repliée dans un <details>
        "phrase": "",                        # une phrase à lire (réconciliation…)
        "phrase_en_alerte": False,           # True : la phrase est écrite en rouge
        "tableaux": [ tableau, ... ],
    }
Un tableau : {"titre", "testid", "alerte", "colonnes": [textes], "lignes": [[cellule]]}.
Une cellule : {"texte": ce qui est écrit, "valeur": le nombre (Decimal, en euros pour un
montant) ou None pour un texte, "est_un_montant": True pour des euros}. Le tableur écrit
la valeur (un nombre qu'on peut additionner), les autres lecteurs écrivent le texte.
/ Shape of a section, a table and a cell.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§2).
Tests : tests/pytest/test_comptabilite_admin.py, tests/pytest/test_comptabilite_exports.py
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils.translation import gettext, ngettext

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration, PaymentMethod
from comptabilite.models import ClotureCaisse
from comptabilite.rapport import (
    CLE_PLUSIEURS_MOYENS,
    MOYENS_CASHLESS,
    STATUT_INTEGRITE_OK,
    nom_du_moyen_de_paiement,
)

# L'espace insécable : entre les milliers, et entre un nombre et « € ».
# / The non-breaking space: between thousands, and between a number and "€".
ESPACE_INSECABLE = "\u00a0"

# Le signe moins typographique, pour un montant négatif.
# / The typographic minus sign, for a negative amount.
SIGNE_MOINS = "\u2212"

# Le texte d'une mention légale vide : on voit qu'elle manque.
# / The text of an empty legal mention: the gap is visible.
MENTION_VIDE = "—"

# Les premiers caractères qui font d'un texte une formule dans un tableur.
# / First characters that turn a text into a spreadsheet formula.
DEBUTS_D_UNE_FORMULE = ("=", "+", "-", "@")


# ----------------------------------------------------------------------
# Les nombres et les montants
# / Numbers and amounts
# ----------------------------------------------------------------------


def _nombre_a_deux_decimales(nombre_en_centiemes):
    """
    Écrit un nombre entier de centièmes avec deux décimales, à la française :
    105000 → « 1 050,00 », −350 → « −3,50 ». Calcul en entiers : jamais de nombre à
    virgule.
    / Writes a whole number of hundredths with two decimals, French style.
    """
    if nombre_en_centiemes is None:
        nombre_en_centiemes = 0
    nombre = int(nombre_en_centiemes)

    if nombre < 0:
        signe = SIGNE_MOINS
    else:
        signe = ""
    valeur_absolue = abs(nombre)
    partie_entiere = valeur_absolue // 100
    partie_decimale = valeur_absolue % 100

    # Les milliers : on découpe les chiffres par groupes de trois, en partant de la fin.
    # / Thousands: digits are cut into groups of three, from the end.
    chiffres_restants = str(partie_entiere)
    groupes_de_trois_chiffres = []
    while len(chiffres_restants) > 3:
        groupes_de_trois_chiffres.insert(0, chiffres_restants[-3:])
        chiffres_restants = chiffres_restants[:-3]
    groupes_de_trois_chiffres.insert(0, chiffres_restants)
    partie_entiere_avec_milliers = ESPACE_INSECABLE.join(groupes_de_trois_chiffres)

    return f"{signe}{partie_entiere_avec_milliers},{partie_decimale:02d}"


def euros_a_la_francaise(montant_en_centimes):
    """
    Écrit un montant en centimes en euros, à la française : 105000 → « 1 050,00 € »
    (espaces insécables), −350 → « −3,50 € ». La seule fonction qui écrit un montant,
    pour tous les lecteurs du rapport.
    / Writes cents as French euros. The single amount formatter of every reader.

    :param montant_en_centimes: un entier (None vaut 0)
    :return: le texte du montant
    """
    return f"{_nombre_a_deux_decimales(montant_en_centimes)}{ESPACE_INSECABLE}€"


def quantite_lisible(quantite_en_texte):
    """
    Une quantité du rapport (un `Decimal` écrit en texte, ex. « 3.000000 ») sans zéros
    inutiles, à la française : « 3 », « 1,428571 », « −1 » (avec le même signe moins
    que les montants).
    / A report quantity without useless zeros, French style.
    """
    if quantite_en_texte is None or quantite_en_texte == "":
        return "0"
    quantite = Decimal(str(quantite_en_texte))

    if quantite < 0:
        signe = SIGNE_MOINS
    else:
        signe = ""
    quantite_sans_signe = abs(quantite)

    if quantite_sans_signe == quantite_sans_signe.to_integral_value():
        return f"{signe}{int(quantite_sans_signe)}"
    quantite_sans_zeros_inutiles = format(quantite_sans_signe.normalize(), "f")
    return f"{signe}{quantite_sans_zeros_inutiles.replace('.', ',')}"


def commence_comme_une_formule(texte):
    """
    Vrai si un texte commence par « = », « + », « - » ou « @ » : un tableur le lirait
    comme une formule (un nom de produit « =1+1 », ou pire, une formule qui appelle
    Internet).
    / True when a text starts like a spreadsheet formula.
    """
    return str(texte).startswith(DEBUTS_D_UNE_FORMULE)


def texte_sans_formule(texte):
    """
    Un texte écrit dans un CSV : s'il commence comme une formule, il est précédé d'une
    apostrophe (l'usage habituel du CSV). Le tableur, lui, garde le texte tel quel et
    pose le marqueur natif « texte » sur la case (comptabilite/excel_export.py).
    / A text written in a CSV: an apostrophe is added in front of a formula-like start.
    """
    texte = str(texte)
    if commence_comme_une_formule(texte):
        return f"'{texte}"
    return texte


def nom_du_fichier_de_la_cloture(cloture, extension):
    """
    Le nom d'un fichier exporté : « cloture-<numéro>-<date de fin>.<extension> ». La
    date est le jour de fin de la clôture EN HEURE DU LIEU (une J close à 2 h du matin
    UTC est encore la veille en Martinique).
    / An export file name, dated by the closure's end day in the venue's local time.

    :param cloture: la `ClotureCaisse`
    :param extension: « pdf », « xlsx » ou « csv »
    """
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    fin_en_heure_du_lieu = cloture.datetime_fin.astimezone(fuseau_du_lieu)
    return (
        f"cloture-{cloture.numero_sequentiel}-"
        f"{fin_en_heure_du_lieu:%Y%m%d}.{extension}"
    )


def _cellule_texte(texte):
    """Une cellule de texte. / A text cell."""
    if texte is None:
        texte = ""
    return {"texte": str(texte), "valeur": None, "est_un_montant": False}


def _cellule_montant(montant_en_centimes):
    """
    Une cellule de montant : le texte à la française, et la valeur en euros (un
    `Decimal` exact) pour le tableur.
    / An amount cell: the French text, and the exact value in euros.
    """
    if montant_en_centimes is None:
        montant_en_centimes = 0
    valeur_en_euros = Decimal(int(montant_en_centimes)) / Decimal(100)
    return {
        "texte": euros_a_la_francaise(montant_en_centimes),
        "valeur": valeur_en_euros,
        "est_un_montant": True,
    }


def _cellule_nombre(nombre):
    """
    Une cellule de nombre entier (un compte). Un négatif porte le même signe moins
    que les montants.
    / A whole number cell (a count).
    """
    if nombre is None:
        nombre = 0
    nombre = int(nombre)
    if nombre < 0:
        texte_du_nombre = f"{SIGNE_MOINS}{abs(nombre)}"
    else:
        texte_du_nombre = str(nombre)
    return {
        "texte": texte_du_nombre,
        "valeur": Decimal(nombre),
        "est_un_montant": False,
    }


def _cellule_quantite(quantite_en_texte):
    """Une cellule de quantité (texte du rapport). / A quantity cell."""
    if quantite_en_texte is None or quantite_en_texte == "":
        quantite_en_texte = "0"
    return {
        "texte": quantite_lisible(quantite_en_texte),
        "valeur": Decimal(str(quantite_en_texte)),
        "est_un_montant": False,
    }


def _cellule_points(nombre_en_centiemes):
    """
    Une cellule de points (ou de temps), en centièmes dans le rapport : 1250 → « 12,50 ».
    / A points cell, in hundredths in the report.
    """
    if nombre_en_centiemes is None:
        nombre_en_centiemes = 0
    return {
        "texte": _nombre_a_deux_decimales(nombre_en_centiemes),
        "valeur": Decimal(int(nombre_en_centiemes)) / Decimal(100),
        "est_un_montant": False,
    }


def _date_heure_locale(date_en_texte_iso, fuseau_du_lieu):
    """
    Une date du rapport (texte ISO) en heure locale du lieu : « 03/10/2026 18:30 ».
    / A report date (ISO text) in the venue's local time.
    """
    if not date_en_texte_iso:
        return ""
    moment = datetime.fromisoformat(date_en_texte_iso)
    moment_local = moment.astimezone(fuseau_du_lieu)
    return moment_local.strftime("%d/%m/%Y %H:%M")


def _tableau(titre, testid, colonnes, lignes, alerte=False, message_d_alerte=""):
    """
    Un tableau d'une section. Un tableau en alerte est écrit en rouge ; son message
    d'alerte dit la même chose en mots (une couleur seule ne se lit pas avec un
    lecteur d'écran).
    / A table of a section; an alert table also carries a text message.
    """
    return {
        "titre": titre,
        "testid": testid,
        "alerte": alerte,
        "message_d_alerte": message_d_alerte,
        "colonnes": colonnes,
        "lignes": lignes,
    }


def _criteres_de_tri_d_un_element(element_a_trier):
    """
    La clé de tri d'un élément à trier : un couple (critères de tri, valeur), trié par
    ses critères seulement.
    / The sort key of a (criteria, value) pair: its criteria.
    """
    criteres_de_tri, _valeur = element_a_trier
    return criteres_de_tri


def _valeurs_triees(dictionnaire_du_rapport, noms_des_champs_de_tri):
    """
    Les valeurs d'un dictionnaire du rapport, triées par ces champs (des textes, sans
    tenir compte des majuscules), puis par leur clé. Le rapport stocké est un `jsonb`,
    qui ne garde pas l'ordre des clés : l'affichage trie toujours lui-même, et deux
    lignes au même nom gardent toujours le même ordre (par leur clé).
    / The values of a report dictionary sorted by these text fields, then by key: the
    stored jsonb does not keep key order.
    """
    elements_a_trier = []
    for cle, valeur in dictionnaire_du_rapport.items():
        criteres_de_tri = []
        for nom_du_champ in noms_des_champs_de_tri:
            texte_du_champ = valeur.get(nom_du_champ) or ""
            criteres_de_tri.append(str(texte_du_champ).casefold())
        criteres_de_tri.append(str(cle))
        elements_a_trier.append((tuple(criteres_de_tri), valeur))

    elements_a_trier.sort(key=_criteres_de_tri_d_un_element)

    valeurs_triees = []
    for _criteres, valeur in elements_a_trier:
        valeurs_triees.append(valeur)
    return valeurs_triees


def _section(cle, titre, repliee, tableaux, phrase="", phrase_en_alerte=False):
    """Une section prête à afficher. / A section ready to display."""
    return {
        "cle": cle,
        "testid": cle.replace("_", "-"),
        "titre": titre,
        "repliee": repliee,
        "phrase": phrase,
        "phrase_en_alerte": phrase_en_alerte,
        "tableaux": tableaux,
    }


def _libelles_d_une_liste_de_moyens(codes_separes_par_des_virgules):
    """
    « CA, CC » → « Espèces, Carte bancaire » : les moyens d'une correction, stockés en
    codes, écrits par leur nom.
    / Correction methods, stored as codes, written by name.
    """
    if not codes_separes_par_des_virgules:
        return ""
    libelles = []
    codes_des_moyens = codes_separes_par_des_virgules.split(",")
    for code_du_moyen in codes_des_moyens:
        libelles.append(nom_du_moyen_de_paiement(code_du_moyen.strip()))
    return ", ".join(libelles)


# ----------------------------------------------------------------------
# Les opérateurs
# / Operators
# ----------------------------------------------------------------------


def _nom_affiche_d_un_utilisateur(utilisateur):
    """
    Le nom affiché d'un utilisateur : prénom et nom, sinon prénom, sinon email.
    / A user's display name: first and last name, otherwise first name, otherwise email.
    """
    prenom = utilisateur.first_name or ""
    nom = utilisateur.last_name or ""
    nom_complet = f"{prenom} {nom}".strip()
    if nom_complet:
        return nom_complet
    return utilisateur.email


def _noms_des_operateurs_des_corrections(liste_des_corrections):
    """
    Les noms affichés des opérateurs des corrections, par identifiant (texte), lus en
    une seule requête. Un identifiant sans compte n'est pas dans le résultat.
    / Operators' display names by id, read in one query.
    """
    identifiants_des_operateurs = []
    for correction in liste_des_corrections:
        identifiant = correction.get("operateur")
        if identifiant:
            identifiants_des_operateurs.append(identifiant)

    noms_par_identifiant = {}
    if len(identifiants_des_operateurs) == 0:
        return noms_par_identifiant

    operateurs_trouves = TibilletUser.objects.filter(pk__in=identifiants_des_operateurs)
    for operateur in operateurs_trouves:
        noms_par_identifiant[str(operateur.pk)] = _nom_affiche_d_un_utilisateur(
            operateur
        )
    return noms_par_identifiant


# ----------------------------------------------------------------------
# Les sections
# / The sections
# ----------------------------------------------------------------------


def _section_en_tete(rapport, fuseau_du_lieu):
    """
    Section 1 : lieu, mentions légales (stockées dans le Z le jour de la clôture),
    niveau, numéro de clôture, période, plage des ventes, opérations numérotées,
    perpétuels. Le rapport X n'a ni niveau, ni numéro, ni perpétuel. Une mention vide
    s'écrit « — » : on voit qu'elle manque ; une ancienne clôture sans mentions légales
    les écrit toutes « — ».
    Les « opérations numérotées » sont toutes les ventes réglées de la période, quelle
    que soit leur nature (clé `nombre_de_ventes` du rapport) : les avoirs, les cartes
    vidées et les corrections y sont, et leurs nombres sont lus dans l'annexe.
    / Section 1: venue, legal mentions (frozen in the Z), level, closure number, period,
    sales range, numbered operations, perpetuals.
    """
    en_tete = rapport["en_tete"]
    lignes = []
    lignes.append(
        [_cellule_texte(gettext("Lieu")), _cellule_texte(en_tete.get("lieu"))]
    )

    mentions_legales = en_tete.get("mentions_legales", {})
    libelles_des_mentions = [
        ("adresse", gettext("Adresse")),
        ("code_postal", gettext("Code postal")),
        ("ville", gettext("Ville")),
        ("siren", gettext("SIREN / SIRET")),
        ("numero_tva", gettext("Numéro de TVA")),
        ("email", gettext("Email")),
        ("telephone", gettext("Téléphone")),
    ]
    for nom_de_la_mention, libelle_de_la_mention in libelles_des_mentions:
        texte_de_la_mention = mentions_legales.get(nom_de_la_mention) or MENTION_VIDE
        lignes.append(
            [
                _cellule_texte(libelle_de_la_mention),
                _cellule_texte(texte_de_la_mention),
            ]
        )

    if "niveau" in en_tete:
        libelles_des_niveaux = dict(ClotureCaisse.NIVEAU_CHOICES)
        libelle_du_niveau = libelles_des_niveaux.get(
            en_tete["niveau"], en_tete["niveau"]
        )
        lignes.append(
            [_cellule_texte(gettext("Niveau")), _cellule_texte(libelle_du_niveau)]
        )
    if "numero_de_cloture" in en_tete:
        lignes.append(
            [
                _cellule_texte(gettext("Numéro de clôture")),
                _cellule_nombre(en_tete["numero_de_cloture"]),
            ]
        )

    lignes.append(
        [
            _cellule_texte(gettext("Début")),
            _cellule_texte(_date_heure_locale(en_tete.get("debut"), fuseau_du_lieu)),
        ]
    )
    lignes.append(
        [
            _cellule_texte(gettext("Fin")),
            _cellule_texte(_date_heure_locale(en_tete.get("fin"), fuseau_du_lieu)),
        ]
    )

    numero_premiere_vente = en_tete.get("numero_premiere_vente")
    numero_derniere_vente = en_tete.get("numero_derniere_vente")
    if numero_premiere_vente is None:
        texte_de_la_plage = gettext("Aucune vente")
    else:
        texte_de_la_plage = gettext("n° %(premier)s à %(dernier)s") % {
            "premier": numero_premiere_vente,
            "dernier": numero_derniere_vente,
        }
    lignes.append(
        [_cellule_texte(gettext("Ventes")), _cellule_texte(texte_de_la_plage)]
    )
    lignes.append(
        [
            _cellule_texte(gettext("Opérations numérotées")),
            _cellule_nombre(en_tete.get("nombre_de_ventes")),
        ]
    )

    # Les avoirs, les cartes vidées et les corrections sont des opérations numérotées :
    # leurs nombres viennent de l'annexe (section 7).
    # / Credit notes, emptied cards and corrections are numbered operations: their
    # counts come from the appendix.
    annexe = rapport["annexe"]
    lignes.append(
        [
            _cellule_texte(gettext("dont avoirs")),
            _cellule_nombre(annexe["avoirs"]["nombre"]),
        ]
    )
    lignes.append(
        [
            _cellule_texte(gettext("dont cartes vidées")),
            _cellule_nombre(annexe["recharges_et_cartes"]["cartes_videes"]["nombre"]),
        ]
    )
    lignes.append(
        [
            _cellule_texte(gettext("dont corrections")),
            _cellule_nombre(annexe["corrections"]["nombre"]),
        ]
    )
    lignes.append(
        [
            _cellule_texte(gettext("dont ventes gratuites")),
            _cellule_nombre(en_tete.get("nombre_de_ventes_gratuites")),
        ]
    )

    if "total_perpetuel_en_centimes" in en_tete:
        lignes.append(
            [
                _cellule_texte(gettext("Total perpétuel")),
                _cellule_montant(en_tete["total_perpetuel_en_centimes"]),
            ]
        )
    if "nombre_de_ventes_perpetuel" in en_tete:
        lignes.append(
            [
                _cellule_texte(gettext("Nombre de ventes perpétuel")),
                _cellule_nombre(en_tete["nombre_de_ventes_perpetuel"]),
            ]
        )

    tableau_de_l_en_tete = _tableau(
        "", "en-tete", [gettext("Libellé"), gettext("Valeur")], lignes
    )
    return _section("en_tete", gettext("En-tête"), False, [tableau_de_l_en_tete])


def _lignes_ttc_ht_tva(dictionnaire_par_cle, nom_du_libelle):
    """
    Les lignes « libellé, TTC, HT, TVA » d'un dictionnaire du chiffre d'affaires (par
    catégorie, par origine…), triées par libellé.
    / The "label, incl. tax, excl. tax, VAT" rows of a revenue dictionary, by label.
    """
    lignes = []
    lignes_triees_du_rapport = _valeurs_triees(dictionnaire_par_cle, [nom_du_libelle])
    for ligne_du_rapport in lignes_triees_du_rapport:
        lignes.append(
            [
                _cellule_texte(ligne_du_rapport.get(nom_du_libelle)),
                _cellule_montant(ligne_du_rapport["total_ttc_en_centimes"]),
                _cellule_montant(ligne_du_rapport["total_ht_en_centimes"]),
                _cellule_montant(ligne_du_rapport["total_tva_en_centimes"]),
            ]
        )
    return lignes


# Les trois moyens du comptoir, en tête de toute liste de moyens, dans cet ordre.
# / The three counter methods, first in every method list, in this order.
MOYENS_DU_COMPTOIR_DANS_L_ORDRE = [
    PaymentMethod.CASH,
    PaymentMethod.CC,
    PaymentMethod.CHEQUE,
]


def codes_des_moyens_dans_l_ordre(par_moyen):
    """
    Les codes d'un dictionnaire « par moyen » du rapport, dans l'ordre d'affichage :
    espèces, carte bancaire, chèque, puis les autres moyens d'argent (par code),
    puis chaque moyen cashless (par code), puis « plusieurs moyens ». C'est le seul
    ordre des moyens : l'écran (`_section_chiffre_affaires`) et les tickets X et Z
    (`laboutik/printing/formatters.py`) le lisent ici.
    / The codes of a "by method" dict in display order: counter methods, other
    money methods, cashless, several. The single method order, for screens and
    tickets.

    :param par_moyen: dict {code du moyen: ligne}
    :return: liste de codes
    """
    codes_tries = sorted(par_moyen.keys())

    codes_dans_l_ordre = []
    for code_du_moyen in MOYENS_DU_COMPTOIR_DANS_L_ORDRE:
        if code_du_moyen in par_moyen:
            codes_dans_l_ordre.append(code_du_moyen)
    for code_du_moyen in codes_tries:
        moyen_deja_place = code_du_moyen in codes_dans_l_ordre
        moyen_a_part = (
            code_du_moyen in MOYENS_CASHLESS or code_du_moyen == CLE_PLUSIEURS_MOYENS
        )
        if not moyen_deja_place and not moyen_a_part:
            codes_dans_l_ordre.append(code_du_moyen)
    for code_du_moyen in codes_tries:
        if code_du_moyen in MOYENS_CASHLESS:
            codes_dans_l_ordre.append(code_du_moyen)
    if CLE_PLUSIEURS_MOYENS in par_moyen:
        codes_dans_l_ordre.append(CLE_PLUSIEURS_MOYENS)
    return codes_dans_l_ordre


def _section_chiffre_affaires(rapport):
    """
    Section 2 : chiffre d'affaires TTC / HT / TVA ; par taux, par catégorie, par
    origine, par journal.
    / Section 2: revenue, by rate, category, origin, journal.
    """
    chiffre_affaires = rapport["chiffre_affaires"]
    colonnes_ttc_ht_tva = [gettext("TTC"), gettext("HT"), gettext("TVA")]

    lignes_des_totaux = [
        [
            _cellule_texte(gettext("Chiffre d'affaires TTC")),
            _cellule_montant(chiffre_affaires["total_ttc_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Chiffre d'affaires HT")),
            _cellule_montant(chiffre_affaires["total_ht_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("TVA")),
            _cellule_montant(chiffre_affaires["total_tva_en_centimes"]),
        ],
    ]
    tableaux = [
        _tableau(
            "",
            "chiffre-affaires-totaux",
            [gettext("Libellé"), gettext("Montant")],
            lignes_des_totaux,
        )
    ]

    # Le chiffre d'affaires par moyen (absent d'une ancienne clôture), dans l'ordre
    # des tickets (`codes_des_moyens_dans_l_ordre`). Les lignes doivent recomposer le
    # chiffre d'affaires TTC : sinon le tableau est en alerte, avec l'écart en mots.
    # / Revenue by method, in the tickets' order; an alert when the lines do not add
    #   up to the revenue.
    par_moyen = chiffre_affaires.get("par_moyen")
    if par_moyen is not None:
        lignes_par_moyen = []
        somme_des_moyens = 0
        codes_dans_l_ordre = codes_des_moyens_dans_l_ordre(par_moyen)
        for code_du_moyen in codes_dans_l_ordre:
            ligne_du_moyen = par_moyen[code_du_moyen]
            lignes_par_moyen.append(
                [
                    _cellule_texte(ligne_du_moyen["libelle"]),
                    _cellule_montant(ligne_du_moyen["total_en_centimes"]),
                ]
            )
            somme_des_moyens += ligne_du_moyen["total_en_centimes"]
        ecart_avec_le_chiffre_d_affaires = (
            somme_des_moyens - chiffre_affaires["total_ttc_en_centimes"]
        )
        il_y_a_un_ecart = ecart_avec_le_chiffre_d_affaires != 0
        message_de_l_ecart = ""
        if il_y_a_un_ecart:
            message_de_l_ecart = gettext(
                "Les lignes par moyen ne recomposent pas le chiffre d'affaires TTC : "
                "écart de %(ecart)s."
            ) % {"ecart": euros_a_la_francaise(ecart_avec_le_chiffre_d_affaires)}
        tableaux.append(
            _tableau(
                gettext("Par moyen de paiement"),
                "chiffre-affaires-par-moyen",
                [gettext("Moyen"), gettext("Montant")],
                lignes_par_moyen,
                alerte=il_y_a_un_ecart,
                message_d_alerte=message_de_l_ecart,
            )
        )

    # Les taux, du plus petit au plus grand (clé « 5.50 », « 20.00 » : triée comme un
    # nombre, jamais comme un texte).
    # / Rates from smallest to largest, sorted as numbers.
    taux_tries = sorted(chiffre_affaires["par_taux"].keys(), key=Decimal)
    lignes_par_taux = []
    for taux_en_texte in taux_tries:
        ligne_du_taux = chiffre_affaires["par_taux"][taux_en_texte]
        taux_a_la_francaise = taux_en_texte.replace(".", ",")
        lignes_par_taux.append(
            [
                _cellule_texte(f"{taux_a_la_francaise}{ESPACE_INSECABLE}%"),
                _cellule_montant(ligne_du_taux["total_ttc_en_centimes"]),
                _cellule_montant(ligne_du_taux["total_ht_en_centimes"]),
                _cellule_montant(ligne_du_taux["total_tva_en_centimes"]),
            ]
        )
    if lignes_par_taux:
        tableaux.append(
            _tableau(
                gettext("Par taux de TVA"),
                "chiffre-affaires-par-taux",
                [gettext("Taux")] + colonnes_ttc_ht_tva,
                lignes_par_taux,
            )
        )

    lignes_par_categorie = _lignes_ttc_ht_tva(chiffre_affaires["par_categorie"], "nom")
    if lignes_par_categorie:
        tableaux.append(
            _tableau(
                gettext("Par catégorie"),
                "chiffre-affaires-par-categorie",
                [gettext("Catégorie")] + colonnes_ttc_ht_tva,
                lignes_par_categorie,
            )
        )

    lignes_par_origine = _lignes_ttc_ht_tva(chiffre_affaires["par_origine"], "libelle")
    if lignes_par_origine:
        tableaux.append(
            _tableau(
                gettext("Par origine"),
                "chiffre-affaires-par-origine",
                [gettext("Origine")] + colonnes_ttc_ht_tva,
                lignes_par_origine,
            )
        )

    # Les journaux, par code.
    # / Journals, by code.
    codes_des_journaux_tries = sorted(chiffre_affaires["par_journal"].keys())
    lignes_par_journal = []
    for code_du_journal in codes_des_journaux_tries:
        ligne_du_journal = chiffre_affaires["par_journal"][code_du_journal]
        lignes_par_journal.append(
            [
                _cellule_texte(code_du_journal),
                _cellule_texte(ligne_du_journal["libelle"]),
                _cellule_montant(ligne_du_journal["total_ttc_en_centimes"]),
                _cellule_montant(ligne_du_journal["total_ht_en_centimes"]),
                _cellule_montant(ligne_du_journal["total_tva_en_centimes"]),
            ]
        )
    if lignes_par_journal:
        tableaux.append(
            _tableau(
                gettext("Par journal"),
                "chiffre-affaires-par-journal",
                [gettext("Journal"), gettext("Libellé")] + colonnes_ttc_ht_tva,
                lignes_par_journal,
            )
        )

    return _section("chiffre_affaires", gettext("Chiffre d'affaires"), False, tableaux)


def _section_reglements(rapport):
    """
    Section 3 : les règlements en trois blocs, argent (par moyen), cashless (par moyen
    et par monnaie), hors argent (offert, points par monnaie). Sommes nettes : le signe
    est gardé.
    / Section 3: payments in three blocks; net sums keep their sign.
    """
    reglements = rapport["reglements"]

    argent = reglements["argent"]
    lignes_de_l_argent = []
    moyens_d_argent_tries = _valeurs_triees(argent["par_moyen"], ["libelle"])
    for ligne_du_moyen in moyens_d_argent_tries:
        lignes_de_l_argent.append(
            [
                _cellule_texte(ligne_du_moyen["libelle"]),
                _cellule_montant(ligne_du_moyen["total_en_centimes"]),
            ]
        )
    lignes_de_l_argent.append(
        [
            _cellule_texte(gettext("Total argent")),
            _cellule_montant(argent["total_en_centimes"]),
        ]
    )

    cashless = reglements["cashless"]
    lignes_du_cashless = []
    moyens_cashless_tries = _valeurs_triees(cashless["par_moyen"], ["libelle"])
    for ligne_du_moyen in moyens_cashless_tries:
        monnaies_du_moyen = _valeurs_triees(ligne_du_moyen["par_monnaie"], ["nom"])
        for ligne_de_la_monnaie in monnaies_du_moyen:
            lignes_du_cashless.append(
                [
                    _cellule_texte(ligne_du_moyen["libelle"]),
                    _cellule_texte(ligne_de_la_monnaie["nom"]),
                    _cellule_montant(ligne_de_la_monnaie["total_en_centimes"]),
                ]
            )
    lignes_du_cashless.append(
        [
            _cellule_texte(gettext("Total cashless")),
            _cellule_texte(""),
            _cellule_montant(cashless["total_en_centimes"]),
        ]
    )

    # L'offert des règlements additionne TOUS les règlements offerts (bouton OFFRIR et
    # recharges cadeau) : ce n'est pas le même nombre que la section « Offerts », qui ne
    # compte que le bouton OFFRIR. Le libellé le dit.
    # / The payments' offered sum adds every offered payment (GIFT button and gift
    # top-ups), unlike the "Offerts" section: the label says so.
    hors_argent = reglements["hors_argent"]
    lignes_hors_argent = [
        [
            _cellule_texte(gettext("Offert (bouton OFFRIR et cadeaux émis)")),
            _cellule_montant(hors_argent["offert_en_centimes"]),
        ]
    ]

    tableaux = [
        _tableau(
            gettext("Argent"),
            "reglements-argent",
            [gettext("Moyen"), gettext("Montant")],
            lignes_de_l_argent,
        ),
        _tableau(
            gettext("Cashless"),
            "reglements-cashless",
            [gettext("Moyen"), gettext("Monnaie"), gettext("Montant")],
            lignes_du_cashless,
        ),
        _tableau(
            gettext("Hors argent"),
            "reglements-hors-argent",
            [gettext("Libellé"), gettext("Montant")],
            lignes_hors_argent,
        ),
    ]

    lignes_des_points = []
    points_par_monnaie = _valeurs_triees(hors_argent["points_par_monnaie"], ["nom"])
    for ligne_de_la_monnaie in points_par_monnaie:
        lignes_des_points.append(
            [
                _cellule_texte(ligne_de_la_monnaie["nom"]),
                _cellule_points(ligne_de_la_monnaie["total_en_centiemes"]),
            ]
        )
    if lignes_des_points:
        tableaux.append(
            _tableau(
                gettext("Points par monnaie"),
                "reglements-points",
                [gettext("Monnaie"), gettext("Points")],
                lignes_des_points,
            )
        )

    return _section("reglements", gettext("Règlements"), False, tableaux)


def lignes_du_tiroir(section_caisse_especes):
    """
    Les lignes du tiroir de la caisse, dans l'ordre, avec un libellé et un montant
    SIGNÉ : l'argent qui sort du tiroir (espèces rendues, sorties de caisse) est
    négatif. Les lignes au-dessus du solde s'additionnent donc en solde théorique.
    C'est la seule écriture du tiroir : l'écran (section « caisse espèces », sortie
    de caisse, récapitulatif) et les tickets X lisent ces lignes.
    / The cash drawer lines, in order, with a label and a SIGNED amount (money
    leaving the drawer is negative); the lines above the balance add up to it. The
    single writing of the drawer, read by screens and tickets.

    APPELÉ PAR : `_section_caisse_especes` (ci-dessous) et
    `laboutik/printing/formatters.py` (`_lignes_du_tiroir_du_rapport`).

    :param section_caisse_especes: `rapport["caisse_especes"]`
    :return: liste de {"libelle", "montant_en_centimes", "toujours_imprimee"} ; le
        fond et le solde sont toujours imprimés, les autres seulement s'ils ne sont
        pas nuls (ticket)
    """
    sorties_en_positif = section_caisse_especes.get("sorties_en_centimes", 0)
    return [
        {
            "libelle": gettext("Fond de caisse"),
            "montant_en_centimes": section_caisse_especes.get(
                "fond_de_caisse_en_centimes", 0
            ),
            "toujours_imprimee": True,
        },
        {
            "libelle": gettext("Espèces reçues"),
            "montant_en_centimes": section_caisse_especes.get(
                "especes_recues_en_centimes", 0
            ),
            "toujours_imprimee": False,
        },
        {
            # Déjà négatives dans le rapport (avoirs, vidages).
            # / Already negative in the report.
            "libelle": gettext("Espèces rendues"),
            "montant_en_centimes": section_caisse_especes.get(
                "especes_rendues_en_centimes", 0
            ),
            "toujours_imprimee": False,
        },
        {
            "libelle": gettext("Corrections"),
            "montant_en_centimes": section_caisse_especes.get(
                "corrections_en_centimes", 0
            ),
            "toujours_imprimee": False,
        },
        {
            # Positives dans le rapport : elles sortent du tiroir, donc négatives ici.
            # / Positive in the report: they leave the drawer, negative here.
            "libelle": gettext("Sorties de caisse"),
            "montant_en_centimes": -sorties_en_positif,
            "toujours_imprimee": False,
        },
        {
            "libelle": gettext("Solde théorique"),
            "montant_en_centimes": section_caisse_especes.get(
                "solde_theorique_en_centimes", 0
            ),
            "toujours_imprimee": True,
        },
    ]


def _section_caisse_especes(rapport):
    """
    Section 4 (J seulement) : le tiroir de la caisse, écrit par `lignes_du_tiroir` :
    montants signés, l'argent qui sort est négatif.
    / Section 4: the cash drawer, written by lignes_du_tiroir (signed amounts).
    """
    lignes_signees_du_tiroir = lignes_du_tiroir(rapport["caisse_especes"])
    lignes = []
    for ligne_du_tiroir in lignes_signees_du_tiroir:
        lignes.append(
            [
                _cellule_texte(ligne_du_tiroir["libelle"]),
                _cellule_montant(ligne_du_tiroir["montant_en_centimes"]),
            ]
        )
    tableau_du_tiroir = _tableau(
        "", "caisse-especes", [gettext("Libellé"), gettext("Montant")], lignes
    )
    return _section(
        "caisse_especes", gettext("Caisse espèces"), False, [tableau_du_tiroir]
    )


def _terme_de_la_phrase(signe_attendu, montant_du_rapport):
    """
    Un terme de la phrase de réconciliation : le signe et le montant POSITIF à écrire.
    Le montant du rapport est signé ; un terme « − » écrit l'opposé. Si le montant à
    écrire est négatif (un cas rare), le signe est inversé : le montant reste positif et
    l'égalité reste juste.
    / A term of the sentence: the sign and the POSITIVE amount to write.

    :param signe_attendu: "+" ou SIGNE_MOINS
    :param montant_du_rapport: le montant signé du rapport, en centimes
    :return: (signe, montant positif en centimes)
    """
    if signe_attendu == "+":
        montant_a_ecrire = montant_du_rapport
    else:
        montant_a_ecrire = -montant_du_rapport

    if montant_a_ecrire >= 0:
        return signe_attendu, montant_a_ecrire

    if signe_attendu == "+":
        signe_inverse = SIGNE_MOINS
    else:
        signe_inverse = "+"
    return signe_inverse, -montant_a_ecrire


def phrase_de_reconciliation(reconciliation):
    """
    La phrase de réconciliation (section 5), dans la langue du lecteur, avec des
    montants positifs après « − » :
    « Argent reçu 5,00 € = ventes payées en argent 10,50 € + recharges 0,00 € −
    remboursements 3,50 € − cartes vidées 2,00 € + écarts d'encaissement 0,00 € ».
    Les écarts d'encaissement prennent le signe de leur somme (« ± »).
    / The reconciliation sentence, positive amounts after "−".
    """
    signe_des_recharges, recharges = _terme_de_la_phrase(
        "+", reconciliation["recharges_en_centimes"]
    )
    signe_des_remboursements, remboursements = _terme_de_la_phrase(
        SIGNE_MOINS, reconciliation["remboursements_en_centimes"]
    )
    signe_des_cartes_videes, cartes_videes = _terme_de_la_phrase(
        SIGNE_MOINS, reconciliation["cartes_videes_en_centimes"]
    )
    signe_des_ecarts, ecarts = _terme_de_la_phrase(
        "+", reconciliation["ecarts_d_encaissement_en_centimes"]
    )

    # Une seule phrase à traduire, avec des variables nommées : un traducteur peut
    # changer l'ordre des mots sans toucher au code.
    # / One single translatable sentence with named variables: a translator can
    # reorder the words.
    phrase = gettext(
        "Argent reçu %(argent_recu)s = ventes payées en argent "
        "%(ventes_payees_en_argent)s %(signe_recharges)s recharges %(recharges)s "
        "%(signe_remboursements)s remboursements %(remboursements)s "
        "%(signe_cartes_videes)s cartes vidées %(cartes_videes)s "
        "%(signe_ecarts)s écarts d'encaissement %(ecarts)s"
    ) % {
        "argent_recu": euros_a_la_francaise(reconciliation["argent_recu_en_centimes"]),
        "ventes_payees_en_argent": euros_a_la_francaise(
            reconciliation["ventes_payees_en_argent_en_centimes"]
        ),
        "signe_recharges": signe_des_recharges,
        "recharges": euros_a_la_francaise(recharges),
        "signe_remboursements": signe_des_remboursements,
        "remboursements": euros_a_la_francaise(remboursements),
        "signe_cartes_videes": signe_des_cartes_videes,
        "cartes_videes": euros_a_la_francaise(cartes_videes),
        "signe_ecarts": signe_des_ecarts,
        "ecarts": euros_a_la_francaise(ecarts),
    }
    return phrase


def _section_reconciliation(rapport):
    """
    Section 5 : la phrase de réconciliation, puis ses termes. Les remboursements et les
    cartes vidées s'écrivent en positif (ils sont retranchés), comme dans la phrase.
    / Section 5: the sentence, then its terms; refunds and emptied cards as positive.
    """
    reconciliation = rapport["reconciliation"]
    lignes = [
        [
            _cellule_texte(gettext("Argent reçu")),
            _cellule_montant(reconciliation["argent_recu_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Ventes payées en argent")),
            _cellule_montant(reconciliation["ventes_payees_en_argent_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Recharges")),
            _cellule_montant(reconciliation["recharges_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Remboursements")),
            _cellule_montant(-reconciliation["remboursements_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Cartes vidées")),
            _cellule_montant(-reconciliation["cartes_videes_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Écarts d'encaissement")),
            _cellule_montant(reconciliation["ecarts_d_encaissement_en_centimes"]),
        ],
    ]
    tableau_des_termes = _tableau(
        "", "reconciliation-termes", [gettext("Libellé"), gettext("Montant")], lignes
    )
    return _section(
        "reconciliation",
        gettext("Réconciliation"),
        False,
        [tableau_des_termes],
        phrase=phrase_de_reconciliation(reconciliation),
    )


def _section_offerts(rapport):
    """
    Section 6 : le bouton OFFRIR, quantité, valeur catalogue, coût d'achat ; par produit.
    / Section 6: the GIFT button; by product.
    """
    offerts = rapport["offerts"]
    lignes_des_totaux = [
        [
            _cellule_texte(gettext("Quantité offerte")),
            _cellule_quantite(offerts["quantite"]),
        ],
        [
            _cellule_texte(gettext("Valeur catalogue offerte")),
            _cellule_montant(offerts["valeur_catalogue_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Coût d'achat")),
            _cellule_montant(offerts["cout_achat_en_centimes"]),
        ],
    ]
    tableaux = [
        _tableau(
            "",
            "offerts-totaux",
            [gettext("Libellé"), gettext("Valeur")],
            lignes_des_totaux,
        )
    ]

    lignes_par_produit = []
    produits_offerts_tries = _valeurs_triees(offerts["par_produit"], ["nom"])
    for ligne_du_produit in produits_offerts_tries:
        lignes_par_produit.append(
            [
                _cellule_texte(ligne_du_produit["nom"]),
                _cellule_quantite(ligne_du_produit["quantite"]),
                _cellule_montant(ligne_du_produit["valeur_catalogue_en_centimes"]),
                _cellule_montant(ligne_du_produit["cout_achat_en_centimes"]),
            ]
        )
    if lignes_par_produit:
        tableaux.append(
            _tableau(
                gettext("Par produit"),
                "offerts-par-produit",
                [
                    gettext("Produit"),
                    gettext("Quantité"),
                    gettext("Valeur catalogue"),
                    gettext("Coût d'achat"),
                ],
                lignes_par_produit,
            )
        )
    return _section("offerts", gettext("Offerts"), False, tableaux)


def _section_annexe(rapport):
    """
    Section 7 : avoirs, recharges et cartes, écarts d'encaissement (en rouge s'il y en
    a), corrections (opérateur par son nom). Les avoirs, remboursements, espèces
    rendues et jetons repris s'écrivent en positif.
    / Section 7: credit notes, top-ups and cards, gaps (red when any), corrections.
    """
    annexe = rapport["annexe"]
    colonnes_libelle_nombre_montant = [
        gettext("Libellé"),
        gettext("Nombre"),
        gettext("Montant"),
    ]

    # Les avoirs : le total et chaque moyen sont des sorties, écrites en positif.
    # / Credit notes: outflows written as positive amounts.
    avoirs = annexe["avoirs"]
    lignes_des_avoirs = [
        [
            _cellule_texte(gettext("Avoirs")),
            _cellule_nombre(avoirs["nombre"]),
            _cellule_montant(-avoirs["total_en_centimes"]),
        ]
    ]
    moyens_des_avoirs_tries = _valeurs_triees(avoirs["par_moyen"], ["libelle"])
    for ligne_du_moyen in moyens_des_avoirs_tries:
        lignes_des_avoirs.append(
            [
                _cellule_texte(
                    gettext("dont %(moyen)s") % {"moyen": ligne_du_moyen["libelle"]}
                ),
                _cellule_texte(""),
                _cellule_montant(-ligne_du_moyen["total_en_centimes"]),
            ]
        )
    retours_consigne = avoirs["retours_consigne"]
    lignes_des_avoirs.append(
        [
            _cellule_texte(gettext("dont retours consigne")),
            _cellule_nombre(retours_consigne["nombre"]),
            _cellule_montant(-retours_consigne["total_en_centimes"]),
        ]
    )
    stripe_a_la_main = avoirs["remboursements_stripe_a_faire_a_la_main"]
    lignes_des_avoirs.append(
        [
            _cellule_texte(gettext("dont remboursements Stripe à faire à la main")),
            _cellule_nombre(stripe_a_la_main["nombre"]),
            _cellule_montant(-stripe_a_la_main["total_en_centimes"]),
        ]
    )

    recharges_et_cartes = annexe["recharges_et_cartes"]
    recharges_encaissees = recharges_et_cartes["recharges_encaissees"]
    cartes_videes = recharges_et_cartes["cartes_videes"]
    lignes_des_recharges = [
        [
            _cellule_texte(gettext("Recharges encaissées")),
            _cellule_texte(""),
            _cellule_montant(recharges_encaissees["total_en_centimes"]),
        ]
    ]
    recharges_par_moyen = _valeurs_triees(recharges_encaissees["par_moyen"], ["libelle"])
    for ligne_du_moyen in recharges_par_moyen:
        lignes_des_recharges.append(
            [
                _cellule_texte(
                    gettext("dont %(moyen)s") % {"moyen": ligne_du_moyen["libelle"]}
                ),
                _cellule_texte(""),
                _cellule_montant(ligne_du_moyen["total_en_centimes"]),
            ]
        )
    lignes_des_recharges.append(
        [
            _cellule_texte(gettext("Cadeau émis")),
            _cellule_texte(""),
            _cellule_montant(recharges_et_cartes["cadeau_emis_en_centimes"]),
        ]
    )
    lignes_des_recharges.append(
        [
            _cellule_texte(gettext("Cartes vidées")),
            _cellule_nombre(cartes_videes["nombre"]),
            _cellule_texte(""),
        ]
    )
    lignes_des_recharges.append(
        [
            _cellule_texte(gettext("dont espèces rendues")),
            _cellule_texte(""),
            _cellule_montant(-cartes_videes["especes_rendues_en_centimes"]),
        ]
    )
    # Les jetons cadeau repris sont positifs par construction : l'article « Jetons
    # cadeau repris au vidage » vaut le montant des jetons repris (laboutik/views.py).
    # Le montant est écrit tel quel : un signe inattendu doit se voir.
    # / Gift tokens taken back are positive by construction: written as is.
    lignes_des_recharges.append(
        [
            _cellule_texte(gettext("dont jetons cadeau repris")),
            _cellule_texte(""),
            _cellule_montant(cartes_videes["jetons_cadeau_repris_en_centimes"]),
        ]
    )

    # Un écart d'encaissement est écrit en rouge ET en mots : une couleur seule ne se
    # lit pas avec un lecteur d'écran.
    # / A collection gap is written in red AND in words.
    ecarts = annexe["ecarts_d_encaissement"]
    il_y_a_des_ecarts = ecarts["nombre"] > 0
    if il_y_a_des_ecarts:
        message_des_ecarts = gettext("Attention : écart d'encaissement")
    else:
        message_des_ecarts = ""
    lignes_des_ecarts = [
        [
            _cellule_texte(gettext("Écarts d'encaissement")),
            _cellule_nombre(ecarts["nombre"]),
            _cellule_montant(ecarts["total_en_centimes"]),
        ]
    ]

    tableaux = [
        _tableau(
            gettext("Avoirs"),
            "annexe-avoirs",
            colonnes_libelle_nombre_montant,
            lignes_des_avoirs,
        ),
        _tableau(
            gettext("Recharges et cartes"),
            "annexe-recharges-et-cartes",
            colonnes_libelle_nombre_montant,
            lignes_des_recharges,
        ),
        _tableau(
            gettext("Écarts d'encaissement"),
            "annexe-ecarts",
            colonnes_libelle_nombre_montant,
            lignes_des_ecarts,
            alerte=il_y_a_des_ecarts,
            message_d_alerte=message_des_ecarts,
        ),
    ]

    # Les corrections : l'opérateur est stocké par son identifiant, son nom est lu ici.
    # / Corrections: the operator is stored by id, the name is read here.
    liste_des_corrections = annexe["corrections"]["liste"]
    noms_des_operateurs = _noms_des_operateurs_des_corrections(liste_des_corrections)
    lignes_des_corrections = []
    for correction in liste_des_corrections:
        identifiant_de_l_operateur = correction.get("operateur")
        if not identifiant_de_l_operateur:
            nom_de_l_operateur = gettext("Sans opérateur")
        elif identifiant_de_l_operateur in noms_des_operateurs:
            nom_de_l_operateur = noms_des_operateurs[identifiant_de_l_operateur]
        else:
            nom_de_l_operateur = gettext("Compte supprimé")
        lignes_des_corrections.append(
            [
                _cellule_nombre(correction["numero"]),
                _cellule_texte(
                    _libelles_d_une_liste_de_moyens(correction["moyen_avant"])
                ),
                _cellule_texte(
                    _libelles_d_une_liste_de_moyens(correction["moyen_apres"])
                ),
                _cellule_texte(nom_de_l_operateur),
            ]
        )
    if lignes_des_corrections:
        tableaux.append(
            _tableau(
                gettext("Corrections de moyen de paiement"),
                "annexe-corrections",
                [
                    gettext("Numéro de vente"),
                    gettext("Moyen avant"),
                    gettext("Moyen après"),
                    gettext("Opérateur"),
                ],
                lignes_des_corrections,
            )
        )

    return _section(
        "annexe",
        gettext("Annexe : avoirs, recharges, écarts, corrections"),
        True,
        tableaux,
    )


def _section_points(rapport):
    """
    Section 8 : les ventes en points ou en temps, par monnaie (en points, jamais en
    euros).
    / Section 8: points or time sales by currency.
    """
    lignes = []
    monnaies_triees = _valeurs_triees(rapport["points"], ["nom"])
    for ligne_de_la_monnaie in monnaies_triees:
        lignes.append(
            [
                _cellule_texte(ligne_de_la_monnaie["nom"]),
                _cellule_points(ligne_de_la_monnaie["total_en_centiemes"]),
                _cellule_points(ligne_de_la_monnaie["offert_en_centiemes"]),
            ]
        )
    if len(lignes) == 0:
        return _section(
            "points",
            gettext("Points"),
            True,
            [],
            phrase=gettext("Aucune vente en points ou en temps."),
        )
    tableau_des_points = _tableau(
        "",
        "points-par-monnaie",
        [gettext("Monnaie"), gettext("Points"), gettext("dont offerts")],
        lignes,
    )
    return _section("points", gettext("Points"), True, [tableau_des_points])


def _section_marge_brute(rapport):
    """
    Section 9 : CA HT − coût d'achat = marge brute ; « marge incomplète » en rouge s'il
    y a des articles vendus sans prix d'achat.
    / Section 9: gross margin; "incomplete margin" in red when costs are missing.
    """
    marge = rapport["marge_brute"]
    lignes = [
        [
            _cellule_texte(gettext("Chiffre d'affaires HT")),
            _cellule_montant(marge["chiffre_affaires_ht_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Coût d'achat")),
            _cellule_montant(marge["cout_achat_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Marge brute")),
            _cellule_montant(marge["marge_brute_en_centimes"]),
        ],
    ]
    tableau_de_la_marge = _tableau(
        "", "marge-brute", [gettext("Libellé"), gettext("Montant")], lignes
    )

    nombre_au_cout_inconnu = marge["nombre_d_articles_au_cout_inconnu"]
    if nombre_au_cout_inconnu > 0:
        phrase = ngettext(
            "Marge incomplète : %(nombre)s article sans prix d'achat.",
            "Marge incomplète : %(nombre)s articles sans prix d'achat.",
            nombre_au_cout_inconnu,
        ) % {"nombre": nombre_au_cout_inconnu}
        return _section(
            "marge_brute",
            gettext("Marge brute"),
            True,
            [tableau_de_la_marge],
            phrase=phrase,
            phrase_en_alerte=True,
        )
    return _section("marge_brute", gettext("Marge brute"), True, [tableau_de_la_marge])


def _evenements_tries_par_date(billets_par_evenement):
    """
    Les événements du détail des billets, triés par date (le plus tôt d'abord), puis
    par nom, puis par clé : deux lectures du même Z donnent toujours le même ordre.
    / Ticket events sorted by date, then name, then key.
    """
    elements_a_trier = []
    for cle_de_l_evenement, evenement in billets_par_evenement.items():
        date_de_l_evenement = datetime.fromisoformat(evenement["date"])
        nom_de_l_evenement = str(evenement["nom"] or "").casefold()
        criteres_de_tri = (date_de_l_evenement, nom_de_l_evenement, cle_de_l_evenement)
        elements_a_trier.append((criteres_de_tri, evenement))

    elements_a_trier.sort(key=_criteres_de_tri_d_un_element)

    evenements_tries = []
    for _criteres, evenement in elements_a_trier:
        evenements_tries.append(evenement)
    return evenements_tries


def _section_detail(rapport, fuseau_du_lieu):
    """
    Section 10 : billets (par événement et tarif), adhésions, ventes par produit (avec
    le nom de leur catégorie, lu dans la section 2).
    / Section 10: tickets, memberships, sales by product.
    """
    detail = rapport["detail"]
    categories_du_chiffre_d_affaires = rapport["chiffre_affaires"]["par_categorie"]
    tableaux = []

    lignes_des_billets = []
    evenements_tries = _evenements_tries_par_date(detail["billets"])
    for evenement in evenements_tries:
        date_de_l_evenement = _date_heure_locale(evenement["date"], fuseau_du_lieu)
        tarifs_tries = _valeurs_triees(evenement["par_tarif"], ["nom", "produit"])
        for tarif in tarifs_tries:
            lignes_des_billets.append(
                [
                    _cellule_texte(evenement["nom"]),
                    _cellule_texte(date_de_l_evenement),
                    _cellule_texte(tarif["produit"]),
                    _cellule_texte(tarif["nom"]),
                    _cellule_quantite(tarif["quantite"]),
                    _cellule_montant(tarif["total_ttc_en_centimes"]),
                ]
            )
    if lignes_des_billets:
        tableaux.append(
            _tableau(
                gettext("Billets"),
                "detail-billets",
                [
                    gettext("Événement"),
                    gettext("Date"),
                    gettext("Produit"),
                    gettext("Tarif"),
                    gettext("Quantité"),
                    gettext("TTC"),
                ],
                lignes_des_billets,
            )
        )

    lignes_des_adhesions = []
    adhesions_triees = _valeurs_triees(detail["adhesions"], ["nom"])
    for adhesion in adhesions_triees:
        lignes_des_adhesions.append(
            [
                _cellule_texte(adhesion["nom"]),
                _cellule_quantite(adhesion["quantite"]),
                _cellule_montant(adhesion["total_ttc_en_centimes"]),
            ]
        )
    if lignes_des_adhesions:
        tableaux.append(
            _tableau(
                gettext("Adhésions"),
                "detail-adhesions",
                [gettext("Produit"), gettext("Quantité"), gettext("TTC")],
                lignes_des_adhesions,
            )
        )

    lignes_par_produit = []
    ventes_par_produit = _valeurs_triees(detail["ventes_par_produit"], ["nom"])
    for ligne_du_produit in ventes_par_produit:
        categorie = categories_du_chiffre_d_affaires.get(ligne_du_produit["categorie"])
        if categorie is None:
            nom_de_la_categorie = ""
        else:
            nom_de_la_categorie = categorie["nom"]
        lignes_par_produit.append(
            [
                _cellule_texte(nom_de_la_categorie),
                _cellule_texte(ligne_du_produit["nom"]),
                _cellule_quantite(ligne_du_produit["quantite"]),
                _cellule_montant(ligne_du_produit["total_ttc_en_centimes"]),
                _cellule_montant(ligne_du_produit["total_ht_en_centimes"]),
                _cellule_montant(ligne_du_produit["offert_en_centimes"]),
                _cellule_montant(ligne_du_produit["cout_achat_en_centimes"]),
            ]
        )
    if lignes_par_produit:
        tableaux.append(
            _tableau(
                gettext("Ventes par produit"),
                "detail-ventes-par-produit",
                [
                    gettext("Catégorie"),
                    gettext("Produit"),
                    gettext("Quantité"),
                    gettext("TTC"),
                    gettext("HT"),
                    gettext("Offert"),
                    gettext("Coût d'achat"),
                ],
                lignes_par_produit,
            )
        )

    if len(tableaux) == 0:
        return _section(
            "detail",
            gettext("Détail des ventes"),
            True,
            [],
            phrase=gettext("Aucune vente sur cette période."),
        )
    return _section("detail", gettext("Détail des ventes"), True, tableaux)


def _section_integrite(rapport):
    """
    Section 11 : « OK », ou la liste des anomalies de la chaîne des ventes (numéro de
    vente, raison), en rouge.
    / Section 11: "OK", or the list of anomalies, in red.
    """
    integrite = rapport["integrite"]
    if integrite["statut"] == STATUT_INTEGRITE_OK:
        return _section(
            "integrite", gettext("Intégrité"), True, [], phrase=STATUT_INTEGRITE_OK
        )

    lignes_des_anomalies = []
    for anomalie in integrite["anomalies"]:
        lignes_des_anomalies.append(
            [
                _cellule_nombre(anomalie["numero"]),
                _cellule_texte(anomalie["raison"]),
            ]
        )
    nombre_d_anomalies = len(lignes_des_anomalies)
    phrase = ngettext(
        "%(nombre)s anomalie dans la chaîne des ventes.",
        "%(nombre)s anomalies dans la chaîne des ventes.",
        nombre_d_anomalies,
    ) % {"nombre": nombre_d_anomalies}
    tableau_des_anomalies = _tableau(
        "",
        "integrite-anomalies",
        [gettext("Numéro de vente"), gettext("Raison")],
        lignes_des_anomalies,
        alerte=True,
    )
    return _section(
        "integrite",
        gettext("Intégrité"),
        True,
        [tableau_des_anomalies],
        phrase=phrase,
        phrase_en_alerte=True,
    )


def _section_habitus_cartes(rapport):
    """
    Rapport X : l'habitus des cartes NFC (dépenses, recharges, reste sur carte, nouveaux
    membres).
    / X report: NFC card habits.
    """
    habitus = rapport["habitus_cartes"]
    lignes = [
        [
            _cellule_texte(gettext("Nombre de cartes")),
            _cellule_nombre(habitus["nombre_de_cartes"]),
        ],
        [
            _cellule_texte(gettext("Total des dépenses")),
            _cellule_montant(habitus["total_des_depenses_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Panier moyen")),
            _cellule_montant(habitus["panier_moyen_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Dépense médiane")),
            _cellule_montant(habitus["depense_mediane_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Recharge médiane")),
            _cellule_montant(habitus["recharge_mediane_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Reste moyen sur carte")),
            _cellule_montant(habitus["reste_moyen_sur_carte_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Reste médian sur carte")),
            _cellule_montant(habitus["reste_median_sur_carte_en_centimes"]),
        ],
        [
            _cellule_texte(gettext("Nouveaux membres")),
            _cellule_nombre(habitus["nouveaux_membres"]),
        ],
    ]
    tableau_de_l_habitus = _tableau(
        "", "habitus-cartes", [gettext("Libellé"), gettext("Valeur")], lignes
    )
    return _section(
        "habitus_cartes", gettext("Habitus des cartes"), True, [tableau_de_l_habitus]
    )


def _section_operateurs(rapport):
    """
    Rapport X : par opérateur, le nombre de ventes, le chiffre d'affaires TTC et
    l'argent. Le rapport X n'est jamais stocké : l'email y est permis.
    / X report: by operator, sales count, revenue and money.
    """
    lignes = []
    operateurs_tries = _valeurs_triees(rapport["operateurs"], ["nom"])
    for operateur in operateurs_tries:
        nom_de_l_operateur = operateur["nom"]
        if not nom_de_l_operateur:
            nom_de_l_operateur = gettext("Compte supprimé")
        lignes.append(
            [
                _cellule_texte(nom_de_l_operateur),
                _cellule_nombre(operateur["nombre_de_ventes"]),
                _cellule_montant(operateur["chiffre_affaires_ttc_en_centimes"]),
                _cellule_montant(operateur["argent_en_centimes"]),
            ]
        )
    if len(lignes) == 0:
        return _section(
            "operateurs",
            gettext("Opérateurs"),
            True,
            [],
            phrase=gettext("Aucune vente sur cette période."),
        )
    tableau_des_operateurs = _tableau(
        "",
        "operateurs",
        [
            gettext("Opérateur"),
            gettext("Nombre de ventes"),
            gettext("Chiffre d'affaires TTC"),
            gettext("Argent"),
        ],
        lignes,
    )
    return _section("operateurs", gettext("Opérateurs"), True, [tableau_des_operateurs])


# ----------------------------------------------------------------------
# La liste des sections
# / The list of sections
# ----------------------------------------------------------------------


def fuseau_d_affichage_du_rapport(rapport):
    """
    Le fuseau dans lequel s'écrivent les heures d'un rapport : celui figé dans son
    en-tête au moment du calcul (`fuseau_horaire`). Un Z scellé garde ainsi ses heures
    d'origine, même si le lieu change de fuseau ensuite. Repli : le fuseau actuel du
    lieu (une ancienne clôture n'a pas ce champ).
    / The time zone of a report's hours: the one frozen in its header, otherwise the
    venue's current one.

    APPELÉE PAR : `sections_pour_affichage` (ci-dessous) et les tickets X et Z
    (`laboutik/printing/formatters.py`).
    """
    en_tete = rapport.get("en_tete", {})
    nom_du_fuseau_fige = en_tete.get("fuseau_horaire")
    if nom_du_fuseau_fige:
        return ZoneInfo(nom_du_fuseau_fige)
    return Configuration.get_solo().get_tzinfo()


def sections_pour_affichage(rapport):
    """
    Les sections d'un rapport, prêtes à afficher, dans l'ordre de la fiche F §2 :
    d'abord l'essentiel (en-tête, chiffre d'affaires, règlements, caisse espèces,
    réconciliation, offerts), puis, repliés, l'annexe, les points, la marge brute, le
    détail, l'intégrité, et, au rapport X, l'habitus des cartes et les opérateurs. Une
    section absente du rapport n'est pas dans la liste.
    / The report's sections ready to display, in the sheet's order; absent sections are
    skipped.

    LOCALISATION : comptabilite/presentation.py

    Les heures s'écrivent dans le fuseau figé dans l'en-tête du rapport ; sans lui (une
    ancienne clôture), dans le fuseau actuel du lieu. Lit aussi, pour les corrections,
    les comptes des opérateurs : l'appelant est dans le lieu (`tenant_context`).
    / Hours are written in the time zone frozen in the report header, otherwise the
    venue's current one; also reads the operators' accounts.

    :param rapport: le dictionnaire du rapport (`rapport_json` d'une clôture, ou
        `RapportDesVentes.rapport_x()`)
    :return: la liste des sections (voir la docstring du module)
    """
    if not rapport:
        return []

    fuseau_du_lieu = fuseau_d_affichage_du_rapport(rapport)
    sections = []

    if "en_tete" in rapport:
        sections.append(_section_en_tete(rapport, fuseau_du_lieu))
    if "chiffre_affaires" in rapport:
        sections.append(_section_chiffre_affaires(rapport))
    if "reglements" in rapport:
        sections.append(_section_reglements(rapport))
    if "caisse_especes" in rapport:
        sections.append(_section_caisse_especes(rapport))
    if "reconciliation" in rapport:
        sections.append(_section_reconciliation(rapport))
    if "offerts" in rapport:
        sections.append(_section_offerts(rapport))
    if "annexe" in rapport:
        sections.append(_section_annexe(rapport))
    if "points" in rapport:
        sections.append(_section_points(rapport))
    if "marge_brute" in rapport:
        sections.append(_section_marge_brute(rapport))
    if "detail" in rapport:
        sections.append(_section_detail(rapport, fuseau_du_lieu))
    if "integrite" in rapport:
        sections.append(_section_integrite(rapport))
    if "habitus_cartes" in rapport:
        sections.append(_section_habitus_cartes(rapport))
    if "operateurs" in rapport:
        sections.append(_section_operateurs(rapport))

    return sections

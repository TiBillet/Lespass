"""
Generateur de Fichier des Ecritures Comptables (FEC) — 18 colonnes.
Transforme les ClotureCaisse en fichier FEC conforme au format
impose par l'administration fiscale francaise (article A.47 A-1 du LPF).

/ FEC (Fichier des Ecritures Comptables) generator — 18 columns.
Transforms ClotureCaisse records into a FEC file compliant with the
French tax administration format (article A.47 A-1 of the LPF).

LOCALISATION : laboutik/fec.py
"""

import logging
from decimal import Decimal

from BaseBillet.models import CategorieProduct, Configuration
from laboutik.models import CompteComptable, MappingMoyenDePaiement

logger = logging.getLogger(__name__)


# --- En-tete FEC (18 colonnes) ---
# / FEC header (18 columns)
ENTETE_FEC = (
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
)

# Mapping entre les cles du rapport_json['totaux_par_moyen'] et
# les codes MappingMoyenDePaiement.
# / Mapping between rapport_json['totaux_par_moyen'] keys and
# MappingMoyenDePaiement codes.
CLE_RAPPORT_VERS_CODE_PAIEMENT = {
    'especes': 'CA',
    'carte_bancaire': 'CC',
    'cheque': 'CH',
    'cashless': 'LE',
}


def _formater_montant(centimes):
    """
    Convertit un montant en centimes (int) en chaine FEC avec virgule.
    Exemples : 15000 → "150,00"   /   0 → "0,00"   /   1234 → "12,34"
    / Converts an amount in cents (int) to FEC string with comma.
    """
    # Utiliser Decimal pour eviter les erreurs d'arrondi float
    # / Use Decimal to avoid float rounding errors
    montant_decimal = Decimal(centimes) / Decimal(100)
    return f"{montant_decimal:.2f}".replace('.', ',')


def _formater_date(dt):
    """
    Formate un datetime en YYYYMMDD pour le FEC.
    Exemple : datetime(2026, 3, 31) → "20260331"
    / Formats a datetime as YYYYMMDD for FEC.
    """
    return dt.strftime("%Y%m%d")


def _generer_ligne_fec(
    journal_code,
    journal_lib,
    numero_ecriture,
    date_ecriture,
    numero_compte,
    libelle_compte,
    reference_piece,
    date_piece,
    libelle_ecriture,
    debit_centimes,
    credit_centimes,
    date_validation,
):
    """
    Genere une ligne FEC (18 champs separes par tabulation).
    Les colonnes 7, 8, 14, 15, 17, 18 sont toujours vides.
    / Generates a FEC line (18 tab-separated fields).
    Columns 7, 8, 14, 15, 17, 18 are always empty.
    """
    champs = [
        journal_code,                               # 1  JournalCode
        journal_lib,                                 # 2  JournalLib
        numero_ecriture,                             # 3  EcritureNum
        date_ecriture,                               # 4  EcritureDate
        numero_compte,                               # 5  CompteNum
        libelle_compte,                              # 6  CompteLib
        "",                                          # 7  CompAuxNum (vide)
        "",                                          # 8  CompAuxLib (vide)
        reference_piece,                             # 9  PieceRef
        date_piece,                                  # 10 PieceDate
        libelle_ecriture,                            # 11 EcritureLib
        _formater_montant(debit_centimes),           # 12 Debit
        _formater_montant(credit_centimes),          # 13 Credit
        "",                                          # 14 EcritureLet (vide)
        "",                                          # 15 DateLet (vide)
        date_validation,                             # 16 ValidDate
        "",                                          # 17 Montantdevise (vide)
        "",                                          # 18 Idevise (vide)
    ]
    return "\t".join(champs)


def generer_fec(clotures_queryset, schema_name):
    """
    Genere un fichier FEC a partir d'un QuerySet de ClotureCaisse.
    / Generates a FEC file from a ClotureCaisse QuerySet.

    :param clotures_queryset: QuerySet de ClotureCaisse, ordonne par date
    :param schema_name: str — nom du schema tenant (pour le nom de fichier)
    :return: tuple (bytes contenu_fec, str nom_fichier, list avertissements)
    """
    avertissements = []

    # --- Charger le SIREN depuis la configuration du tenant ---
    # / Load SIREN from tenant configuration
    try:
        configuration = Configuration.get_solo()
        siren = configuration.siren or ""
    except Exception:
        siren = ""

    if not siren:
        siren = schema_name.upper()
        avertissements.append(
            f"SIREN absent de la configuration. Utilisation de '{siren}' par defaut."
        )

    # --- Charger tous les mappings moyen de paiement en memoire ---
    # Peu d'enregistrements (4-6 max), on charge tout d'un coup.
    # / Load all payment method mappings into memory.
    # Few records (4-6 max), load all at once.
    mappings_paiement = {}
    for mapping in MappingMoyenDePaiement.objects.select_related('compte_de_tresorerie').all():
        mappings_paiement[mapping.moyen_de_paiement] = mapping

    # --- Charger toutes les categories avec leur compte comptable ---
    # / Load all categories with their accounting code
    categories_par_nom = {}
    for categorie in CategorieProduct.objects.select_related('compte_comptable').all():
        categories_par_nom[categorie.name] = categorie

    # --- Charger les comptes TVA indexes par taux ---
    # / Load VAT accounts indexed by rate
    comptes_tva = {}
    for compte in CompteComptable.objects.filter(nature_du_compte=CompteComptable.TVA, est_actif=True):
        if compte.taux_de_tva is not None:
            # Cle = chaine du taux tel qu'il apparait dans rapport_json (ex: "20.00%")
            # / Key = rate string as it appears in rapport_json (e.g. "20.00%")
            cle_taux = f"{compte.taux_de_tva:.2f}%"
            comptes_tva[cle_taux] = compte

    # --- Construire les lignes FEC ---
    # / Build FEC lines
    lignes = []

    # Ligne d'en-tete / Header line
    lignes.append("\t".join(ENTETE_FEC))

    journal_code = "VE"
    journal_lib = "Journal de ventes"

    # Ordonner les clotures par date
    # / Order closures by date
    clotures = clotures_queryset.order_by('datetime_cloture')

    for seq, cloture in enumerate(clotures, start=1):
        rapport = cloture.rapport_json or {}
        date_cloture_str = _formater_date(cloture.datetime_cloture)
        numero_ecriture = f"VE-{date_cloture_str}-{seq:03d}"
        reference_piece = f"Z-{date_cloture_str}-{seq:03d}"

        # --- 1. LIGNES DEBIT : moyens de paiement ---
        # Pour chaque moyen de paiement avec montant > 0, chercher le mapping.
        # / For each payment method with amount > 0, look up the mapping.
        totaux_par_moyen = rapport.get('totaux_par_moyen', {})

        for cle_rapport, code_paiement in CLE_RAPPORT_VERS_CODE_PAIEMENT.items():
            montant_centimes = totaux_par_moyen.get(cle_rapport, 0)
            if montant_centimes <= 0:
                continue

            mapping = mappings_paiement.get(code_paiement)
            if mapping is None or mapping.compte_de_tresorerie is None:
                # Moyen de paiement sans mapping ou sans compte : on ignore.
                # Par defaut, le cashless NFC est mappe vers 4191 (avances clients)
                # pour equilibrer le FEC. Si le gerant a mis null, on ignore.
                # / Payment method without mapping or account: skip.
                # By default, cashless NFC is mapped to 4191 (customer advances)
                # to balance the FEC. If the user set null, we skip.
                continue

            compte = mapping.compte_de_tresorerie
            ligne = _generer_ligne_fec(
                journal_code=journal_code,
                journal_lib=journal_lib,
                numero_ecriture=numero_ecriture,
                date_ecriture=date_cloture_str,
                numero_compte=compte.numero_de_compte,
                libelle_compte=compte.libelle_du_compte,
                reference_piece=reference_piece,
                date_piece=date_cloture_str,
                libelle_ecriture=f"Cloture {date_cloture_str} — {mapping.libelle_moyen}",
                debit_centimes=montant_centimes,
                credit_centimes=0,
                date_validation=date_cloture_str,
            )
            lignes.append(ligne)

        # --- 2. LIGNES CREDIT : ventes par categorie (HT) ---
        # Pour chaque categorie dans detail_ventes, chercher le compte comptable.
        # / For each category in detail_ventes, look up the accounting code.
        detail_ventes = rapport.get('detail_ventes', {})

        for nom_categorie, donnees_categorie in detail_ventes.items():
            # Le total_ht peut etre dans les articles ou calcule
            # On utilise total_ttc - tva pour obtenir le HT si total_ht n'est pas direct
            # / total_ht might be in articles or computed
            articles = donnees_categorie.get('articles', [])
            total_ht_centimes = 0
            for article in articles:
                total_ht_centimes += article.get('total_ht', 0)

            if total_ht_centimes <= 0:
                continue

            # Chercher la categorie et son compte comptable
            # / Look up the category and its accounting code
            categorie = categories_par_nom.get(nom_categorie)
            if categorie and categorie.compte_comptable:
                numero_compte = categorie.compte_comptable.numero_de_compte
                libelle_compte = categorie.compte_comptable.libelle_du_compte
            else:
                numero_compte = "000000"
                libelle_compte = f"Compte inconnu ({nom_categorie})"
                avertissements.append(
                    f"Cloture {date_cloture_str} : categorie '{nom_categorie}' "
                    f"sans compte comptable. Utilisation du compte 000000."
                )

            ligne = _generer_ligne_fec(
                journal_code=journal_code,
                journal_lib=journal_lib,
                numero_ecriture=numero_ecriture,
                date_ecriture=date_cloture_str,
                numero_compte=numero_compte,
                libelle_compte=libelle_compte,
                reference_piece=reference_piece,
                date_piece=date_cloture_str,
                libelle_ecriture=f"Cloture {date_cloture_str} — Ventes {nom_categorie} (HT)",
                debit_centimes=0,
                credit_centimes=total_ht_centimes,
                date_validation=date_cloture_str,
            )
            lignes.append(ligne)

        # --- 3. LIGNES CREDIT : TVA par taux ---
        # Pour chaque taux dans rapport_json['tva'], chercher le CompteComptable TVA.
        # / For each rate in rapport_json['tva'], look up the TVA CompteComptable.
        tva_rapport = rapport.get('tva', {})

        for cle_taux, donnees_tva in tva_rapport.items():
            total_tva_centimes = donnees_tva.get('total_tva', 0)
            if total_tva_centimes <= 0:
                continue

            compte_tva = comptes_tva.get(cle_taux)
            if compte_tva:
                numero_compte = compte_tva.numero_de_compte
                libelle_compte = compte_tva.libelle_du_compte
            else:
                numero_compte = "000000"
                libelle_compte = f"TVA inconnue ({cle_taux})"
                avertissements.append(
                    f"Cloture {date_cloture_str} : taux TVA '{cle_taux}' "
                    f"sans compte comptable TVA. Utilisation du compte 000000."
                )

            ligne = _generer_ligne_fec(
                journal_code=journal_code,
                journal_lib=journal_lib,
                numero_ecriture=numero_ecriture,
                date_ecriture=date_cloture_str,
                numero_compte=numero_compte,
                libelle_compte=libelle_compte,
                reference_piece=reference_piece,
                date_piece=date_cloture_str,
                libelle_ecriture=f"Cloture {date_cloture_str} — TVA {cle_taux}",
                debit_centimes=0,
                credit_centimes=total_tva_centimes,
                date_validation=date_cloture_str,
            )
            lignes.append(ligne)

    # --- Assembler le fichier FEC ---
    # Separateur de ligne : CRLF (norme FEC)
    # Encodage : UTF-8
    # / Assemble the FEC file — line separator: CRLF, encoding: UTF-8
    contenu_texte = "\r\n".join(lignes) + "\r\n"
    contenu_bytes = contenu_texte.encode("utf-8")

    # --- Nom du fichier : {SIREN}FEC{YYYYMMDD}.txt ---
    # Date = date de la derniere cloture du QuerySet
    # / Filename: {SIREN}FEC{YYYYMMDD}.txt — date = last closure date
    derniere_cloture = clotures.last()
    if derniere_cloture:
        date_fichier = _formater_date(derniere_cloture.datetime_cloture)
    else:
        # Queryset vide / Empty queryset
        from django.utils import timezone
        date_fichier = _formater_date(timezone.now())

    nom_fichier = f"{siren}FEC{date_fichier}.txt"

    return contenu_bytes, nom_fichier, avertissements

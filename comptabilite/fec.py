"""
Export FEC (Fichier des Ecritures Comptables) — norme francaise.
/ FEC export — French legal accounting file format.

LOCALISATION : comptabilite/fec.py

Format texte tabule, 18 colonnes obligatoires, encodage CP1252.
Reference : article A47 A-1 du Livre des procedures fiscales.

S4 : FEC simplifie avec comptes par defaut (hardcodes).
S5 ajoutera la personnalisation via CompteComptable / MappingMoyenDePaiement.

/ Tab-separated text, 18 mandatory columns, CP1252 encoding.
Simplified FEC with hardcoded default accounts. Customizable in S5.
"""

# Comptes comptables par defaut (plan comptable francais standard PCG).
# Personnalisable en S5 via le modele CompteComptable.
# / Default accounting accounts (standard French PCG). Customizable in S5.
COMPTES_PAR_DEFAUT = {
    "client": ("411000", "Clients"),
    "banque": ("512000", "Banque"),
    "caisse": ("530000", "Caisse"),
    "cheques": ("511000", "Cheques a encaisser"),
    "tva_55": ("4457100", "TVA collectee 5.5%"),
    "tva_10": ("4457200", "TVA collectee 10%"),
    "tva_20": ("4457300", "TVA collectee 20%"),
    "ventes_billets": ("706000", "Prestations - Billets"),
    "ventes_adhesions": ("756000", "Cotisations - Adhesions"),
}

# Mapping PaymentMethod -> compte de tresorerie (clef de COMPTES_PAR_DEFAUT).
# / PaymentMethod -> treasury account.
MAPPING_PAIEMENT = {
    "CA": "caisse",
    "CC": "banque",
    "CH": "cheques",
    "TR": "banque",
    "SF": "banque", "SN": "banque", "SP": "banque", "SR": "banque",
    "QR": "banque",
    "LE": "client", "LG": "client",
}

# 18 colonnes obligatoires du FEC (article A47 A-1).
# / 18 mandatory FEC columns.
COLONNES_FEC = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise",
]


def _euros_str(centimes):
    """Convertit centimes (int) en string decimal francais '12,34'."""
    if centimes is None or centimes == 0:
        return "0,00"
    return f"{centimes / 100:.2f}".replace(".", ",")


def _ligne_fec(**champs):
    """
    Construit une ligne FEC tabulee a partir des colonnes nommees.
    Toute valeur contenant '\\t' est remplacee par ' ' (separateur FEC).
    / Build a tab-separated FEC line. Any '\\t' in values is replaced by ' '.
    """
    valeurs = []
    for col in COLONNES_FEC:
        val = str(champs.get(col, ""))
        # Eviter les tabulations dans les libelles (casserait le format)
        # / Avoid tabs in field values (would break the format)
        val = val.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        valeurs.append(val)
    return "\t".join(valeurs)


def generer_fec_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export FEC.
    / Returns (bytes, filename, content_type) for the FEC export.

    Strategie : 1 ecriture comptable par cloture, ventilee en N lignes :
    - 1 debit par moyen de paiement (compte tresorerie)
    - 1 credit par categorie de vente (billets/adhesions)
    - 1 credit par taux TVA collectee
    / Strategy: 1 accounting entry per closure, split into N lines.
    """
    rapport = cloture.rapport_json or {}

    journal_code = "VTE"
    journal_lib = "Ventes"
    ecriture_num = str(cloture.numero_sequentiel)
    ecriture_date = cloture.datetime_fin.strftime("%Y%m%d")
    piece_ref = f"CLOT-{cloture.numero_sequentiel}"
    piece_date = ecriture_date
    valid_date = ecriture_date
    ecriture_lib_base = f"Cloture {cloture.get_niveau_display()} #{cloture.numero_sequentiel}"

    # Premiere ligne : en-tete (les 18 noms de colonnes)
    # / First line: header
    lignes = ["\t".join(COLONNES_FEC)]

    # --- Debits : 1 ligne par moyen de paiement utilise (non zero)
    # / Debits: 1 line per used payment method (non-zero)
    for code, item in (rapport.get("totaux_par_moyen") or {}).items():
        if code in ("total", "currency_code", "categories"):
            continue
        if not isinstance(item, dict):
            continue
        total = item.get("total", 0)
        if total == 0:
            continue
        compte_key = MAPPING_PAIEMENT.get(code, "banque")
        num, lib = COMPTES_PAR_DEFAUT[compte_key]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib_base} - {item.get('label', code)}",
            Debit=_euros_str(total), Credit="0,00",
            ValidDate=valid_date,
        ))

    # --- Credit ventes billets (706)
    # / Ticket sales credit (706)
    total_billets = (rapport.get("billets") or {}).get("total", 0)
    if total_billets:
        num, lib = COMPTES_PAR_DEFAUT["ventes_billets"]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib_base} - Billets",
            Debit="0,00", Credit=_euros_str(total_billets),
            ValidDate=valid_date,
        ))

    # --- Credit adhesions (756)
    # / Memberships credit (756)
    total_adhesions = (rapport.get("adhesions") or {}).get("total", 0)
    if total_adhesions:
        num, lib = COMPTES_PAR_DEFAUT["ventes_adhesions"]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib_base} - Adhesions",
            Debit="0,00", Credit=_euros_str(total_adhesions),
            ValidDate=valid_date,
        ))

    # --- Credits TVA (4457X) : 1 ligne par taux
    # / VAT credits: 1 line per VAT rate
    for taux, item in (rapport.get("tva") or {}).items():
        if not isinstance(item, dict):
            continue
        tva_montant = item.get("total_tva", 0)
        if tva_montant == 0:
            continue
        taux_float = float(item.get("taux", 0))
        if taux_float <= 6:
            compte_key = "tva_55"
        elif taux_float <= 12:
            compte_key = "tva_10"
        else:
            compte_key = "tva_20"
        num, lib = COMPTES_PAR_DEFAUT[compte_key]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib_base} - TVA {taux_float}%",
            Debit="0,00", Credit=_euros_str(tva_montant),
            ValidDate=valid_date,
        ))

    # Encodage CP1252 obligatoire (norme francaise FEC). Replace les caracteres
    # impossibles a encoder (rares : caracteres unicode hors plage Windows-1252).
    # / CP1252 encoding required by the French FEC norm.
    contenu = "\r\n".join(lignes).encode("cp1252", errors="replace")

    filename = f"FEC-{cloture.datetime_fin:%Y%m%d}-{cloture.numero_sequentiel}.txt"
    content_type = "text/plain; charset=cp1252"
    return contenu, filename, content_type

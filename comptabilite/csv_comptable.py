"""
Generation des CSV comptables par profil (Sage 50, EBP, Paheko).
/ Accounting CSV generation per profile (Sage 50, EBP, Paheko).

LOCALISATION : comptabilite/csv_comptable.py

Pipeline :
1. Calculer les ecritures comptables (ventilation) :
   - 1 debit tresorerie par moyen de paiement utilise (via MappingMoyenDePaiement)
   - 1 credit 706 par total HT billets
   - 1 credit 756 par total HT adhesions
   - 1 credit 4457X par taux TVA
2. Rendre selon le mode_montant du profil
3. Encoder selon encodage du profil

Retourne (bytes, filename, content_type, avertissements).
"""
import csv
import io

from comptabilite.profils_csv import PROFILS


# Comptes par defaut si MappingMoyenDePaiement ou CompteComptable manquent
# (defense en profondeur — le seed normalement les cree tous).
# / Default accounts if mapping/compte missing (defense in depth).
COMPTES_DEFAUT = {
    "banque": "512000",
    "ventes_billets": "706000",
    "ventes_adhesions": "756000",
    "tva_55": "4457100",
    "tva_10": "4457200",
    "tva_20": "4457300",
}


def _decimal_str(centimes, decimal_sep):
    """Convertit centimes (int) en string avec le separateur decimal du profil."""
    if centimes is None or centimes == 0:
        return f"0{decimal_sep}00"
    return f"{centimes / 100:.2f}".replace(".", decimal_sep)


def _construire_ecritures(cloture):
    """
    Calcule la ventilation des ecritures comptables pour une cloture.
    Retourne (lignes, avertissements, date_ecriture, piece_ref) ou lignes est
    une liste de dict {compte_num, compte_lib, libelle, debit_centimes,
    credit_centimes}.

    / Computes the dispatch of accounting entries. Returns (lines, warnings,
    date, ref).
    """
    from comptabilite.models import CompteComptable, MappingMoyenDePaiement
    rapport = cloture.rapport_json or {}
    lignes = []
    avertissements = []

    date_ecriture = cloture.datetime_fin
    piece_ref = f"CLOT-{cloture.numero_sequentiel}"
    libelle_base = f"Clôture {cloture.get_niveau_display()} #{cloture.numero_sequentiel}"

    # --- Debits : 1 ligne par moyen de paiement non nul
    # / Debits: 1 line per non-zero payment method
    totaux_par_moyen = rapport.get("totaux_par_moyen") or {}
    for code, item in totaux_par_moyen.items():
        if code in ("total", "currency_code", "categories"):
            continue
        if not isinstance(item, dict):
            continue
        total = item.get("total", 0)
        if total == 0:
            continue
        # Chercher le mapping
        # / Look up the mapping
        mapping = MappingMoyenDePaiement.objects.filter(payment_method=code).first()
        if mapping:
            compte = mapping.compte
            compte_num = compte.numero
            compte_lib = compte.libelle
        else:
            avertissements.append(
                f"Aucun mapping pour PaymentMethod '{code}' — compte 512000 utilisé par défaut."
            )
            compte_num = COMPTES_DEFAUT["banque"]
            compte_lib = "Banque (défaut)"

        lignes.append({
            "compte_num": compte_num,
            "compte_lib": compte_lib,
            "libelle": f"{libelle_base} - {item.get('label', code)}",
            "debit_centimes": total,
            "credit_centimes": 0,
        })

    # Totaux billets/adhesions depuis detail_ventes (par categorie d'article).
    # 706 (Prestations) : BILLET 'B', FREERES 'F', BADGE 'G', QRCODE_MA 'Q'
    # 756 (Cotisations) : ADHESION 'A'
    # / Compute totals from detail_ventes (per article category).
    detail = rapport.get("detail_ventes") or {}
    total_billets_ttc = sum(
        detail.get(c, {}).get("total_ttc", 0) for c in ("B", "F", "G", "Q")
    )
    total_adhesions_ttc = detail.get("A", {}).get("total_ttc", 0)

    # --- Credit 706 (ventes billets/prestations HT)
    # / Credit 706 (services/tickets HT)
    if total_billets_ttc:
        # Estimer HT billets : (billets TTC / total_general TTC) * total_ht
        # Si total_general est 0 on evite la division par zero avec "or 1".
        # / Estimate HT from ratio; guard against zero division with "or 1".
        ratio = total_billets_ttc / (cloture.total_general or 1) if cloture.total_general else 1
        ht_billets = int(round(cloture.total_ht * ratio)) if cloture.total_ht else total_billets_ttc
        compte = CompteComptable.objects.filter(numero=COMPTES_DEFAUT["ventes_billets"]).first()
        compte_num = compte.numero if compte else COMPTES_DEFAUT["ventes_billets"]
        compte_lib = compte.libelle if compte else "Prestations - Billets"
        lignes.append({
            "compte_num": compte_num,
            "compte_lib": compte_lib,
            "libelle": f"{libelle_base} - Billets HT",
            "debit_centimes": 0,
            "credit_centimes": ht_billets,
        })

    # --- Credit 756 (ventes adhesions HT)
    # / Credit 756 (HT memberships)
    if total_adhesions_ttc:
        ratio = total_adhesions_ttc / (cloture.total_general or 1) if cloture.total_general else 1
        ht_adhesions = int(round(cloture.total_ht * ratio)) if cloture.total_ht else total_adhesions_ttc
        compte = CompteComptable.objects.filter(numero=COMPTES_DEFAUT["ventes_adhesions"]).first()
        compte_num = compte.numero if compte else COMPTES_DEFAUT["ventes_adhesions"]
        compte_lib = compte.libelle if compte else "Cotisations - Adhésions"
        lignes.append({
            "compte_num": compte_num,
            "compte_lib": compte_lib,
            "libelle": f"{libelle_base} - Adhésions HT",
            "debit_centimes": 0,
            "credit_centimes": ht_adhesions,
        })

    # --- Credits TVA (4457X) : 1 ligne par taux
    # / VAT credits: 1 line per rate
    for taux, item in (rapport.get("tva") or {}).items():
        if not isinstance(item, dict):
            continue
        tva = item.get("total_tva", 0)
        if tva == 0:
            continue
        taux_float = float(item.get("taux", 0))
        if taux_float <= 6:
            compte_key = "tva_55"
        elif taux_float <= 12:
            compte_key = "tva_10"
        else:
            compte_key = "tva_20"
        compte = CompteComptable.objects.filter(numero=COMPTES_DEFAUT[compte_key]).first()
        compte_num = compte.numero if compte else COMPTES_DEFAUT[compte_key]
        compte_lib = compte.libelle if compte else f"TVA collectée {taux_float}%"
        lignes.append({
            "compte_num": compte_num,
            "compte_lib": compte_lib,
            "libelle": f"{libelle_base} - TVA {taux_float}%",
            "debit_centimes": 0,
            "credit_centimes": tva,
        })

    return lignes, avertissements, date_ecriture, piece_ref


def _generer_csv_debit_credit(lignes, profil, date_ecriture, piece_ref):
    """
    Mode DEBIT_CREDIT : 2 colonnes Debit + Credit. Supporte les profils
    Sage 50, Dolibarr, PennyLane, CIEL, ODOO, DOKO via un mapping
    nom_colonne -> valeur, pour gerer leurs noms de colonnes differents.
    / DEBIT_CREDIT mode: 2 columns. Supports all 6 profiles via a
    column-name -> value mapping to handle their varied column names.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=profil["separateur"], quoting=csv.QUOTE_MINIMAL)
    writer.writerow(profil["colonnes"])
    date_str = date_ecriture.strftime(profil["format_date"])

    for ligne in lignes:
        debit_str = _decimal_str(ligne["debit_centimes"], profil["decimal"])
        credit_str = _decimal_str(ligne["credit_centimes"], profil["decimal"])

        # Mapping nom_colonne -> valeur pour les 6 profils DEBIT_CREDIT.
        # Chaque profil pioche selon profil["colonnes"] dans l'ordre defini.
        # / Column name -> value mapping for all 6 DEBIT_CREDIT profiles.
        valeurs_par_nom = {
            # Code journal
            "JournalCode": "VTE", "Journal": "VTE", "journal_id": "VTE",
            "code_journal": "VTE",
            # Date
            "EcritureDate": date_str, "Date": date_str, "date": date_str,
            # Compte (numero)
            "CompteNum": ligne["compte_num"], "Compte": ligne["compte_num"],
            "compte": ligne["compte_num"], "account_id": ligne["compte_num"],
            # Libelle compte
            "CompteLib": ligne["compte_lib"], "LibelleCompte": ligne["compte_lib"],
            "libelle_compte": ligne["compte_lib"],
            # Reference piece
            "PieceRef": piece_ref, "Piece": piece_ref,
            "piece": piece_ref, "ref": piece_ref,
            # Libelle de l'ecriture
            "EcritureLib": ligne["libelle"], "Libelle": ligne["libelle"],
            "label_operation": ligne["libelle"], "name": ligne["libelle"],
            # Montants
            "Debit": debit_str, "debit": debit_str,
            "Credit": credit_str, "credit": credit_str,
        }

        # On reconstruit la ligne dans l'ordre des colonnes du profil.
        # Si une colonne n'est pas connue, on met une chaine vide.
        # / Reconstruct row in profile's column order. Unknown columns -> "".
        writer.writerow([valeurs_par_nom.get(col, "") for col in profil["colonnes"]])

    return buffer.getvalue()


def _generer_csv_montant_sens(lignes, profil, date_ecriture, piece_ref):
    """Mode MONTANT_SENS : 1 colonne montant + 1 colonne sens (D/C) (EBP)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=profil["separateur"], quoting=csv.QUOTE_MINIMAL)
    writer.writerow(profil["colonnes"])
    date_str = date_ecriture.strftime(profil["format_date"])
    for ligne in lignes:
        if ligne["debit_centimes"]:
            montant_centimes = ligne["debit_centimes"]
            sens = "D"
        else:
            montant_centimes = ligne["credit_centimes"]
            sens = "C"
        writer.writerow([
            date_str,
            "VTE",
            ligne["compte_num"],
            ligne["libelle"],
            _decimal_str(montant_centimes, profil["decimal"]),
            sens,
        ])
    return buffer.getvalue()


def _generer_csv_montant_unique(lignes, profil, date_ecriture, piece_ref):
    """
    Mode MONTANT_UNIQUE : compte_debit + compte_credit + montant (Paheko).
    On emet 1 ligne par debit et 1 ligne par credit, en remplissant
    la colonne adequate. Plus lisible pour le comptable que le pairage.
    / We emit 1 line per debit AND 1 line per credit, with the appropriate
    column filled. More explicit than artificial pairing.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=profil["separateur"], quoting=csv.QUOTE_MINIMAL)
    writer.writerow(profil["colonnes"])
    date_str = date_ecriture.strftime(profil["format_date"])

    for ligne in lignes:
        if ligne["debit_centimes"]:
            writer.writerow([
                date_str,
                ligne["libelle"],
                ligne["compte_num"],   # compte_debit
                "",                    # compte_credit
                _decimal_str(ligne["debit_centimes"], profil["decimal"]),
            ])
        else:
            writer.writerow([
                date_str,
                ligne["libelle"],
                "",                    # compte_debit
                ligne["compte_num"],   # compte_credit
                _decimal_str(ligne["credit_centimes"], profil["decimal"]),
            ])
    return buffer.getvalue()


def generer_csv_comptable(cloture, profil_slug) -> tuple:
    """
    Retourne (bytes, filename, content_type, avertissements) pour l'export.
    / Returns (bytes, filename, content_type, warnings).

    profil_slug : 'sage_50' | 'ebp' | 'paheko' (defini dans PROFILS).
    """
    profil = PROFILS.get(profil_slug)
    if not profil:
        profil = PROFILS["sage_50"]
        profil_slug = "sage_50"

    lignes, avertissements, date_ecriture, piece_ref = _construire_ecritures(cloture)

    # Dispatch selon mode_montant
    if profil["mode_montant"] == "DEBIT_CREDIT":
        contenu_str = _generer_csv_debit_credit(lignes, profil, date_ecriture, piece_ref)
    elif profil["mode_montant"] == "MONTANT_SENS":
        contenu_str = _generer_csv_montant_sens(lignes, profil, date_ecriture, piece_ref)
    elif profil["mode_montant"] == "MONTANT_UNIQUE":
        contenu_str = _generer_csv_montant_unique(lignes, profil, date_ecriture, piece_ref)
    else:
        raise ValueError(f"Mode montant inconnu : {profil['mode_montant']}")

    # Encodage
    # utf-8-sig : Python encode avec BOM automatiquement
    # / utf-8-sig: Python encodes with BOM automatically
    contenu_bytes = contenu_str.encode(profil["encodage"], errors="replace")

    filename = (
        f"compta-{profil_slug}-{cloture.numero_sequentiel}-"
        f"{cloture.datetime_fin:%Y%m%d}{profil['extension']}"
    )
    content_type = f"text/csv; charset={profil['encodage']}"
    return contenu_bytes, filename, content_type, avertissements

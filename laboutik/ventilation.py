"""
Logique de ventilation comptable partagee — debit/credit par cloture.
Utilisee par le generateur FEC (laboutik/fec.py) et les exports CSV.

/ Shared accounting ventilation logic — debit/credit per closure.
Used by the FEC generator (laboutik/fec.py) and CSV exports.

LOCALISATION : laboutik/ventilation.py
"""

import logging

from BaseBillet.models import CategorieProduct
from laboutik.models import CompteComptable, MappingMoyenDePaiement

logger = logging.getLogger(__name__)


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


def charger_mappings_paiement():
    """
    Charge tous les MappingMoyenDePaiement avec leur compte de tresorerie.
    Retourne un dict {code_moyen: objet_mapping}.
    Peu d'enregistrements (4-6 max), on charge tout d'un coup.

    / Load all MappingMoyenDePaiement with their treasury account.
    Returns a dict {payment_code: mapping_obj}.
    Few records (4-6 max), load all at once.
    """
    mappings_paiement = {}
    for mapping in MappingMoyenDePaiement.objects.select_related('compte_de_tresorerie').all():
        mappings_paiement[mapping.moyen_de_paiement] = mapping
    return mappings_paiement


def charger_categories_par_nom():
    """
    Charge toutes les CategorieProduct avec leur compte comptable.
    Retourne un dict {nom_categorie: objet_categorie}.

    / Load all CategorieProduct with their accounting account.
    Returns a dict {category_name: category_obj}.
    """
    categories_par_nom = {}
    for categorie in CategorieProduct.objects.select_related('compte_comptable').all():
        categories_par_nom[categorie.name] = categorie
    return categories_par_nom


def charger_comptes_tva():
    """
    Charge les CompteComptable de nature TVA actifs, indexes par taux.
    Retourne un dict {"20.00%": objet_compte}.

    / Load active VAT CompteComptable records, indexed by rate.
    Returns a dict {"20.00%": account_obj}.
    """
    comptes_tva = {}
    for compte in CompteComptable.objects.filter(
        nature_du_compte=CompteComptable.TVA,
        est_actif=True,
    ):
        if compte.taux_de_tva is not None:
            # Cle = chaine du taux tel qu'il apparait dans rapport_json (ex: "20.00%")
            # / Key = rate string as it appears in rapport_json (e.g. "20.00%")
            cle_taux = f"{compte.taux_de_tva:.2f}%"
            comptes_tva[cle_taux] = compte
    return comptes_tva


def ventiler_cloture(cloture, mappings_paiement, categories_par_nom, comptes_tva):
    """
    Ventile une cloture en lignes debit/credit comptables.
    Retourne (lignes, avertissements).

    / Break down a closure into accounting debit/credit lines.
    Returns (lines, warnings).

    :param cloture: objet ClotureCaisse
    :param mappings_paiement: dict {code: MappingMoyenDePaiement} (cf. charger_mappings_paiement)
    :param categories_par_nom: dict {nom: CategorieProduct} (cf. charger_categories_par_nom)
    :param comptes_tva: dict {"20.00%": CompteComptable} (cf. charger_comptes_tva)
    :return: tuple (lignes, avertissements)
        - lignes : list de dicts avec sens, numero_compte, libelle_compte,
          montant_centimes, libelle_ecriture
        - avertissements : list de str
    """
    lignes = []
    avertissements = []

    rapport = cloture.rapport_json or {}
    date_cloture_str = cloture.datetime_cloture.strftime("%Y%m%d")

    # --- 1. LIGNES DEBIT : moyens de paiement ---
    # Pour chaque moyen de paiement avec montant != 0, chercher le mapping.
    # Un montant positif = encaissement (debit normal).
    # Un montant negatif = remboursement/avoir (le sens s'inverse : credit au lieu de debit).
    # / For each payment method with amount != 0, look up the mapping.
    # Positive = collection (normal debit).
    # Negative = refund/credit note (sense inverts: credit instead of debit).
    totaux_par_moyen = rapport.get('totaux_par_moyen', {})

    for cle_rapport, code_paiement in CLE_RAPPORT_VERS_CODE_PAIEMENT.items():
        montant_centimes = totaux_par_moyen.get(cle_rapport, 0)
        if montant_centimes == 0:
            continue

        mapping = mappings_paiement.get(code_paiement)
        if mapping is None or mapping.compte_de_tresorerie is None:
            continue

        compte = mapping.compte_de_tresorerie

        # Montant negatif = remboursement → inverser le sens
        # / Negative amount = refund → invert the sense
        if montant_centimes > 0:
            sens = "D"
            montant_abs = montant_centimes
        else:
            sens = "C"
            montant_abs = abs(montant_centimes)

        lignes.append({
            "sens": sens,
            "numero_compte": compte.numero_de_compte,
            "libelle_compte": compte.libelle_du_compte,
            "montant_centimes": montant_abs,
            "libelle_ecriture": f"Cloture {date_cloture_str} — {mapping.libelle_moyen}",
        })

    # --- 2. LIGNES CREDIT : ventes par categorie (HT) ---
    # Pour chaque categorie dans detail_ventes, chercher le compte comptable.
    # / For each category in detail_ventes, look up the accounting account.
    detail_ventes = rapport.get('detail_ventes', {})

    for nom_categorie, donnees_categorie in detail_ventes.items():
        # Calculer le total HT a partir des articles
        # / Compute HT total from articles
        articles = donnees_categorie.get('articles', [])
        total_ht_centimes = 0
        for article in articles:
            total_ht_centimes += article.get('total_ht', 0)

        if total_ht_centimes == 0:
            continue

        # Chercher la categorie et son compte comptable
        # / Look up the category and its accounting account
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

        # Montant negatif = avoir/remboursement → inverser le sens (debit au lieu de credit)
        # / Negative amount = credit note/refund → invert sense (debit instead of credit)
        if total_ht_centimes > 0:
            sens = "C"
            montant_abs = total_ht_centimes
        else:
            sens = "D"
            montant_abs = abs(total_ht_centimes)

        lignes.append({
            "sens": sens,
            "numero_compte": numero_compte,
            "libelle_compte": libelle_compte,
            "montant_centimes": montant_abs,
            "libelle_ecriture": f"Cloture {date_cloture_str} — Ventes {nom_categorie} (HT)",
        })

    # --- 3. LIGNES CREDIT : TVA par taux ---
    # Pour chaque taux dans rapport_json['tva'], chercher le CompteComptable TVA.
    # / For each rate in rapport_json['tva'], look up the TVA CompteComptable.
    tva_rapport = rapport.get('tva', {})

    for cle_taux, donnees_tva in tva_rapport.items():
        total_tva_centimes = donnees_tva.get('total_tva', 0)
        if total_tva_centimes == 0:
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

        # Montant negatif = avoir → inverser le sens
        # / Negative amount = credit note → invert sense
        if total_tva_centimes > 0:
            sens = "C"
            montant_abs = total_tva_centimes
        else:
            sens = "D"
            montant_abs = abs(total_tva_centimes)

        lignes.append({
            "sens": sens,
            "numero_compte": numero_compte,
            "libelle_compte": libelle_compte,
            "montant_centimes": montant_abs,
            "libelle_ecriture": f"Cloture {date_cloture_str} — TVA {cle_taux}",
        })

    # Verification d'equilibre : sum debits doit egal sum credits
    # Si desequilibre, on logue un warning (pas bloquant pour l'export)
    # / Balance check: sum debits must equal sum credits
    # If unbalanced, log a warning (non-blocking for export)
    total_debits = 0
    total_credits = 0
    for ligne in lignes:
        if ligne["sens"] == "D":
            total_debits += ligne["montant_centimes"]
        else:
            total_credits += ligne["montant_centimes"]

    if total_debits != total_credits:
        ecart = total_debits - total_credits
        avertissements.append(
            f"Cloture {date_cloture_str} : desequilibre comptable de "
            f"{ecart} centimes (debits={total_debits}, credits={total_credits}). "
            f"Verifiez les mappings moyens de paiement."
        )
        logger.warning(
            f"Ventilation desequilibree pour cloture {date_cloture_str}: "
            f"debits={total_debits}, credits={total_credits}, ecart={ecart}"
        )

    return lignes, avertissements

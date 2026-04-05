"""
Module d'integrite des donnees d'encaissement.
Chainage HMAC-SHA256 conforme a l'exigence 8 du referentiel LNE v1.7.
/ Data integrity module for POS transactions.
HMAC-SHA256 chaining per LNE certification standard v1.7, requirement 8.

LOCALISATION : laboutik/integrity.py

Algorithmes acceptables selon le referentiel LNE (page 37) :
- HMAC-SHA-256 (utilise ici)
- HMAC-SHA3
- RSA-SSA-PSS, ECDSA (surdimensionne pour notre cas)

Algorithmes NON acceptables :
- SHA-256 seul (sans cle), SHA-1, MD5, CRC16, CRC32

La cle HMAC est par tenant, chiffree Fernet dans LaboutikConfiguration.
L'utilisateur final (le lieu/association) n'a jamais acces a la cle.
/ The HMAC key is per tenant, Fernet-encrypted in LaboutikConfiguration.
The end user (venue/association) never has access to the key.
"""

import hmac
import hashlib
import json


def calculer_hmac(ligne, cle_secrete, previous_hmac=""):
    """
    Calcule le HMAC-SHA256 d'une LigneArticle chainee avec la precedente.
    Les champs hashes sont ceux qui impactent le rapport comptable.
    / Computes HMAC-SHA256 of a LigneArticle chained with the previous one.
    Hashed fields are those impacting the accounting report.

    LOCALISATION : laboutik/integrity.py

    :param ligne: LigneArticle instance
    :param cle_secrete: str — cle HMAC en clair (dechiffree depuis Fernet)
    :param previous_hmac: str — HMAC de la ligne precedente ('' si premiere)
    :return: str — empreinte HMAC-SHA256 de 64 caracteres hex
    """
    donnees = json.dumps(
        [
            str(ligne.uuid),
            str(ligne.datetime.isoformat()) if ligne.datetime else "",
            ligne.amount,
            ligne.total_ht,
            # Normaliser qty et vat en string avec 6 decimales pour que le hash
            # soit identique que l'objet vienne de la memoire (int/float)
            # ou de la DB (Decimal avec 6 decimales).
            # / Normalize qty and vat to 6-decimal strings so the hash is
            # identical whether the object comes from memory or from DB.
            f"{float(ligne.qty):.6f}",
            f"{float(ligne.vat):.2f}",
            ligne.payment_method or "",
            ligne.status or "",
            ligne.sale_origin or "",
            # Quantite poids/volume saisie par le caissier (donnee elementaire LNE exigence 3).
            # None → '' pour retrocompatibilite avec les lignes existantes.
            # / Weight/volume quantity entered by cashier (LNE elementary data requirement 3).
            # None → '' for backward compatibility with existing lines.
            str(ligne.weight_quantity) if ligne.weight_quantity is not None else "",
            previous_hmac,
        ]
    )
    return hmac.new(
        cle_secrete.encode("utf-8"),
        donnees.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def obtenir_previous_hmac(sale_origin=None):
    """
    Retourne le hmac_hash de la derniere LigneArticle chainee.
    Les chaines sont separees par sale_origin (production vs test).
    / Returns the hmac_hash of the last chained LigneArticle.
    Chains are separated by sale_origin (production vs test).

    LOCALISATION : laboutik/integrity.py
    """
    from BaseBillet.models import LigneArticle, SaleOrigin

    if sale_origin is None:
        sale_origin = SaleOrigin.LABOUTIK
    derniere_hmac = (
        LigneArticle.objects.filter(
            sale_origin=sale_origin,
            hmac_hash__gt="",
        )
        .order_by("-datetime", "-pk")
        .values_list("hmac_hash", flat=True)
        .first()
    )
    return derniere_hmac or ""


def verifier_chaine(lignes_queryset, cle_secrete):
    """
    Verifie l'integrite de la chaine HMAC sur un queryset de LigneArticle.
    Croise avec CorrectionPaiement pour distinguer corrections tracees de falsifications.
    / Verifies HMAC chain integrity on a LigneArticle queryset.
    Cross-checks with CorrectionPaiement to distinguish traced corrections from tampering.

    LOCALISATION : laboutik/integrity.py

    :param lignes_queryset: QuerySet de LigneArticle (sera ordonne par datetime, pk)
    :param cle_secrete: str — cle HMAC en clair
    :return: tuple (est_valide: bool, erreurs: list, corrections_tracees: list)
    """
    erreurs = []
    corrections_tracees = []
    previous = ""

    for ligne in lignes_queryset.order_by("datetime", "pk"):
        # Les lignes pre-migration n'ont pas de HMAC — on les ignore
        # / Pre-migration lines have no HMAC — skip them
        if not ligne.hmac_hash:
            continue

        attendu = calculer_hmac(ligne, cle_secrete, previous)

        if ligne.hmac_hash != attendu:
            # Verifier si c'est une correction tracee (CorrectionPaiement)
            # Le modele n'existe pas encore (session 17) — on gere le cas
            # / Check if it's a traced correction (CorrectionPaiement)
            # Model doesn't exist yet (session 17) — handle gracefully
            correction_trouvee = False
            try:
                from laboutik.models import CorrectionPaiement

                correction = CorrectionPaiement.objects.filter(
                    ligne_article=ligne,
                ).first()
                if correction:
                    correction_trouvee = True
                    corrections_tracees.append(
                        {
                            "uuid": str(ligne.uuid),
                            "correction_uuid": str(correction.uuid),
                            "ancien_moyen": correction.ancien_moyen,
                            "nouveau_moyen": correction.nouveau_moyen,
                            "raison": correction.raison,
                        }
                    )
            except (ImportError, LookupError):
                # Le modele CorrectionPaiement n'existe pas encore
                # / CorrectionPaiement model doesn't exist yet
                pass

            if not correction_trouvee:
                erreurs.append(
                    {
                        "uuid": str(ligne.uuid),
                        "datetime": str(ligne.datetime),
                        "attendu": attendu,
                        "trouve": ligne.hmac_hash,
                    }
                )

        previous = ligne.hmac_hash

    est_valide = len(erreurs) == 0
    return (est_valide, erreurs, corrections_tracees)


def calculer_total_ht(amount_ttc_centimes, taux_tva):
    """
    Calcule le total HT depuis le TTC et le taux de TVA.
    / Computes HT total from TTC and VAT rate.

    LOCALISATION : laboutik/integrity.py

    Formule LNE : HT = round(TTC / (1 + taux/100))
    TVA = TTC - HT

    :param amount_ttc_centimes: int — montant TTC en centimes
    :param taux_tva: Decimal ou float — taux TVA en % (ex: 20.0)
    :return: int — total HT en centimes
    """
    taux = float(taux_tva)
    if taux > 0:
        return int(round(amount_ttc_centimes / (1 + taux / 100)))
    return amount_ttc_centimes


def ligne_couverte_par_cloture(ligne):
    """
    Verifie si une LigneArticle est couverte par une cloture journaliere existante.
    Retourne la ClotureCaisse si oui, None sinon.
    Utilisee comme garde pour interdire les corrections post-cloture.
    Seules les clotures J sont verifiees (M/A sont des agregats, pas des periodes).
    / Checks if a LigneArticle is covered by an existing daily closure.
    Returns the ClotureCaisse if yes, None otherwise.
    Only daily closures are checked (M/A are aggregates, not periods).

    LOCALISATION : laboutik/integrity.py
    """
    from laboutik.models import ClotureCaisse

    return ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.JOURNALIERE,
        datetime_ouverture__lte=ligne.datetime,
        datetime_cloture__gte=ligne.datetime,
    ).first()

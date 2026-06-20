"""
Module central d'archivage fiscal pour la caisse LaBoutik.
Exporte les donnees d'encaissement en CSV (UTF-8 BOM, delimiteur ;) + JSON + hash HMAC.
Appele par 3 management commands et 1 vue admin.
/ Central fiscal archiving module for the LaBoutik POS.
Exports POS data as CSV (UTF-8 BOM, delimiter ;) + JSON + HMAC hash.
Called by 3 management commands and 1 admin view.

LOCALISATION : laboutik/archivage.py
"""
import csv
import hmac
import hashlib
import io
import json
import zipfile
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone


# =====================================================================
# Colonnes CSV par modele / CSV columns per model
# =====================================================================

COLONNES_LIGNES_ARTICLE = [
    'uuid', 'datetime', 'article', 'categorie', 'prix_ttc_centimes',
    'quantite', 'payment_method', 'sale_origin', 'taux_tva',
    'total_ht_centimes', 'total_tva_centimes', 'point_de_vente',
    'operateur_email', 'user_email', 'uuid_transaction', 'hmac_hash',
]

COLONNES_CLOTURES = [
    'uuid', 'datetime_cloture', 'datetime_ouverture', 'niveau',
    'numero_sequentiel', 'total_especes', 'total_carte_bancaire',
    'total_cashless', 'total_cheque', 'total_general',
    'nombre_transactions', 'total_perpetuel', 'hash_lignes',
    'responsable_email', 'point_de_vente',
]

COLONNES_CORRECTIONS = [
    'uuid', 'datetime', 'ligne_article_uuid', 'ancien_moyen',
    'nouveau_moyen', 'raison', 'operateur_email',
]

COLONNES_IMPRESSIONS = [
    'uuid', 'datetime', 'type_justificatif', 'is_duplicata',
    'format_emission', 'ligne_article_uuid', 'cloture_uuid',
    'uuid_transaction', 'operateur_email', 'printer_name',
]

COLONNES_SORTIES_CAISSE = [
    'uuid', 'datetime', 'point_de_vente', 'montant_total_centimes',
    'ventilation_json', 'note', 'operateur_email',
]

COLONNES_HISTORIQUE_FOND = [
    'uuid', 'datetime', 'point_de_vente', 'ancien_montant_centimes',
    'nouveau_montant_centimes', 'raison', 'operateur_email',
]


# =====================================================================
# Fonctions utilitaires / Utility functions
# =====================================================================

def _ecrire_csv(colonnes, lignes_dicts):
    """
    Ecrit un CSV en memoire avec BOM UTF-8 et delimiteur ;.
    Retourne des bytes prets a etre ecrits dans un fichier ou un ZIP.
    / Writes a CSV in memory with UTF-8 BOM and ; delimiter.
    Returns bytes ready to write into a file or ZIP.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=colonnes,
        delimiter=';',
        quoting=csv.QUOTE_ALL,
        extrasaction='ignore',
    )
    writer.writeheader()
    for ligne in lignes_dicts:
        writer.writerow(ligne)
    contenu = buffer.getvalue()
    # BOM UTF-8 pour Excel FR / UTF-8 BOM for French Excel
    return b'\xef\xbb\xbf' + contenu.encode('utf-8')


def _calculer_hmac_fichier(contenu_bytes, cle_secrete):
    """
    Calcule le HMAC-SHA256 d'un contenu en bytes.
    Retourne une chaine hexadecimale de 64 caracteres.
    / Computes HMAC-SHA256 of byte content.
    Returns a 64-character hex string.
    """
    return hmac.new(
        cle_secrete.encode('utf-8'),
        contenu_bytes,
        hashlib.sha256,
    ).hexdigest()


# =====================================================================
# Fonctions d'extraction / Extract functions
# =====================================================================

def _extraire_lignes_article(debut, fin):
    """
    Extrait les LigneArticle de la periode [debut, fin].
    debut et fin sont des datetime aware ou None (None = pas de filtre).
    Retourne une liste de dicts avec des valeurs string pour le CSV.
    / Extracts LigneArticle for the period [debut, fin].
    debut and fin are aware datetimes or None (None = no filter).
    Returns list of dicts with string values for CSV.
    """
    from BaseBillet.models import LigneArticle, SaleOrigin

    # Filtrer uniquement les ventes caisse (production + test)
    # Les ventes en ligne (billetterie, adhesions) ne sont pas du ressort de la caisse.
    # / Filter only POS sales (production + test)
    qs = LigneArticle.objects.filter(
        sale_origin__in=[SaleOrigin.LABOUTIK, SaleOrigin.LABOUTIK_TEST],
    ).select_related(
        'pricesold__productsold__product__categorie_pos',
        'point_de_vente',
        'membership__user',
        'reservation__user_commande',
        'paiement_stripe__user',
    ).order_by('datetime')

    if debut is not None:
        qs = qs.filter(datetime__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime__lte=fin)

    resultats = []
    for ligne in qs.iterator():
        # Nom de l'article / Article name
        article = ''
        categorie = ''
        try:
            if ligne.pricesold and ligne.pricesold.productsold:
                product = ligne.pricesold.productsold.product
                article = product.name if product else ''
                if hasattr(product, 'categorie_pos') and product.categorie_pos:
                    categorie = product.categorie_pos.name
        except Exception:
            # Certaines LigneArticle historiques n'ont pas de PriceSold lie.
            # On utilise les champs directs article/categorie de LigneArticle.
            # / Some historical LigneArticle lack a linked PriceSold.
            pass

        # Total TTC en centimes / Total incl. tax in cents
        prix_ttc_centimes = str(ligne.amount)
        quantite = str(ligne.qty)

        # Taux de TVA / VAT rate
        taux_tva = f"{float(ligne.vat):.2f}"

        # Total HT en centimes (stocke en base) / Total excl. tax in cents (from DB)
        total_ht_centimes = str(ligne.total_ht)

        # Total TVA = TTC * qty - HT / VAT amount = TTC * qty - HT
        total_ttc = int(ligne.amount * ligne.qty)
        total_tva_centimes = str(total_ttc - ligne.total_ht)

        # Point de vente / Point of sale
        pdv = ''
        if ligne.point_de_vente:
            pdv = ligne.point_de_vente.name

        # Email operateur : pas de FK responsable sur LigneArticle, champ vide
        # / Operator email: no responsable FK on LigneArticle, empty field
        operateur_email = ''

        # Email utilisateur / User email
        user_email = ligne.user_email() or ''

        resultats.append({
            'uuid': str(ligne.uuid),
            'datetime': ligne.datetime.isoformat() if ligne.datetime else '',
            'article': article,
            'categorie': categorie,
            'prix_ttc_centimes': prix_ttc_centimes,
            'quantite': quantite,
            'payment_method': ligne.payment_method or '',
            'sale_origin': ligne.sale_origin or '',
            'taux_tva': taux_tva,
            'total_ht_centimes': total_ht_centimes,
            'total_tva_centimes': total_tva_centimes,
            'point_de_vente': pdv,
            'operateur_email': operateur_email,
            'user_email': user_email,
            'uuid_transaction': str(ligne.uuid_transaction) if ligne.uuid_transaction else '',
            'hmac_hash': ligne.hmac_hash or '',
        })

    return resultats


def _extraire_clotures(debut, fin):
    """
    Extrait les ClotureCaisse de la periode [debut, fin].
    / Extracts ClotureCaisse for the period [debut, fin].
    """
    from laboutik.models import ClotureCaisse

    qs = ClotureCaisse.objects.select_related(
        'point_de_vente',
        'responsable',
    ).order_by('datetime_cloture')

    if debut is not None:
        qs = qs.filter(datetime_cloture__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime_cloture__lte=fin)

    resultats = []
    for cloture in qs.iterator():
        # Le modele n'a pas de champ total_cheque — on met 0
        # / Model has no total_cheque field — default to 0
        total_cheque = '0'

        pdv = ''
        if cloture.point_de_vente:
            pdv = cloture.point_de_vente.name

        responsable_email = ''
        if cloture.responsable:
            responsable_email = cloture.responsable.email or ''

        resultats.append({
            'uuid': str(cloture.uuid),
            'datetime_cloture': cloture.datetime_cloture.isoformat() if cloture.datetime_cloture else '',
            'datetime_ouverture': cloture.datetime_ouverture.isoformat() if cloture.datetime_ouverture else '',
            'niveau': cloture.niveau or '',
            'numero_sequentiel': str(cloture.numero_sequentiel),
            'total_especes': str(cloture.total_especes),
            'total_carte_bancaire': str(cloture.total_carte_bancaire),
            'total_cashless': str(cloture.total_cashless),
            'total_cheque': total_cheque,
            'total_general': str(cloture.total_general),
            'nombre_transactions': str(cloture.nombre_transactions),
            'total_perpetuel': str(cloture.total_perpetuel),
            'hash_lignes': cloture.hash_lignes or '',
            'responsable_email': responsable_email,
            'point_de_vente': pdv,
        })

    return resultats


def _extraire_corrections(debut, fin):
    """
    Extrait les CorrectionPaiement de la periode [debut, fin].
    / Extracts CorrectionPaiement for the period [debut, fin].
    """
    from laboutik.models import CorrectionPaiement

    qs = CorrectionPaiement.objects.select_related(
        'ligne_article',
        'operateur',
    ).order_by('datetime')

    if debut is not None:
        qs = qs.filter(datetime__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime__lte=fin)

    resultats = []
    for correction in qs.iterator():
        operateur_email = ''
        if correction.operateur:
            operateur_email = correction.operateur.email or ''

        resultats.append({
            'uuid': str(correction.uuid),
            'datetime': correction.datetime.isoformat() if correction.datetime else '',
            'ligne_article_uuid': str(correction.ligne_article_id) if correction.ligne_article_id else '',
            'ancien_moyen': correction.ancien_moyen or '',
            'nouveau_moyen': correction.nouveau_moyen or '',
            'raison': correction.raison or '',
            'operateur_email': operateur_email,
        })

    return resultats


def _extraire_impressions(debut, fin):
    """
    Extrait les ImpressionLog de la periode [debut, fin].
    / Extracts ImpressionLog for the period [debut, fin].
    """
    from laboutik.models import ImpressionLog

    qs = ImpressionLog.objects.select_related(
        'ligne_article',
        'cloture',
        'operateur',
        'printer',
    ).order_by('datetime')

    if debut is not None:
        qs = qs.filter(datetime__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime__lte=fin)

    resultats = []
    for imp in qs.iterator():
        operateur_email = ''
        if imp.operateur:
            operateur_email = imp.operateur.email or ''

        printer_name = ''
        if imp.printer:
            printer_name = imp.printer.name or ''

        resultats.append({
            'uuid': str(imp.uuid),
            'datetime': imp.datetime.isoformat() if imp.datetime else '',
            'type_justificatif': imp.type_justificatif or '',
            'is_duplicata': str(imp.is_duplicata),
            'format_emission': imp.format_emission or '',
            'ligne_article_uuid': str(imp.ligne_article_id) if imp.ligne_article_id else '',
            'cloture_uuid': str(imp.cloture_id) if imp.cloture_id else '',
            'uuid_transaction': str(imp.uuid_transaction) if imp.uuid_transaction else '',
            'operateur_email': operateur_email,
            'printer_name': printer_name,
        })

    return resultats


def _extraire_sorties_caisse(debut, fin):
    """
    Extrait les SortieCaisse de la periode [debut, fin].
    / Extracts SortieCaisse for the period [debut, fin].
    """
    from laboutik.models import SortieCaisse

    qs = SortieCaisse.objects.select_related(
        'point_de_vente',
        'operateur',
    ).order_by('datetime')

    if debut is not None:
        qs = qs.filter(datetime__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime__lte=fin)

    resultats = []
    for sortie in qs.iterator():
        pdv = ''
        if sortie.point_de_vente:
            pdv = sortie.point_de_vente.name

        operateur_email = ''
        if sortie.operateur:
            operateur_email = sortie.operateur.email or ''

        resultats.append({
            'uuid': str(sortie.uuid),
            'datetime': sortie.datetime.isoformat() if sortie.datetime else '',
            'point_de_vente': pdv,
            'montant_total_centimes': str(sortie.montant_total),
            'ventilation_json': json.dumps(sortie.ventilation, ensure_ascii=False),
            'note': sortie.note or '',
            'operateur_email': operateur_email,
        })

    return resultats


def _extraire_historique_fond(debut, fin):
    """
    Extrait les HistoriqueFondDeCaisse de la periode [debut, fin].
    / Extracts HistoriqueFondDeCaisse for the period [debut, fin].
    """
    from laboutik.models import HistoriqueFondDeCaisse

    qs = HistoriqueFondDeCaisse.objects.select_related(
        'point_de_vente',
        'operateur',
    ).order_by('datetime')

    if debut is not None:
        qs = qs.filter(datetime__gte=debut)
    if fin is not None:
        qs = qs.filter(datetime__lte=fin)

    resultats = []
    for hist in qs.iterator():
        pdv = ''
        if hist.point_de_vente:
            pdv = hist.point_de_vente.name

        operateur_email = ''
        if hist.operateur:
            operateur_email = hist.operateur.email or ''

        resultats.append({
            'uuid': str(hist.uuid),
            'datetime': hist.datetime.isoformat() if hist.datetime else '',
            'point_de_vente': pdv,
            'ancien_montant_centimes': str(hist.ancien_montant),
            'nouveau_montant_centimes': str(hist.nouveau_montant),
            'raison': hist.raison or '',
            'operateur_email': operateur_email,
        })

    return resultats


# =====================================================================
# Construction des metadonnees / Metadata construction
# =====================================================================

def _construire_meta(schema, debut, fin, compteurs):
    """
    Construit le dictionnaire de metadonnees de l'archive.
    Lit Configuration.get_solo() pour les infos de l'organisation.
    / Builds the archive metadata dict.
    Reads Configuration.get_solo() for organization info.
    """
    from BaseBillet.models import Configuration

    config = Configuration.get_solo()

    meta = {
        'schema': schema,
        'organisation': config.organisation or '',
        'siren': config.siren or '',
        'tva_number': config.tva_number or '',
        'email': config.email or '',
        'adresse': config.adress or '',
        'code_postal': str(config.postal_code) if config.postal_code else '',
        'ville': config.city or '',
        'debut': debut.isoformat() if debut else None,
        'fin': fin.isoformat() if fin else None,
        'date_generation': timezone.now().isoformat(),
        'compteurs': compteurs,
    }
    return meta


# =====================================================================
# Fonction centrale de generation / Central generation function
# =====================================================================

def generer_fichiers_archive(schema, debut=None, fin=None):
    """
    Genere tous les fichiers d'une archive fiscale pour un tenant.
    Convertit les dates (date) en datetime aware si necessaire.
    Retourne un dict {nom_fichier: bytes}.
    / Generates all files for a fiscal archive for a tenant.
    Converts date objects to aware datetimes if needed.
    Returns dict {filename: bytes}.
    """
    from datetime import date as date_type

    # Convertir date → datetime aware / Convert date → aware datetime
    if debut is not None and isinstance(debut, date_type) and not isinstance(debut, datetime):
        debut = timezone.make_aware(datetime.combine(debut, time.min))
    if fin is not None and isinstance(fin, date_type) and not isinstance(fin, datetime):
        fin = timezone.make_aware(datetime.combine(fin, time.max))

    # Extraction de toutes les donnees / Extract all data
    lignes_article = _extraire_lignes_article(debut, fin)
    clotures = _extraire_clotures(debut, fin)
    corrections = _extraire_corrections(debut, fin)
    impressions = _extraire_impressions(debut, fin)
    sorties_caisse = _extraire_sorties_caisse(debut, fin)
    historique_fond = _extraire_historique_fond(debut, fin)

    # Generation des CSV / Generate CSVs
    fichiers = {}
    fichiers['lignes_article.csv'] = _ecrire_csv(COLONNES_LIGNES_ARTICLE, lignes_article)
    fichiers['clotures.csv'] = _ecrire_csv(COLONNES_CLOTURES, clotures)
    fichiers['corrections.csv'] = _ecrire_csv(COLONNES_CORRECTIONS, corrections)
    fichiers['impressions.csv'] = _ecrire_csv(COLONNES_IMPRESSIONS, impressions)
    fichiers['sorties_caisse.csv'] = _ecrire_csv(COLONNES_SORTIES_CAISSE, sorties_caisse)
    fichiers['historique_fond.csv'] = _ecrire_csv(COLONNES_HISTORIQUE_FOND, historique_fond)

    # Donnees JSON completes / Full JSON data
    donnees = {
        'lignes_article': lignes_article,
        'clotures': clotures,
        'corrections': corrections,
        'impressions': impressions,
        'sorties_caisse': sorties_caisse,
        'historique_fond': historique_fond,
    }
    fichiers['donnees.json'] = json.dumps(donnees, ensure_ascii=False, indent=2).encode('utf-8')

    # Compteurs pour meta.json / Counters for meta.json
    compteurs = {
        'lignes_article': len(lignes_article),
        'clotures': len(clotures),
        'corrections': len(corrections),
        'impressions': len(impressions),
        'sorties_caisse': len(sorties_caisse),
        'historique_fond': len(historique_fond),
    }

    meta = _construire_meta(schema, debut, fin, compteurs)
    fichiers['meta.json'] = json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8')

    return fichiers


# =====================================================================
# Hash et verification / Hash and verification
# =====================================================================

def calculer_hash_fichiers(fichiers, cle_secrete):
    """
    Calcule le HMAC-SHA256 de chaque fichier + un hash global.
    Retourne un dict pret a etre serialise en hash.json.
    / Computes HMAC-SHA256 of each file + a global hash.
    Returns a dict ready to be serialized as hash.json.
    """
    hash_par_fichier = {}
    for nom_fichier in sorted(fichiers.keys()):
        contenu = fichiers[nom_fichier]
        hash_par_fichier[nom_fichier] = _calculer_hmac_fichier(contenu, cle_secrete)

    # Hash global = HMAC de la concatenation triee des hash par fichier
    # / Global hash = HMAC of sorted concatenation of per-file hashes
    concatenation = ''.join(
        hash_par_fichier[nom] for nom in sorted(hash_par_fichier.keys())
    )
    hash_global = hmac.new(
        cle_secrete.encode('utf-8'),
        concatenation.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return {
        'fichiers': hash_par_fichier,
        'hash_global': hash_global,
        'algorithme': 'HMAC-SHA256',
    }


def empaqueter_zip(fichiers, hash_json_dict):
    """
    Cree un ZIP en memoire contenant tous les fichiers + hash.json.
    Retourne des bytes (le contenu du ZIP).
    / Creates an in-memory ZIP containing all files + hash.json.
    Returns bytes (the ZIP content).
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Ecrire chaque fichier dans le ZIP / Write each file to ZIP
        for nom_fichier, contenu in sorted(fichiers.items()):
            zf.writestr(nom_fichier, contenu)

        # Ajouter hash.json / Add hash.json
        hash_json_bytes = json.dumps(hash_json_dict, ensure_ascii=False, indent=2).encode('utf-8')
        zf.writestr('hash.json', hash_json_bytes)

    return buffer.getvalue()


def verifier_hash_archive(zip_bytes, cle_secrete):
    """
    Verifie l'integrite d'une archive ZIP en recalculant les HMAC.
    Retourne (bool, list[dict]) : (tout_ok, details_par_fichier).
    Chaque detail contient : nom, hash_attendu, hash_calcule, valide.
    / Verifies a ZIP archive integrity by recalculating HMACs.
    Returns (bool, list[dict]): (all_ok, per_file_details).
    Each detail contains: nom, hash_attendu, hash_calcule, valide.
    """
    buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buffer, 'r') as zf:
        # Lire hash.json / Read hash.json
        hash_json_bytes = zf.read('hash.json')
        hash_json_dict = json.loads(hash_json_bytes.decode('utf-8'))

        hash_par_fichier = hash_json_dict.get('fichiers', {})
        hash_global_attendu = hash_json_dict.get('hash_global', '')

        details = []
        tout_ok = True

        # Verifier chaque fichier / Verify each file
        for nom_fichier in sorted(hash_par_fichier.keys()):
            hash_attendu = hash_par_fichier[nom_fichier]
            try:
                contenu = zf.read(nom_fichier)
                hash_calcule = _calculer_hmac_fichier(contenu, cle_secrete)
            except KeyError:
                hash_calcule = ''

            valide = hmac.compare_digest(hash_attendu, hash_calcule)
            if not valide:
                tout_ok = False

            details.append({
                'nom': nom_fichier,
                'hash_attendu': hash_attendu,
                'hash_calcule': hash_calcule,
                'valide': valide,
            })

        # Verifier le hash global / Verify global hash
        concatenation = ''.join(
            hash_par_fichier[nom] for nom in sorted(hash_par_fichier.keys())
        )
        hash_global_calcule = hmac.new(
            cle_secrete.encode('utf-8'),
            concatenation.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        global_valide = hmac.compare_digest(hash_global_attendu, hash_global_calcule)
        if not global_valide:
            tout_ok = False

        details.append({
            'nom': 'hash_global',
            'hash_attendu': hash_global_attendu,
            'hash_calcule': hash_global_calcule,
            'valide': global_valide,
        })

    return tout_ok, details


# =====================================================================
# README fiscal / Fiscal README
# =====================================================================

def generer_readme_fiscal(schema):
    """
    Genere un fichier README.txt expliquant le contenu de l'archive fiscale.
    Retourne des bytes UTF-8.
    / Generates a README.txt explaining the fiscal archive content.
    Returns UTF-8 bytes.
    """
    from BaseBillet.models import Configuration

    config = Configuration.get_solo()
    texte = f"""ARCHIVE FISCALE — {config.organisation or schema}
{'=' * 60}

Date de generation : {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
Schema tenant : {schema}
Organisation : {config.organisation or ''}
SIREN : {config.siren or 'Non renseigne'}
N° TVA : {config.tva_number or 'Non renseigne'}

CONTENU DE L'ARCHIVE
---------------------
- lignes_article.csv : Toutes les lignes d'articles (ventes)
- clotures.csv : Rapports de cloture de caisse
- corrections.csv : Corrections de moyens de paiement
- impressions.csv : Journal des impressions de justificatifs
- sorties_caisse.csv : Retraits d'especes
- historique_fond.csv : Historique des changements de fond de caisse
- donnees.json : Ensemble des donnees au format JSON
- meta.json : Metadonnees de l'archive (organisation, periode, compteurs)
- hash.json : Empreintes HMAC-SHA256 de chaque fichier + hash global
- README.txt : Ce fichier

FORMAT CSV
----------
- Encodage : UTF-8 avec BOM
- Delimiteur : ; (point-virgule)
- Guillemets : tous les champs sont entre guillemets doubles
- Montants : en centimes (entiers). Ex: 50,10 EUR = 5010

VERIFICATION D'INTEGRITE
-------------------------
Chaque fichier est signe avec HMAC-SHA256.
La cle de signature est la cle HMAC du tenant (chiffree Fernet).
Pour verifier : recalculer le HMAC de chaque fichier et comparer avec hash.json.

CONFORMITE
----------
Ce format d'archivage respecte les exigences du referentiel LNE v1.7 :
- Exigence 3 : donnees elementaires (HT, TTC, TVA stockes)
- Exigence 6 : clotures numerotees sans trous
- Exigence 7 : total perpetuel
- Exigence 8 : chainage HMAC-SHA256
- Exigence 9 : tracabilite des impressions
- Exigence 10 : archivage periodique
"""
    return texte.encode('utf-8')


# =====================================================================
# Journal des operations / Operations log
# =====================================================================

def creer_entree_journal(type_operation, details, cle_secrete, operateur=None):
    """
    Cree une entree dans le journal des operations techniques (JournalOperation).
    L'entree est chainee HMAC avec la precedente.
    / Creates an entry in the technical operations log (JournalOperation).
    The entry is HMAC-chained with the previous one.

    :param type_operation: str — type d'operation (ARCHIVAGE, VERIFICATION, EXPORT_FISCAL)
    :param details: dict — details de l'operation
    :param cle_secrete: str — cle HMAC en clair
    :param operateur: TibilletUser ou None
    :return: JournalOperation instance
    """
    from laboutik.models import JournalOperation

    # Section atomique pour empecher les acces concurrents de casser le chainage HMAC.
    # select_for_update() verrouille la derniere entree pendant le create + update.
    # / Atomic section to prevent concurrent access from breaking the HMAC chain.
    # select_for_update() locks the last entry during create + update.
    with transaction.atomic():
        # Recuperer le HMAC de la derniere entree pour le chainage
        # / Get the HMAC of the last entry for chaining
        derniere_entree = (
            JournalOperation.objects
            .select_for_update()
            .order_by('-datetime', '-pk')
            .first()
        )
        previous_hmac = ''
        if derniere_entree and derniere_entree.hmac_hash:
            previous_hmac = derniere_entree.hmac_hash

        # Creer l'entree / Create the entry
        entree = JournalOperation.objects.create(
            type_operation=type_operation,
            details=details,
            operateur=operateur,
        )

        # Calculer le HMAC : json.dumps([type, datetime_iso, sorted_details_json, previous_hmac])
        # / Compute HMAC: json.dumps([type, datetime_iso, sorted_details_json, previous_hmac])
        details_json_trie = json.dumps(details, sort_keys=True, ensure_ascii=False)
        donnees = json.dumps([
            type_operation,
            entree.datetime.isoformat() if entree.datetime else '',
            details_json_trie,
            previous_hmac,
        ])
        hmac_hash = hmac.new(
            cle_secrete.encode('utf-8'),
            donnees.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        # Sauvegarder le hash / Save the hash
        entree.hmac_hash = hmac_hash
        entree.save(update_fields=['hmac_hash'])

    return entree

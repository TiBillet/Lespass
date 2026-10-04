"""
Module central d'archivage fiscal d'un lieu : toutes ses ventes reglees, de toutes
les origines (caisse, tireuse, en ligne, admin, API...), pas seulement la caisse.
Exporte en CSV (UTF-8 BOM, delimiteur ;) + JSON + hash HMAC :
- les ventes reglees, leurs articles et leurs reglements, avec les montants STOCKES
  et l'empreinte chainee de chaque vente ;
- les clotures `comptabilite.ClotureCaisse`, avec leur rapport complet ;
- le journal des impressions, les sorties de caisse et l'historique du fond.
Appele par 3 management commands (archiver_donnees, verifier_archive,
acces_fiscal) et la route d'export fiscal de la caisse (`laboutik/views.py`).
/ Central fiscal archiving module of a venue: every settled sale, every origin.
Exports CSV + JSON + HMAC hash. Called by 3 management commands and the export route.

LOCALISATION : laboutik/archivage.py
"""
import csv
import hmac
import hashlib
import io
import json
import zipfile
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone


# =====================================================================
# Colonnes CSV par modele / CSV columns per model
# =====================================================================

# Les ventes réglées : l'en-tête de chaque vente, ses totaux et son empreinte.
# Les montants sont des entiers en centimes, tels qu'ils sont stockés.
# / Settled sales: header, totals and fingerprint. Amounts are stored integer cents.
COLONNES_VENTES = [
    'uuid', 'numero', 'nature', 'statut', 'origine', 'unite',
    'datetime_encaissement', 'point_de_vente', 'point_de_vente_uuid',
    'operateur_email', 'vente_liee_uuid', 'total_catalogue', 'total_offert',
    'total_ttc', 'total_ht', 'total_tva', 'previous_hmac', 'hmac_hash',
]

# Les articles des ventes réglées, avec le HT et la TVA STOCKÉS sur l'article.
# `uuid_transaction` relie un ticket imprimé (`impressions.csv`) à son article ;
# `pricesold_uuid` est dans l'empreinte de la vente.
# / The settled sales' items, with the HT and VAT STORED on the item.
COLONNES_ARTICLES = [
    'uuid', 'vente_uuid', 'vente_numero', 'datetime', 'article', 'categorie',
    'pricesold_uuid', 'uuid_transaction', 'quantite', 'prix_unitaire', 'taux_tva',
    'total_catalogue', 'part_offerte', 'source_offert', 'total_ttc', 'total_ht',
    'total_tva', 'hors_chiffre_affaires',
]

# Les règlements des ventes réglées. Une correction de moyen de paiement est une
# vente CORRECTION : ses deux règlements (ancien moyen en négatif, nouveau moyen en
# positif) sont ici.
# / The settled sales' payments. A payment correction is a CORRECTION sale.
COLONNES_REGLEMENTS = [
    'uuid', 'vente_uuid', 'vente_numero', 'moyen', 'montant', 'asset', 'carte',
    'fedow_transaction_uuid', 'reference_externe', 'datetime',
]

# Les clôtures du lieu (`comptabilite.ClotureCaisse`), tous niveaux, chaînées.
# `rapport_json` : le rapport complet de la clôture (ventilations par moyen, par
# taux...), en JSON canonique (clés triées, sans espace, accents gardés), comme dans
# le message de l'empreinte de la clôture (`comptabilite/integrite.py`).
# / The venue's closures, every level, chained, with their full report as
# canonical JSON.
COLONNES_CLOTURES = [
    'uuid', 'niveau', 'numero_sequentiel', 'datetime_debut', 'datetime_fin',
    'numero_premiere_vente', 'numero_derniere_vente',
    'empreinte_de_la_derniere_vente', 'total_general',
    'total_ht', 'total_tva', 'total_argent_recu', 'nombre_transactions',
    'total_perpetuel', 'nombre_ventes_perpetuel', 'responsable_email',
    'point_de_vente', 'rapport_json', 'previous_hmac', 'hmac_hash',
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

def _texte_ou_vide(valeur):
    """
    La valeur en texte pour le CSV, ou "" si elle est vide (None).
    / The value as text for the CSV, or "" when it is None.
    """
    if valeur is None:
        return ''
    return str(valeur)


def _ventes_reglees_de_la_periode(debut, fin):
    """
    Les ventes RÉGLÉES du lieu encaissées dans [debut, fin[, par numéro croissant.
    La fin est EXCLUSIVE : une vente encaissée pile à la fin appartient à la
    période suivante. Toutes les origines : caisse, tireuse, en ligne, admin, API…
    Une vente en attente ou annulée n'a ni numéro ni empreinte : elle n'est pas un
    enregistrement fiscal, elle n'est pas archivée.
    / The venue's SETTLED sales collected in [debut, fin[, by number. The end is
    EXCLUSIVE. Every origin. Pending or cancelled sales are not archived.

    :param debut: datetime aware ou None (None = pas de borne)
    :param fin: datetime aware ou None (None = pas de borne), exclusive
    :return: QuerySet de `Vente`
    """
    from BaseBillet.models_vente import Vente

    ventes_reglees = Vente.objects.filter(statut=Vente.Statut.REGLEE)
    if debut is not None:
        ventes_reglees = ventes_reglees.filter(datetime_encaissement__gte=debut)
    if fin is not None:
        ventes_reglees = ventes_reglees.filter(datetime_encaissement__lt=fin)
    return ventes_reglees.order_by('numero')


def _extraire_ventes(debut, fin):
    """
    Extrait l'en-tête des ventes réglées de la période : numéro, nature, origine,
    totaux stockés, et l'empreinte chaînée (`previous_hmac`, `hmac_hash`).
    Retourne une liste de dicts avec des valeurs texte pour le CSV.
    / Extracts the settled sales' headers: number, nature, origin, stored totals and
    chained fingerprint. Returns a list of dicts with text values for the CSV.
    """
    ventes_reglees = _ventes_reglees_de_la_periode(debut, fin).select_related(
        'point_de_vente',
        'operateur',
    )

    resultats = []
    for vente in ventes_reglees.iterator():
        nom_du_point_de_vente = ''
        if vente.point_de_vente:
            nom_du_point_de_vente = vente.point_de_vente.name

        email_de_l_operateur = ''
        if vente.operateur:
            email_de_l_operateur = vente.operateur.email or ''

        resultats.append({
            'uuid': str(vente.uuid),
            'numero': _texte_ou_vide(vente.numero),
            'nature': vente.nature,
            'statut': vente.statut,
            'origine': vente.origine,
            'unite': vente.unite,
            'datetime_encaissement': vente.datetime_encaissement.isoformat(),
            'point_de_vente': nom_du_point_de_vente,
            'point_de_vente_uuid': _texte_ou_vide(vente.point_de_vente_id),
            'operateur_email': email_de_l_operateur,
            'vente_liee_uuid': _texte_ou_vide(vente.vente_liee_id),
            'total_catalogue': str(vente.total_catalogue),
            'total_offert': str(vente.total_offert),
            'total_ttc': str(vente.total_ttc),
            'total_ht': str(vente.total_ht),
            'total_tva': str(vente.total_tva),
            'previous_hmac': vente.previous_hmac,
            'hmac_hash': vente.hmac_hash,
        })

    return resultats


def _extraire_articles(identifiants_des_ventes):
    """
    Extrait les articles des ventes extraites (`_extraire_ventes`), avec leurs
    montants entiers STOCKÉS : total catalogue, part offerte, net vendu (TTC), HT et
    TVA. Rien n'est recalculé : ce sont les montants scellés dans l'empreinte de la
    vente. Les articles sont lus par la LISTE des ventes déjà extraites : une vente
    encaissée pendant la génération n'a pas ses articles sans son en-tête.
    / Extracts the extracted sales' items with their STORED whole-cent amounts, read
    from the list of already extracted sales.

    :param identifiants_des_ventes: liste des uuid (texte) des ventes extraites
    """
    from BaseBillet.models import LigneArticle

    articles = LigneArticle.objects.filter(
        vente_id__in=identifiants_des_ventes,
    ).select_related(
        'vente',
        'pricesold__productsold__product__categorie_pos',
    ).order_by('vente__numero', 'uuid')

    resultats = []
    for article in articles.iterator():
        # Nom et catégorie du produit vendu.
        # / Name and category of the sold product.
        nom_de_l_article = ''
        nom_de_la_categorie = ''
        produit = article.pricesold.productsold.product
        if produit is not None:
            nom_de_l_article = produit.name
            if produit.categorie_pos is not None:
                nom_de_la_categorie = produit.categorie_pos.name

        resultats.append({
            'uuid': str(article.uuid),
            'vente_uuid': str(article.vente_id),
            'vente_numero': _texte_ou_vide(article.vente.numero),
            'datetime': article.datetime.isoformat() if article.datetime else '',
            'article': nom_de_l_article,
            'categorie': nom_de_la_categorie,
            'pricesold_uuid': str(article.pricesold_id),
            'uuid_transaction': _texte_ou_vide(article.uuid_transaction),
            'quantite': str(article.qty),
            'prix_unitaire': str(article.amount),
            'taux_tva': f"{article.vat:.2f}",
            'total_catalogue': str(article.total_catalogue),
            'part_offerte': str(article.part_offerte),
            'source_offert': article.source_offert or '',
            'total_ttc': str(article.total_ttc),
            'total_ht': str(article.total_ht),
            'total_tva': str(article.total_tva),
            'hors_chiffre_affaires': str(article.hors_chiffre_affaires),
        })

    return resultats


def _extraire_reglements(identifiants_des_ventes):
    """
    Extrait les règlements des ventes extraites (`_extraire_ventes`) : moyen et
    montant signé, en centimes. Une correction de moyen de paiement est une vente
    CORRECTION à deux règlements qui s'annulent : elle est ici, sans fichier à part.
    / Extracts the extracted sales' payments (method, signed amount). A payment
    correction is a CORRECTION sale with two payments that cancel out.

    :param identifiants_des_ventes: liste des uuid (texte) des ventes extraites
    """
    from BaseBillet.models_vente import Reglement

    reglements = Reglement.objects.filter(
        vente_id__in=identifiants_des_ventes,
    ).select_related('vente').order_by('vente__numero', 'uuid')

    resultats = []
    for reglement in reglements.iterator():
        resultats.append({
            'uuid': str(reglement.uuid),
            'vente_uuid': str(reglement.vente_id),
            'vente_numero': _texte_ou_vide(reglement.vente.numero),
            'moyen': reglement.moyen,
            'montant': str(reglement.montant),
            'asset': _texte_ou_vide(reglement.asset),
            'carte': _texte_ou_vide(reglement.carte_id),
            'fedow_transaction_uuid': _texte_ou_vide(reglement.fedow_transaction_uuid),
            'reference_externe': reglement.reference_externe or '',
            'datetime': reglement.datetime.isoformat() if reglement.datetime else '',
        })

    return resultats


def _extraire_clotures(debut, fin):
    """
    Extrait les clôtures du lieu (`comptabilite.ClotureCaisse`, tous niveaux) dont
    la fin tombe dans ]debut, fin], par numéro croissant, avec leur empreinte
    chaînée. La fin d'une clôture est exclusive pour ses ventes : une M de décembre
    finit le 1er janvier à 00:00. Elle va donc dans l'archive qui finit à cet
    instant, et pas dans celle qui en commence.
    / Extracts the venue's closures (every level) ending in ]debut, fin], by
    number. A closure's end is exclusive for its sales: a December M ends on
    January 1st at 00:00, so it belongs to the archive ending at that instant.

    Chaque clôture porte aussi l'empreinte de sa dernière vente couverte
    (`empreinte_de_la_derniere_vente`), relue en base comme le fait
    `calculer_hmac_cloture` : avec elle, l'empreinte de la clôture se recalcule
    depuis les seuls fichiers de l'archive et la clé.
    / Each closure also carries its last covered sale's fingerprint, read back
    like `calculer_hmac_cloture` does: the closure's fingerprint can be recomputed
    from the archive files and the key alone.
    """
    from BaseBillet.models_vente import Vente
    from comptabilite.models import ClotureCaisse

    clotures = ClotureCaisse.objects.select_related(
        'point_de_vente',
        'responsable',
    ).order_by('numero_sequentiel')

    if debut is not None:
        clotures = clotures.filter(datetime_fin__gte=debut)
    if fin is not None:
        clotures = clotures.filter(datetime_fin__lte=fin)

    # Les empreintes des dernières ventes couvertes, en une seule requête.
    # / The last covered sales' fingerprints, in a single query.
    numeros_lus_sur_les_clotures = clotures.values_list(
        'numero_derniere_vente', flat=True
    )
    numeros_des_dernieres_ventes = []
    for numero_de_la_derniere_vente in numeros_lus_sur_les_clotures:
        if numero_de_la_derniere_vente is not None:
            numeros_des_dernieres_ventes.append(numero_de_la_derniere_vente)
    empreinte_par_numero_de_vente = {}
    ventes_couvertes = Vente.objects.filter(
        numero__in=numeros_des_dernieres_ventes
    ).values_list('numero', 'hmac_hash')
    for numero_de_la_vente, empreinte_de_la_vente in ventes_couvertes:
        empreinte_par_numero_de_vente[numero_de_la_vente] = empreinte_de_la_vente

    resultats = []
    for cloture in clotures.iterator():
        empreinte_de_la_derniere_vente = ''
        if cloture.numero_derniere_vente is not None:
            empreinte_de_la_derniere_vente = empreinte_par_numero_de_vente.get(
                cloture.numero_derniere_vente, ''
            )

        nom_du_point_de_vente = ''
        if cloture.point_de_vente:
            nom_du_point_de_vente = cloture.point_de_vente.name

        email_du_responsable = ''
        if cloture.responsable:
            email_du_responsable = cloture.responsable.email or ''

        resultats.append({
            'uuid': str(cloture.uuid),
            'niveau': cloture.niveau,
            'numero_sequentiel': str(cloture.numero_sequentiel),
            'datetime_debut': cloture.datetime_debut.isoformat(),
            'datetime_fin': cloture.datetime_fin.isoformat(),
            'numero_premiere_vente': _texte_ou_vide(cloture.numero_premiere_vente),
            'numero_derniere_vente': _texte_ou_vide(cloture.numero_derniere_vente),
            'empreinte_de_la_derniere_vente': empreinte_de_la_derniere_vente,
            'total_general': str(cloture.total_general),
            'total_ht': str(cloture.total_ht),
            'total_tva': str(cloture.total_tva),
            'total_argent_recu': str(cloture.total_argent_recu),
            'nombre_transactions': str(cloture.nombre_transactions),
            'total_perpetuel': str(cloture.total_perpetuel),
            'nombre_ventes_perpetuel': str(cloture.nombre_ventes_perpetuel),
            'responsable_email': email_du_responsable,
            'point_de_vente': nom_du_point_de_vente,
            # L'objet entier : `donnees.json` le garde tel quel, `clotures.csv`
            # l'écrit en JSON canonique (`_lignes_csv_des_clotures`).
            # / The whole object: kept as is in donnees.json, canonical JSON in CSV.
            'rapport_json': cloture.rapport_json,
            'previous_hmac': cloture.previous_hmac,
            'hmac_hash': cloture.hmac_hash,
        })

    return resultats


def _lignes_csv_des_clotures(clotures):
    """
    Les lignes du CSV des clôtures : comme les clôtures extraites, avec le rapport
    écrit en JSON canonique (clés triées, sans espace, accents gardés) pour tenir
    dans une cellule.
    / The closures CSV rows: the report written as canonical JSON in one cell.

    :param clotures: liste de dicts de `_extraire_clotures`
    :return: liste de dicts pour `_ecrire_csv`
    """
    lignes_csv = []
    for cloture in clotures:
        ligne_csv = dict(cloture)
        ligne_csv['rapport_json'] = json.dumps(
            cloture['rapport_json'],
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
        lignes_csv.append(ligne_csv)
    return lignes_csv


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
    Retourne un dict {nom_fichier: bytes}.
    / Generates all files for a fiscal archive for a tenant.
    Returns dict {filename: bytes}.

    LES BORNES :
    - une date (`date`) est lue dans le FUSEAU DU LIEU (`Configuration.fuseau_horaire`) :
      le debut est le jour de `debut` a 00:00, la fin est le LENDEMAIN de `fin` a
      00:00, heure du lieu, et elle est EXCLUSIVE ;
    - sans `fin`, la fin est figee a maintenant, au debut de la generation : tous les
      fichiers s'arretent au meme instant ;
    - une vente est dans l'archive si son ENCAISSEMENT tombe dans [debut, fin[ ;
    - une cloture est dans l'archive si sa FIN tombe dans ]debut, fin] : une J a
      cheval sur deux periodes va dans l'archive de sa fin ; la M de decembre et l'A
      de l'annee, qui finissent le 1er janvier a 00:00, vont dans l'archive de
      l'annee, pas dans celle de l'annee suivante ;
    - les articles et les reglements sont lus par la liste des ventes extraites.
    / Dates are read in the venue's time zone: start at 00:00 of `debut`, end at
    00:00 of the day after `fin`, exclusive. Without an end, the end is frozen to
    now. Sales by settlement time in [debut, fin[, closures by their end in
    ]debut, fin].
    """
    from datetime import date as date_type

    from BaseBillet.models import Configuration

    # Convertir une date en datetime aware, dans le fuseau du lieu. La fin devient
    # le lendemain a 00:00 : c'est une borne exclusive, comme celle des clotures.
    # / Convert a date into an aware datetime, in the venue's time zone. The end
    # becomes the next day at 00:00: an exclusive bound, like the closures' one.
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    if debut is not None and isinstance(debut, date_type) and not isinstance(debut, datetime):
        debut = timezone.make_aware(datetime.combine(debut, time.min), fuseau_du_lieu)
    if fin is not None and isinstance(fin, date_type) and not isinstance(fin, datetime):
        lendemain_de_la_fin = fin + timedelta(days=1)
        fin = timezone.make_aware(
            datetime.combine(lendemain_de_la_fin, time.min), fuseau_du_lieu
        )
    if fin is None:
        fin = timezone.now()

    # Extraction de toutes les donnees. Les articles et les reglements sont lus par
    # la liste des ventes extraites, jamais par une deuxieme lecture des bornes.
    # / Extract all data; items and payments from the list of extracted sales.
    ventes = _extraire_ventes(debut, fin)
    identifiants_des_ventes = []
    for vente in ventes:
        identifiants_des_ventes.append(vente['uuid'])
    articles = _extraire_articles(identifiants_des_ventes)
    reglements = _extraire_reglements(identifiants_des_ventes)
    clotures = _extraire_clotures(debut, fin)
    impressions = _extraire_impressions(debut, fin)
    sorties_caisse = _extraire_sorties_caisse(debut, fin)
    historique_fond = _extraire_historique_fond(debut, fin)

    # Generation des CSV / Generate CSVs
    fichiers = {}
    fichiers['ventes.csv'] = _ecrire_csv(COLONNES_VENTES, ventes)
    fichiers['articles.csv'] = _ecrire_csv(COLONNES_ARTICLES, articles)
    fichiers['reglements.csv'] = _ecrire_csv(COLONNES_REGLEMENTS, reglements)
    fichiers['clotures.csv'] = _ecrire_csv(
        COLONNES_CLOTURES, _lignes_csv_des_clotures(clotures)
    )
    fichiers['impressions.csv'] = _ecrire_csv(COLONNES_IMPRESSIONS, impressions)
    fichiers['sorties_caisse.csv'] = _ecrire_csv(COLONNES_SORTIES_CAISSE, sorties_caisse)
    fichiers['historique_fond.csv'] = _ecrire_csv(COLONNES_HISTORIQUE_FOND, historique_fond)

    # Donnees JSON completes / Full JSON data
    donnees = {
        'ventes': ventes,
        'articles': articles,
        'reglements': reglements,
        'clotures': clotures,
        'impressions': impressions,
        'sorties_caisse': sorties_caisse,
        'historique_fond': historique_fond,
    }
    fichiers['donnees.json'] = json.dumps(donnees, ensure_ascii=False, indent=2).encode('utf-8')

    # Compteurs pour meta.json / Counters for meta.json
    compteurs = {
        'ventes': len(ventes),
        'articles': len(articles),
        'reglements': len(reglements),
        'clotures': len(clotures),
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
- ventes.csv : Les ventes REGLEES seulement (une vente en attente ou annulee
  n'a ni numero ni empreinte), de toutes les origines (caisse, tireuse,
  en ligne, admin, API) : numero, nature, origine, totaux, empreinte chainee
- articles.csv : Les articles de chaque vente, avec le HT et la TVA stockes
- reglements.csv : Les reglements de chaque vente (moyen, montant signe)
- clotures.csv : Les clotures (journalieres, hebdomadaires, mensuelles,
  annuelles), numerotees et chainees, avec leur rapport complet (colonne
  rapport_json, JSON canonique)
- impressions.csv : Journal des impressions de justificatifs
- sorties_caisse.csv : Retraits d'especes
- historique_fond.csv : Historique des changements de fond de caisse
- donnees.json : Ensemble des donnees au format JSON
- meta.json : Metadonnees de l'archive (organisation, periode, compteurs)
- hash.json : Empreintes HMAC-SHA256 de chaque fichier ci-dessus + hash global
- README.txt : Ce fichier. Il n'est PAS signe (absent de hash.json) : il
  explique l'archive, il n'en fait pas partie.

FORMAT CSV
----------
- Encodage : UTF-8 avec BOM
- Delimiteur : ; (point-virgule)
- Guillemets : tous les champs sont entre guillemets doubles
- Montants : en centimes (entiers). Ex: 50,10 EUR = 5010
- Dates : ISO 8601 avec le decalage horaire

LES BORNES DE LA PERIODE
------------------------
Les dates de debut et de fin sont lues dans le fuseau horaire du lieu.
La periode commence le jour de debut a 00:00. Elle finit le LENDEMAIN du
jour de fin a 00:00, et cette fin est EXCLUSIVE (c'est la fin ecrite dans
meta.json). Sans date de fin, l'archive s'arrete au moment de sa generation.
Une vente est dans l'archive si son heure d'ENCAISSEMENT est au debut ou
apres, et strictement avant la fin. Une cloture est dans l'archive si sa
FIN est strictement apres le debut, et au plus a la fin : une cloture a
cheval sur deux periodes va dans l'archive de la periode ou elle finit.
La fin d'une cloture est elle aussi exclusive pour ses ventes : la
cloture mensuelle de decembre et la cloture annuelle finissent le 1er
janvier a 00:00, et vont dans l'archive de l'annee qu'elles couvrent.

LES ARTICLES EN PARTS
---------------------
Un article paye avec deux moyens peut etre ecrit en deux lignes (deux
parts) : meme prix unitaire, quantites fractionnaires (ex. 1,428571 et
1,571429), chacune avec ses montants reels. La somme des parts donne
l'article ; la somme des articles donne les totaux de la vente.

CORRECTIONS
-----------
Une vente reglee ne se modifie jamais. Une correction de moyen de paiement
est une nouvelle vente de nature CORRECTION, liee a la vente d'origine
(vente_liee_uuid), avec deux reglements qui s'annulent, sur deux moyens.
Le sens ne se lit pas au signe : la paire de moyens dit d'ou part l'argent
(le moyen de la vente liee, apres ses corrections precedentes, par numero
croissant) et ou il arrive (l'autre moyen de la paire). La caisse ecrit
l'ancien moyen en negatif et le nouveau en positif ; une correction d'un
avoir (montants de signes inverses) se lit de la meme facon.
Un remboursement est une vente AVOIR.

VERIFICATION D'INTEGRITE
-------------------------
Chaque fichier liste dans hash.json est signe avec HMAC-SHA256.
La cle de signature est la cle HMAC du tenant (chiffree Fernet).
Pour verifier : recalculer le HMAC de chaque fichier et comparer avec hash.json.

Chaque vente porte aussi son empreinte (hmac_hash), chainee avec celle de la
vente precedente (previous_hmac). Elle se recalcule avec la cle du lieu,
sur ce message : un JSON canonique (cles triees, separateurs "," et ":",
sans espace, accents gardes) de l'objet
  format = 1
  uuid, numero, nature, origine, unite, statut (ventes.csv)
  datetime_encaissement : ISO 8601 en UTC
  point_de_vente : point_de_vente_uuid ("" sans point de vente)
  vente_liee : vente_liee_uuid ("" sans vente liee)
  totaux = [total_catalogue, total_offert, total_ttc, total_ht, total_tva]
  articles = liste, triee par uuid, de
    [uuid, pricesold_uuid, quantite avec 6 decimales, prix_unitaire,
     taux_tva avec 2 decimales, total_catalogue, part_offerte,
     source_offert, total_ttc, total_ht, total_tva, hors_chiffre_affaires
     (vrai/faux JSON)]
  reglements = liste, triee par uuid, de
    [uuid, moyen, montant, asset, carte, fedow_transaction_uuid,
     reference_externe] (un champ vide s'ecrit "")
  previous_hmac
Les nombres (numero, montants) sont des entiers JSON.

Chaque cloture porte de meme son empreinte (hmac_hash), chainee avec la
cloture precedente (previous_hmac), tous niveaux confondus, dans l'ordre
de numero_sequentiel. Elle se recalcule avec la meme cle, sur le meme
JSON canonique, de l'objet (colonnes de clotures.csv)
  format = 1
  niveau, numero_sequentiel
  datetime_debut, datetime_fin : ISO 8601 en UTC
  numero_premiere_vente, numero_derniere_vente (null si vide)
  empreinte_de_la_derniere_vente ("" sans vente)
  totaux = {{total_general, total_ht, total_tva, total_argent_recu,
            nombre_transactions}}
  perpetuels = {{total_perpetuel, nombre_ventes_perpetuel}}
  rapport_json : l'objet JSON de la colonne rapport_json
  previous_hmac
Les nombres (numeros, totaux, perpetuels) sont des entiers JSON. Le point
de vente et le responsable ne sont pas dans le message.

CONFORMITE
----------
Ce format d'archivage respecte les exigences du referentiel LNE v1.7 :
- Exigence 3 : donnees elementaires (HT, TTC, TVA stockes)
- Exigence 6 : clotures numerotees sans trous
- Exigence 7 : total perpetuel
- Exigence 8 : chainage HMAC-SHA256 des ventes et des clotures
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

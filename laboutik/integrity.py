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

import datetime
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


def vente_couverte_par_cloture(vente):
    """
    Dit si une vente réglée est couverte par une clôture journalière (J) du lieu.
    / Tells whether a settled sale is covered by a daily closure (J) of the venue.

    LOCALISATION : laboutik/integrity.py

    Une vente est couverte quand son numéro est inférieur ou égal au PLUS GRAND
    numéro de dernière vente de toutes les J du lieu (`comptabilite.ClotureCaisse`,
    `numero_derniere_vente`). Le plus grand numéro ne dépend ni de l'ordre des J, ni
    d'une J sans plage (son numéro vide est ignoré).
    / A sale is covered when its number is ≤ the HIGHEST last-sale number of all the
    venue's J. Independent of J order; a J without range is ignored.

    La règle porte sur les J seulement. Une semaine, un mois ou une année recouvre
    des ventes que leurs J couvrent déjà. Conséquence : une M lancée à la main avant
    la J de son dernier jour ne protège pas les ventes de ce jour ; c'est la J qui
    les protège, à sa création.
    / J only: a manual M created before the J of its last day does not protect that
    day's sales; the J does.

    Une vente sans numéro (pas encore réglée) n'est jamais couverte : c'est à
    l'appelant de la refuser (seule une vente réglée se corrige).
    / A sale without a number is never covered: the caller refuses it.

    FLUX : appelée par `laboutik/views.py` — `raison_du_refus_de_correction`
    (route de correction et écran du détail d'une vente).
    / Called by raison_du_refus_de_correction (correction route and detail screen).

    :param vente: la `Vente` dont on veut savoir si elle est figée par une J
    :return: True si une J couvre la vente, False sinon
    """
    # Import local, comme dans tout ce module : `laboutik.integrity` se charge sans
    # charger les modèles des autres applications.
    # / Local import, as in this whole module.
    from django.db.models import Max

    from comptabilite.models import ClotureCaisse

    if vente.numero is None:
        return False

    numero_de_la_derniere_vente_couverte = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER
    ).aggregate(plus_grand_numero=Max("numero_derniere_vente"))["plus_grand_numero"]

    # Aucune J (ou aucune J avec une plage) : rien n'est couvert.
    # / No J (or no J with a range): nothing is covered.
    if numero_de_la_derniere_vente_couverte is None:
        return False

    vente_dans_une_plage_de_j = vente.numero <= numero_de_la_derniere_vente_couverte
    return vente_dans_une_plage_de_j


def calculer_hmac_vente(vente, cle, previous_hmac):
    """
    Calcule l'empreinte HMAC-SHA256 d'une vente, chaînée avec la vente précédente.
    / Computes the chained HMAC-SHA256 fingerprint of a sale.

    LOCALISATION : laboutik/integrity.py

    Le message couvre la vente, ses articles et ses règlements. C'est un JSON
    canonique : clés triées, sans espace, accents gardés. Les articles et les
    règlements sont triés par uuid, les dates sont écrites en UTC. Le numéro de format
    (1) permet de changer un jour le message sans casser les anciennes empreintes.
    / The message covers the sale, its items and its payments, as canonical JSON.

    Articles et règlements sont RELUS EN BASE : l'empreinte porte sur ce qui est
    écrit, pas sur des objets gardés en mémoire. Les champs de la vente, eux, sont lus
    sur l'objet reçu : `encaisser_vente` les pose juste avant l'enregistrement.
    / Items and payments are read from the database; sale fields come from the object.

    FLUX :
    - `BaseBillet/services_vente.py` `encaisser_vente` l'appelle sous le verrou du lieu,
      avec l'empreinte de la vente numéro − 1 ;
    - `verifier_chaine_ventes` (ci-dessous) la recalcule pour chaque vente réglée.

    Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md §5.

    :param vente: la `Vente` (numéro, heure d'encaissement, totaux et statut posés)
    :param cle: str — la clé HMAC du lieu, en clair
    :param previous_hmac: str — l'empreinte de la vente précédente ("" pour la première)
    :return: str — empreinte HMAC-SHA256 de 64 caractères hexadécimaux
    """
    # Imports locaux, comme dans tout ce module : `laboutik.integrity` se charge sans
    # charger les modèles de BaseBillet. `BaseBillet/services_vente.py` importe ce
    # module à son propre chargement : ce module ne l'importe donc jamais en tête de
    # fichier (voir `verifier_chaine_ventes`).
    # / Local imports, as in this whole module: it loads without BaseBillet's models.
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Reglement

    # Les articles, triés par uuid. qty et vat sont écrits avec un nombre fixe de
    # décimales : le texte ne change pas entre la mémoire et la base (PIEGES 9.56).
    # / Items sorted by uuid. qty and vat get fixed decimals, stable across reads.
    articles_du_message = []
    articles_tries = LigneArticle.objects.filter(vente_id=vente.pk).order_by("uuid")
    for article in articles_tries:
        articles_du_message.append(
            [
                str(article.uuid),
                str(article.pricesold_id),
                f"{article.qty:.6f}",
                article.amount,
                f"{article.vat:.2f}",
                article.total_catalogue,
                article.part_offerte,
                article.source_offert,
                article.part_en_jetons,
                article.total_ttc,
                article.total_ht,
                article.total_tva,
                article.hors_chiffre_affaires,
            ]
        )

    # Les règlements, triés par uuid. Un champ vide s'écrit "".
    # / Payments sorted by uuid. An empty field is written "".
    reglements_du_message = []
    reglements_tries = Reglement.objects.filter(vente_id=vente.pk).order_by("uuid")
    for reglement in reglements_tries:
        reglements_du_message.append(
            [
                str(reglement.uuid),
                reglement.moyen,
                reglement.montant,
                str(reglement.asset or ""),
                str(reglement.carte_id or ""),
                str(reglement.fedow_transaction_uuid or ""),
                reglement.reference_externe,
            ]
        )

    heure_d_encaissement_en_utc = vente.datetime_encaissement.astimezone(
        datetime.timezone.utc
    )
    donnees = {
        "format": 1,
        "uuid": str(vente.uuid),
        "numero": vente.numero,
        "datetime_encaissement": heure_d_encaissement_en_utc.isoformat(),
        "nature": vente.nature,
        "origine": vente.origine,
        "unite": vente.unite,
        "statut": vente.statut,
        # Le point de vente décide du journal du FEC : il est dans l'empreinte.
        # / The point of sale decides the FEC journal: it is fingerprinted.
        "point_de_vente": str(vente.point_de_vente_id or ""),
        "vente_liee": str(vente.vente_liee_id or ""),
        "totaux": [
            vente.total_catalogue,
            vente.total_offert,
            vente.total_ttc,
            vente.total_ht,
            vente.total_tva,
        ],
        "articles": articles_du_message,
        "reglements": reglements_du_message,
        "previous_hmac": previous_hmac,
    }
    message = json.dumps(
        donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hmac.new(
        cle.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verifier_chaine_ventes(
    cle, numero_de_la_premiere_vente=None, numero_de_la_derniere_vente=None
):
    """
    Vérifie la chaîne des ventes réglées du lieu, et renvoie la liste des anomalies.
    / Checks the chain of settled sales of the venue, returns the list of anomalies.

    LOCALISATION : laboutik/integrity.py

    LA PLAGE (facultative) : sans les deux numéros, toute la chaîne du lieu est
    vérifiée. Avec eux, seules les ventes de la plage [première, dernière] le sont :
    un lieu qui a des années de ventes ne relit pas tout pour une journée. La première
    vente de la plage est alors reliée à l'empreinte STOCKÉE de la vente qui la précède
    (la dernière vente réglée de numéro inférieur ; "" s'il n'y en a pas) : une
    altération avant la plage n'est pas vue, mais un maillon cassé ou un trou de
    numéro à l'entrée de la plage l'est.
    / Optional range: without both numbers, the whole chain is checked. With them,
    only the sales of the range; the first one is linked to the STORED fingerprint of
    the sale before it.

    Les ventes REGLEE sont parcourues par numéro croissant. Pour chaque vente :
    1. trou de numéro : son numéro n'est pas le numéro de la vente d'avant + 1 ;
    2. maillon cassé : son `previous_hmac` n'est pas l'empreinte de la vente d'avant
       ("" pour la première) ;
    3. empreinte fausse : l'empreinte recalculée (avec son `previous_hmac`) n'est pas
       celle enregistrée — un article, un règlement ou la vente a été modifié ;
    4. égalité rompue : relues en base, les deux égalités de la vente ne tiennent plus
       (Σ règlements = Σ totaux catalogue ; Σ règlements hors offert = Σ nets vendus).
    Aucune exception n'est tolérée : une correction est une nouvelle vente, jamais une
    modification.
    / Walks settled sales by number: gap, broken link, wrong fingerprint, broken
    equality. No exception is tolerated.

    Une anomalie est un dictionnaire : "numero", "uuid" (texte) et "raison" (phrase en
    français). Une vente peut avoir plusieurs anomalies.
    / An anomaly is a dict: "numero", "uuid" (text), "raison" (French sentence).

    FLUX : appelée par la section « intégrité » du rapport des ventes
    (`comptabilite/rapport.py`) sur la plage de sa période, par `verify_clotures` (la
    plage de chaque J) et par `verify_integrity` (toute la chaîne).

    :param cle: str — la clé HMAC du lieu, en clair
    :param numero_de_la_premiere_vente: int ou None — début de la plage (inclus)
    :param numero_de_la_derniere_vente: int ou None — fin de la plage (incluse)
    :return: list — les anomalies ; vide si la chaîne est saine
    """
    # Imports locaux, comme dans tout ce module. Pour `services_vente`, c'est
    # obligatoire : il importe ce module à son chargement (`calculer_hmac_vente`).
    # Importés l'un l'autre en tête de fichier, chacun trouverait l'autre à moitié
    # chargé : ImportError (cycle d'import).
    # / Local imports. Required for services_vente: it imports this module at load
    # time, so a top-level import here would be an import cycle.
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Reglement, Vente
    from BaseBillet.services_vente import MOYENS_OFFERTS

    anomalies = []
    empreinte_de_la_vente_precedente = ""
    # Vide tant qu'aucune vente n'a été vue : la première vente n'a pas de précédente.
    # / Empty until a sale is seen: the first sale has no previous one.
    numero_precedent = None

    ventes_reglees = Vente.objects.filter(statut=Vente.Statut.REGLEE).order_by(
        "numero"
    )

    # Début de plage : la première vente est reliée à la vente qui la précède, lue
    # en base avec son empreinte stockée. C'est la DERNIÈRE vente réglée de numéro
    # inférieur au début de la plage, pas « numéro − 1 » : une vente supprimée juste
    # avant la plage sort alors en « trou de numéro », comme sur la chaîne entière.
    # Sans vente avant, la plage commence la chaîne : empreinte "" et aucun numéro
    # précédent.
    # / Range start: linked to the stored fingerprint of the last settled sale
    # numbered below the range (not "number − 1"); if none, the range starts the chain.
    if numero_de_la_premiere_vente is not None:
        ventes_reglees = ventes_reglees.filter(numero__gte=numero_de_la_premiere_vente)
        vente_avant_la_plage = (
            Vente.objects.filter(
                statut=Vente.Statut.REGLEE,
                numero__lt=numero_de_la_premiere_vente,
            )
            .order_by("-numero")
            .first()
        )
        if vente_avant_la_plage is not None:
            empreinte_de_la_vente_precedente = vente_avant_la_plage.hmac_hash
            numero_precedent = vente_avant_la_plage.numero

    # Fin de plage : les ventes d'après ne sont pas vérifiées.
    # / Range end: later sales are not checked.
    if numero_de_la_derniere_vente is not None:
        ventes_reglees = ventes_reglees.filter(numero__lte=numero_de_la_derniere_vente)

    for vente in ventes_reglees:
        # 1. Trou de numéro : le numéro ne suit pas celui de la vente d'avant.
        # / 1. Number gap: the number does not follow the previous sale's one.
        premiere_vente_de_la_chaine = numero_precedent is None
        if not premiere_vente_de_la_chaine and vente.numero != numero_precedent + 1:
            anomalies.append(
                {
                    "numero": vente.numero,
                    "uuid": str(vente.uuid),
                    "raison": (
                        f"Trou de numéro : la vente n° {vente.numero} suit la vente "
                        f"n° {numero_precedent}."
                    ),
                }
            )

        # 2. Maillon cassé : le lien vers la vente d'avant.
        # / 2. Broken link to the previous sale.
        if vente.previous_hmac != empreinte_de_la_vente_precedente:
            anomalies.append(
                {
                    "numero": vente.numero,
                    "uuid": str(vente.uuid),
                    "raison": (
                        f"Maillon cassé : l'empreinte précédente de la vente "
                        f"n° {vente.numero} n'est pas l'empreinte de la vente d'avant."
                    ),
                }
            )

        # 3. Empreinte fausse : la vente, ses articles ou ses règlements ont changé.
        # / 3. Wrong fingerprint: the sale, its items or its payments changed.
        empreinte_recalculee = calculer_hmac_vente(vente, cle, vente.previous_hmac)
        if empreinte_recalculee != vente.hmac_hash:
            anomalies.append(
                {
                    "numero": vente.numero,
                    "uuid": str(vente.uuid),
                    "raison": (
                        f"Empreinte fausse : la vente n° {vente.numero}, ses articles "
                        f"ou ses règlements ont été modifiés après l'encaissement."
                    ),
                }
            )

        # 4. Les deux égalités, relues en base.
        # / 4. The two equalities, read back from the database.
        articles_de_la_vente = LigneArticle.objects.filter(vente_id=vente.pk)
        somme_des_totaux_catalogue = 0
        somme_des_nets_vendus = 0
        for article in articles_de_la_vente:
            somme_des_totaux_catalogue += article.total_catalogue
            somme_des_nets_vendus += article.total_ttc

        reglements_de_la_vente = Reglement.objects.filter(vente_id=vente.pk)
        somme_de_tous_les_reglements = 0
        somme_des_reglements_hors_offert = 0
        for reglement in reglements_de_la_vente:
            somme_de_tous_les_reglements += reglement.montant
            reglement_offert = reglement.moyen in MOYENS_OFFERTS
            if not reglement_offert:
                somme_des_reglements_hors_offert += reglement.montant

        egalites_tenues = (
            somme_de_tous_les_reglements == somme_des_totaux_catalogue
            and somme_des_reglements_hors_offert == somme_des_nets_vendus
        )
        if not egalites_tenues:
            anomalies.append(
                {
                    "numero": vente.numero,
                    "uuid": str(vente.uuid),
                    "raison": (
                        f"Égalité rompue : vente n° {vente.numero}, règlements "
                        f"{somme_de_tous_les_reglements} pour {somme_des_totaux_catalogue} "
                        f"de totaux catalogue ; règlements hors offert "
                        f"{somme_des_reglements_hors_offert} pour "
                        f"{somme_des_nets_vendus} de nets vendus (centimes)."
                    ),
                }
            )

        empreinte_de_la_vente_precedente = vente.hmac_hash
        numero_precedent = vente.numero

    return anomalies

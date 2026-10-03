"""
L'intégrité des clôtures : l'empreinte chaînée de chaque clôture, et sa vérification.
/ Closure integrity: the chained fingerprint of each closure, and its check.

LOCALISATION : comptabilite/integrite.py

LA CHAÎNE : toutes les clôtures du lieu (J, H, M, A) forment UNE seule chaîne, dans
l'ordre de leur numéro (`numero_sequentiel`). Chaque clôture porte :
- `hmac_hash` : l'empreinte HMAC-SHA256 de son contenu (`calculer_hmac_cloture`) ;
- `previous_hmac` : l'empreinte de la clôture précédente ("" pour la première).
La clé est celle du lieu, la même que pour les ventes
(`LaboutikConfiguration.get_or_create_hmac_key()`, chiffrée en base).
Une clôture modifiée après coup (un total, une borne, une section du rapport) n'a plus
la bonne empreinte ; une clôture supprimée ou insérée casse un maillon.
/ One chain for every closure of the venue, in number order. Each closure carries the
HMAC of its content and the previous closure's HMAC. Same venue key as the sales.

FLUX :
- `comptabilite/tasks.py` (`generer_cloture_pour_tenant`) calcule l'empreinte à la
  création de la clôture, sous le verrou des clôtures du lieu ;
- `comptabilite/management/commands/verify_clotures.py` appelle
  `verifier_chaine_clotures`.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§3.2).
"""

import datetime
import hashlib
import hmac
import json

from BaseBillet.models_vente import Vente
from comptabilite.models import ClotureCaisse


def _texte_utc(moment):
    """
    Un moment écrit en UTC, au format ISO : le même texte, quel que soit le fuseau dans
    lequel il a été lu.
    / A moment written in UTC, ISO format: the same text whatever the reading time zone.
    """
    return moment.astimezone(datetime.timezone.utc).isoformat()


def calculer_hmac_cloture(cloture, cle, previous_hmac):
    """
    Calcule l'empreinte HMAC-SHA256 d'une clôture, chaînée avec la clôture précédente.
    / Computes the chained HMAC-SHA256 fingerprint of a closure.

    LOCALISATION : comptabilite/integrite.py

    Le message est un JSON canonique (clés triées, sans espace, accents gardés). Il
    contient : le niveau, le numéro, les bornes (en UTC), la plage de ventes, l'empreinte
    de la dernière vente couverte (relue en base), les totaux, les perpétuels, TOUT le
    `rapport_json`, et `previous_hmac`. Le point de vente et le responsable n'y sont pas
    (informatifs). Le numéro de format (1) permet de changer un jour le message sans
    casser les anciennes empreintes.
    / Canonical JSON of the level, number, bounds, sales range, fingerprint of the last
    covered sale, totals, perpetual totals, the whole stored report and previous_hmac.

    :param cloture: la `ClotureCaisse` (tous ses champs posés, sauf `hmac_hash`)
    :param cle: str — la clé HMAC du lieu, en clair
    :param previous_hmac: str — l'empreinte de la clôture précédente ("" pour la première)
    :return: str — empreinte de 64 caractères hexadécimaux
    """
    # L'empreinte de la dernière vente couverte : elle scelle la plage. Une clôture
    # sans vente n'en a pas.
    # / The last covered sale's fingerprint seals the range.
    empreinte_de_la_derniere_vente = ""
    if cloture.numero_derniere_vente is not None:
        derniere_vente = Vente.objects.filter(
            numero=cloture.numero_derniere_vente
        ).first()
        if derniere_vente is not None:
            empreinte_de_la_derniere_vente = derniere_vente.hmac_hash

    donnees = {
        "format": 1,
        "niveau": cloture.niveau,
        "numero_sequentiel": cloture.numero_sequentiel,
        "datetime_debut": _texte_utc(cloture.datetime_debut),
        "datetime_fin": _texte_utc(cloture.datetime_fin),
        "numero_premiere_vente": cloture.numero_premiere_vente,
        "numero_derniere_vente": cloture.numero_derniere_vente,
        "empreinte_de_la_derniere_vente": empreinte_de_la_derniere_vente,
        "totaux": {
            "total_general": cloture.total_general,
            "total_ht": cloture.total_ht,
            "total_tva": cloture.total_tva,
            "total_argent_recu": cloture.total_argent_recu,
            "nombre_transactions": cloture.nombre_transactions,
        },
        "perpetuels": {
            "total_perpetuel": cloture.total_perpetuel,
            "nombre_ventes_perpetuel": cloture.nombre_ventes_perpetuel,
        },
        "rapport_json": cloture.rapport_json,
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


def verifier_continuite_des_journees():
    """
    Vérifie que les J du lieu se suivent sans trou ni chevauchement, et renvoie la liste
    des anomalies.
    / Checks that the venue's J follow each other with no gap nor overlap.

    LOCALISATION : comptabilite/integrite.py

    Les J sont parcourues par numéro croissant. Pour chaque J après la première :
    1. elle commence exactement où la J d'avant finit (`datetime_debut` = `datetime_fin`
       de la J d'avant) ;
    2. sa première vente suit la dernière vente de la J d'avant (numéro + 1) : aucune
       vente n'est oubliée ni comptée deux fois.
    / Each J starts where the previous one ends, and its first sale follows the previous
    one's last sale.

    FLUX : appelée par `verify_clotures`.

    :return: list — les anomalies `{"numero", "uuid", "raison"}` ; vide si tout se suit
    """
    anomalies = []
    journee_precedente = None

    journees_par_numero = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER
    ).order_by("numero_sequentiel")
    for journee in journees_par_numero:
        premiere_journee = journee_precedente is None
        if premiere_journee:
            journee_precedente = journee
            continue

        # 1. Elle commence où la J d'avant finit.
        # / 1. It starts where the previous J ends.
        if journee.datetime_debut != journee_precedente.datetime_fin:
            anomalies.append(
                {
                    "numero": journee.numero_sequentiel,
                    "uuid": str(journee.uuid),
                    "raison": (
                        f"Journée discontinue : la clôture n° "
                        f"{journee.numero_sequentiel} ne commence pas à la fin de la "
                        f"clôture n° {journee_precedente.numero_sequentiel}."
                    ),
                }
            )

        # 2. Sa première vente suit la dernière de la J d'avant.
        # / 2. Its first sale follows the previous J's last sale.
        les_deux_ont_des_ventes = (
            journee.numero_premiere_vente is not None
            and journee_precedente.numero_derniere_vente is not None
        )
        if les_deux_ont_des_ventes:
            premiere_vente_attendue = journee_precedente.numero_derniere_vente + 1
            if journee.numero_premiere_vente != premiere_vente_attendue:
                anomalies.append(
                    {
                        "numero": journee.numero_sequentiel,
                        "uuid": str(journee.uuid),
                        "raison": (
                            f"Journée discontinue : la première vente de la clôture "
                            f"n° {journee.numero_sequentiel} ne suit pas la dernière "
                            f"vente de la clôture n° "
                            f"{journee_precedente.numero_sequentiel}."
                        ),
                    }
                )

        journee_precedente = journee

    return anomalies


def verifier_chaine_clotures(cle):
    """
    Vérifie la chaîne des clôtures du lieu, et renvoie la liste des anomalies.
    / Checks the chain of closures of the venue, returns the list of anomalies.

    LOCALISATION : comptabilite/integrite.py

    Les clôtures sont parcourues par numéro croissant. Pour chaque clôture :
    1. maillon cassé : son `previous_hmac` n'est pas l'empreinte stockée de la clôture
       d'avant ("" pour la première) ;
    2. empreinte fausse : l'empreinte recalculée (avec son `previous_hmac`) n'est pas
       celle enregistrée — la clôture a été modifiée après coup.
    Les trous de numéro sont vérifiés par `verify_clotures`.
    / Walks closures by number: broken link, wrong fingerprint. Number gaps are checked
    by the verify_clotures command.

    Une anomalie est un dictionnaire : "numero" (numéro de la clôture), "uuid" (texte)
    et "raison" (phrase en français).
    / An anomaly is a dict: "numero", "uuid", "raison".

    :param cle: str — la clé HMAC du lieu, en clair
    :return: list — les anomalies ; vide si la chaîne est saine
    """
    anomalies = []
    empreinte_de_la_cloture_precedente = ""

    clotures_par_numero = ClotureCaisse.objects.order_by("numero_sequentiel")
    for cloture in clotures_par_numero:
        # 1. Maillon cassé : le lien vers la clôture d'avant.
        # / 1. Broken link to the previous closure.
        if cloture.previous_hmac != empreinte_de_la_cloture_precedente:
            anomalies.append(
                {
                    "numero": cloture.numero_sequentiel,
                    "uuid": str(cloture.uuid),
                    "raison": (
                        f"Maillon cassé : l'empreinte précédente de la clôture "
                        f"n° {cloture.numero_sequentiel} n'est pas l'empreinte de la "
                        f"clôture d'avant."
                    ),
                }
            )

        # 2. Empreinte fausse : la clôture a changé après sa création.
        # / 2. Wrong fingerprint: the closure changed after its creation.
        empreinte_recalculee = calculer_hmac_cloture(
            cloture, cle, cloture.previous_hmac
        )
        if empreinte_recalculee != cloture.hmac_hash:
            anomalies.append(
                {
                    "numero": cloture.numero_sequentiel,
                    "uuid": str(cloture.uuid),
                    "raison": (
                        f"Empreinte fausse : la clôture n° {cloture.numero_sequentiel} "
                        f"a été modifiée après sa création."
                    ),
                }
            )

        empreinte_de_la_cloture_precedente = cloture.hmac_hash

    return anomalies

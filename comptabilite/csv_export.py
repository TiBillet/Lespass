"""
Export CSV d'une clôture comptable.
/ CSV export of an accounting closure.

LOCALISATION : comptabilite/csv_export.py

Le CSV écrit les sections du rapport stocké (`cloture.rapport_json`), préparées par
comptabilite/presentation.py `sections_pour_affichage` : les mêmes que la fiche de
l'admin, dans le même ordre. Chaque section commence par une ligne « [Titre] », puis sa
phrase (s'il y en a une), puis ses tableaux (titre, message d'alerte, colonnes,
lignes). Les montants sont écrits à la française (« 1 050,00 € »), comme à l'écran.
Un texte qui commence par « = », « + », « - » ou « @ » est précédé d'une apostrophe :
un tableur ne le lit jamais comme une formule.
Format : séparateur « ; », UTF-8 avec BOM (ouverture directe dans Excel). Le nom du
fichier est daté du jour de fin de la clôture, en heure du lieu.
/ The CSV writes the stored report's sections (same as the admin page), French amounts,
texts protected against formulas. ";" separator, UTF-8 with BOM.

FLUX : comptabilite/admin.py `exporter_csv` → `generer_csv_cloture`.
"""
import csv
import io

from django.utils.translation import gettext

from comptabilite.presentation import (
    nom_du_fichier_de_la_cloture,
    sections_pour_affichage,
    texte_sans_formule,
)

# La marque d'ordre des octets (BOM) : Excel ouvre alors le fichier en UTF-8.
# / The byte order mark: Excel then opens the file as UTF-8.
MARQUE_UTF_8_POUR_EXCEL = "\ufeff"


def _ecrire_une_ligne(ecrivain_csv, textes):
    """
    Écrit une ligne du CSV. Chaque texte passe par `texte_sans_formule` : un nom de
    produit ou d'opérateur qui commence par « = » n'est jamais lu comme une formule.
    / Writes a CSV row; every text is protected against formulas.
    """
    textes_proteges = []
    for texte in textes:
        textes_proteges.append(texte_sans_formule(texte))
    ecrivain_csv.writerow(textes_proteges)


def generer_csv_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export CSV.
    / Returns (bytes, filename, content_type) for the CSV export.
    """
    tampon_du_csv = io.StringIO()
    ecrivain_csv = csv.writer(
        tampon_du_csv, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL
    )

    # L'identité de la clôture : son numéro et son empreinte (le reste de l'en-tête est
    # dans la première section du rapport).
    # / The closure's identity: number and fingerprint.
    _ecrire_une_ligne(ecrivain_csv, [gettext("Rapport de clôture")])
    _ecrire_une_ligne(
        ecrivain_csv, [gettext("Numéro de clôture"), cloture.numero_sequentiel]
    )
    _ecrire_une_ligne(
        ecrivain_csv, [gettext("Empreinte de la clôture"), cloture.hmac_hash]
    )
    _ecrire_une_ligne(ecrivain_csv, [])

    sections = sections_pour_affichage(cloture.rapport_json)
    for section in sections:
        _ecrire_une_ligne(ecrivain_csv, [f"[{section['titre']}]"])
        if section["phrase"]:
            _ecrire_une_ligne(ecrivain_csv, [section["phrase"]])
        for tableau in section["tableaux"]:
            if tableau["titre"]:
                _ecrire_une_ligne(ecrivain_csv, [tableau["titre"]])
            if tableau["message_d_alerte"]:
                _ecrire_une_ligne(ecrivain_csv, [tableau["message_d_alerte"]])
            _ecrire_une_ligne(ecrivain_csv, tableau["colonnes"])
            for ligne in tableau["lignes"]:
                textes_de_la_ligne = []
                for cellule in ligne:
                    textes_de_la_ligne.append(cellule["texte"])
                _ecrire_une_ligne(ecrivain_csv, textes_de_la_ligne)
        _ecrire_une_ligne(ecrivain_csv, [])

    contenu_en_octets = (MARQUE_UTF_8_POUR_EXCEL + tampon_du_csv.getvalue()).encode(
        "utf-8"
    )
    nom_du_fichier = nom_du_fichier_de_la_cloture(cloture, "csv")
    return contenu_en_octets, nom_du_fichier, "text/csv; charset=utf-8"

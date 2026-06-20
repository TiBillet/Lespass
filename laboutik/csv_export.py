# laboutik/csv_export.py
# Generation du rapport CSV de cloture de caisse.
# CSV generation for cash register closure report.
#
# Utilise io.StringIO + csv.writer (stdlib).
# Les donnees viennent du rapport_json, pas d'un queryset.
# Uses io.StringIO + csv.writer (stdlib).
# Data comes from rapport_json, not a queryset.

import csv
import io
import logging

from django.utils.translation import activate, gettext as _

from BaseBillet.models import Configuration
from laboutik.models import ClotureCaisse

logger = logging.getLogger(__name__)


def generer_csv_cloture(cloture: ClotureCaisse) -> str:
    """
    Genere le CSV du rapport de cloture de caisse.
    Generates the CSV for the cash register closure report.

    LOCALISATION : laboutik/csv_export.py

    :param cloture: instance ClotureCaisse avec rapport_json rempli
    :return: string CSV
    """
    config = Configuration.get_solo()
    activate(config.language)

    rapport = cloture.rapport_json
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # --- En-tete / Header ---
    writer.writerow([_("Rapport de clôture de caisse")])
    writer.writerow([_("Organisation"), config.organisation])
    writer.writerow([_("Point de vente"), cloture.point_de_vente.name])
    writer.writerow([_("Ouverture"), str(cloture.datetime_ouverture)])
    writer.writerow([_("Clôture"), str(cloture.datetime_cloture)])
    if cloture.responsable:
        writer.writerow([_("Responsable"), str(cloture.responsable)])
    writer.writerow([_("Transactions"), cloture.nombre_transactions])
    writer.writerow([])

    # --- Totaux par moyen de paiement / Totals by payment method ---
    writer.writerow([_("Totaux par moyen de paiement")])
    writer.writerow([_("Moyen de paiement"), _("Total (EUR)")])
    writer.writerow([_("Espèces"), f"{cloture.total_especes / 100:.2f}"])
    writer.writerow([_("Carte bancaire"), f"{cloture.total_carte_bancaire / 100:.2f}"])
    writer.writerow([_("Cashless"), f"{cloture.total_cashless / 100:.2f}"])
    writer.writerow([_("Total général"), f"{cloture.total_general / 100:.2f}"])
    writer.writerow([])

    # --- Par produit / By product ---
    par_produit = rapport.get("par_produit", {})
    if par_produit:
        writer.writerow([_("Détail par produit")])
        writer.writerow([_("Produit"), _("Quantité"), _("Total (EUR)")])
        for nom_produit, donnees in par_produit.items():
            total_euros = f"{donnees.get('total', 0) / 100:.2f}"
            quantite = donnees.get("qty", 0)
            writer.writerow([nom_produit, quantite, total_euros])
        writer.writerow([])

    # --- Par categorie / By category ---
    par_categorie = rapport.get("par_categorie", {})
    if par_categorie:
        writer.writerow([_("Détail par catégorie")])
        writer.writerow([_("Catégorie"), _("Total (EUR)")])
        for nom_categorie, total_centimes in par_categorie.items():
            writer.writerow([nom_categorie, f"{total_centimes / 100:.2f}"])
        writer.writerow([])

    # --- Ventilation TVA / VAT breakdown ---
    par_tva = rapport.get("par_tva", {})
    if par_tva:
        writer.writerow([_("Ventilation TVA")])
        writer.writerow([_("Taux"), _("HT (EUR)"), _("TVA (EUR)"), _("TTC (EUR)")])
        for taux_label, tva_data in par_tva.items():
            writer.writerow([
                taux_label,
                f"{tva_data.get('total_ht', 0) / 100:.2f}",
                f"{tva_data.get('total_tva', 0) / 100:.2f}",
                f"{tva_data.get('total_ttc', 0) / 100:.2f}",
            ])
        writer.writerow([])

    # --- Commandes / Orders ---
    commandes = rapport.get("commandes", {})
    if commandes:
        writer.writerow([_("Commandes")])
        writer.writerow([_("Total commandes"), commandes.get("total", 0)])
        writer.writerow([_("Commandes annulées"), commandes.get("annulees", 0)])

    csv_string = output.getvalue()
    logger.info(f"CSV cloture genere: {cloture.uuid} ({len(csv_string)} caracteres)")
    return csv_string

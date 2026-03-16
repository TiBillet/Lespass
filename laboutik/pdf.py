# laboutik/pdf.py
# Generation du rapport PDF de cloture de caisse avec WeasyPrint.
# PDF generation for cash register closure report using WeasyPrint.
#
# Pattern identique a BaseBillet/tasks.py:create_membership_invoice_pdf()
# Same pattern as BaseBillet/tasks.py:create_membership_invoice_pdf()

import logging

from django.template.loader import get_template
from django.utils.translation import activate

from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from BaseBillet.models import Configuration
from laboutik.models import ClotureCaisse

logger = logging.getLogger(__name__)


def generer_pdf_cloture(cloture: ClotureCaisse) -> bytes:
    """
    Genere le PDF du rapport de cloture de caisse.
    Generates the PDF for the cash register closure report.

    LOCALISATION : laboutik/pdf.py

    :param cloture: instance ClotureCaisse avec rapport_json rempli
    :return: bytes du fichier PDF
    """
    config = Configuration.get_solo()
    activate(config.language)

    rapport = cloture.rapport_json

    # Construire le contexte pour le template PDF
    # Build the context for the PDF template
    context = {
        "config": config,
        "cloture": cloture,
        "point_de_vente": cloture.point_de_vente,
        "responsable": cloture.responsable,
        "datetime_ouverture": cloture.datetime_ouverture,
        "datetime_cloture": cloture.datetime_cloture,
        # Totaux en euros (division centimes → euros)
        # Totals in euros (cents → euros)
        "total_especes_euros": cloture.total_especes / 100,
        "total_cb_euros": cloture.total_carte_bancaire / 100,
        "total_nfc_euros": cloture.total_cashless / 100,
        "total_general_euros": cloture.total_general / 100,
        "nombre_transactions": cloture.nombre_transactions,
        # Sections du rapport JSON converties en euros
        # JSON report sections converted to euros
        "par_produit": {
            nom: {"total_euros": donnees.get("total", 0) / 100, "qty": donnees.get("qty", 0)}
            for nom, donnees in rapport.get("par_produit", {}).items()
        },
        "par_categorie": {
            nom: total_cts / 100
            for nom, total_cts in rapport.get("par_categorie", {}).items()
        },
        "par_tva": {
            taux_label: {
                "taux": tva.get("taux", 0),
                "total_ht_euros": tva.get("total_ht", 0) / 100,
                "total_tva_euros": tva.get("total_tva", 0) / 100,
                "total_ttc_euros": tva.get("total_ttc", 0) / 100,
            }
            for taux_label, tva in rapport.get("par_tva", {}).items()
        },
        "commandes": rapport.get("commandes", {}),
    }

    template = get_template("laboutik/pdf/cloture_rapport_pdf.html")
    html_string = template.render(context)

    font_config = FontConfiguration()
    pdf_bytes = HTML(string=html_string).write_pdf(font_config=font_config)

    logger.info(f"PDF cloture genere: {cloture.uuid} ({len(pdf_bytes)} octets)")
    return pdf_bytes

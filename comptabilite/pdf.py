"""
Export PDF d'une cloture comptable (WeasyPrint).
/ PDF export of an accounting closure (WeasyPrint).

LOCALISATION : comptabilite/pdf.py

Template HTML standalone (styles inline obligatoires pour WeasyPrint —
pas de CSS externe fiable). Format A4, marges 1.5cm.
/ Standalone HTML template (inline styles mandatory for WeasyPrint).
A4, 1.5cm margins.
"""
import io

from django.template.loader import render_to_string
from weasyprint import HTML


def _euros(centimes):
    """Convertit centimes (int) en string '12.34' (jamais None).
    / Convert cents (int) to '12.34' string (never None).
    """
    if centimes is None:
        return "0.00"
    return f"{centimes / 100:.2f}"


def generer_pdf_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export PDF.
    / Returns (bytes, filename, content_type) for the PDF export.

    Pre-formate les montants en chaines '12.34' AVANT le rendu template,
    pour eviter d'avoir a creer des filtres Django custom.
    / Pre-formats amounts as '12.34' strings BEFORE template rendering,
    to avoid creating custom Django filters.
    """
    rapport = cloture.rapport_json or {}

    # Build template context with pre-formatted euro strings.
    # / Build the template context with pre-formatted euro strings.
    contexte = {
        "cloture": cloture,
        "rapport": rapport,
        "totaux_par_moyen_items": [
            {
                "code": code,
                "label": item.get("label", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for code, item in (rapport.get("totaux_par_moyen") or {}).items()
            if code not in ("total", "currency_code", "categories")
            and isinstance(item, dict)
        ],
        "tva_items": [
            {
                "taux": item.get("taux", taux),
                "ht": _euros(item.get("total_ht")),
                "tva": _euros(item.get("total_tva")),
                "ttc": _euros(item.get("total_ttc")),
            }
            for taux, item in (rapport.get("tva") or {}).items()
            if isinstance(item, dict)
        ],
        "adhesions_items": [
            {
                "nom_produit": item.get("nom_produit", ""),
                "nom_tarif": item.get("nom_tarif", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for item in (rapport.get("adhesions") or {}).get("detail", {}).values()
        ],
        "billets_items": [
            {
                "nom_event": item.get("nom_event", ""),
                "nom_produit": item.get("nom_produit", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for item in (rapport.get("billets") or {}).get("detail", {}).values()
        ],
        "infos_legales": rapport.get("infos_legales") or {},
        "cloture_total_ttc_euros": _euros(cloture.total_general),
    }

    html_string = render_to_string("comptabilite/pdf/rapport_comptable.html", contexte)
    buffer = io.BytesIO()
    HTML(string=html_string).write_pdf(buffer)

    filename = f"cloture-{cloture.numero_sequentiel}-{cloture.datetime_fin:%Y%m%d}.pdf"
    return buffer.getvalue(), filename, "application/pdf"

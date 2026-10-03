"""
Export PDF d'une clôture comptable (WeasyPrint).
/ PDF export of an accounting closure (WeasyPrint).

LOCALISATION : comptabilite/pdf.py

Le PDF imprime les sections du rapport stocké (`cloture.rapport_json`), préparées par
comptabilite/presentation.py `sections_pour_affichage` : les mêmes que la fiche de
l'admin, dans le même ordre, toutes dépliées (un papier ne se replie pas). Gabarit
autonome, styles inline (WeasyPrint ne charge pas de CSS externe fiable). A4 paysage.
/ The PDF prints the stored report's sections (same as the admin page), all unfolded.

FLUX : comptabilite/admin.py `exporter_pdf` et comptabilite/tasks.py
`envoyer_email_cloture` (pièce jointe) → `generer_pdf_cloture`.
"""
import io

from django.template.loader import render_to_string
from weasyprint import HTML

from comptabilite.presentation import (
    nom_du_fichier_de_la_cloture,
    sections_pour_affichage,
)


def html_du_pdf_de_la_cloture(cloture):
    """
    Le HTML que WeasyPrint imprime pour une clôture : l'empreinte de la clôture, puis
    les sections de son rapport stocké.
    / The HTML printed for a closure: its fingerprint, then its stored report's sections.
    """
    contexte = {
        "cloture": cloture,
        "sections": sections_pour_affichage(cloture.rapport_json),
    }
    return render_to_string("comptabilite/pdf/rapport_comptable.html", contexte)


def generer_pdf_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export PDF.
    / Returns (bytes, filename, content_type) for the PDF export.
    """
    html_a_imprimer = html_du_pdf_de_la_cloture(cloture)
    buffer = io.BytesIO()
    HTML(string=html_a_imprimer).write_pdf(buffer)

    nom_du_fichier = nom_du_fichier_de_la_cloture(cloture, "pdf")
    return buffer.getvalue(), nom_du_fichier, "application/pdf"

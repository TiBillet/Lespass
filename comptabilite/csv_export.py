"""
Export CSV d'une cloture comptable.
/ CSV export of an accounting closure.

LOCALISATION : comptabilite/csv_export.py

Format : separateur ';', UTF-8 avec BOM (pour ouverture directe dans Excel).
Lit cloture.rapport_json (pre-calcule par S2), pas de recalcul.
/ Format: ';' separator, UTF-8 with BOM (so Excel opens it correctly).
Reads cloture.rapport_json (pre-computed by S2), no re-aggregation.
"""
import csv
import io


def _euros(centimes):
    """Convertit centimes (int) en string '12.34' (jamais None)."""
    if centimes is None:
        return "0.00"
    return f"{centimes / 100:.2f}"


def generer_csv_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export CSV.
    / Returns (bytes, filename, content_type) for the CSV export.
    """
    rapport = cloture.rapport_json or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)

    writer.writerow(["Rapport de cloture comptable"])
    writer.writerow(["Numero", cloture.numero_sequentiel])
    writer.writerow(["Niveau", cloture.get_niveau_display()])
    writer.writerow(["Debut", cloture.datetime_debut.strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["Fin", cloture.datetime_fin.strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["Transactions", cloture.nombre_transactions])
    writer.writerow(["Total TTC (EUR)", _euros(cloture.total_general)])
    writer.writerow(["Total HT (EUR)", _euros(cloture.total_ht)])
    writer.writerow(["Total TVA (EUR)", _euros(cloture.total_tva)])
    writer.writerow(["Hash lignes", cloture.hash_lignes or ""])
    writer.writerow([])

    writer.writerow(["[Totaux par moyen de paiement]"])
    writer.writerow(["Code", "Libelle", "Total (EUR)", "Nb"])
    for code, item in (rapport.get("totaux_par_moyen") or {}).items():
        if code in ("total", "currency_code"):
            continue
        if isinstance(item, dict):
            writer.writerow([code, item.get("label", ""), _euros(item.get("total")), item.get("nb", 0)])
    writer.writerow([])

    writer.writerow(["[Ventilation TVA]"])
    writer.writerow(["Taux %", "Total HT", "Total TVA", "Total TTC"])
    for taux, item in (rapport.get("tva") or {}).items():
        if isinstance(item, dict):
            writer.writerow([
                item.get("taux", taux),
                _euros(item.get("total_ht")),
                _euros(item.get("total_tva")),
                _euros(item.get("total_ttc")),
            ])
    writer.writerow([])

    writer.writerow(["[Adhesions]"])
    writer.writerow(["Produit", "Tarif", "Moyen paiement", "Total (EUR)", "Nb"])
    for item in (rapport.get("adhesions") or {}).get("detail", {}).values():
        writer.writerow([
            item.get("nom_produit", ""),
            item.get("nom_tarif", ""),
            item.get("moyen_paiement_label") or item.get("moyen_paiement", ""),
            _euros(item.get("total")),
            item.get("nb", 0),
        ])
    writer.writerow([])

    writer.writerow(["[Billets evenements]"])
    writer.writerow(["Evenement", "Date", "Produit", "Tarif", "Total (EUR)", "Nb"])
    for item in (rapport.get("billets") or {}).get("detail", {}).values():
        writer.writerow([
            item.get("nom_event", ""),
            item.get("date_event", ""),
            item.get("nom_produit", ""),
            item.get("nom_tarif", ""),
            _euros(item.get("total")),
            item.get("nb", 0),
        ])
    writer.writerow([])

    writer.writerow(["[Remboursements et avoirs]"])
    writer.writerow(["Type", "Total (EUR)", "Nb"])
    rb = rapport.get("remboursements") or {}
    cn = rb.get("credit_notes", {})
    rf = rb.get("refunded", {})
    writer.writerow(["Avoirs (credit notes)", _euros(cn.get("total")), cn.get("nb", 0)])
    writer.writerow(["Remboursements (refunded)", _euros(rf.get("total")), rf.get("nb", 0)])

    # UTF-8 avec BOM (U+FEFF) pour ouverture directe Excel
    # / UTF-8 with BOM for Excel compatibility
    contenu_bytes = ("﻿" + buffer.getvalue()).encode("utf-8")
    filename = f"cloture-{cloture.numero_sequentiel}-{cloture.datetime_fin:%Y%m%d}.csv"
    return contenu_bytes, filename, "text/csv; charset=utf-8"

# Ticket client imprimé : montants justes et détail des moyens / Customer receipt: correct amounts and payment detail

**Date :** 2026-09-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** le ticket client imprimé après une vente de caisse regroupe les parts
d'un même article payé avec plusieurs monnaies (« Vin x3 15,00 »), calcule chaque
montant sur `amount × qty`, et imprime le détail de tous les moyens de paiement
(monnaies de carte par nom, espèces, CB, chèque) quand au moins deux ont servi. /
The customer receipt groups the parts of one item, computes amounts on
`amount × qty`, and prints the payment detail when two methods or more were used.

**Pourquoi / Why :** la quantité était tronquée à l'entier : 3 vins payés 6 € cadeau +
9 € monnaie locale s'imprimaient « x1 5,00 / x1 5,00 », total 10 € au lieu de 15 € ;
une bouteille payée 2 € + 8 € s'imprimait « x0 0,00 ». La TVA du ticket était calculée
sur ces totaux faux. Le détail par monnaie additionnait des prix unitaires, ignorait les
espèces d'un complément, et n'était imprimé par aucune imprimante. /
Quantity was truncated to an integer (15 € printed as 10 €); the detail summed unit
prices and was never printed.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-C-ticket-imprime.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/printing/formatters.py` | `formatter_ticket_vente` : regroupement par (tarif vendu, prix unitaire, TVA), montant `amount × qty` arrondi comme les rapports, quantité en `int` (ou 2 décimales), détail de tous les moyens via `montant_ttc_centimes()` : monnaies de carte d'abord dans l'ordre de la cascade (cadeau, locale, fédérée), puis les autres moyens |
| `laboutik/views.py` | `LABELS_MOYENS_PAIEMENT_DB` : `STRIPE_FED` → « Monnaie fédérée » (au lieu du libellé anglais « Online: federated Stripe ») ; impression du ticket : `select_related` du tarif et du produit (plus de requête par article) |
| `laboutik/printing/escpos_builder.py` | impression du détail si ≥ 2 moyens (Sunmi Cloud, LAN, mock) |
| `laboutik/printing/sunmi_inner.py` | idem pour l'imprimante interne |
| `tests/pytest/test_ticket_client_imprime.py` | nouveau (schéma dédié), 11 tests (dont ordre du détail, libellé de la monnaie fédérée, impression d'un seul moyen) |

**i18n** : une nouvelle chaîne traduisible, « Monnaie fédérée » (`laboutik/views.py`).
Le workflow i18n est à lancer par le mainteneur.

Un paiement réparti peut montrer un écart d'un centime entre le TOTAL (arrondi par
article) et la somme du détail (arrondi par moyen) : inhérent à la règle `amount × qty`.

### Tests vus échouer puis mutations
Avant correctif : les 8 tests rouges (deux articles au lieu d'un, total 0 au lieu de
1000, TVA sur 1000 au lieu de 1500, détail 500/500 au lieu de 600/900, espèces absentes,
rien imprimé).

| Mutation du code de production | Tests qui tombent |
|---|---|
| quantité tronquée (`Decimal(int(ligne.qty))`) | regroupement, part < 1 article, TVA, complément espèces |
| détail sur `Sum("amount")` | détail par monnaie, complément espèces |
| détail limité aux lignes avec asset | complément espèces, espèces seules, deux imprimantes |
| bloc de détail retiré d'ESC/POS | imprimante ESC/POS |
| seuil « ≥ 2 moyens » ramené à 1 | imprimante ESC/POS |
| bloc de détail retiré de Sunmi interne | imprimante Sunmi interne |
| tri du détail par code de paiement | ordre de la cascade |
| libellé « Monnaie fédérée » retiré | libellé de la monnaie fédérée |

Chaque mutation restaurée, empreinte sha256 vérifiée.

---

## Comment tester (a la main) / Manual test

### Test 1 — paiement réparti
1. Carte avec 6 € de monnaie cadeau et 9 € de monnaie locale.
2. Vendre 3 vins à 5 € en cashless, puis « Imprimer le ticket ».
3. Attendu : « Vin x3 15.00EUR », TOTAL 15.00, puis le détail
   « Cadeau 6.00EUR / Monnaie locale 9.00EUR », puis la TVA sur 15 €.

### Test 2 — complément en espèces
1. Carte avec 6 € cadeau + 4 € locale, vendre 3 vins (15 €), compléter 5 € en espèces.
2. Attendu : détail à trois lignes, dont « Espèces 5.00EUR ».

### Test 3 — un seul moyen
1. Vendre 2 vins en espèces, imprimer.
2. Attendu : « x2 10.00EUR », aucun bloc de détail.

# Offerts et recharges cadeau hors des calculs d'argent / Gifted items and gift top-ups out of money totals

**Date :** 2026-09-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** une ligne de caisse « offerte » (`FREE` : article offert, recharge cadeau)
garde sa valeur, reste dans la clôture (hash, compteurs), mais sort de tout calcul
d'argent du ticket X / Z : TVA, détail des ventes, CA par point de vente, panier moyen,
totaux des recharges / adhésions / billets, écriture FEC. Elle est montrée à part :
section « Offerts (hors argent) » et ligne « Cadeau émis (hors argent) » dans les
recharges. Une ligne offerte est créée avec une TVA à 0. Une ligne offerte ne peut plus
être « corrigée » en espèces / CB. /
A gifted line keeps its value and stays in the closure, but leaves every money
computation; it is shown apart. Created with VAT 0; cannot be corrected into money.

**Pourquoi / Why :** la TVA et le détail des ventes comptaient les offerts alors que le
total ne les comptait pas : l'écriture FEC n'était pas équilibrée (déséquilibre du montant
offert). Une recharge cadeau gonflait le total des recharges et le panier moyen. La
correction de moyen de paiement acceptait de transformer une recharge cadeau en espèces :
de l'argent jamais encaissé apparaissait dans le Z. /
VAT and sales detail counted gifted lines while the total did not (unbalanced FEC); gift
top-ups inflated top-up totals; a gift top-up could be "corrected" into cash.

**OFFRIR en mode gérant (session D-2)** : une carte primaire en mode gérant
(`CartePrimaire.edit_mode`, lu en base) fait apparaître la tuile OFFRIR, comme dans
LaBoutik v1 ; le panier est enregistré « Offert » (FREE) à son prix. Aussi pour une
adhésion ou un billet (popup « client identifié »). Refusé pour un retour de consigne et
une recharge en euros. Le paiement d'une commande de table n'accepte plus que ses moyens
(un POST « gift » y enregistrait la commande comme offerte, sans mode gérant). /
A manager-mode primary card shows the GIFT tile; refused for deposit returns and euro
top-ups; table-order payment now whitelists its methods.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-D-offerts.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/reports.py` | `MOYENS_HORS_ARGENT`, `self.lignes_argent` ; détail des ventes, TVA, habitus, ventilation par PV sur `lignes_argent` ; recharges : `total` encaissé + `cadeau_emis` ; adhésions et billets : nombre sur toutes les lignes, montant hors FREE ; `calculer_offerts()` ; rapport à 14 clés |
| `BaseBillet/models.py` | `LigneArticle._compute_default_vat` : TVA 0 pour une ligne créée en FREE |
| `laboutik/views.py` | `corriger_moyen_paiement` : garde « ligne hors argent » ; ticket X (écran et impression) : section « Offerts » |
| `Administration/admin/laboutik.py` | mapping moyen → compte de trésorerie : NA retiré des choix |
| `laboutik/printing/formatters.py` | tickets X et Z imprimés : ligne « Offerts : N articles, valeur X EUR » |
| `laboutik/csv_export.py`, `laboutik/excel_export.py` | section « Offerts (hors argent) » |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html`, `hx_cloture_rapport.html` | bloc « Offerts » |
| `Administration/templates/admin/cloture/rapport_before.html`, `rapport_temps_reel.html`, `laboutik/templates/laboutik/pdf/rapport_comptable.html` | section « Offerts », ligne « Cadeau émis », colonne « Payé en cadeau » |
| `laboutik/views.py` (D-2) | `_panier_peut_etre_offert()` ; `moyens_paiement` et popup « client identifié » : tuile OFFRIR ; `_executer_paiement` : `gift` accepté si panier gratuit OU offert par le gérant ; `payer_commande` : liste blanche des moyens |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | tuile OFFRIR : `&total=` dans l'URL de confirmation (l'écran affichait 0,00 €) |
| `tests/pytest/test_hors_argent_offerts.py` | nouveau (schéma dédié), 22 tests |
| `tests/pytest/test_cloture_enrichie.py`, `test_cloture_caisse.py` | le rapport compte 14 clés (`offerts`) |

**i18n** : nouvelles chaînes (source FR) : « Offerts (hors argent) », « Valeur offerte »,
« Coût d'achat », « Cadeau émis (hors argent) », « Payé en cadeau », « Offerts »,
« articles », « valeur », « Article », « Quantité », « Une vente offerte ne peut pas etre
corrigee en paiement ». Workflow i18n à lancer par le mainteneur.

### Tests vus échouer puis mutations
Avant correctif : 11 des 12 premiers tests rouges (TVA 1500 au lieu de 500, CA du PV
1500, qty vendus 3, recharges 3000 au lieu de 2000, panier moyen 1500, TVA de la ligne
offerte 20 %, correction acceptée en 200, `NA` proposé dans l'admin, pas de section
« Offerts ») ; la non-régression du total passait déjà.

| Mutation du code de production | Tests qui tombent |
|---|---|
| `lignes_argent = self.lignes` | FEC, TVA, CA par PV, détail des ventes, panier moyen |
| règle TVA 0 retirée | ligne offerte sans TVA |
| `calculer_offerts` sur `LOCAL_GIFT` | section offerts, ticket X, ticket Z, CSV |
| recharge cadeau comptée dans le total | total des recharges |
| habitus sur toutes les lignes | panier moyen |
| garde de correction retirée | correction refusée |
| menu du mapping non filtré | admin |
| offerts retirés du contexte du ticket X | ticket X |
| ligne « Offerts » retirée du ticket Z | ticket Z imprimé |
| section retirée du CSV | export CSV |
| tuile OFFRIR forcée à faux | tuile en mode gérant |
| `edit_mode` ignoré | refus sans mode gérant, pas de tuile sans mode gérant |
| retour de consigne offrable | offrir une consigne refusé |
| recharge euros offrable | offrir une recharge euros refusé |
| liste blanche de `payer_commande` retirée | commande de table offerte par un POST |
| `&total=` retiré de la tuile | tuile en mode gérant |
| popup client identifié sans OFFRIR | tuile pour une adhésion identifiée |

Avant correctif (D-2) : 4 rouges (pas de tuile en mode gérant ni pour l'adhésion, panier
payant offert refusé, commande de table offerte par un POST « gift » acceptée en 200) ;
les refus (sans mode gérant, recharge euros, consigne) passaient déjà et restent verts.

**Démo et E2E** : la carte primaire de démo (`create_test_pos_data`, `A49E8E2A`) est en
mode gérant : la tuile OFFRIR apparaît dans les parcours de caisse de démo.
Limite connue : le mode gérant repose sur le secret du tag de la carte primaire, comme
tout l'accès caisse.

**i18n (D-2)** : « Moyen de paiement non accepte pour une commande ».

Chaque mutation restaurée, empreinte sha256 vérifiée.

---

## Comment tester (a la main) / Manual test

### Test 1 — recharge cadeau
1. Caisse : recharger 10 € de monnaie cadeau sur une carte, puis 20 € en euros (espèces).
2. Ticket X (écran Ventes) et clôture : recharges « Total 20,00 € », ligne
   « Cadeau émis (hors argent) 10,00 € ».

### Test 2 — article offert (après la session D-2)
1. Carte primaire en mode gérant : offrir 2 vins, vendre 1 vin en espèces.
2. Ticket X : TVA sur 5 € seulement, section « Offerts (hors argent) » : 2 vins, 10 €.
3. Clôturer, exporter le FEC : écriture équilibrée.

### Test 3 — correction interdite
1. Historique des ventes : essayer de corriger la recharge cadeau en espèces.
2. Attendu : refus « Une vente offerte ne peut pas etre corrigee en paiement ».

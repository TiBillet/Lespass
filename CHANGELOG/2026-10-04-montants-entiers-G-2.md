# Les écrans de vente et le ticket de la caisse lisent la vente (chantier 05, fiche G, session G-2) / Register sales screens and receipt read the sale (worksite 05, sheet G, session G-2)

**Date :** 2026-10-04
**Migration :** Non

## Resume / Summary
**Quoi / What :** la liste des ventes, le détail d'une vente, l'écran « corriger le moyen », le récapitulatif en cours et le ticket de vente imprimé lisent la `Vente` (articles, règlements, numéro), et plus aucune ligne d'article par `amount × qty`, `payment_method` ou `uuid_transaction`. Le ticket se ré-imprime par l'uuid de la vente ; le DUPLICATA se compte par vente. /
The sales list, sale detail, correction screen, current recap and printed sale receipt read the sale; reprint by sale uuid, DUPLICATE counted per sale.

**Pourquoi / Why :** fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md` §3, brief `CHANTIER-05-briefs/05-G-2.md`, décisions Q-G13, Q-G14 et relecture Opus de G-2a (SUIVI §4).

## G-2a — Liste, détail, correction

### Resume / Summary
- **Liste des ventes** (`liste_ventes`) : une ligne par vente réglée du service en cours, faite sur un point de vente du lieu (caisse, tireuse ; jamais une vente en ligne, Q-G13), toutes natures avec un badge court « Vente », « Avoir », « Correction », « Carte vidée » (Q-G14). Numéro, heure locale du lieu, point de vente, total (`Vente.total_ttc`), moyens en clair lus dans les règlements (« 5,50 € Carte bancaire + 5,00 € <monnaie> » : un moyen d'argent par son nom, un règlement cashless par le nom de sa monnaie, l'offert exclu), nombre d'articles (quantités réelles). Filtre par moyen = au moins un règlement de ce moyen (`Exists`). 20 ventes à la fois, la suite par numéro (`?avant=<numéro>`). Nombre de requêtes constant. Lignes atteignables au clavier (`role="button"`, Entrée / Espace, `aria-expanded`). /
  One row per settled sale made on a point of sale, nature badge, methods in words from the payments, filter on payments, keyset pagination by number, keyboard-accessible rows.
- **Détail d'une vente** (`detail_vente`, adresse `detail-vente/<uuid de la vente>/`) : articles regroupés (les parts d'un article payé avec plusieurs moyens forment UN article ; clé : tarif, événement, prix unitaire, poids ; poids d'un tirage ou d'un vrac affiché une fois), prix unitaire, part offerte, total ; règlements (moyen, monnaie, montant) ; vente liée et ventes dérivées (« Corrigée par la vente n° X »), avec leur lien ; statut (une vente en attente s'affiche, sans bouton « Corriger ») ; un bouton « Corriger » par moyen actuel corrigeable des lignes. /
  Grouped items, payments, linked and derived sales, status, one Correct button per current correctable method.
- **Correction du moyen** : une seule fonction `lignes_que_la_correction_deplace(ligne)` (lignes de la même vente au même moyen actuel), lue par l'écran (montant affiché = somme de leurs `total_ttc`, « Règlement <moyen> ») et par la route `corriger_moyen_paiement` (montant déplacé). Deux corrections successives permises (corriger une correction erronée). Après une correction, le détail de la vente est re-rendu. L'écran refuse d'abord ce que la route refuserait (`raison_du_refus_de_correction`). /
  One function for what a correction moves, read by the screen and the route; a correction can be corrected; the detail is re-rendered.
- **Récapitulatif en cours** : les boutons « Historique de vente » et « Lignes de caisse » sont retirés (leurs sections sont déjà sur la page, lues dans `RapportDesVentes.rapport_x()`), ainsi que les routes `?vue=` ; « Historique de commande » reste. /
  The two history buttons are removed; their sections are already on the page.
- **Module commun** `laboutik/affichage_des_ventes.py` : articles regroupés, règlements à afficher, moyens en clair, badges, noms des monnaies — lu par l'écran et par le ticket. Noms des monnaies par lot (`laboutik/plan_comptable.py` `noms_des_monnaies`, fedow_core puis l'ancien Fedow, la règle du rapport ; `nom_de_la_monnaie` l'utilise). /
  Shared module read by the screens and the receipt; currency names in batch, the report's rule.
- `comptabilite/presentation.py` : `montant_a_la_francaise_dans_l_unite` (euros, ou points / temps).
- Retirés : `LABELS_MOYENS_PAIEMENT_DB` (libellés d'une seule source : `nom_du_moyen_de_paiement`), la garde « lignes de plusieurs ventes » (impossible : la correction lit une seule vente), le gabarit `_ventes_historique_recap.html`, le CSS mort (`.cat-row`, `.poids-vol`, `.num-fort`, `.ventes-badge-moyen`) ; ajouté : CSS du badge de nature.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `liste_ventes`, `detail_vente`, `recap_en_cours`, `formulaire_correction`, `corriger_moyen_paiement`, `imprimer_ticket` ; `lignes_que_la_correction_deplace`, `_contexte_du_detail_d_une_vente` |
| `laboutik/affichage_des_ventes.py` | Nouveau : ce que l'écran et le ticket montrent d'une vente |
| `laboutik/plan_comptable.py` | `noms_des_monnaies` (par lot) |
| `comptabilite/presentation.py` | `montant_a_la_francaise_dans_l_unite` |
| `laboutik/templates/laboutik/partial/hx_liste_ventes.html`, `_ligne_vente.html`, `hx_detail_vente.html`, `hx_corriger_moyen_paiement.html`, `hx_recap_en_cours.html` | Liste, détail, correction, récap |
| `laboutik/templates/laboutik/partial/_ventes_historique_recap.html` | Supprimé |
| `laboutik/static/css/ventes.css` | Badge de nature, focus des lignes, CSS mort retiré |

## G-2b — Ticket de vente et réimpression

### Resume / Summary
- `formatter_ticket_vente(vente, operateur)` lit la vente : numéro de vente dans l'en-tête (« Vente n° 12 », sur les deux imprimantes ; il remplace l'ancien « Ticket: T-… »), articles du détail à l'écran (parts regroupées, quantité réelle), part offerte imprimée sous l'article, TOTAL = `Vente.total_ttc`, TVA par taux = sommes des HT et TVA figés sur les lignes, détail des règlements comme la liste (sans l'offert ; imprimé seulement avec au moins deux moyens), pied du lieu replié en lignes de 32 caractères. Plus aucun calcul ni `laboutik.reports`. /
  The receipt reads the sale: sale number in the header, grouped items, TOTAL = net sold, stored VAT, payments like the list, footer folded to 32 characters.
- `imprimer_ticket` reçoit `uuid_vente` (bouton « Ré-imprimer » du détail). L'écran de succès d'un paiement n'a que l'identifiant du paiement : la vente est celle de ses lignes. `ImpressionLog.uuid_transaction` reçoit l'uuid de la vente : la 2ᵉ impression d'une vente est un DUPLICATA. /
  Reprint by sale uuid; the print log counts per sale.
- `escpos_builder.py`, `sunmi_inner.py` : impriment `header["numero"]` et `detail_offert`.
- `LaboutikConfiguration.compteur_tickets` n'est plus incrémenté (il n'avait pas d'autre usage) ; le champ reste (affiché en lecture dans l'admin) jusqu'à la fiche H. /
  The ticket counter is no longer incremented; the field stays until sheet H.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/printing/formatters.py` | `formatter_ticket_vente(vente, operateur)`, pied replié |
| `laboutik/printing/escpos_builder.py`, `laboutik/printing/sunmi_inner.py` | Numéro de vente, part offerte |
| `laboutik/printing/tasks.py` | Commentaire : DUPLICATA compté par vente |

## G-2b-bis — Correction sous verrou, ticket daté de l'encaissement, imprimantes

### Resume / Summary
- **Correction sous verrou** : le formulaire poste `ancien_moyen` (champ caché). Dans la transaction de `corriger_moyen_paiement`, la vente d'origine est verrouillée (`select_for_update`) ; sous ce verrou, la ligne est relue, `raison_du_refus_de_correction` rejouée, le moyen actuel comparé à `ancien_moyen`, les lignes déplacées relues. Deux envois identiques ne font qu'une vente CORRECTION ; le second est refusé (« Ce paiement vient d'être corrigé … »). Un refus est rendu dans la zone du formulaire (`HX-Retarget`). Après une correction, le message reçoit le focus. /
  Correction under the original sale's lock; a duplicate submission is refused.
- **Ticket** : daté de l'encaissement, dans le fuseau du lieu ; un DUPLICATA imprime en plus « Imprimé le … ». Nom du tarif quand il diffère du produit, nom et date de l'événement. « Avoir n° » pour un avoir. Espace ordinaire sur le papier. Monnaie fédérée inconnue : « Monnaie fédérée ». Lignes vides du pied gardées. `legal.receipt_number` (mort) retiré. /
  Receipt dated at settlement; "Imprimé le" on a duplicate; price and event names.
- **Imprimantes** : une ligne de prix négatif (retour de consigne, moyen remboursé d'un X/Z) s'imprime avec son montant et son signe (ESC/POS et Sunmi) ; la Sunmi interne imprime « *** DUPLICATA *** » et le TOTAL même à 0 (fiche BUGS n°30 en partie traitée). /
  Negative lines printed with their sign; Sunmi prints DUPLICATE and a zero TOTAL.
- **Impression** : l'écran de fin de paiement envoie l'uuid de la vente (retrouvée par la clé d'idempotence du paiement, `_uuid_de_la_vente_du_paiement`) ; la route n'accepte plus que `uuid_vente`. Seule une vente ou un avoir réglé, fait sur un point de vente, s'imprime (`vente_imprimable_a_la_caisse`) ; « Ré-imprimer » n'est proposé que pour eux. /
  The success screen sends the sale uuid; only sales and credit notes on a point of sale print.
- **Accessibilité** : la ligne de la liste reste un `<tr>` ; la cellule du numéro porte un vrai bouton (`aria-expanded`, `aria-controls` vers la ligne du détail), focus visible.
- **Mineurs** : 404 sur un uuid illisible à l'écran de correction ; « — » quand une vente n'a aucun moyen ; clé d'unité normalisée ; règlements préchargés (détail, ticket) ; JS du récap simplifié ; branche morte retirée.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Correction sous verrou, `_refus_de_correction`, `vente_imprimable_a_la_caisse`, `_uuid_de_la_vente_du_paiement`, contextes de fin de paiement |
| `laboutik/serializers.py` | `CorrectionPaiementSerializer.ancien_moyen` |
| `laboutik/affichage_des_ventes.py` | « Monnaie fédérée », date de l'événement, « — », clé d'unité |
| `laboutik/printing/formatters.py`, `escpos_builder.py`, `sunmi_inner.py` | Dates, noms, avoir, lignes négatives, DUPLICATA Sunmi, TOTAL à 0 |
| gabarits `hx_corriger_moyen_paiement.html`, `hx_correction_succes.html`, `hx_detail_vente.html`, `_ligne_vente.html`, `hx_liste_ventes.html`, `hx_recap_en_cours.html`, `hx_return_payment_success.html` ; `ventes.css` | Formulaire, focus, bouton du numéro, impression par vente |
| `TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md` | n°30 en partie traité |

## Tests réécrits, ajoutés ou retirés
| Test | Raison |
|---|---|
| `test_menu_ventes.py` (réécrit, schéma dédié `test_menu_ventes`, ventes par le service de vente) | Liste, détail, correction et récap sur la `Vente` : fiche tests 7, 8, 9, Q-G13, Q-G14, filtres, pagination par numéro, requêtes constantes, correction (montant affiché = montant déplacé, deux lignes, sans identifiant de paiement, correction d'une correction, détail re-rendu), ventes dérivées, tirage en deux parts, billets de deux événements, monnaie de l'ancien Fedow, offert hors des moyens. Les anciens tests en base partagée (`TestDetailVente`, `TestParamsVentesPropages`) et sur les lignes écrites à la main sont remplacés. |
| `test_menu_ventes.py` `test_historique_par_moyen…`, `test_historique_par_article…` → `test_recap_montre_les_reglements…`, `test_recap_montre_le_detail_des_ventes…`, `test_recap_n_a_plus_que_le_bouton_historique_de_commande` | Les historiques du récap sont retirés ; leurs sections sont sur la page. |
| `test_lecteurs_montants_entiers.py` `test_detail_vente_sans_bouton_corriger_ligne_sans_vente` → `test_correction_refusee_ligne_sans_vente` | Le détail s'ouvre par une vente : une ligne sans vente n'y apparaît plus ; le refus est vérifié sur la route. |
| `test_lecteurs_montants_entiers.py` `test_detail_vente_sans_bouton_corriger_vente_en_attente` | Adresse par vente ; 200 avec le statut « En attente ». |
| `test_vente_en_points.py` `test_le_detail_d_une_vente_repartie_tombe_juste` | Un seul article de 10,50 € (les parts forment un article). |
| `test_vente_en_points.py` tests de liste / détail / ticket | Adresse par vente, espaces insécables normalisées, `formatter_ticket_vente(vente, …)` ; le ticket « sans monnaie connue » lit une vraie vente. |
| `test_caisse_ecrit_la_vente.py` `test_correction_de_lignes_de_deux_ventes_refusee` → `test_correction_de_lignes_de_deux_ventes_ne_touche_que_la_vente_cliquee` | La correction lit la vente, plus l'identifiant de paiement : deux ventes au même identifiant ne sont plus mêlées. |
| `test_ticket_client_imprime.py` (réécrit) | Le ticket lit la vente : un article pour les parts, TVA figée, offert sous l'article, numéro de vente, pied ≤ 32, détail des règlements dans l'ordre de la liste (comptoir puis cashless), libellé d'une monnaie inconnue = nom du moyen ; fiche test 10 (réimpression par vente, DUPLICATA) ; bouton « Ré-imprimer » du détail. `test_le_detail_suit_l_ordre_de_la_cascade` → `…_ordre_de_la_liste_des_ventes` ; « Monnaie fédérée » → « En ligne: Stripe fédéré ». |
| G-2b-bis : `test_menu_ventes.py` (deux envois → une correction, uuid illisible 404, bouton du numéro, « Ré-imprimer » sur une vente pas sur une correction, « — » sans moyen, focus du message) ; `test_ticket_client_imprime.py` (paiement puis Imprimer : DUPLICATA sur la vente ; vente en ligne refusée ; date d'encaissement et « Imprimé le » ; tarif ; événement et date ; avoir négatif ; ligne de prix négatif ; Sunmi DUPLICATA et TOTAL 0 ; offert hors du détail ; lignes vides du pied ; « Monnaie fédérée » ; « Espèces » absent d'un ticket à un moyen) ; `test_vente_en_points.py` (`vente-total` et `vente-moyens` exacts) | Décisions de la relecture de G-2b. |
| `tests/e2e/test_caisse_liste_detail_ventes.py` (nouveau) | Liste, détail déplié et réimpression d'une vente monnaie locale + CB, dans le navigateur. |

## Chaînes i18n nouvelles (texte source français) / New i18n strings
« Vente », « Correction », « Carte vidée », « Corrigée par la vente n° %(numero)s », « Remboursée par l'avoir n° %(numero)s », « Vente liée n° %(numero)s », « Vente introuvable », « Vente n° », « N° », « Nature », « Moyens », « Ventes du service en cours », « Détail de la vente n° %(numero)s », « Statut », « Articles de la vente », « Qté », « Monnaie », « Montant », « Règlements », « Vente liée : n° %(numero)s (%(nature)s) », « Corriger : %(moyen)s », « Règlement %(moyen)s », « Avoir n° », « Monnaie fédérée », « Ce paiement vient d'être corrigé (moyen actuel : %(moyen)s). Rouvrez la vente pour le corriger à nouveau. » (« Imprimé le » est écrit en dur dans les imprimantes, comme « DUPLICATA »). Le workflow i18n est à lancer par le mainteneur. Retirées des gabarits : « Lignes de caisse (hors ventes en ligne, recharges comprises) », « Lignes de caisse », « Historique de vente », « Historique de vente par article ».

---

## Comment tester (a la main) / Manual test

### Test 1 — liste et détail
1. À la caisse, vendre 3 jus : 5,00 € sur une carte cashless, le reste par CB.
2. Ventes → « Historique de commande » : une ligne, badge « Vente », total 10,50 €, « 5,50 € Carte bancaire + 5,00 € <monnaie> ».
3. Cliquer la ligne (ou Tab puis Entrée) : un article « 3 », deux règlements, un seul bouton « Corriger : Carte bancaire ».

### Test 2 — correction, puis correction de la correction
1. Vendre une pinte et un demi en espèces ; ouvrir le détail, « Corriger : Espèces » : l'écran affiche « Règlement Espèces 8,00 € ».
2. Corriger en CB : le détail se ré-affiche avec le message et « Corrigée par la vente n° X ».
3. « Corriger : Carte bancaire » → chèque : une 2ᵉ vente CORRECTION apparaît dans la liste, badge « Correction ».

### Test 3 — ticket
1. Depuis un terminal qui a une imprimante, ré-imprimer une vente : « Vente n° X » en tête, TOTAL = total de la vente.
2. Ré-imprimer une 2ᵉ fois : « *** DUPLICATA *** ».

### Vérifs DB / Playwright
- `ImpressionLog.objects.filter(type_justificatif="VENTE").values("uuid_transaction", "is_duplicata")` : l'uuid de la vente, faux puis vrai.
- E2E : `make e2e ARGS="tests/e2e/test_caisse_liste_detail_ventes.py"`.

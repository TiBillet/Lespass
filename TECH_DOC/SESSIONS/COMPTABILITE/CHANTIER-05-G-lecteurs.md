# Chantier 05-G — Tous les lecteurs passent sur le nouveau modèle

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D14, D18 à D20, D24, D27, D28
> Effort : 4,75 j (3 sessions : §2, §3, §4, plus les tests existants du §6) — Dépend de : F.
> **Migrations : oui** (`ImpressionLog.cloture` déplacée, §2.1, deux fichiers).
> À la fin de la fiche, **plus aucun lecteur** ne calcule d'argent depuis `amount`,
> `qty` ou `payment_method` d'une ligne, et plus aucun code de production n'écrit ni ne
> lit `laboutik.ClotureCaisse` (seul son admin reste, en lecture, jusqu'à H).

## 1. La règle pour chaque lecteur

| Il lisait… | Il lit désormais… |
|---|---|
| `amount × qty`, `ligne.total()`, `int(...)` | `ligne.total_ttc` / `total_ht` / `total_tva` (ou les totaux de la `Vente`) |
| `ligne.payment_method` pour savoir « payé comment » | `vente.reglements` |
| un regroupement par `uuid_transaction` | la `Vente` |
| `laboutik.ClotureCaisse` / `RapportComptableService` (caisse) | `comptabilite.ClotureCaisse` / `RapportDesVentes` |
| `calculer_hmac` par ligne, `verifier_chaine` | `verifier_chaine_ventes` + chaîne des clôtures |

## 2. Session G-1 — clôture de la caisse, gardes, archive, intégrité

| Lecteur | Fichier | Changement |
|---|---|---|
| Bouton « Clôturer » | `laboutik/views.py` ~l.2651-2725 | crée la J **unique** (fiche F §3.1) |
| Ticket X, rapport temps réel, récap en cours | `laboutik/views.py` ~l.2981, ~l.3780, ~l.3856 | `RapportDesVentes` non stocké |
| Sortie de caisse (solde) | ~l.3569 | section « caisse espèces » du rapport |
| Auto-clôture et tâches H/M/A de la caisse | `laboutik/tasks.py` ~l.441-505, ~l.669-800 | retirées au profit de `comptabilite/tasks.py` (filet à l'heure de fermeture + 2 h, D28) |
| **Garde « correction interdite après clôture »** | `ligne_couverte_par_cloture` (`laboutik/integrity.py` ~l.187), utilisée ~l.4198 et ~l.11061 | une vente est couverte si son `numero` ≤ `numero_derniere_vente` de la dernière J (sinon, après G, plus rien n'alimente la garde et les corrections redeviennent possibles après un Z) |
| Stock | FK `MouvementStock.cloture` (`inventaire/models.py` ~l.195) | **FK morte** : `rattacher_a_cloture` (`inventaire/services.py` ~l.209) n'a **aucun appelant en production** (seul `tests/pytest/test_inventaire.py` ~l.765). **Rien en G** ; la FK, la fonction et son test sont retirés en H avec l'ancienne clôture |
| Journal d'impression | `ImpressionLog.cloture` (`laboutik/models.py` ~l.1462), lu et écrit par `laboutik/printing/tasks.py` ~l.86-125 (détection du DUPLICATA d'un Z par `cloture__uuid`) | FK déplacée vers `comptabilite.ClotureCaisse` (§2.1) ; la tâche cherche la clôture dans `comptabilite.ClotureCaisse` (sinon `DoesNotExist` avalé : trace LNE perdue en silence) |
| Tickets X et Z imprimés | `laboutik/printing/formatters.py` (~l.522-620), `escpos_builder.py`, `sunmi_inner.py` | sections « essentiel » du rapport unique |
| **Archive fiscale LNE** | `laboutik/archivage.py` (~l.135-179) | exporte les **ventes** (en-tête, articles avec `total_ht` / `total_tva` **stockés**, règlements, empreintes) et les clôtures, **toutes origines** |
| Vérification d'intégrité | `laboutik/management/commands/verify_integrity.py`, `comptabilite/management/commands/verify_clotures.py` (~l.110) | `verifier_chaine_ventes` + chaîne des clôtures ; code de sortie ≠ 0 si anomalie |
| Admin des clôtures | `Administration/admin/laboutik.py` ~l.1140, `comptabilite/admin.py` ~l.277 | la fiche de clôture unique affiche les sections ; l'ancienne reste consultable jusqu'à H |

### 2.1 La FK de clôture des impressions (migrations)

`ImpressionLog.cloture` pointe vers `laboutik.ClotureCaisse`. Après G, plus aucune
clôture n'y est créée : elle passe vers `comptabilite.ClotureCaisse`. Les valeurs
existantes pointent vers d'anciennes clôtures (dev uniquement) : on les remet à vide,
puis on change la cible. Deux migrations **séparées** (PIEGES 9.113 : jamais DDL et
DML dans la même) :

1. `RunPython` : `cloture = NULL` (les impressions de Z anciennes perdent leur lien :
   dev, accepté) ;
2. `AlterField` : nouvelle cible `comptabilite.ClotureCaisse` (même `null`, même
   `on_delete`).

## 3. Session G-2 — écrans et tickets de la caisse

| Lecteur | Fichier | Changement |
|---|---|---|
| Liste des ventes | `laboutik/views.py` `liste_ventes` ~l.3933-3999 | une ligne par `Vente` : n°, heure, total, **moyens en clair** (« 5,00 € monnaie locale + 5,50 € CB »), nombre d'articles ; filtre par moyen = ventes ayant un règlement de ce moyen. Adapter `tests/pytest/test_menu_ventes.py` |
| Détail d'une vente | `detail_vente` ~l.4137-4184, `hx_detail_vente.html` | articles (qté, PU, total) puis règlements |
| Écran « corriger le moyen » | ~l.10935, `hx_corriger_moyen_paiement.html` | montant du **règlement** à corriger |
| Ticket de vente | `laboutik/printing/formatters.py` ~l.95-130, `cascade_detail` ~l.285-341 | lit la vente : **numéro de vente** (D3), articles regroupés, règlements (détail imprimé si au moins deux moyens, D20 du chantier 04) |
| Réimpression | chemin par `uuid_transaction` ; la mention « DUPLICATA » existe déjà (`laboutik/printing/tasks.py` ~l.86-101, compte des impressions par `uuid_transaction`) | par `Vente` : le compte des impressions se fait par l'uuid de la vente (le champ `ImpressionLog.uuid_transaction` reçoit l'uuid de la vente) |

## 4. Session G-3 — admin, totaux client, exports, API, ancien LaBoutik

**Fiche « Vente » dans l'admin (nouvelle, lecture seule)** — le cœur du back-office :

- Liste : n°, date, origine (libellé), client (e-mail ou carte), total, moyens en
  badges, statut ; filtres date, origine, point de vente, moyen, nature ; recherche par
  n°, e-mail, carte. Filtre **« À vérifier »** : ventes `EN_ATTENTE` depuis plus d'une
  heure, ventes avec écart d'encaissement (D26).
- Fiche : en-tête, inline **Articles** (produit, qté, PU, offert, total, TVA), inline
  **Règlements** (moyen, monnaie, montant, référence), badge « Intégrité OK ».
- Action : **« Avoir total »** de la vente (reprend `emettre_avoir` de
  `Administration/admin_tenant.py` ~l.2059-2105), avec le champ **« Remboursé par »**
  (D27, fiche D ; absent si l'article est entièrement offert) ; liens vers la vente liée
  et vers Stripe. Action **« Rejouer l'encaissement »** sur une vente Stripe
  `EN_ATTENTE` du filtre « À vérifier » : un simple `paiement_stripe.save()` (T4, fiche
  D). **« Avoir sur un article »**
  (quantité partielle) arrive en **H** : avant H, un article payé avec deux moyens est
  coupé en parts à quantité fractionnaire, et « 1 jus sur 3 » n'y a pas de sens.
- Menu « Ventes & comptabilité » : **Ventes**, puis rapport / clôtures, puis plan
  comptable. « Entries » reste jusqu'à H.
- Skill `unfold` (styles en ligne, `data-testid`, accessibilité).

**Autres lecteurs** :

| Lecteur | Fichier | Changement |
|---|---|---|
| `Reservation.total_paid()` | `BaseBillet/models.py` ~l.2921 | Σ `total_ttc`. Conséquence : un billet **entièrement offert** (FREE à prix non nul, caisse ou admin) n'a plus rien à rembourser → son annulation ne crée plus d'avoir d'argent ; seule la trace `FREE −X` (fiche D) reste. Le test A′ `test_annuler_un_billet_caisse_offert_cree_un_avoir` change **ici** (A′ §4 ; validé le 2026-09-29) |
| `Paiement_stripe.total()` / `articles()` | ~l.3489, ~l.3509 | Σ `total_ttc` des lignes du paiement (avoirs compris) ; cas `TRANSFERT` gardé. La ligne d'écart d'encaissement n'a pas de `paiement_stripe` (fiche D) : le montant réellement encaissé se lit dans `montant_encaisse` |
| Fiche utilisateur admin | `Administration/admin_tenant.py` ~l.1176 | Σ `total_ttc` |
| Totaux booking / panier / gratuit-payant | `booking/models.py` ~l.578-590, `booking/tasks.py` ~l.51, `services_commande.py` ~l.300/321, `validators.py` ~l.290 | Σ `total_ttc` |
| Remboursement Stripe | `PaiementStripe/utils.py` ~l.36-44 | Σ `total_ttc` des articles remboursés ; corriger le commentaire du seuil (« 1 € » alors que le code compare à 1 centime) |
| Facture d'adhésion | `BaseBillet/tasks.py` ~l.160-175, `invoice.html` | totaux de la vente (35 €, plus la 1ʳᵉ part seule) |
| Annulation d'adhésion | `cancel_form.html` ~l.40 | `total_ttc` |
| Exports de clôture (CSV, Excel, PDF, e-mail) | `laboutik/csv_export.py`, `laboutik/excel_export.py` (~l.45), `laboutik/pdf.py`, `comptabilite/csv_export.py`, `excel_export.py`, `pdf.py`, gabarits `rapport_comptable.html`, `cloture_rapport_pdf.html` | **un seul jeu**, sur `rapport_json` de la clôture unique ; l'autre retiré en H |
| Export des lignes | `Administration/importers/lignearticle_exporter.py` | colonnes `total_ttc`, `total_ht`, `total_tva`, n° de vente |
| API v2 | `api_v2/serializers.py` ~l.798 | montants depuis les champs entiers |
| Crowds (fonds disponibles) | `crowds/views.py` `allocate` ~l.345-357 | seul le calcul de montant change : Σ `total_ttc` (la logique reste, tronc §9) |
| Données de démo | `laboutik/management/commands/create_test_pos_data.py` ~l.1752 | rapport unique |
| Envoi vers l'ancien LaBoutik | `ApiBillet/serializers.py` `LigneArticleSerializer` ~l.1296 via `BaseBillet/tasks.py` `send_sale_to_laboutik` ~l.1029 (appelé ~l.2053, ~l.2324 de `BaseBillet/views.py`, `triggers.py` ~l.235, ~l.315, `admin_tenant.py` ~l.3107) | **un envoi par ligne, comme aujourd'hui** (`trigger_A/B`, anti-doublon `sended_to_laboutik`, D24) : la tâche reçoit toujours l'uuid de la ligne ; le sérialiseur lit `payment_method`, `asset`, `wallet` dans **le** règlement de la vente (les ventes envoyées n'en ont qu'un : le QR / NFC, seul à plusieurs règlements, n'envoie plus rien depuis C). Mêmes champs, **mêmes charges utiles** qu'aujourd'hui. Cette forme survit à H (retrait de `payment_method`, `asset`, `wallet` de la ligne) — détail T10 ci-dessous |

## 5. Tests

Fichiers : `tests/pytest/test_lecteurs_montants_entiers.py`, `tests/pytest/test_admin_vente.py`,
`tests/pytest/test_archive_lne_ventes.py` ; E2E `tests/e2e/test_caisse_liste_detail_ventes.py`.
**Schéma dédié** (tronc §8.5) : les tests 1, 2, 3 (ils créent une J) et 4, 5, 6 (archive,
vérification d'intégrité sur une vente altérée) ; les autres en base partagée.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_bouton_cloturer_cree_la_cloture_unique` | plus de `laboutik.ClotureCaisse` créée |
| 2 | `test_correction_refusee_apres_la_j_unique` | la garde lit la J unique |
| 3 | `test_fk_de_cloture_vers_la_cloture_unique` | un `ImpressionLog` accepte une `comptabilite.ClotureCaisse` ; le ticket Z réimprimé est marqué DUPLICATA |
| 4 | `test_archive_lne_tva_stockee_175` | aujourd'hui 174 |
| 5 | `test_archive_lne_contient_tireuse_et_en_ligne` | |
| 6 | `test_verify_integrity_detecte_article_modifie` | sortie ≠ 0 |
| 7 | `test_liste_des_ventes_une_ligne_moyens_en_clair` | |
| 8 | `test_detail_vente_quantites_reelles` | « 3 » jus (pas « 2 » et « 1 ») |
| 9 | `test_ecran_corriger_moyen_affiche_le_montant_du_reglement` | 5,50 € |
| 10 | `test_ticket_vente_numero_et_duplicata` | n° de vente imprimé ; réimpression de la **vente** « DUPLICATA » |
| 11 | `test_reservation_total_paid_1050` | aujourd'hui 1049 |
| 11b | `test_billet_entierement_offert_total_paid_zero_avoir_free_seul` | billet FREE à 1500 : `total_paid()` = 0 ; annulation → aucun règlement d'argent, un règlement `FREE −1500` |
| 12 | `test_facture_adhesion_multi_moyens_35_euros` | aujourd'hui 20,00 |
| 13 | `test_remboursement_stripe_montant_depuis_total_ttc` | |
| 14 | `test_admin_fiche_vente_articles_et_reglements` | lecture seule |
| 15 | `test_admin_avoir_total_rembourse_par_especes` | vente CB 1050 → vente `AVOIR` −1050, un règlement espèces −1050 |
| 16 | `test_admin_filtre_ventes_a_verifier` | |
| 16b | `test_admin_rejouer_l_encaissement` | vente Stripe `EN_ATTENTE` (paiement `PAID`) → action → `REGLEE`, un règlement |
| 17 | `test_export_lignes_colonnes_entieres` | |
| 18 | `test_envoi_ancien_laboutik_charge_utile_inchangee` | **non-régression** : vente à un règlement → même charge utile avant et après ; panier 2 billets + adhésion payé Stripe → **3 messages**, identiques à aujourd'hui |
| 19 | `test_aucun_lecteur_ne_multiplie_amount_par_qty` | garde sur les fichiers des §2-4 |
| E2E | `test_caisse_liste_et_detail_d_une_vente_nfc_plus_cb` | liste, détail, ticket |

Vus rouges : 2 (garde muette après bascule du bouton), 3 (FK vers l'ancienne table),
4, 7-9, 11, 11b, 12, 14-17, 16b, 19 sur le code actuel ; 1, 5, 6, 13 une fois le
nouveau lecteur branché à vide ; 10 : rouge pour le numéro de vente (la mention
DUPLICATA existe déjà). 18 : vert avant et après (noté).

Mutations : la garde relit l'ancienne clôture (2) ; la tâche d'impression cherche la
clôture dans `laboutik` (3) ; l'archive recalcule la TVA (4) ; `liste_ventes` groupe
par `uuid_transaction` (7) ; `total_paid` repasse par `int(amount×qty)` (11) ; compte
des impressions par `uuid_transaction` de la ligne (10) ; moyen lu dans la ligne au
lieu du règlement (18).

## 6. Tests existants à réécrire

Ils lisent l'ancienne clôture caisse, son moteur ou ses exports, ou les écrans
réécrits. Vérifiés au 2026-09-28 par `rg -l "laboutik\.(reports|tasks|archivage|csv_export|excel_export|integrity)|ClotureCaisse|liste_ventes|detail_vente|total_paid|rattacher_a_cloture" tests/pytest/` :

| Fichier | Quoi |
|---|---|
| `tests/pytest/test_cloture_caisse.py`, `test_cloture_enrichie.py`, `test_cloture_export.py`, `test_cloture_colonne_poids.py` | le bouton crée la J unique ; exports sur `rapport_json` de la clôture unique |
| `tests/pytest/test_ventes_remontent_au_ticket_z.py`, `test_rapports_cheque.py`, `test_hors_argent_offerts.py`, `test_vente_en_points.py`, `test_remboursement_especes_trace_comptable.py`, `test_paiement_complementaire.py` (~l.308) | lisent `laboutik.reports` / `laboutik.ClotureCaisse` → `RapportDesVentes` et la clôture unique |
| `tests/pytest/test_rapport_temps_reel.py` | ticket X et récap en cours sur `RapportDesVentes` |
| `tests/pytest/test_archivage_fiscal_lne.py`, `test_total_ht_ligne.py` (~l.245) | archive LNE par ventes |
| `tests/pytest/test_integrity_hmac.py` | `verify_integrity` passe par `verifier_chaine_ventes` ; les tests du HMAC par ligne restent jusqu'à H |
| `tests/pytest/test_menu_ventes.py` | liste et détail par `Vente` |
| `tests/pytest/test_stripe_refund.py`, `test_mail_annulation_booking.py` | `total_paid()` sur `total_ttc` : valeurs attendues à relire (normalement inchangées) |
| `tests/pytest/test_caracterisation_annulations.py` (A′) | `test_annuler_un_billet_caisse_offert_cree_un_avoir` : plus d'avoir d'argent (A′ §4) |

Chaque réécriture est listée dans le CHANGELOG avec sa raison.

`make e2e` complet en fin de fiche. CHANGELOG :
`CHANGELOG/2026-MM-JJ-montants-entiers-G-lecteurs.md`.

## Machine à états — compléments obligatoires

Source : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) §5 (trous T…). Les tests de
caractérisation de la fiche A′ doivent rester verts pendant cette fiche.

| Trou | À faire dans cette fiche | Test |
|---|---|---|
| T3 | **Remboursements vers l'ancien LaBoutik** : `send_refund_to_laboutik` (déclenché par chaque avoir, `BaseBillet/signals.py` ~l.144-160) utilise `LigneArticleSerializer` (`payment_method`, `asset`, `wallet`). Même traitement que l'envoi des ventes : moyen, `asset`, `wallet` lus dans le règlement de la vente `AVOIR`. | `test_envoi_remboursement_ancien_laboutik_charge_utile_inchangee` |
| T10 | Ancien LaBoutik : **un envoi par ligne** (comme aujourd'hui, `trigger_A/B`, anti-doublon `sended_to_laboutik`) ; moyen / `asset` / `wallet` lus dans **le** règlement de la vente (un seul pour toute vente envoyée : l'envoi QR / NFC est débranché en C, décision du mainteneur 2026-09-29). Appliqué dans le tableau §4. | test 18 (panier 2 billets + adhésion → 3 messages identiques) |
| T11 | **Tranché (D29)** : le nouveau bouton « Clôturer » **garde** ses deux effets actuels (commandes de table `OPEN` → `CANCEL`, tables libérées, `laboutik/views.py` ~l.2727-2737) ; le Z automatique ne les fait **pas** (comme l'auto-clôture actuelle). | `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` (A′) reste vert |
| T21 | Décisions prises sur `amount × qty` hors du tableau : `Booking.to_pay` (`booking/booking_engine.py` ~l.722), `TicketCreator` (~l.289), montant envoyé à `stripe.Refund` (`PaiementStripe/utils.py` ~l.39-44). Réécrites sur `total_ttc` en gardant **la même décision**. | `test_decision_stripe_ou_gratuit_billets_et_booking` (A′) |

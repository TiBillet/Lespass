# Chantier 05-G — Tous les lecteurs passent sur le nouveau modèle

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D18 à D20, D24
> Effort : 2,5 j (3 sessions : §2, §3, §4) — Dépend de : F. Pas de migration.
> À la fin de la fiche, **plus aucun lecteur** ne calcule d'argent depuis
> `amount`, `qty` ou `payment_method` d'une ligne. Inventaire complet : diagnostic §2.

## 1. La règle pour chaque lecteur

| Il lisait… | Il lit désormais… |
|---|---|
| `amount × qty`, `ligne.total()`, `int(...)` | `ligne.total_ttc` / `total_ht` / `total_tva` (ou les totaux de la `Vente`) |
| `ligne.payment_method` pour savoir « payé comment » | `vente.reglements` |
| un regroupement par `uuid_transaction` | la `Vente` |
| `laboutik.ClotureCaisse` / `laboutik/reports.py` | `comptabilite.ClotureCaisse` / `comptabilite/rapport.py` |
| `calculer_hmac` par ligne, `verifier_chaine` | `verifier_chaine_ventes` + chaîne des clôtures |

## 2. Session G-1 — clôture de la caisse, archive fiscale, intégrité

| Lecteur | Fichier | Changement |
|---|---|---|
| Bouton « Clôturer » de la caisse | `laboutik/views.py` ~l.2651-2725 | crée la clôture **unique** J (fiche F) ; `point_de_vente` informatif |
| Auto-clôture et tâches H/M/A de la caisse | `laboutik/tasks.py` ~l.441-505, ~l.669-800 | retirées au profit de `comptabilite/tasks.py` ; l'auto-clôture cherche la première **vente** du lieu (toutes origines), plus seulement `LABOUTIK` |
| Tickets X et Z imprimés | `laboutik/printing/formatters.py` (~l.522-620), `escpos_builder.py`, `sunmi_inner.py` | lisent le rapport unique (sections du §2 de F : CA, règlements par moyen et monnaie, offerts, points, caisse espèces) |
| **Archive fiscale LNE** | `laboutik/archivage.py` (~l.135-179) | exporte les **ventes** (en-tête, articles avec `total_ht`/`total_tva` **stockés**, règlements, empreintes) et les clôtures, **toutes origines** ; plus aucun `int(amount×qty)` |
| Vérification d'intégrité | `laboutik/management/commands/verify_integrity.py` | `verifier_chaine_ventes` + chaîne des clôtures ; code de sortie ≠ 0 si anomalie |
| `verify_clotures` | `comptabilite/management/commands/verify_clotures.py` | chaîne des clôtures (plus de `hash_lignes`) |

## 3. Session G-2 — écrans et tickets de la caisse

| Lecteur | Fichier | Changement |
|---|---|---|
| Liste des ventes | `laboutik/views.py` `liste_ventes` ~l.3933-3999 | une ligne par `Vente` : n°, heure, total, **moyens en clair** (« 5,00 € monnaie locale + 5,50 € CB »), nombre d'articles (plus le nombre de parts) ; filtre par moyen = ventes ayant un règlement de ce moyen |
| Détail d'une vente | `detail_vente` ~l.4137-4184, `hx_detail_vente.html` | articles (qté réelle, PU, total) puis règlements ; plus de `qty|floatformat:0` qui affiche « 2 » et « 1 » |
| Écran « corriger le moyen » | ~l.10935, `hx_corriger_moyen_paiement.html` | affiche le **montant du règlement** à corriger (5,50 €), plus le prix unitaire |
| Ticket de vente imprimé | `laboutik/printing/formatters.py` ~l.95-130, `cascade_detail` ~l.285-341 | lit la vente : articles regroupés, puis règlements (règle D20 du chantier 04 conservée : détail imprimé si au moins deux moyens) |
| Réimpression | chemin de réimpression par `uuid_transaction` | par `Vente` |

## 4. Session G-3 — admin, totaux affichés au client, exports, API, ancien LaBoutik

**Fiche « Vente » dans l'admin (nouvelle, lecture seule)** — le cœur du back-office simple :

- Liste : n°, date, origine (libellé), client (e-mail ou carte), total, moyens en
  badges, statut ; filtres par date, origine, point de vente, moyen, nature ;
  recherche par n°, e-mail, carte.
- Fiche : en-tête, puis inline **Articles** (produit, qté, PU, offert, total, TVA), puis
  inline **Règlements** (moyen, monnaie, montant, référence). Badge « Intégrité OK ».
- Actions : **« Avoir total »** et **« Avoir sur un article »** (reprennent
  `emettre_avoir` de `Administration/admin_tenant.py` ~l.2101, désormais sur la vente,
  fiche D) ; lien vers la vente liée (avoir, correction) ; lien Stripe si règlement Stripe.
- Ventes `EN_ATTENTE` depuis plus d'une heure : filtre dédié (paiements Stripe en
  anomalie, fiche D §2).
- Menu « Ventes & comptabilité » : **Ventes** en premier, puis le rapport / les clôtures,
  puis le plan comptable. « Entries » reste visible jusqu'à H.
- Skill `unfold` pour l'admin (styles en ligne, `data-testid`, accessibilité).

**Autres lecteurs :**

| Lecteur | Fichier | Changement |
|---|---|---|
| `Reservation.total_paid()` | `BaseBillet/models.py` ~l.2921 | Σ `total_ttc` (compte client, e-mails, admin) |
| `Paiement_stripe.total()` / `articles()` | ~l.3489, ~l.3509 | Σ `total_ttc` ; cas `TRANSFERT` gardé tel quel |
| Fiche utilisateur admin | `Administration/admin_tenant.py` ~l.1176 | Σ `total_ttc` |
| Totaux booking / panier / choix gratuit-payant | `booking/models.py` ~l.578-590, `services_commande.py` ~l.300/321, `validators.py` ~l.290 | Σ `total_ttc` (lignes créées par le service, fiche D) |
| Montant d'un remboursement Stripe | `PaiementStripe/utils.py` ~l.36-44 | Σ `total_ttc` des articles remboursés (plus `amount × qty`) ; seuil minimal : corriger le commentaire (« 1 € » alors que le code compare à 1 centime) |
| Facture d'adhésion | `BaseBillet/tasks.py` ~l.160-175, `invoice.html` | totaux de la vente (plus seulement la 1ʳᵉ part) |
| Exports de la clôture (CSV, Excel, PDF, e-mail) | `laboutik/csv_export.py`, `excel_export.py`, `pdf.py`, `comptabilite/csv_export.py`, `excel_export.py`, `pdf.py`, gabarits `rapport_comptable.html`, `cloture_rapport_pdf.html` | **un seul jeu** d'exports, sur `rapport_json` de la clôture unique ; l'autre est retiré en H |
| Export des lignes | `Administration/importers/lignearticle_exporter.py` | colonnes `total_ttc`, `total_ht`, `total_tva`, n° de vente ; `qty` à 3 décimales |
| API v2 | `api_v2/serializers.py` ~l.798 | montants depuis les champs entiers |
| Crowds (fonds disponibles) | `crowds/views.py` ~l.345-357 | Σ `total_ttc` |
| Envoi vers l'ancien LaBoutik | `ApiBillet/serializers.py` ~l.1296 via `BaseBillet/tasks.py` ~l.1029 | le moyen de paiement est lu dans le **règlement** de la vente de la ligne (D24) ; format envoyé inchangé |

## 5. Tests

Fichiers : `tests/pytest/test_lecteurs_montants_entiers.py` (un test par lecteur,
sur l'exemple fil rouge ou une vente fabriquée), `tests/pytest/test_admin_vente.py`,
`tests/pytest/test_archive_lne_ventes.py` (schéma dédié) ; E2E
`tests/e2e/test_caisse_liste_detail_ventes.py`.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_bouton_cloturer_cree_la_cloture_unique` | `comptabilite.ClotureCaisse` J, plus de `laboutik.ClotureCaisse` créée |
| 2 | `test_archive_lne_tva_stockee_175` | TVA de l'archive = 175 (aujourd'hui 174) |
| 3 | `test_archive_lne_contient_tireuse_et_en_ligne` | toutes origines |
| 4 | `test_verify_integrity_detecte_article_modifie` | code de sortie ≠ 0 |
| 5 | `test_liste_des_ventes_une_ligne_moyens_en_clair` | 1 ligne, « monnaie locale + CB » |
| 6 | `test_detail_vente_quantites_reelles` | « 3 » jus, pas « 2 » et « 1 » |
| 7 | `test_ecran_corriger_moyen_affiche_le_montant_du_reglement` | 5,50 € |
| 8 | `test_ticket_vente_depuis_la_vente` | articles regroupés + règlements |
| 9 | `test_reservation_total_paid_1050` | aujourd'hui 1049 |
| 10 | `test_paiement_stripe_total_entier` | |
| 11 | `test_facture_adhesion_multi_moyens_35_euros` | 35,00 (aujourd'hui 20,00) |
| 12 | `test_remboursement_stripe_montant_depuis_total_ttc` | |
| 13 | `test_admin_fiche_vente_articles_et_reglements` | inlines présents, lecture seule |
| 14 | `test_admin_action_avoir_total_cree_vente_avoir` | |
| 15 | `test_export_lignes_colonnes_entieres` | |
| 16 | `test_envoi_ancien_laboutik_moyen_depuis_le_reglement` | charge utile identique à aujourd'hui sur une vente QR |
| 17 | `test_aucun_lecteur_ne_multiplie_amount_par_qty` | garde (grep des fichiers listés au §2-4) |
| E2E | `test_caisse_liste_et_detail_d_une_vente_nfc_plus_cb` | vente fil rouge : liste, détail, ticket |

Vus rouges : 2, 5-7, 9, 11, 13-17 sur le code actuel ; 1, 3, 4, 8, 10, 12 une fois
le nouveau lecteur branché à vide.

Mutations : l'archive recalcule la TVA (2) ; `liste_ventes` groupe par
`uuid_transaction` (5) ; `total_paid` repasse par `int(amount×qty)` (9) ; l'envoi
LaBoutik lit `ligne.payment_method` (16, après que la fiche H l'a retiré : noter).

`make e2e` complet en fin de fiche. CHANGELOG :
`CHANGELOG/2026-MM-JJ-montants-entiers-G-lecteurs.md`.

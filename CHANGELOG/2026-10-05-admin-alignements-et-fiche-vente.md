# Admin : blocs alignés sur la colonne, fiche « Vente » lisible, lignes retirées de l'admin / Admin: aligned blocks, readable "Sale" page, lines removed from the admin

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Les gabarits posés avant ou après un formulaire ou une liste de l'admin n'ont plus de marge intérieure horizontale (`p-4`, `px-4`) : leurs cartes s'alignent sur les blocs de champs et la barre d'enregistrement (x=304→1409 en 1440 px). Seul un espacement vertical reste (`mb-6` avant un formulaire, `mt-6` après, `mb-4` au-dessus d'une liste).
- Les écrans « Émettre un avoir » / « Avoir total », « Avoir sur un article », « Rejouer l'encaissement » et « Annuler et rembourser » prennent toute la colonne, comme un bloc de champs Unfold (titre gris, carte bordée, lignes en pointillés, libellé à gauche). Leurs champs utilisent les widgets Unfold.
- Un bloc de champs ne déborde plus de la colonne : `min-width: 0` sur `fieldset.module`, listes `filter_horizontal` souples. Fiche d'un utilisateur : blocs `min-w-0`, titres sans marge négative, bouton « cartes et portefeuille » qui passe à la ligne (plus de défilement horizontal en 390 px).
- Les lignes conditionnelles des tarifs sont marquées par une ombre intérieure, sans décalage.
- Fiche « Vente » : nature et statut en badge (au lieu du tuple brut `('VENTE', 'Vente')`), titre « Vente n° X » (« Vente sans numéro — En attente » avant l'encaissement), quantité lisible sur l'écran « Avoir sur un article » d'une part d'historique (1,571 au lieu de 1,571429). Renvoyée telle quelle, la quantité proposée rend toujours tout le reste exact.
- Fiche « Vente », inlines « Articles » et « Règlements », et onglet des ventes de la fiche adhésion : plus de titre au-dessus de chaque ligne (option Unfold `hide_title` ; avant : uuid court, « Reglement object (uuid) »), les colonnes disent tout ; les quantités s'écrivent à la française (« 1,571 », « 3 », « 0,350 kg », « 0,33 L »).
- Fiche « Vente », inline « Règlements », colonne « Monnaie » : le NOM de la monnaie (même règle que la liste et le détail des ventes, `noms_des_monnaies_des_ventes`, lue une seule fois pour tout l'inline), « — » sans monnaie ou pour une monnaie introuvable ; plus jamais son uuid.
- **`LigneArticle` n'a plus d'admin** (décision du mainteneur) : plus de liste « Entries » ni de fiche de ligne, plus de bouton « Avoir » de ligne, plus d'entrée de menu. Les avoirs se font depuis la fiche « Vente » (« Avoir total », « Avoir sur un article »). L'export tableur passe sur la liste des Ventes : bouton « Exporter » (liste filtrée) ou action sur la sélection, qui exportent les ARTICLES de ces ventes, mêmes colonnes et même format que l'ancien export des lignes (`LigneArticleExportResource`, BOM pour Excel). Les liens qui menaient aux lignes mènent à la liste des ventes filtrée (règle 7 du plan comptable : `?moyen=UK` ; formulaires d'adhésion : `?q=<e-mail>`) ou à la fiche de la vente écrite (paiement d'adhésion enregistré). L'onglet des ventes de la fiche adhésion reste, sans lien vers une fiche ligne.
  **Conséquence connue et acceptée** : les lignes écrites SANS vente (demande de paiement par lien QR, virement reçu Fedow, historique d'avant le chantier) ne sont plus visibles dans l'admin jusqu'à la reprise (fiche R).

/ Before/after admin templates lose their horizontal padding and align on the content column. The four action screens are full-width Unfold fieldsets with Unfold widgets. Fieldsets and filter_horizontal selectors no longer overflow; the user page no longer scrolls sideways on mobile. Conditional price rows use an inset shadow. Sale page: nature and status badges, "Vente n° X" title, readable quantity on the item credit note screen (the exact remainder is still given back), readable inline titles, French quantities. `LigneArticle` has no admin any more: credit notes go through the sale page, the spreadsheet export of the items moves to the sales list (same columns), links point to the sales list or the sale page. Lines written without a sale are no longer visible in the admin until the takeover (sheet R).

**Pourquoi / Why :** audit visuel de l'admin (2026-10-05) : blocs décalés de 16 px, écrans d'action en boîte étroite centrée, blocs de champs plus larges que la colonne, tuple brut et « Vente object (uuid) » sur la fiche d'une vente. Les lignes : « Ligne invisible : on retire de l'admin » (mainteneur) ; la vente est l'objet que l'admin lit, corrige et exporte. / Visual audit of the admin. Lines: removed from the admin by the maintainer's decision; the sale is the object the admin reads, corrects and exports.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/templates/admin/membership/actions_panel.html`, `ghost/panneau_newsletter.html`, `asset/asset_change_form_before.html`, `federation/federation_members.html` | bloc racine `p-4` → `mb-6` (avant un formulaire) |
| `Administration/templates/admin/membership/custom_form.html`, `reservation/custom_form.html` | bloc racine `p-4` → `mt-6` (après un formulaire) |
| `Administration/templates/admin/comptable/plan_complet.html`, `comptable/changelist_before.html` (×2), `comptable/monnaies_changelist_before.html`, `asset/asset_list_before.html`, `scanapp/list_before.html`, `asset/asset_changelist_invitations.html`, `federation/federation_list_before.html` | bloc racine `p-4` / `px-4` → `mb-4` (au-dessus d'une liste) |
| `Administration/templates/admin/vente/avoir_total.html` (**déplacé** depuis `admin/lignearticle/emettre_avoir.html`, branche « ligne » sans appelant retirée), `vente/avoir_sur_un_article.html`, `vente/rejouer_encaissement.html`, `annulation/confirmer_annulation.html` | boîte centrée → `fieldset.module` Unfold en pleine largeur (titre `data-testid="<écran>-titre"`) |
| `Administration/admin_tenant.py` | widgets Unfold (`UnfoldAdminSelectWidget`, `UnfoldAdminDecimalFieldWidget`) des formulaires d'avoir ; `_badge_unfold` (badge rendu en HTML, liste et fiche) ; `_quantite_restante_proposee_dans_le_champ` (reste arrondi : kg 3 décimales, L 2, sinon 3 au plus sans zéros inutiles) ; dans `avoir_sur_un_article`, la valeur proposée renvoyée telle quelle rend le reste exact |
| `Administration/admin_tenant.py` (F) | `LigneArticleAdmin` et `LigneArticlePublishedFilter` **supprimés** ; `VenteAdmin` hérite de `ExportCsvLisibleParExcelMixin` et `ExportActionModelAdmin`, `resource_classes = [LigneArticleExportResource]`, `get_data_for_export` exporte les articles des ventes (`_articles_des_ventes_pour_l_export`) ; `LigneArticleInline` sans lien de modification ; `hide_title = True` sur `LigneArticleInline`, `ArticlesDeLaVenteInline`, `ReglementsDeLaVenteInline` ; `_quantite_d_une_ligne` à la française |
| `Administration/admin/dashboard.py` | entrée « Entries » retirée |
| `laboutik/plan_comptable.py` | règle 7 : lien vers la liste des ventes `?moyen=UK` |
| `Administration/templates/admin/membership/partials/ajouter_paiement_form.html`, `cancel_form.html` | lien vers la liste des ventes filtrée sur l'e-mail de l'adhérent·e |
| `Administration/templates/admin/membership/partials/ajouter_paiement_success.html`, `BaseBillet/views.py` | lien vers la fiche de la vente écrite (`vente_de_l_admin` passé au partiel) |
| `BaseBillet/models_vente.py` | `Vente.__str__` : « Vente n° X » / « Vente sans numéro — <statut> »  |
| `BaseBillet/services_vente.py` | commentaires : appelants à jour |
| `static/css/tibillet-admin.css` | `#content-main fieldset.module { min-width: 0 }` ; `html .selector-available, html .selector-chosen` souples dès 48rem |
| `Administration/templates/admin/human_user/right_and_wallet_info.html` | `min-w-0` sur les 4 blocs, `@min-[1570px]:-mx-4` retiré des titres, bouton `whitespace-normal` |
| `Administration/static/admin/js/inline_conditional_fields.js` | `appliquer_style_rangee` : `box-shadow: inset 3px 0 0` au lieu de bordure + marge + retrait |
| `tests/pytest/test_admin_alignements_et_fiche_vente.py` | **neuf** — 32 tests (A à F, inlines) |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py`, `test_caracterisation_annulations.py`, `test_caracterisation_en_ligne.py`, `test_part_en_jetons.py`, `test_une_ligne_par_article_lecteurs.py`, `test_lecteurs_montants_entiers.py`, `test_plan_comptable_unique.py`, `test_export_csv_bom_excel.py`, `test_admin_placeholder_recherche.py`, `test_admin_filtre_produit_liste_deroulante.py` | passent par la fiche « Vente » ou par le service au lieu de l'admin des lignes (détail dans le rapport de session) |
| `tests/e2e/test_admin_credit_note.py`, `test_admin_ajouter_paiement.py`, `test_admin_reservation_cancel.py`, `test_membership_manual_validation_stripe.py` | idem en E2E |

### Chaines i18n nouvelles / New i18n strings
- `Vente sans numéro — %(statut)s`
- `Vente n° %(numero)s`

Le workflow i18n (makemessages, traduction EN) est à lancer par le mainteneur. / The i18n workflow is left to the maintainer.

Chaînes devenues orphelines (à nettoyer par le workflow i18n) : « Entries », « Credit note » (bouton de ligne), « A credit note can only be issued for a confirmed or paid entry. », « A credit note already exists for this entry. », « La vente d'origine n'est pas réglée : l'avoir est impossible. », « Cette ligne a été payée en points ou en temps : l'avoir est impossible. », « Credit note created. ».

### Non fait / Not done
- `Administration/templates/admin/cloture/export_csv_comptable_detail_form.html` : aucun appelant (gabarit mort, retrait prévu par la fiche H, `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md`). Laissé en place.

---

## Comment tester (a la main) / Manual test

### Test 1 — alignement des blocs avant / après (1440 px)
1. Ouvrir une adhésion (`/admin/BaseBillet/membership/<id>/change/`) : la carte « Actions » commence au même x que le bloc de champs en dessous (pas de retrait de 16 px), avec 24 px d'écart vertical.
2. `/admin/laboutik/comptecomptable/` : les cartes « Plan complet ? », « Charger le plan », « Les natures de compte » sont alignées sur le tableau.
3. Fiche Ghost, liste des actifs, application de scan, comptes des monnaies : même constat.

### Test 2 — écrans d'action en pleine largeur
1. Fiche d'une vente réglée → « Avoir total » : un bloc de champs avec titre gris, sur toute la colonne ; champ « Remboursé par » à droite de son libellé ; boutons en bas.
2. « Avoir sur un article » : la liste des articles, puis l'écran d'un article, même mise en page.
3. Liste des réservations → cocher une réservation → action « Annuler et rembourser » : même mise en page.
4. Une vente en ligne restée en attente (paiement Stripe payé) → « Rejouer l'encaissement ».

### Test 3 — blocs de champs qui ne débordent pas
1. Carte primaire (`/admin/laboutik/carteprimaire/<id>/change/`) en 1440 et 1280 px : les deux listes « Points de vente » tiennent dans le bloc, pas de défilement horizontal.
2. Point de vente : même constat sur le bloc des produits / catégories.
3. Fiche d'un utilisateur en 390 px (outils du navigateur) : plus de défilement horizontal ; le bouton « Get cards and wallet information » passe à la ligne.

### Test 4 — lignes conditionnelles des tarifs
1. Fiche d'un produit de caisse → un tarif : la ligne « Contenance » garde un trait vert à gauche, mais son libellé et son champ sont alignés sur les autres lignes.

### Test 5 — fiche « Vente »
1. Fiche d'une vente réglée : titre « Vente n° X », « Nature » et « Statut » en badges colorés.
2. Fiche d'une vente en attente : titre « Vente sans numéro — En attente ».
3. Liste des ventes : badges inchangés.
4. Vente fil rouge (3 jus en deux parts, 1,428571 et 1,571429) → « Avoir sur un article » → la part de 5,50 € : le champ propose 1,571. Valider (Remboursé par : espèces) : l'avoir vaut −5,50 € et rend 1,571429 (fiche de la vente d'avoir, onglet Articles).

### Test 6 — les lignes n'ont plus d'admin, l'export passe par les ventes
1. Menu « Ventes et comptabilité » : plus d'entrée « Lignes comptables » / « Entries ».
2. `/admin/BaseBillet/lignearticle/` : page 404.
3. Liste des ventes → chercher un e-mail client → « Exporter » → CSV : une ligne par ARTICLE des ventes trouvées, colonnes « Référence paiement, Date, Libellé, Quantité, Prix Unitaire, TVA, Montant, Total HT, Total TVA, N° de vente, Moyens de la vente, … » ; ouverture dans Excel avec les accents corrects.
4. Liste des ventes → cocher deux ventes → action « Exporter » : les articles de ces deux ventes seulement.
5. Fiche d'une adhésion → « Ajouter un paiement » (espèces) → le lien « Ventes » du message de succès ouvre la fiche de la vente écrite.
6. Plan comptable → « Vérifier le plan » avec des règlements au compte d'attente : le lien « Régler » ouvre la liste des ventes filtrée sur « Inconnu ».

### Verifs automatiques / Automated checks
```bash
make test ARGS="tests/pytest/test_admin_alignements_et_fiche_vente.py"
make test ARGS="tests/pytest/test_admin_vente.py tests/pytest/test_admin_avoir_sur_un_article.py tests/pytest/test_avoirs_ecrivent_la_vente.py"
make e2e ARGS="tests/e2e/test_admin_credit_note.py tests/e2e/test_admin_ajouter_paiement.py tests/e2e/test_admin_reservation_cancel.py tests/e2e/test_membership_manual_validation_stripe.py"
```

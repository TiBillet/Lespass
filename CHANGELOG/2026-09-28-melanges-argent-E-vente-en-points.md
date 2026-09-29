# Vente en points ou en temps à la caisse (`NM`) / Selling in points or time at the register (`NM`)

**Date :** 2026-09-28
**Migration :** Oui — `BaseBillet/migrations/0229_paymentmethod_non_monetaire.py` (choices
seulement, 3 `AlterField`, aucune donnée modifiée).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary

**Quoi / What :** nouveau moyen de paiement `NON_MONETAIRE` (`"NM"`) pour une vente payée
en points de fidélité (FID) ou en temps (TIM). La ligne garde le prix en unités de la
monnaie (centièmes : 300 points = 30000), avec une TVA à 0. Elle est hors argent
(`MOYENS_HORS_ARGENT`) : jamais dans le total, la TVA, le CA, le FEC. Le rapport a une
section `non_monetaire`, une ligne par nom de monnaie. Dans l'admin, un tarif en points
n'est accepté que sur un article de vente ou une adhésion. /
New `NON_MONETAIRE` payment method for points/time sales: VAT 0, out of every money
computation, own report section; admin accepts a points price only on a sale item or a
membership.

**Pourquoi / Why :** FID était enregistré en `LOCAL_EURO` : une vente en points aurait
été comptée comme des euros encaissés (argent inventé dans le Z). /
FID was recorded as local euros: a points sale would have been counted as collected money.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-E-vente-en-points.md`.

### Session E1 — modèle, mapping, rapport, admin

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `PaymentMethod.NON_MONETAIRE` ; `LigneArticle._compute_default_vat` : TVA 0 pour NM |
| `BaseBillet/migrations/0229_paymentmethod_non_monetaire.py` | choices de `payment_method` (Ticket, LigneArticle, Membership) |
| `laboutik/views.py` | `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD` : TIM et FID → NM ; les 6 accès sans repli sur `LOCAL_EURO` ; `LABELS_MOYENS_PAIEMENT_DB` : NM ; `corriger_moyen_paiement` : message « hors argent » |
| `controlvanne/billing.py` | accès au mapping sans repli |
| `laboutik/reports.py` | `MOYENS_HORS_ARGENT = [FREE, NON_MONETAIRE]` ; `calculer_offerts()` filtre sur FREE seulement ; `calculer_non_monetaire()` ; rapport à 15 clés |
| `Administration/admin/products.py` | `POSPriceInlineFormSet` : tarif en points refusé hors vente / adhésion |
| `tests/pytest/test_vente_en_points.py` | nouveau (schéma dédié) |
| `tests/pytest/test_cloture_enrichie.py`, `test_cloture_caisse.py` | le rapport compte 15 clés (`non_monetaire`) |

**i18n** : nouvelles chaînes (source FR) : « Points ou temps (non monétaire) », « Points ou
temps », « Une vente hors argent (offerte, en points ou en temps) ne peut pas être
corrigée en paiement », « Un tarif en points n'est possible que sur un article de vente
ou une adhésion. ». L'ancienne chaîne « Une vente offerte ne peut pas etre corrigee en
paiement » (CHANGELOG D) n'est plus utilisée. Workflow i18n à lancer par le mainteneur.

### Tests vus échouer puis mutations (E1)
Avant correctif : 9 des 12 tests rouges (`PaymentMethod` sans `NON_MONETAIRE`,
formulaire admin accepté sur une recharge). Les 3 tests « accepté » passaient déjà.

| Mutation | Test tombé |
|---|---|
| `Asset.FID: LOCAL_EURO` rétabli | `test_les_points_et_le_temps_sont_enregistres_en_non_monetaire` |
| TVA 0 retirée pour NM | `test_une_ligne_en_points_est_creee_sans_tva` |
| NM retiré de `MOYENS_HORS_ARGENT` | `test_la_tva_du_rapport_ignore_les_points`, `test_une_vente_en_points_ne_peut_pas_etre_corrigee_en_especes` |
| `calculer_offerts` relit `MOYENS_HORS_ARGENT` | `test_une_vente_en_points_n_est_pas_un_article_offert` |
| clé `non_monetaire` retirée du rapport complet | `test_le_rapport_complet_contient_la_section_non_monetaire` |
| validation admin retirée | `test_un_tarif_en_points_est_refuse_sur_une_recharge` |

Suite complète après E1 : `make test` 1982 passed (1970 + 12).

### Session E2 — la caisse vend en points

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_tarifs_vendables_a_la_caisse()` : tarifs en euros OU en points/temps (FID/TIM actifs), euros d'abord, pour les tuiles ET le panier ; `_retirer_les_tarifs_en_points_non_vendables()` (ni vente ni adhésion) ; `_panier_est_en_points()`, `_monnaie_du_panier()` ; `moyens_paiement` refuse un panier mélangé ; `_executer_paiement` : une seule monnaie + NFC uniquement (contre un POST forgé « espèces » / « gift ») ; `_determiner_moyens_paiement` : `["nfc"]` ; `_panier_peut_etre_offert` : jamais un panier en points ; `_payer_par_nfc` : tarif en points classé en premier (adhésion en points débitée en points, créée en 7e), catégorie de monnaie vérifiée avant tout débit, solde comparé à la somme par monnaie ; `_executer_paiement_complementaire` : panier en points refusé ; `ouvrir_commande`, `ajouter_articles`, `payer_commande` : tarif en points refusé |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | panier en points : manque dans la monnaie du panier, pas de bloc « Compléter avec » |
| `controlvanne/billing.py`, `controlvanne/models.py` | la tireuse ne prend que le tarif « au litre » en euros |
| `tests/pytest/test_vente_en_points.py` | E1-E16 |

Écart assumé avec la fiche : `_executer_paiement_complementaire` refuse un panier en points
dès la lecture du panier, sans recopier le nouveau classement (aucun article en points ne
peut plus l'atteindre).

**i18n (E2)** : « Un panier ne mélange pas plusieurs monnaies : encaissez-les séparément. »,
« Un panier en points ou en temps se paie uniquement avec la carte du client. », « Un tarif
en points ou en temps ne passe pas par une commande de table : encaissez-le au comptoir. »,
« Cette monnaie n'est pas acceptée à la caisse. »

Avant correctif : 20 des 22 nouveaux tests rouges (le Pin's sans tuile, paniers acceptés,
tireuse facturant le tarif en temps, etc.).

### Mutations (E2) — 23 jouées, toutes détectées

| Mutation | Test tombé |
|---|---|
| tri « euros d'abord » retiré | `test_le_tarif_en_euros_passe_avant_le_tarif_en_temps` |
| tarifs en points non chargés | 16 tests (tuile, paiements, rapport) |
| tarif en points gardé sur une consigne | `test_un_tarif_en_points_sur_une_recharge_n_est_pas_propose` |
| `["nfc"]` seul retiré / OFFRIR permis en points | `test_un_panier_en_points_ne_propose_que_la_carte_nfc` |
| garde « une seule monnaie » retirée (`moyens_paiement`) | `test_les_moyens_de_paiement_refusent_un_panier_melange` |
| garde « une seule monnaie » retirée (`_executer_paiement`) | E4, E5, E6 |
| garde « NFC uniquement » retirée | `test_un_panier_en_points_ne_se_paie_pas_en_especes` |
| adhésion classée avant le tarif en points / adhésions en points non créées | `test_une_adhesion_payee_en_points_ne_debite_pas_d_euros` |
| vérification de catégorie retirée | `test_une_monnaie_hors_mapping_est_refusee_avant_le_debit` |
| solde vérifié article par article | `test_le_solde_est_compare_a_la_somme_du_panier` (après renforcement : le repli `SoldeInsuffisant` affichait aussi un popup, mais « 600,00 € » avec les compléments) |
| garde du complément retirée | `test_le_complement_de_paiement_refuse_un_panier_en_points` |
| gardes `ouvrir_commande` / `ajouter_articles` / `payer_commande` retirées | E13, E13, E13b |
| filtre euros de la tireuse retiré (`billing.py`, `models.py`) | `test_la_tireuse_facture_le_tarif_en_euros` |
| popup : complément rendu / manque en euros | `test_solde_de_points_insuffisant_popup_sans_deuxieme_carte` |
| FID → `LOCAL_EURO` | 6 tests dont E3, E10, E11, E12 |
| NM retiré de `MOYENS_HORS_ARGENT` | E10, E11 + 2 tests E1 |
| TVA 0 retirée pour NM | E3, E12 + 1 test E1 |

Suite complète après E2 : `make test` 2004 passed (1982 + 22).

### Relecture Opus + Fable (après E2) et corrections

Deux relectures indépendantes (lecture seule). Gardes de la caisse jugées solides ; défauts
trouvés en dehors, corrigés après décision du mainteneur :

| Défaut | Correction |
|---|---|
| Un tarif d'adhésion en points, publié pour la caisse, était proposé **sur le site** à « 300 € » et payé par Stripe | exclu de la page d'adhésion, de la liste (prix « à partir de »), de `MembershipValidator` (site + API v2) et du panier en ligne ; l'offre API v2 porte le code de sa monnaie |
| Un tarif coché « non fiduciaire » sans monnaie se vendait en euros ; décocher la case gardait la monnaie | `POSPriceInlineForm` : monnaie obligatoire si coché, vidée si décoché ; caisse : « en euros » = sans monnaie ET non coché ; `_tarif_est_en_points()` (une seule définition) |
| Adhésion payée en points : `payment_method` vide | `payment_method = NON_MONETAIRE` ; `contribution_value` garde le prix en unités de la monnaie (décision mainteneur) |
| Tri entre deux monnaies de points par uuid | rang « euros / points » puis `order` |
| Repli `SoldeInsuffisant` (course) en euros avec compléments | popup dans la monnaie du panier, sans complément |
| Admin : 0,50 heure refusé ; prix libre / au poids en points acceptés | 0 < prix < 1 refusé pour les euros seulement ; points ni libres ni au poids |
| Classement mort dans `_executer_paiement_complementaire` | commentaire : inaccessible, et pourquoi |

Faux positif écarté : l'exclusion des tarifs récurrents / à validation manuelle existait déjà
dans l'ancienne requête de la caisse.

Tests renforcés : message exact vérifié sur chaque refus ; règle OFFRIR testée directement ;
nouveaux cas (quantité 2, paiement en temps, deux monnaies FID, monnaie archivée / inactive,
tarif non publié, POST forgé d'une consigne, commande en espèces, champs de l'adhésion).
`test_vente_en_points.py` : 57 tests.
18 mutations des corrections, toutes détectées. Suite complète : `make test` 2027 passed.

**i18n (relecture)** : « Choisissez la monnaie d'un tarif en points ou en temps. », « Un tarif
en points ou en temps n'est pas à prix libre. », « Un tarif en points ou en temps n'est pas
vendu au poids. », « Ce tarif se règle à la caisse, en points ou en temps. »

Fichiers en plus : `BaseBillet/views.py`, `BaseBillet/validators.py`,
`BaseBillet/services_panier.py`, `api_v2/serializers.py`, `Administration/admin/laboutik.py`
(commentaire).

### Session E3 (1er temps) — affichage à la caisse

Un article, un panier ou une vente en points affiche le **nom de sa monnaie** là où la
caisse affichait « € ».

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templatetags/laboutik_filters.py` | filtre `montant_dans_la_monnaie` : `30000, "Points fidélité"` → « 300,00 Points fidélité » ; sans monnaie → comme `euros` |
| `laboutik/views.py` | `_unite_du_tarif()` ; tuiles : `unite_label` et `est_en_points` par article et par tarif ; `_currency_data_du_panier()` pour `moyens_paiement` et la popup « client identifié » (le solde du client reste en €) ; écran de succès NFC : `nom_monnaie_du_panier_en_points`, `unite` de chaque solde ; liste des ventes : monnaie d'une vente NM (une requête) ; détail : montants en points, pas de bouton « Corriger » sur une vente hors argent |
| `laboutik/templates/cotton/articles.html` | `data-currency` et prix des tuiles dans l'unité du tarif |
| `laboutik/static/js/tarif.js` | chaque tarif de la popup affiche son `unite_label` (repli sur `currency`) |
| `laboutik/static/js/addition.js` | `montantAvecUnite()` (espace devant un nom de monnaie, pas devant €) ; le total prend l'unité de la 1re ligne ; unité échappée |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html`, `hx_return_payment_success.html`, `_succes_carte.html`, `_ligne_vente.html`, `hx_detail_vente.html` | montants dans la monnaie du panier |
| `tests/pytest/test_vente_en_points.py` | tuiles, écrans, liste et détail des ventes (E18), filtre |
| `tests/e2e/test_caisse_vente_en_points.py` | nouveau : E19-E23 (tuile, popup des tarifs, panier + CASHLESS seul, panier mélangé, succès NFC simulé) — crée ses propres données |

Constat hors chantier (non corrigé) : en mode démo, le bouton « Valider » de la simulation
NFC est recouvert par le fond de la popup d'attente de carte ; la saisie se valide par la
touche Entrée (utilisée par l'E2E).

### Session E3 (2e temps) — impression et rapports

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/printing/formatters.py` | ticket client : clé `unite` (« EUR » ou nom de la monnaie ; « Points ou temps » si introuvable), pas de TVA pour un ticket en points ; `_lignes_du_non_monetaire()` : une ligne par monnaie au pied des tickets X et Z (« Points fidélité (hors argent): 1 articles, 300.00 ») |
| `laboutik/printing/escpos_builder.py`, `sunmi_inner.py` | montants dans l'unité du ticket (« EUR » collé comme avant, nom de monnaie séparé) |
| `laboutik/views.py` | ticket X imprimé et écran : `calculer_non_monetaire()` |
| `hx_recap_en_cours.html`, `hx_cloture_rapport.html`, `admin/cloture/rapport_before.html`, `rapport_temps_reel.html`, `pdf/rapport_comptable.html`, `csv_export.py`, `excel_export.py` | section « Non monétaire (hors argent) » : Monnaie, Quantité, Total dans la monnaie |

### Relecture Opus + Fable (après E3) et corrections

| Défaut | Correction |
|---|---|
| Section Adhésions (admin, temps réel, PDF, export admin) : adhésion en points écrite « 300,00 € » | `calculer_adhesions` : clé `unite` ; gabarits et export dans la monnaie |
| Exports CSV/Excel **de l'admin** (`_ecrire_rapport_csv_excel`) sans « Non monétaire » ni « Offerts » | les deux sections (décision mainteneur) |
| PDF du Z envoyé par e-mail (`laboutik/pdf.py`, `cloture_rapport_pdf.html`) sans ces sections | les deux sections (décision mainteneur) |
| Panier : le total suivait une ligne en train de disparaître (600 ms) | sélecteur `:not(.is-removing)` |
| Succès NFC : total affiché = total envoyé par le navigateur | total recalculé par le serveur pour un panier en points |
| Popup « client identifié » : solde en € pour un panier en points | solde de la carte dans la monnaie du panier (décision mainteneur) |
| Tuile : nom complet de la monnaie | **initiales** (« 300 PF »), nom complet en infobulle `<abbr>` (décision mainteneur) ; ailleurs le nom complet |
| Liste des ventes : pas de filtre « Points ou temps » | option ajoutée |
| Monnaie introuvable → « EUR » / « € » | « Points ou temps » |
| `est_en_points` recalculé à part | `_tarif_est_en_points()` (une seule définition) |

Écarts assumés à la fiche : tuile au format des tuiles en euros (« 300 PF », décimales
masquées si nulles) ; filtre `montant_dans_la_monnaie` (nom de monnaie inclus) au lieu de
`montant_en_unites` ; `hx_confirm_payment.html` non modifié (jamais atteint par un panier en
points : NFC seul) ; l'écran de succès en euros affiche toujours le total envoyé par le
navigateur (comportement existant, hors chantier).

### Mutations (E3)

Caisse — 15 jouées, toutes détectées (la 15e après renforcement du test de succès) :
filtre sans nom de monnaie, unité du tarif toujours €, `data-currency` et prix de tuile en €,
total des moyens de paiement et de la popup « client identifié » en €, solde de la popup,
nom de la monnaie absent du succès, soldes du succès en €, liste et détail en €, bouton
« Corriger » sur une vente en points, `tarif.js` sans unité du tarif (E2E), total du panier
en € et unité collée (E2E).

Impression et rapports — 16 jouées, toutes détectées : ticket en EUR, TVA gardée, TOTAL et
lignes ESC/POS et Sunmi en EUR, tickets X et Z sans les points, contexte et section de
l'écran X, section de l'écran Z, de l'admin (clôture, temps réel), du PDF, du CSV, de
l'Excel.

Corrections de la relecture — 14 jouées, toutes détectées (la dernière après ajout d'un
test du repli « Points ou temps ») : unité des adhésions absente, adhésion en € dans
l'admin et dans l'export admin, sections « Non monétaire » et « Offerts » absentes de
l'export admin et du PDF e-mail, total du succès pris au navigateur, solde du client en €,
filtre « Points ou temps » absent, tuile avec le nom complet, initiales = mot entier, repli
du ticket en EUR, ligne retirée comptée dans l'unité du total (E2E).

`test_vente_en_points.py` : 87 tests ; `tests/e2e/test_caisse_vente_en_points.py` : 6 tests.

Suites complètes après E3 : `make test` 2057 passed ; `make e2e` 116 passed (après vidage de la
file Celery, voir `CHANGELOG/2026-09-28-trigger-product-update-sans-pause.md`).

**i18n (E3)** : « Non monétaire (hors argent) », « hors argent ». (« Monnaie »,
« Quantité », « Total », « Points ou temps » existent déjà.)

### Session E4 — relecture finale (Fable) et corrections

Gardes de la caisse, rapports, N+1 et djc jugés conformes. Défauts restants corrigés :

| Défaut | Correction |
|---|---|
| Cotisation d'une adhésion payée en points affichée « 300 € » hors caisse : « Mon compte » (gabarits classic et V2), fiche utilisateur de l'admin, confirmation de renouvellement | `Membership.unite_de_la_contribution()` (« € », ou le nom de la monnaie) utilisée par ces gabarits |
| Renouvellement admin (vue `renouveller`) : tarif, montant en points et moyen `NM` pré-remplis dans un formulaire qui n'encaisse que de l'argent (→ vente « 300 € ») | rien de tout cela n'est pré-rempli pour une adhésion payée en points (e-mail et nom le restent) |
| Classement phase 2 : deuxième définition de « tarif en points » | `_tarif_est_en_points()` ; un tarif en points sans monnaie est refusé comme une monnaie inconnue |
| Tarif à 0 point accepté (panier « gratuit » → VALIDER → refusé : caissier bloqué) | refusé dans l'admin |
| Export CSV/Excel de l'admin : total non monétaire en nombre nu | écrit avec le nom de la monnaie, comme la ligne d'adhésion |
| Tests : assertion `<= 20` (boucle de 10) ; repli « Points ou temps » de la liste des ventes non testé ; en-tête de section qui racontait la session | `== 10` ; test ajouté ; en-tête renommé |

Supprimé ensuite : `extra_context["renouveller_url"]` de `MembershipAdmin.changeform_view`
(`Administration/admin_tenant.py`), copie du calcul du lien que ne lisait aucun gabarit (le
bouton « Renouveler » passe par la vue `renouveller`, seule source du lien) ; commentaire de
`actions_panel.html` corrigé ; `make test` 2082 passed. Laissés tels quels (signalés) : N+1 préexistant de la liste des adhésions du site
(`BaseBillet/views.py` ~l.3590) ; le total du panier s'écrit « 5.00 € » (espace) quand les lignes
écrivent « 5.00€ » (préexistant). `webhook_membership` transmet `contribution_value` avec
`payment_method = "NM"` et son libellé : le destinataire peut les distinguer.

Mutations (E4) — 10 jouées, 9 détectées ; la 10e (garde « fût sans tarif en euros » dans
`facturer_tirage`) a montré la garde inaccessible (`prix_litre` vaut déjà 0 et arrête le tirage
plus haut) : garde retirée, le test du comportement est gardé.

Suites après E4 : `make test` 2070 passed ; `make e2e` 116 passed.

### i18n — toutes les chaînes nouvelles de la fiche E (source FR, absentes des `.po`)

1. « Points ou temps (non monétaire) » — `BaseBillet/models.py`
2. « Points ou temps » — `laboutik/views.py`, `laboutik/reports.py`, `laboutik/printing/formatters.py`, `BaseBillet/models.py`
3. « Une vente hors argent (offerte, en points ou en temps) ne peut pas être corrigée en paiement » — `laboutik/views.py`
4. « Un tarif en points n'est possible que sur un article de vente ou une adhésion. » — `Administration/admin/products.py`
5. « Un panier ne mélange pas plusieurs monnaies : encaissez-les séparément. » — `laboutik/views.py`
6. « Un panier en points ou en temps se paie uniquement avec la carte du client. » — `laboutik/views.py`
7. « Un tarif en points ou en temps ne passe pas par une commande de table : encaissez-le au comptoir. » — `laboutik/views.py`
8. « Cette monnaie n'est pas acceptée à la caisse. » — `laboutik/views.py`
9. « Choisissez la monnaie d'un tarif en points ou en temps. » — `Administration/admin/products.py`
10. « Un tarif en points ou en temps n'est pas à prix libre. » — idem
11. « Un tarif en points ou en temps n'est pas vendu au poids. » — idem
12. « Un tarif en points ou en temps vaut plus de 0. » — idem
13. « Ce tarif se règle à la caisse, en points ou en temps. » — `BaseBillet/services_panier.py`
14. « Non monétaire (hors argent) » — gabarits X/Z caisse et admin, PDF (×2), `csv_export.py`, `excel_export.py`, `Administration/admin/laboutik.py`
15. « hors argent » — `laboutik/printing/formatters.py`

Réutilisées (déjà dans les `.po`) : « Monnaie », « Quantité », « Total », « Inconnu », « articles »,
« Solde ». Fiche D, également absentes des `.po` (même passage) : « Offerts (hors argent) »,
« Valeur offerte », « Coût d'achat » ; l'ancienne « Une vente offerte ne peut pas etre corrigee en
paiement » n'est plus utilisée.

---

## Comment tester (a la main) / Manual test

### Test 1 — admin : tarif en points
1. Admin → Caisse → Produits de caisse → un produit « Recharge euros ».
2. Ajouter un tarif, cocher « Tarif non fiduciaire », choisir une monnaie FID, enregistrer.
3. Attendu : erreur « Un tarif en points n'est possible que sur un article de vente ou une
   adhésion. » sous la case.
4. Même manipulation sur un article de vente : accepté.

### Test 2 — vendre un Pin's en points (données de démo)
1. Caisse, point de vente où le « Pin's TiBillet » (300 points) est vendu.
2. Le Pin's a une tuile. L'ajouter, VALIDER : seul CASHLESS est proposé (pas d'OFFRIR,
   même avec une carte gérant).
3. Scanner une carte avec au moins 300 points : succès. En base, une ligne `NM`,
   `amount` 30000, TVA 0.
4. Avec une carte à 100 points : popup « Il manque 200,00 Points fidélité », sans
   « Compléter avec ».

### Test 3 — paniers refusés
1. Pin's + une bière à 5 € → VALIDER : « Un panier ne mélange pas plusieurs monnaies :
   encaissez-les séparément. »
2. Bière : popup des tarifs, « Pinte 5 € » en premier, « Bénévole 1 heure » ensuite.

### Verifs DB
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from laboutik.views import MAPPING_ASSET_CATEGORY_PAYMENT_METHOD as M; print(M)"
```
